"""Evaluation: clustering metrics (supervised/unsupervised), anomaly metrics, and the configuration comparison grid.

Every number returned here is computed from an executed run; nothing is hardcoded.
"""
from __future__ import annotations

import time
import tracemalloc

import numpy as np
from sklearn import metrics as skm

from app.pipelines.clustering.engine import run_clustering


def clustering_metrics(X: np.ndarray, labels, truth: list | None, inverse=None) -> dict:
    """X/labels are over the points that were clustered (unique messages). If `inverse` (log -> unique index) is given,
    supervised metrics and noise ratio are computed per *log line*; unsupervised indices use the unique points (unweighted)."""
    labels = np.asarray(labels)
    full = labels[np.asarray(inverse)] if inverse is not None else labels
    n = len(full)
    noise = float((full == -1).mean()) if n else 0.0
    out: dict = {"n_clusters": int(len(set(labels.tolist()) - {-1})), "noise_ratio": round(noise, 4), "n_points": int(n)}
    if truth is not None and n:
        t = np.asarray(truth)
        # noise points each count as their own singleton cluster so noise is penalised, not ignored
        pred = np.where(full == -1, -(np.arange(n) + 2), full)
        out.update(ari=skm.adjusted_rand_score(t, pred), nmi=skm.normalized_mutual_info_score(t, pred), homogeneity=skm.homogeneity_score(t, pred),
                   completeness=skm.completeness_score(t, pred), v_measure=skm.v_measure_score(t, pred))
    mask = labels != -1
    nc = len(set(labels[mask].tolist()))
    if mask.sum() > nc >= 2:
        Xm, lm = X[mask], labels[mask]
        if len(Xm) > 5000:  # silhouette is O(n^2): evaluate on a fixed random subsample
            idx = np.random.RandomState(0).choice(len(Xm), 5000, replace=False)
            Xs, ls = Xm[idx], lm[idx]
            out["silhouette_subsampled"] = True
        else:
            Xs, ls = Xm, lm
        if len(set(ls.tolist())) >= 2:
            out["silhouette"] = skm.silhouette_score(Xs, ls, metric="cosine")
        out["davies_bouldin"] = skm.davies_bouldin_score(Xm, lm)
        out["calinski_harabasz"] = skm.calinski_harabasz_score(Xm, lm)
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()}


def anomaly_metrics(y_true: list[int], scores, threshold: float | None = None, binary: bool = False) -> dict:
    y = np.asarray(y_true)
    s = np.asarray(scores, dtype=float)
    if len(set(y.tolist())) < 2:
        return {"note": "labels contain a single class; metrics undefined"}
    pred = (s >= 0.5).astype(int) if binary else (s >= threshold).astype(int)
    out = {"precision": skm.precision_score(y, pred, zero_division=0), "recall": skm.recall_score(y, pred, zero_division=0), "f1": skm.f1_score(y, pred, zero_division=0),
           "flagged": int(pred.sum()), "positives": int(y.sum())}
    if not binary:
        out["roc_auc"] = skm.roc_auc_score(y, s)
        out["pr_auc"] = skm.average_precision_score(y, s)
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in out.items()}


def timed(fn, *a, **kw):
    """Run fn measuring wall-clock seconds and peak Python-allocated memory (tracemalloc; numpy allocations included)."""
    tracemalloc.start()
    t0 = time.perf_counter()
    res = fn(*a, **kw)
    dt = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return res, dt, peak / 1e6


def compare_configurations(feature_mats: dict[str, tuple[np.ndarray, float, str]], weights: np.ndarray, truth_full: list | None, inverse: np.ndarray,
                           params: dict, include_kmeans: bool = True) -> list[dict]:
    """feature_mats: {name: (matrix over unique messages, feature_seconds, backend)}. Runs every (features x algorithm) cell."""
    rows = []
    algos = ["dbscan", "hdbscan"] + (["kmeans"] if include_kmeans else [])
    for fname, (X, fsec, backend) in feature_mats.items():
        for algo in algos:
            try:
                (labels, used), dt, mem = timed(run_clustering, X, weights, algo, params.get("eps") or None, params.get("min_samples", 3), params.get("min_cluster_size", 5), params.get("n_clusters") or None)
                m = clustering_metrics(X, labels, truth_full, inverse)
                rows.append({"features": fname, "feature_backend": backend, "algorithm": algo, "parameters": used, "metrics": m,
                             "cluster_seconds": round(dt, 4), "feature_seconds": round(fsec, 4), "peak_memory_mb": round(mem, 2)})
            except Exception as e:  # noqa: BLE001 - one failing cell must not hide the others
                rows.append({"features": fname, "feature_backend": backend, "algorithm": algo, "error": f"{type(e).__name__}: {str(e)[:150]}"})
    return rows
