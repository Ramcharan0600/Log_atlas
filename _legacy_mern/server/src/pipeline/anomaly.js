// Isolation Forest (event-level) + rolling z-score spikes (1m/5m/1h) + per-cluster spikes + new/rare patterns
// + severity-ratio shift + service outliers.
import { isolationForest } from "./isolationForest.js";

const LEVEL_W = { FATAL: 4, ERROR: 3, WARN: 2, INFO: 1, DEBUG: 0, UNKNOWN: 1 };
const isErr = (l) => l.level === "ERROR" || l.level === "FATAL";
const MS = { "1min": 60e3, "5min": 300e3, "15min": 900e3, "1h": 3600e3 };

export function bucketCounts(rows, freq, pred = isErr) {
  const ms = MS[freq], ts = rows.filter((r) => r.timestamp).map((r) => r.timestamp.getTime());
  if (!ts.length) return [];
  const start = Math.floor(Math.min(...ts) / ms) * ms, end = Math.max(...ts);
  const n = Math.floor((end - start) / ms) + 1, counts = new Array(n).fill(0);
  for (const r of rows) if (r.timestamp && pred(r)) counts[Math.floor((r.timestamp.getTime() - start) / ms)]++;
  return counts.map((c, i) => ({ t: new Date(start + i * ms), c }));
}

export function zscoreSpikes(series, { window = 12, z = 3, minCount = 5 } = {}) {
  const out = [];
  for (let i = 3; i < series.length; i++) {
    const base = series.slice(Math.max(0, i - window), i).map((s) => s.c);
    const m = base.reduce((a, b) => a + b, 0) / base.length;
    const sd = Math.sqrt(base.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(base.length - 1, 1)) || 1;
    const zv = (series[i].c - m) / sd;
    if (zv >= z && series[i].c >= minCount) out.push({ time: series[i].t, count: series[i].c, baseline: m, z: zv, pct: m > 0 ? ((series[i].c - m) / m) * 100 : Infinity });
  }
  return out;
}

const groupBy = (arr, f) => arr.reduce((m, x, i) => { const k = f(x, i); (m.get(k) || m.set(k, []).get(k)).push(i); return m; }, new Map());
const mode = (xs) => { const c = new Map(); xs.forEach((x) => c.set(x, (c.get(x) || 0) + 1)); return [...c.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]; };
const minTs = (rows, idx) => idx.reduce((m, i) => (rows[i].timestamp && (!m || rows[i].timestamp < m) ? rows[i].timestamp : m), null);

export function detectAll(rows, X, { contamination = 0.02, z_threshold = 3 } = {}) {
  const anomalies = [];
  const tcount = new Map(); rows.forEach((r) => tcount.set(r.template_id, (tcount.get(r.template_id) || 0) + 1));
  const feats = rows.map((r, i) => {
    const rarity = -Math.log(tcount.get(r.template_id) / rows.length);
    const hour = r.timestamp ? r.timestamp.getUTCHours() : 12;
    return [...Array.from(X[i].slice(0, 24)), rarity / 10, LEVEL_W[r.level] / 4, Math.sin((hour / 24) * 2 * Math.PI)];
  });
  const scores = isolationForest(feats);
  const sorted = [...scores].sort((a, b) => b - a), thr = rows.length > 10 ? sorted[Math.floor(rows.length * contamination)] : 2;
  const flagged = scores.map((s, i) => (s >= thr ? i : -1)).filter((i) => i >= 0);
  for (const [cid, idxs] of groupBy(flagged.map((i) => rows[i]), (r) => r.cluster_id)) {
    const ids = idxs.map((k) => flagged[k]);
    anomalies.push({ kind: "isolation_forest", score: Math.max(...ids.map((i) => scores[i])), cluster_key: cid, log_idx: ids.slice(0, 200), detected_at: minTs(rows, ids),
      reason: `Isolation Forest flagged ${ids.length} event(s) as outliers (unusual message content, severity or template rarity).` });
  }
  for (const freq of ["1min", "5min", "1h"]) {
    for (const s of zscoreSpikes(bucketCounts(rows, freq), { z: z_threshold })) {
      const end = new Date(s.time.getTime() + MS[freq]);
      const win = rows.map((r, i) => (r.timestamp >= s.time && r.timestamp < end && isErr(r) ? i : -1)).filter((i) => i >= 0);
      anomalies.push({ kind: `frequency_spike_${freq}`, score: Math.min(1, s.z / 10), detected_at: s.time, cluster_key: mode(win.map((i) => rows[i].cluster_id)) ?? null, log_idx: win.slice(0, 200),
        reason: `Error count ${s.count} in ${freq} window (z=${s.z.toFixed(1)}, ${isFinite(s.pct) ? `+${s.pct.toFixed(0)}% vs rolling baseline ${s.baseline.toFixed(1)}` : "a new burst"}).` });
    }
  }
  const tsRows = rows.filter((r) => r.timestamp);
  if (tsRows.length) {
    const t0 = Math.min(...tsRows.map((r) => r.timestamp.getTime())), t1 = Math.max(...tsRows.map((r) => r.timestamp.getTime())), mid = t0 + (t1 - t0) / 2;
    for (const [cid, idxs] of groupBy(rows, (r) => r.cluster_id)) {
      const grp = idxs.map((i) => rows[i]).filter((r) => r.timestamp);
      if (!grp.length) continue;
      const first = minTs(rows, idxs);
      if (grp.some(isErr) && t1 > t0 && first.getTime() > mid && grp.length >= 3)
        anomalies.push({ kind: "new_pattern", score: 0.7, detected_at: first, cluster_key: cid, log_idx: idxs.slice(0, 200), reason: `New error pattern first appeared at ${first.toISOString()} (second half of the window) and occurred ${grp.length} times.` });
      for (const s of zscoreSpikes(bucketCounts(grp, "5min", () => true), { z: z_threshold + 0.5 }))
        anomalies.push({ kind: "cluster_spike", score: Math.min(1, s.z / 10), detected_at: s.time, cluster_key: cid, log_idx: idxs.slice(0, 200), reason: `Cluster volume spiked to ${s.count} per 5 min (z=${s.z.toFixed(1)}).` });
    }
    const ratio = bucketCounts(rows, "15min", () => true).map((b, i, all) => b);
    const errs = bucketCounts(rows, "15min");
    const pct = errs.map((e, i) => ({ t: e.t, c: ratio[i].c ? Math.round((e.c / ratio[i].c) * 100) : 0 }));
    for (const s of zscoreSpikes(pct, { z: z_threshold, minCount: 20 }))
      anomalies.push({ kind: "severity_shift", score: 0.65, detected_at: s.time, cluster_key: null, log_idx: [], reason: `Error ratio jumped to ${s.count}% of logs (baseline ${s.baseline.toFixed(0)}%).` });
  }
  const minT = Math.max(1, Math.floor(rows.length * 0.0005));
  const rare = rows.map((r, i) => (tcount.get(r.template_id) <= minT && isErr(r) ? i : -1)).filter((i) => i >= 0);
  for (const [cid, k] of groupBy(rare.map((i) => rows[i]), (r) => r.cluster_id)) {
    const ids = k.map((j) => rare[j]);
    anomalies.push({ kind: "rare_template", score: 0.6, detected_at: minTs(rows, ids), cluster_key: cid, log_idx: ids, reason: `${ids.length} error event(s) with rare template(s) seen ≤${minT} times.` });
  }
  const svc = groupBy(rows, (r) => r.service);
  const rates = [...svc].map(([s, idx]) => [s, idx.filter((i) => isErr(rows[i])).length / idx.length, idx]);
  if (rates.length >= 3) {
    const mu = rates.reduce((a, r) => a + r[1], 0) / rates.length, sd = Math.sqrt(rates.reduce((a, r) => a + (r[1] - mu) ** 2, 0) / (rates.length - 1)) || 1;
    for (const [s, r, idx] of rates) {
      const e = idx.filter((i) => isErr(rows[i]));
      if ((r - mu) / sd > 2 && e.length >= 5) anomalies.push({ kind: "component", score: 0.55, detected_at: null, cluster_key: null, log_idx: e.slice(0, 200), reason: `Service '${s}' error rate ${(r * 100).toFixed(0)}% vs mean ${(mu * 100).toFixed(0)}% across services.` });
    }
  }
  return { scores, anomalies };
}
