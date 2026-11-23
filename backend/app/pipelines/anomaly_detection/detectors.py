"""Anomaly detection: Isolation Forest (event level) + statistical / time-based detectors (rolling z-score), each with a reason."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.pipelines.parsing.parser import ParsedLog

LEVEL_W = {"FATAL": 4, "ERROR": 3, "WARN": 2, "INFO": 1, "DEBUG": 0, "UNKNOWN": 1}
MAX_BUCKETS = 20000
FREQ = {"1min": "1min", "5min": "5min", "15min": "15min", "1h": "1h"}


def is_err(r: ParsedLog) -> bool:
    return r.level in ("ERROR", "FATAL")


def event_features(rows: list[ParsedLog], X: np.ndarray, k: int = 24) -> np.ndarray:
    tcount = Counter(r.template_id for r in rows)
    n = len(rows)
    extra = np.array([[-np.log(tcount[r.template_id] / n) / 10, LEVEL_W[r.level] / 4,
                       np.sin((r.timestamp.hour / 24) * 2 * np.pi) if r.timestamp else 0.0] for r in rows])
    return np.hstack([X[:, :k], extra])


def isolation_forest_scores(F: np.ndarray, contamination: float = 0.02, seed: int = 42) -> np.ndarray:
    """Higher = more anomalous, scaled to roughly [0,1]."""
    if len(F) < 5:
        return np.zeros(len(F))
    m = IsolationForest(n_estimators=150, contamination=min(max(contamination, 0.001), 0.5), random_state=seed, n_jobs=1).fit(F)
    s = -m.score_samples(F)
    return (s - s.min()) / (s.max() - s.min() + 1e-12)


def rarity_scores(rows: list[ParsedLog]) -> np.ndarray:
    """Baseline statistical detector: rarer template -> more anomalous (negative log frequency, min-max scaled)."""
    tc = Counter(r.template_id for r in rows)
    s = np.array([-np.log(tc[r.template_id] / len(rows)) for r in rows])
    return (s - s.min()) / (s.max() - s.min() + 1e-12)


def level_scores(rows: list[ParsedLog]) -> np.ndarray:
    """Baseline: severity only."""
    return np.array([LEVEL_W[r.level] / 4 for r in rows])


def bucket_series(rows: list[ParsedLog], freq: str, pred=is_err) -> pd.Series:
    ts = [r.timestamp for r in rows if r.timestamp]
    if not ts:
        return pd.Series(dtype=float)
    n_buckets = (max(ts) - min(ts)).total_seconds() / pd.Timedelta(FREQ[freq]).total_seconds()
    if n_buckets > MAX_BUCKETS:  # e.g. mixed-year timestamps: a 1-minute series over decades is meaningless and unbounded in memory
        return pd.Series(dtype=float)
    idx = pd.date_range(pd.Timestamp(min(ts)).floor(FREQ[freq]), pd.Timestamp(max(ts)).floor(FREQ[freq]), freq=FREQ[freq])
    sel = pd.Series([r.timestamp for r in rows if r.timestamp and pred(r)], dtype="datetime64[ns]")
    counts = sel.dt.floor(FREQ[freq]).value_counts() if len(sel) else pd.Series(dtype=float)
    return counts.reindex(idx, fill_value=0).astype(float).sort_index()


def zscore_spikes(series: pd.Series, window: int = 12, z: float = 3.0, min_count: float = 5) -> list[dict]:
    """Compare each bucket to the rolling mean/std of the preceding `window` buckets."""
    out = []
    v = series.values
    for i in range(3, len(v)):
        base = v[max(0, i - window): i]
        mu, sd = base.mean(), (base.std(ddof=1) if len(base) > 1 else 0.0) or 1.0
        zz = (v[i] - mu) / sd
        if zz >= z and v[i] >= min_count:
            out.append({"time": series.index[i].to_pydatetime(), "count": float(v[i]), "baseline": float(mu), "z": float(zz),
                        "pct": float((v[i] - mu) / mu * 100) if mu > 0 else None})
    return out


def _mode(xs):
    return Counter(xs).most_common(1)[0][0] if xs else None


def _min_ts(rows, idx):
    ts = [rows[i].timestamp for i in idx if rows[i].timestamp]
    return min(ts) if ts else None


def detect_all(rows: list[ParsedLog], X: np.ndarray, contamination: float = 0.02, z_threshold: float = 3.0) -> tuple[np.ndarray, list[dict]]:
    """Returns (isolation-forest score per log, list of anomaly dicts with kind/score/reason/log_idx/detected_at/cluster)."""
    anomalies: list[dict] = []
    n = len(rows)
    scores = isolation_forest_scores(event_features(rows, X), contamination)
    tcount = Counter(r.template_id for r in rows)
    thr = np.quantile(scores, 1 - contamination) if n > 10 else 2.0
    flagged = [i for i in range(n) if scores[i] >= thr and scores[i] > 0]
    by_c: dict[int, list[int]] = defaultdict(list)
    for i in flagged:
        by_c[rows[i].cluster_id].append(i)
    for cid, ids in by_c.items():
        anomalies.append(dict(kind="isolation_forest", score=float(max(scores[i] for i in ids)), cluster_key=cid, log_idx=ids[:200], detected_at=_min_ts(rows, ids),
                              reason=f"Isolation Forest flagged {len(ids)} event(s) as outliers: unusual message content, severity or template rarity "
                                     f"(top {contamination:.1%} of anomaly scores)."))
    # time-based spikes at several resolutions
    for freq in ("1min", "5min", "1h"):
        s = bucket_series(rows, freq)
        for sp in zscore_spikes(s, z=z_threshold):
            end = sp["time"] + pd.Timedelta(FREQ[freq]).to_pytimedelta()
            win = [i for i, r in enumerate(rows) if r.timestamp and sp["time"] <= r.timestamp < end and is_err(r)]
            pct = f"+{sp['pct']:.0f}% vs rolling baseline {sp['baseline']:.1f}" if sp["pct"] is not None else "a new burst vs an empty baseline"
            anomalies.append(dict(kind=f"frequency_spike_{freq}", score=min(1.0, sp["z"] / 10), cluster_key=_mode([rows[i].cluster_id for i in win]),
                                  log_idx=win[:200], detected_at=sp["time"],
                                  reason=f"Error count {int(sp['count'])} in a {freq} window (z={sp['z']:.1f}, {pct})."))
    ts_rows = [r for r in rows if r.timestamp]
    if ts_rows:
        t0 = min(r.timestamp for r in ts_rows); t1 = max(r.timestamp for r in ts_rows); mid = t0 + (t1 - t0) / 2
        groups: dict[int, list[int]] = defaultdict(list)
        for i, r in enumerate(rows):
            groups[r.cluster_id].append(i)
        for cid, idxs in groups.items():
            grp = [rows[i] for i in idxs if rows[i].timestamp]
            if not grp:
                continue
            first = _min_ts(rows, idxs)
            if any(is_err(r) for r in grp) and t1 > t0 and first > mid and len(grp) >= 3:
                anomalies.append(dict(kind="new_pattern", score=0.7, cluster_key=cid, log_idx=idxs[:200], detected_at=first,
                                      reason=f"New error pattern first appeared at {first:%Y-%m-%d %H:%M:%S} (second half of the observed window) and occurred {len(grp)} times."))
            if len(grp) >= 10:
                for sp in zscore_spikes(bucket_series(grp, "5min", lambda r: True), z=z_threshold + 0.5):
                    anomalies.append(dict(kind="cluster_spike", score=min(1.0, sp["z"] / 10), cluster_key=cid, log_idx=idxs[:200], detected_at=sp["time"],
                                          reason=f"Cluster volume spiked to {int(sp['count'])} per 5 min (z={sp['z']:.1f}, baseline {sp['baseline']:.1f})."))
        # error-ratio shift
        allb, errb = bucket_series(rows, "15min", lambda r: True), bucket_series(rows, "15min")
        if len(allb) >= 6:
            pct = (errb / allb.replace(0, np.nan) * 100).fillna(0).round()
            for sp in zscore_spikes(pct, z=z_threshold, min_count=20):
                anomalies.append(dict(kind="severity_shift", score=0.65, cluster_key=None, log_idx=[], detected_at=sp["time"],
                                      reason=f"Error ratio jumped to {sp['count']:.0f}% of logs (rolling baseline {sp['baseline']:.0f}%)."))
    min_t = max(1, int(n * 0.0005))
    rare = [i for i, r in enumerate(rows) if tcount[r.template_id] <= min_t and is_err(r)]
    rc: dict[int, list[int]] = defaultdict(list)
    for i in rare:
        rc[rows[i].cluster_id].append(i)
    for cid, ids in rc.items():
        anomalies.append(dict(kind="rare_template", score=0.6, cluster_key=cid, log_idx=ids[:200], detected_at=_min_ts(rows, ids),
                              reason=f"{len(ids)} error event(s) with rare template(s) seen at most {min_t} time(s) in the dataset."))
    svc: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        svc[r.service or "unknown"].append(i)
    rates = [(s, sum(is_err(rows[i]) for i in ix) / len(ix), ix) for s, ix in svc.items()]
    if len(rates) >= 3:
        mu = np.mean([r[1] for r in rates]); sd = np.std([r[1] for r in rates], ddof=1) or 1.0
        for s, rate, ix in rates:
            errs = [i for i in ix if is_err(rows[i])]
            if (rate - mu) / sd > 2 and len(errs) >= 5:
                anomalies.append(dict(kind="component", score=0.55, cluster_key=_mode([rows[i].cluster_id for i in errs]), log_idx=errs[:200], detected_at=_min_ts(rows, errs),
                                      reason=f"Service '{s}' has an error rate of {rate:.0%} versus a mean of {mu:.0%} across services (z={(rate - mu) / sd:.1f})."))
    return scores, anomalies
