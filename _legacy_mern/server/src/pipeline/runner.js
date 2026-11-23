// End-to-end orchestration: pure analyze() + parseFiles(); persistence lives in jobs.js.
import { readRecords } from "./ingestion.js";
import { parseLine, detectFormat } from "./parser.js";
import { normalize } from "./normalizer.js";
import { mineTemplates, groupingAccuracy } from "./templates.js";
import { tfidfVectors } from "./features.js";
import { runClustering, assignNoiseToTemplates, representatives, topKeywords, centroidSimilarity } from "./clustering.js";
import { detectAll } from "./anomaly.js";
import { priorityScore, priorityLabel } from "./priority.js";
import { buildInsights } from "./rootcause.js";
import { ruleSummary, llmEnhance } from "./summarize.js";
import * as evaluation from "./evaluation.js";

export const DEFAULT_CONFIG = {
  features: "tfidf", algorithm: "auto", eps: 0.3, min_samples: 3, min_cluster_size: 5,
  contamination: 0.02, z_threshold: 3.0, sim_threshold: 0.5, lowercase: false, keep_stack_trace: false, run_evaluation: true,
};

export function parseFiles(files) {
  const rows = [], meta = { files: [], invalid_lines: 0 };
  for (const { name, data } of files) {
    const { recs, encoding, invalid } = readRecords(data, name);
    const fmt = recs[0]?.fields ? "structured" : detectFormat(recs.slice(0, 200).map((r) => r.text));
    meta.files.push({ name, encoding, format: fmt, records: recs.length }); meta.invalid_lines += invalid;
    for (const r of recs) rows.push({ ...parseLine(r.lineNo, r.text, r.fields, fmt), source: name });
  }
  if (!rows.length) throw new Error("No parsable log records found");
  rows.forEach((r) => { r.service = r.service || r.component || "unknown"; });
  return { rows, meta };
}

const counter = (xs) => xs.reduce((m, x) => ((m[x] = (m[x] || 0) + 1), m), {});
const topN = (obj, n) => Object.fromEntries(Object.entries(obj).sort((a, b) => b[1] - a[1]).slice(0, n));

export async function analyze(rows, config = {}, progress = async () => {}, env = {}) {
  const cfg = { ...DEFAULT_CONFIG, ...config }, timings = {};
  let t = performance.now();
  rows.forEach((r) => { r.normalized = normalize(r.message, cfg); });
  timings.normalize = (performance.now() - t) / 1000; await progress(0.25, "Extracting templates");

  t = performance.now();
  const { ids: tids, info: tinfo } = mineTemplates(rows.map((r) => r.normalized), { simTh: cfg.sim_threshold });
  rows.forEach((r, i) => { r.template_id = tids[i]; });
  timings.templates = (performance.now() - t) / 1000; await progress(0.35, "Building features");

  t = performance.now();
  const uniqMap = new Map(); const inverse = rows.map((r) => { if (!uniqMap.has(r.normalized)) uniqMap.set(r.normalized, uniqMap.size); return uniqMap.get(r.normalized); });
  const uniq = [...uniqMap.keys()], weights = new Array(uniq.length).fill(0); inverse.forEach((u) => weights[u]++);
  const { vectors: Xu } = tfidfVectors(uniq, { mode: cfg.features });
  timings.features = (performance.now() - t) / 1000; await progress(0.5, "Clustering");

  t = performance.now();
  const { labels: lu, eps } = runClustering(Xu, weights, cfg);
  let labels = inverse.map((u) => lu[u]);
  const rawNoise = labels.filter((l) => l === -1).length / labels.length;
  labels = assignNoiseToTemplates(labels, tids);
  rows.forEach((r, i) => { r.cluster_id = labels[i]; });
  const X = inverse.map((u) => Xu[u]);
  timings.clustering = (performance.now() - t) / 1000; await progress(0.65, "Detecting anomalies");

  t = performance.now();
  const { scores, anomalies } = detectAll(rows, X, cfg);
  const anomIdx = new Set(anomalies.flatMap((a) => a.log_idx));
  rows.forEach((r, i) => { r.anomaly_score = scores[i]; r.is_anomaly = anomIdx.has(i); });
  timings.anomaly = (performance.now() - t) / 1000; await progress(0.75, "Analyzing clusters");

  t = performance.now();
  const clusters = describeClusters(rows, X, anomalies, tinfo);
  for (const c of clusters) c.summary = await llmEnhance(ruleSummary(c), c, env.LLM_PROVIDER, env.LLM_API_KEY);
  const insights = buildInsights(clusters, anomalies);
  const pr = Object.fromEntries(clusters.map((c) => [c.cluster_key, c]));
  for (const a of anomalies) {
    const c = pr[a.cluster_key];
    a.severity = c?.priority || "Medium";
    a.impact = c ? `Affects ${Object.keys(c.services).length} service(s) (${Object.keys(c.services).slice(0, 3).join(", ")}); ${c.size} related events.` : "System-wide signal; check overall error budget.";
  }
  timings.analysis = (performance.now() - t) / 1000; await progress(0.85, "Evaluating models");

  const ev = { timings_s: Object.fromEntries(Object.entries(timings).map(([k, v]) => [k, Math.round(v * 1e4) / 1e4])), feature_backend: cfg.features, eps_used: Math.round(eps * 1000) / 1000, raw_noise_ratio: Math.round(rawNoise * 1e4) / 1e4 };
  const labelled = rows.filter((r) => r.label != null).length / rows.length > 0.9;
  const truth = labelled ? rows.map((r) => r.label) : null;
  if (cfg.run_evaluation) {
    ev.final = evaluation.clusteringMetrics(X, labels, truth);
    ev.comparison = evaluation.compare(uniq, inverse, weights, truth, cfg);
    if (truth) {
      ev.template_grouping_accuracy = Math.round(groupingAccuracy(tids, truth) * 1e4) / 1e4;
      const y = truth.map((l) => (["normal", "0", "false", "-"].includes(String(l).toLowerCase()) ? 0 : 1));
      const pos = y.filter(Boolean).length;
      if (pos > 0 && pos < y.length) {
        const thr = [...scores].sort((a, b) => b - a)[Math.floor(scores.length * cfg.contamination)];
        ev.anomaly = evaluation.anomalyMetrics(y, scores, thr);
        ev.anomaly_combined = evaluation.anomalyMetrics(y, rows.map((r) => (r.is_anomaly ? 1 : 0)), 0.5);
      }
    }
  }
  await progress(0.95, "Saving results");
  const ts = rows.filter((r) => r.timestamp).map((r) => r.timestamp.getTime());
  const stats = { total_logs: rows.length, n_templates: Object.keys(tinfo).length, n_clusters: clusters.length,
    critical: clusters.filter((c) => c.priority === "Critical").length, anomalies: anomalies.length,
    levels: counter(rows.map((r) => r.level)), services: topN(counter(rows.map((r) => r.service)), 15),
    time_range: ts.length ? [new Date(Math.min(...ts)).toISOString(), new Date(Math.max(...ts)).toISOString()] : [] };
  return { rows, templates: tinfo, clusters, anomalies, insights, evaluation: ev, stats };
}

const ORDER = ["FATAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"];
function bucketMs(spanMs) { const h = spanMs / 3600e3; return h <= 2 ? 60e3 : h <= 12 ? 300e3 : h <= 96 ? 3600e3 : 86400e3; }

export function describeClusters(rows, X, anomalies, tinfo) {
  const total = rows.length, totalSvcs = new Set(rows.map((r) => r.service)).size;
  const ts = rows.filter((r) => r.timestamp).map((r) => r.timestamp.getTime());
  const tmin = ts.length ? Math.min(...ts) : null, tmax = ts.length ? Math.max(...ts) : null, span = tmax - tmin;
  const anomScore = {}; for (const a of anomalies) if (a.cluster_key != null) anomScore[a.cluster_key] = Math.max(anomScore[a.cluster_key] || 0, a.score);
  const labels = rows.map((r) => r.cluster_id);
  const sims = new Set(labels).size <= 1500 ? centroidSimilarity(X, labels) : {};
  const groups = new Map(); rows.forEach((r, i) => { if (!groups.has(r.cluster_id)) groups.set(r.cluster_id, []); groups.get(r.cluster_id).push(i); });
  const out = [];
  for (const [cid, idx] of groups) {
    const g = idx.map((i) => rows[i]);
    const levels = counter(g.map((r) => r.level));
    const level = ORDER.find((l) => (levels[l] || 0) >= Math.max(1, 0.2 * g.length)) || Object.keys(levels)[0];
    const tc = counter(g.map((r) => r.template_id)), topT = Object.entries(tc).sort((a, b) => b[1] - a[1])[0][0];
    const gts = g.filter((r) => r.timestamp).map((r) => r.timestamp.getTime());
    let trend = [], trendRatio = 1, recency = 0.5, first = null, last = null;
    if (gts.length) {
      first = new Date(Math.min(...gts)); last = new Date(Math.max(...gts));
      if (span > 0) {
        const b = bucketMs(span), cnt = counter(gts.map((t) => Math.floor(t / b) * b));
        trend = Object.keys(cnt).map(Number).sort((a, b) => a - b).map((k) => ({ t: new Date(k).toISOString(), count: cnt[k] }));
        const mid = tmin + span / 2, f = gts.filter((t) => t < mid).length;
        trendRatio = (gts.length - f + 1) / (f + 1); recency = (last.getTime() - tmin) / span;
      }
    }
    const services = topN(counter(g.map((r) => r.service)), 8);
    const { score, parts } = priorityScore({ level, size: g.length, total, anomaly: anomScore[cid] || 0, trendRatio, recency, nServices: Object.keys(counter(g.map((r) => r.service))).length, totalServices: totalSvcs });
    const template = tinfo[topT]?.template || g[0].normalized;
    const keywords = topKeywords(g.slice(0, 500).map((r) => r.normalized));
    const words = template.replace(/<\*>/g, "").split(" ").filter((w) => w && !w.startsWith("<")).slice(0, 7);
    out.push({ cluster_key: cid, name: (words.join(" ") || keywords.slice(0, 3).join(" ") || "Misc pattern").slice(0, 80), size: g.length, severity: level,
      priority: priorityLabel(score, level), priority_score: score, priority_factors: parts, first_seen: first, last_seen: last, keywords,
      representatives: representatives(X, idx).map((i) => rows[i].message.slice(0, 400)), template, services, levels, trend, trend_ratio: trendRatio,
      related: (sims[cid] || []).filter(([, s]) => s > 0.3).map(([k, s]) => ({ cluster_key: k, similarity: Math.round(s * 1000) / 1000 })),
      is_anomalous: cid in anomScore });
  }
  return out.sort((a, b) => b.priority_score - a.priority_score);
}
