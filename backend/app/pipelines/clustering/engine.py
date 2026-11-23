"""Clustering engine: DBSCAN, HDBSCAN, K-Means baseline over dense L2-normalised feature vectors.

Clustering runs on *unique normalized messages* (weighted by frequency for DBSCAN), which is what makes 100k+ line files tractable.
Noise points (-1) are reported as `raw_noise_ratio`, then re-attached to their Drain template group so every log belongs to a cluster.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import numpy as np
from sklearn.cluster import DBSCAN, HDBSCAN, KMeans
from sklearn.neighbors import NearestNeighbors

STOP = set("the a an of to for in on at is was are be by with from and or not no this that it as has have had been failed error".split())


def estimate_eps(X: np.ndarray, k: int = 3, lo: float = 0.05, hi: float = 0.9) -> float:
    """eps from the k-distance curve knee (largest second difference), clamped to a sane range (euclid on unit vectors)."""
    n = len(X)
    if n <= k + 1:
        return 0.3
    sample = X if n <= 4000 else X[np.random.RandomState(42).choice(n, 4000, replace=False)]
    d, _ = NearestNeighbors(n_neighbors=min(k + 1, len(sample))).fit(sample).kneighbors(sample)
    kd = np.sort(d[:, -1])
    if len(kd) < 5:
        return float(np.clip(kd[-1], lo, hi))
    diffs = np.diff(kd)
    knee = int(np.argmax(np.diff(diffs))) + 1 if len(diffs) > 1 else len(kd) // 2
    return float(np.clip(kd[min(knee, len(kd) - 1)], lo, hi))


def run_clustering(X: np.ndarray, weights: np.ndarray | None, algorithm: str = "hdbscan", eps: float | None = None,
                   min_samples: int = 3, min_cluster_size: int = 5, n_clusters: int | None = None) -> tuple[np.ndarray, dict]:
    """Return (labels with -1 = noise, params used). `algorithm`: dbscan | hdbscan | kmeans."""
    n = len(X)
    if n == 0:
        return np.array([], dtype=int), {}
    if n < 3:
        return np.zeros(n, dtype=int), {"algorithm": algorithm, "note": "too few points"}
    algorithm = algorithm.lower()
    if algorithm == "dbscan":
        e = eps if eps and eps > 0 else estimate_eps(X, min_samples)
        lab = DBSCAN(eps=e, min_samples=min_samples, metric="euclidean").fit(X, sample_weight=weights).labels_
        return lab, {"algorithm": "dbscan", "eps": round(float(e), 4), "min_samples": min_samples}
    if algorithm == "hdbscan":
        mcs = max(2, min(min_cluster_size, max(2, n // 10)))  # HDBSCAN counts points, not weights: shrink for small unique sets
        lab = HDBSCAN(min_cluster_size=mcs, min_samples=min(min_samples, mcs), metric="euclidean", copy=True).fit(X).labels_
        return lab, {"algorithm": "hdbscan", "min_cluster_size": mcs, "min_samples": min(min_samples, mcs)}
    if algorithm == "kmeans":
        k = n_clusters or max(2, min(30, int(np.sqrt(n / 2))))
        k = min(k, n)
        lab = KMeans(n_clusters=k, n_init=5, random_state=42).fit(X, sample_weight=weights).labels_
        return lab, {"algorithm": "kmeans", "n_clusters": k}
    raise ValueError(f"unknown clustering algorithm '{algorithm}'")


def attach_noise_to_templates(labels: np.ndarray, template_ids: np.ndarray) -> np.ndarray:
    """Noise logs share their Drain template's cluster; templates with no clustered member get their own new cluster."""
    labels = labels.copy()
    votes: dict[int, Counter] = defaultdict(Counter)
    for l, t in zip(labels, template_ids):
        if l >= 0:
            votes[t][l] += 1
    nxt = (labels.max() + 1) if len(labels) and labels.max() >= 0 else 0
    new: dict[int, int] = {}
    for i, (l, t) in enumerate(zip(labels, template_ids)):
        if l >= 0:
            continue
        if t in votes:
            labels[i] = votes[t].most_common(1)[0][0]
        else:
            labels[i] = new.setdefault(int(t), nxt + len(new))
    return labels


def representatives(X: np.ndarray, idx: list[int], k: int = 3) -> list[int]:
    """Indices (into the full array) of the k members closest to the cluster centroid."""
    sub = X[idx]
    c = sub.mean(0)
    order = np.argsort(np.linalg.norm(sub - c, axis=1))
    return [idx[i] for i in order[:k]]


def top_keywords(texts: list[str], k: int = 6) -> list[str]:
    c: Counter = Counter()
    for t in texts:
        for w in set(re.findall(r"[A-Za-z][A-Za-z_-]{2,}", t.lower())):
            if w not in STOP:
                c[w] += 1
    return [w for w, _ in c.most_common(k)]


def centroid_similarity(X: np.ndarray, labels: np.ndarray, top: int = 5) -> dict[int, list[tuple[int, float]]]:
    ids = sorted(set(labels.tolist()))
    cents = np.stack([X[labels == i].mean(0) for i in ids])
    cents /= np.linalg.norm(cents, axis=1, keepdims=True) + 1e-12
    S = cents @ cents.T
    out = {}
    for a, ia in enumerate(ids):
        order = [b for b in np.argsort(-S[a]) if b != a][:top]
        out[ia] = [(ids[b], float(S[a, b])) for b in order]
    return out
