"""End-to-end analysis orchestration (pure: rows in -> results out). Persistence lives in services/jobs.py."""
from __future__ import annotations

import logging
import re
import time
from collections import Counter

import numpy as np

from app.pipelines.anomaly_detection.detectors import (bucket_series, detect_all, event_features, is_err, isolation_forest_scores, level_scores, rarity_scores)
from app.pipelines.clustering.engine import (attach_noise_to_templates, centroid_similarity, run_clustering, top_keywords)
from app.pipelines.evaluation.metrics import anomaly_metrics, clustering_metrics, compare_configurations, timed
from app.pipelines.features.extractors import build_features, embedding_features, tfidf_features
from app.pipelines.parsing.parser import ParsedLog
from app.pipelines.preprocessing.normalizer import normalize
from app.pipelines.root_cause.analyzer import build_insights
from app.pipelines.root_cause.priority import explain_priority, priority_label, priority_score
from app.pipelines.summarization.summarizer import llm_enhance, rule_summary
from app.pipelines.templates.miner import compare_template_methods, grouping_accuracy, mine_templates

log = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "features": "tfidf",           # tfidf | embeddings
    "algorithm": "dbscan",         # dbscan | hdbscan | kmeans (dbscan with k-distance eps scored best on labelled data, see docs/experiments.md)
    "eps": 0.0,                    # 0 => estimated from the k-distance knee (DBSCAN)
    "min_samples": 3, "min_cluster_size": 5, "n_clusters": 0,
    "sim_threshold": 0.5,          # Drain similarity threshold
    "contamination": 0.02, "z_threshold": 3.0,
    "lowercase": False, "keep_stack_trace": False,
    "run_evaluation": True, "evaluation_max_unique": 4000,
    "random_seed": 42,
}
LEVEL_ORDER = ["FATAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"]
NOISE_LIKE = {"normal", "0", "false", "-", "ok"}


def _bucket_seconds(span: float) -> int:
    h = span / 3600
    return 60 if h <= 2 else 300 if h <= 12 else 3600 if h <= 96 else 86400


def _title(words: list[str]) -> str:
    return " ".join(w if w.isupper() and len(w) > 1 else w.capitalize() for w in words)


def describe_clusters(rows: list[ParsedLog], Xu: np.ndarray, inverse: np.ndarray, weights: np.ndarray, anomalies: list[dict], tinfo: dict, uniq: list[str]) -> list[dict]:
    total = len(rows)
    total_svcs = len({r.service for r in rows})
    ts = [r.timestamp for r in rows if r.timestamp]
    tmin, tmax = (min(ts), max(ts)) if ts else (None, None)
    span = (tmax - tmin).total_seconds() if ts else 0
    anom_score: dict[int, float] = {}
    for a in anomalies:
        if a.get("cluster_key") is not None:
            anom_score[a["cluster_key"]] = max(anom_score.get(a["cluster_key"], 0), a["score"])
    groups: dict[int, list[int]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(r.cluster_id, []).append(i)
    # centroid similarity at the unique-message level (weighted by frequency)
    cent: dict[int, np.ndarray] = {}
    uniq_by_cluster: dict[int, dict[int, int]] = {}
    for cid, idx in groups.items():
        cnt = Counter(int(inverse[i]) for i in idx)
        uniq_by_cluster[cid] = cnt
        us = np.fromiter(cnt.keys(), dtype=int)
        w = np.fromiter(cnt.values(), dtype=float)
        c = (Xu[us] * w[:, None]).sum(0) / w.sum()
        cent[cid] = c / (np.linalg.norm(c) + 1e-12)
    keys = list(cent)
    sims: dict[int, list] = {}
    if 1 < len(keys) <= 1500:
        M = np.stack([cent[k] for k in keys])
        S = M @ M.T
        for a, ka in enumerate(keys):
            order = [b for b in np.argsort(-S[a]) if b != a][:5]
            sims[ka] = [(keys[b], float(S[a, b])) for b in order]
    out = []
    for cid, idx in groups.items():
        g = [rows[i] for i in idx]
        levels = Counter(r.level for r in g)
        level = next((l for l in LEVEL_ORDER if levels.get(l, 0) >= max(1, 0.2 * len(g))), next(iter(levels)))
        tc = Counter(r.template_id for r in g)
        top_t = tc.most_common(1)[0][0]
        gts = [r.timestamp for r in g if r.timestamp]
        trend, trend_ratio, recency, first, last = [], 1.0, 0.5, None, None
        if gts:
            first, last = min(gts), max(gts)
            if span > 0:
                b = _bucket_seconds(span)
                cnt = Counter(int(t.timestamp() // b * b) for t in gts)
                trend = [{"t": datetime_iso(k), "count": cnt[k]} for k in sorted(cnt)]
                mid = tmin.timestamp() + span / 2
                f = sum(1 for t in gts if t.timestamp() < mid)
                trend_ratio = (len(gts) - f + 1) / (f + 1)
                recency = (last - tmin).total_seconds() / span
        services = dict(Counter(r.service or "unknown" for r in g).most_common(8))
        score, parts = priority_score(level, len(g), total, anom_score.get(cid, 0.0), trend_ratio, recency, len(set(r.service for r in g)), total_svcs)
        label = priority_label(score, level)
        template = tinfo.get(top_t, {}).get("template") or g[0].normalized
        keywords = top_keywords([r.normalized for r in g[:500]])
        words = [w for w in template.replace("<*>", "").split() if w and not re.search(r"[<>=/\\]", w) and re.search(r"[A-Za-z]{2}", w)][:6]
        name = (_title([w.strip(":,;()[]") for w in words]) or _title(keywords[:3]) or "Miscellaneous pattern")[:80]
        # representatives: unique messages closest to the weighted centroid, mapped back to one original log each
        cnt = uniq_by_cluster[cid]
        us = np.fromiter(cnt.keys(), dtype=int)
        order = np.argsort(np.linalg.norm(Xu[us] - cent[cid], axis=1))[:3]
        first_log_of = {}
        for i in idx:
            first_log_of.setdefault(int(inverse[i]), i)
        reps = [rows[first_log_of[int(us[o])]].message[:400] for o in order]
        out.append(dict(cluster_key=cid, name=name, size=len(g), severity=level, priority=label, priority_score=score, priority_factors=parts,
                        priority_explanation=explain_priority(label, level, parts, score), first_seen=first, last_seen=last, keywords=keywords,
                        representatives=reps, template=template, services=services, levels=dict(levels), trend=trend, trend_ratio=trend_ratio,
                        related=[{"cluster_key": k, "similarity": round(s, 3)} for k, s in sims.get(cid, []) if s > 0.3], is_anomalous=cid in anom_score,
                        n_unique_messages=len(cnt), template_ids=[t for t, _ in tc.most_common(5)]))
    return sorted(out, key=lambda c: -c["priority_score"])


def datetime_iso(epoch: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None).isoformat()


def _majority_truth(truth: list, inverse: np.ndarray, n_unique: int) -> list:
    votes: list[Counter] = [Counter() for _ in range(n_unique)]
    for u, t in zip(inverse, truth):
        votes[u][t] += 1
    return [v.most_common(1)[0][0] if v else "?" for v in votes]


def run_experiments(uniq: list[str], inverse: np.ndarray, weights: np.ndarray, truth: list | None, cfg: dict, feat_cache: dict | None = None) -> dict:
    """TF-IDF vs embeddings x DBSCAN / HDBSCAN / K-Means, on (a capped sample of) the unique messages. All numbers are measured."""
    cap = int(cfg.get("evaluation_max_unique", 4000))
    note = None
    if len(uniq) > cap:
        keep = np.argsort(-weights)[:cap]
        remap = {int(u): k for k, u in enumerate(keep)}
        sel = [i for i, u in enumerate(inverse) if int(u) in remap]
        uniq = [uniq[int(u)] for u in keep]
        inv = np.array([remap[int(inverse[i])] for i in sel])
        weights = weights[keep]
        truth = [truth[i] for i in sel] if truth is not None else None
        note = f"Comparison grid evaluated on the {cap} most frequent unique messages ({len(sel):,} log lines) to bound runtime."
    else:
        inv = inverse
    mats: dict[str, tuple] = {}
    for name, fn in (("tfidf", lambda: tfidf_features(uniq, "word+char")), ("embeddings", lambda: embedding_features(uniq))):
        try:
            fr, dt, mem = timed(fn)
            mats[name] = (fr.matrix, fr.seconds, fr.backend)
        except Exception as e:  # noqa: BLE001
            log.warning("feature method %s failed: %s", name, e)
    grid = compare_configurations(mats, weights, truth, inv, cfg)
    out = {"grid": grid, "evaluated_unique_messages": len(uniq), "evaluated_logs": int(len(inv)), "supervised": truth is not None, "note": note}
    if any(v[2] == "lsa-fallback" for v in mats.values()):
        out["warning"] = "Sentence-Transformer embeddings were unavailable; the 'embeddings' rows used an LSA character-n-gram fallback and are NOT semantic-embedding results."
    return out


def analyze(rows: list[ParsedLog], config: dict | None = None, progress=lambda p, s: None, env: dict | None = None) -> dict:
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    env = env or {}
    np.random.seed(int(cfg["random_seed"]))
    timings: dict[str, float] = {}
    t_all = time.perf_counter()

    t = time.perf_counter()
    pre = {"lowercase": cfg["lowercase"], "keep_stack_trace": cfg["keep_stack_trace"], "disabled_rules": cfg.get("disabled_rules", [])}
    for r in rows:
        r.normalized = normalize(r.message, pre)
    timings["normalize"] = time.perf_counter() - t
    progress(0.25, "Extracting templates")

    t = time.perf_counter()
    tids, tinfo = mine_templates([r.normalized for r in rows], sim_th=float(cfg["sim_threshold"]))
    for r, tid in zip(rows, tids):
        r.template_id = tid
    timings["templates"] = time.perf_counter() - t
    progress(0.35, "Building features")

    t = time.perf_counter()
    uniq_idx: dict[str, int] = {}
    inverse = np.array([uniq_idx.setdefault(r.normalized, len(uniq_idx)) for r in rows])
    uniq = list(uniq_idx)
    weights = np.bincount(inverse, minlength=len(uniq)).astype(float)
    feats = build_features(uniq, "tfidf-word+char" if cfg["features"].startswith("tfidf") else "embeddings")
    Xu = feats.matrix
    timings["features"] = time.perf_counter() - t
    progress(0.5, "Clustering")

    t = time.perf_counter()
    lab_u, used = run_clustering(Xu, weights, cfg["algorithm"], cfg["eps"] or None, int(cfg["min_samples"]), int(cfg["min_cluster_size"]), cfg["n_clusters"] or min(len(tinfo), 50))
    labels = lab_u[inverse]
    raw_noise = float((labels == -1).mean())
    labels = attach_noise_to_templates(labels, np.array(tids))
    for r, l in zip(rows, labels):
        r.cluster_id = int(l)
    timings["clustering"] = time.perf_counter() - t
    progress(0.65, "Detecting anomalies")

    t = time.perf_counter()
    X24 = Xu[:, :24][inverse]
    scores, anomalies = detect_all(rows, X24, float(cfg["contamination"]), float(cfg["z_threshold"]))
    flagged = {i for a in anomalies for i in a["log_idx"]}
    for i, r in enumerate(rows):
        r.anomaly_score = float(scores[i])
        r.is_anomaly = i in flagged
    timings["anomaly"] = time.perf_counter() - t
    progress(0.75, "Analyzing clusters")

    t = time.perf_counter()
    clusters = describe_clusters(rows, Xu, inverse, weights, anomalies, tinfo, uniq)
    for c in clusters:
        base = rule_summary(c)
        c["summary"], c["summary_source"] = llm_enhance(base, c, env.get("llm_provider", ""), env.get("llm_api_key", ""), env.get("llm_model", ""))
    insights = build_insights(clusters, anomalies)
    cmap = {c["cluster_key"]: c for c in clusters}
    for a in anomalies:
        c = cmap.get(a.get("cluster_key"))
        a["severity"] = c["priority"] if c else "Medium"
        a["impact"] = (f"Affects {len(c['services'])} service(s) ({', '.join(list(c['services'])[:3])}); {c['size']} related events in cluster '{c['name']}'." if c
                       else "System-wide signal; compare against overall error budget and recent changes.")
    timings["analysis"] = time.perf_counter() - t
    progress(0.85, "Evaluating models")

    cluster_truth = [r.cluster_truth for r in rows] if sum(r.cluster_truth is not None for r in rows) > 0.9 * len(rows) else None
    anomaly_truth = [r.anomaly_truth for r in rows] if sum(r.anomaly_truth is not None for r in rows) > 0.9 * len(rows) else None
    ev: dict = {"timings_s": {}, "feature_backend": feats.backend, "feature_note": feats.note, "feature_dim": feats.dim, "clustering_used": used,
                "raw_noise_ratio": round(raw_noise, 4), "n_unique_messages": len(uniq), "has_cluster_labels": cluster_truth is not None,
                "has_anomaly_labels": anomaly_truth is not None}
    if cfg["run_evaluation"]:
        t = time.perf_counter()
        ev["final"] = clustering_metrics(Xu, lab_u, cluster_truth, inverse)  # raw algorithm output (noise kept as noise)
        lab_att_u = lab_u.copy()
        lab_att_u[inverse] = labels  # labels after noise->template attachment (what the dashboard shows)
        ev["final_after_noise_attachment"] = clustering_metrics(Xu, lab_att_u, cluster_truth, inverse)
        ev["template_methods"] = compare_template_methods([r.normalized for r in rows[:20000]], cluster_truth[:20000] if cluster_truth else None, float(cfg["sim_threshold"]))
        if cluster_truth:
            ev["template_grouping_accuracy"] = round(grouping_accuracy(tids, cluster_truth), 4)
        ev["comparison"] = run_experiments(uniq, inverse, weights, cluster_truth, {**cfg, "n_clusters": cfg["n_clusters"] or min(len(tinfo), 50)})
        if anomaly_truth:
            y = [0 if str(l).lower() in NOISE_LIKE or l == "normal" else 1 for l in anomaly_truth]
            contam = float(cfg["contamination"])
            det = {}
            for name, s, th in (("isolation_forest", scores, None), ("template_rarity_baseline", rarity_scores(rows), None), ("severity_baseline", level_scores(rows), None)):
                thr = float(np.quantile(s, 1 - max(sum(y) / len(y), contam)))  # threshold at the (known) positive rate for a like-for-like comparison
                det[name] = anomaly_metrics(y, s, thr)
            det["combined_detectors(flagged)"] = anomaly_metrics(y, [1 if r.is_anomaly else 0 for r in rows], binary=True)
            ev["anomaly"] = det
            ev["anomaly_note"] = "Per-detector thresholds are set at the labelled positive rate for a like-for-like comparison; ROC-AUC/PR-AUC are threshold-free."
        timings["evaluation"] = time.perf_counter() - t
    ev["timings_s"] = {k: round(v, 4) for k, v in timings.items()}
    total_s = time.perf_counter() - t_all
    ev["total_seconds"] = round(total_s, 3)
    ev["logs_per_second"] = round(len(rows) / total_s) if total_s else None
    progress(0.95, "Saving results")

    ts = [r.timestamp for r in rows if r.timestamp]
    stats = {"total_logs": len(rows), "n_templates": len(tinfo), "n_clusters": len(clusters), "critical": sum(1 for c in clusters if c["priority"] == "Critical"),
             "anomalies": len(anomalies), "levels": dict(Counter(r.level for r in rows)),
             "services": dict(Counter(r.service or "unknown" for r in rows).most_common(15)),
             "error_services": dict(Counter(r.service or "unknown" for r in rows if is_err(r)).most_common(10)),
             "time_range": [min(ts).isoformat(), max(ts).isoformat()] if ts else [], "unparsed_timestamps": sum(1 for r in rows if not r.timestamp)}
    return {"rows": rows, "templates": tinfo, "clusters": clusters, "anomalies": anomalies, "insights": insights, "evaluation": ev, "stats": stats}
