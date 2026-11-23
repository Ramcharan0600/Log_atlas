// Clustering metrics (ARI, NMI, homogeneity, completeness, V-measure, silhouette, Davies-Bouldin, Calinski-Harabasz)
// and anomaly metrics (precision, recall, F1, ROC-AUC, PR-AUC, confusion matrix). Comparison grid across configs.
import { cosDist, mean, dot } from "./features.js";
import { runClustering } from "./clustering.js";
import { tfidfVectors } from "./features.js";

const comb2 = (n) => (n * (n - 1)) / 2;
function contingency(a, b) {
  const m = new Map(), ra = new Map(), rb = new Map();
  a.forEach((x, i) => { const k = x + "\u0000" + b[i]; m.set(k, (m.get(k) || 0) + 1); ra.set(x, (ra.get(x) || 0) + 1); rb.set(b[i], (rb.get(b[i]) || 0) + 1); });
  return { m, ra, rb, n: a.length };
}
const entropy = (counts, n) => [...counts.values()].reduce((s, c) => s - (c / n) * Math.log(c / n), 0);

export function externalMetrics(truth, pred) {
  const { m, ra, rb, n } = contingency(truth, pred);
  const sumComb = [...m.values()].reduce((s, c) => s + comb2(c), 0), a = [...ra.values()].reduce((s, c) => s + comb2(c), 0), b = [...rb.values()].reduce((s, c) => s + comb2(c), 0);
  const exp = (a * b) / comb2(n), max = (a + b) / 2;
  const ARI = max === exp ? 1 : (sumComb - exp) / (max - exp);
  let mi = 0; for (const [k, c] of m) { const [x, y] = k.split("\u0000"); mi += (c / n) * Math.log((c * n) / (ra.get(x) * rb.get(y))); }
  const hT = entropy(ra, n), hP = entropy(rb, n);
  const homogeneity = hT === 0 ? 1 : 1 - (hT - mi) / hT; // 1 - H(C|K)/H(C)
  const completeness = hP === 0 ? 1 : 1 - (hP - mi) / hP;
  const v = homogeneity + completeness === 0 ? 0 : (2 * homogeneity * completeness) / (homogeneity + completeness);
  return { ARI, NMI: hT + hP === 0 ? 1 : (2 * mi) / (hT + hP), homogeneity, completeness, v_measure: v };
}

export function internalMetrics(X, labels, sample = 600) {
  const idx = labels.map((l, i) => (l !== -1 ? i : -1)).filter((i) => i >= 0);
  const step = Math.max(1, Math.ceil(idx.length / sample)), s = idx.filter((_, k) => k % step === 0);
  const ks = [...new Set(s.map((i) => labels[i]))];
  if (ks.length < 2 || s.length < 10) return {};
  const by = new Map(ks.map((k) => [k, s.filter((i) => labels[i] === k)]));
  let sil = 0;
  for (const i of s) {
    const own = by.get(labels[i]);
    const a = own.length > 1 ? own.reduce((t, j) => t + (j === i ? 0 : cosDist(X[i], X[j])), 0) / (own.length - 1) : 0;
    let b = Infinity; for (const [k, g] of by) if (k !== labels[i]) b = Math.min(b, g.reduce((t, j) => t + cosDist(X[i], X[j]), 0) / g.length);
    sil += own.length > 1 ? (b - a) / Math.max(a, b) : 0;
  }
  const C = new Map(ks.map((k) => [k, mean(by.get(k).map((i) => X[i]))]));
  const S = new Map(ks.map((k) => [k, by.get(k).reduce((t, i) => t + cosDist(X[i], C.get(k)), 0) / by.get(k).length]));
  let db = 0; for (const k of ks) { let mx = 0; for (const k2 of ks) if (k2 !== k) mx = Math.max(mx, (S.get(k) + S.get(k2)) / Math.max(cosDist(C.get(k), C.get(k2)), 1e-9)); db += mx; }
  const g = mean(s.map((i) => X[i]));
  const B = ks.reduce((t, k) => t + by.get(k).length * (1 - dot(C.get(k), g)) ** 2, 0), W = s.reduce((t, i) => t + cosDist(X[i], C.get(labels[i])) ** 2, 0);
  return { silhouette: sil / s.length, davies_bouldin: db / ks.length, calinski_harabasz: W > 0 ? (B / (ks.length - 1)) / (W / (s.length - ks.length)) : null };
}

const r4 = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, typeof v === "number" && !Number.isInteger(v) ? Math.round(v * 1e4) / 1e4 : v]));

export function clusteringMetrics(X, labels, truth) {
  return r4({ n_clusters: new Set(labels.filter((l) => l !== -1)).size, noise_ratio: labels.filter((l) => l === -1).length / labels.length,
    ...(truth ? externalMetrics(truth, labels) : {}), ...internalMetrics(X, labels) });
}

function auc(xs, ys) { let a = 0; for (let i = 1; i < xs.length; i++) a += (xs[i] - xs[i - 1]) * (ys[i] + ys[i - 1]) / 2; return a; }
export function anomalyMetrics(y, scores, thr) {
  let tp = 0, fp = 0, fn = 0, tn = 0;
  y.forEach((t, i) => { const p = scores[i] >= thr ? 1 : 0; if (p && t) tp++; else if (p) fp++; else if (t) fn++; else tn++; });
  const precision = tp + fp ? tp / (tp + fp) : 0, recall = tp + fn ? tp / (tp + fn) : 0;
  const out = { precision, recall, f1: precision + recall ? (2 * precision * recall) / (precision + recall) : 0, confusion_matrix: [[tn, fp], [fn, tp]] };
  const P = y.filter(Boolean).length, N = y.length - P;
  if (P && N) {
    const order = scores.map((s, i) => [s, y[i]]).sort((a, b) => b[0] - a[0]);
    const fpr = [0], tpr = [0], rec = [0], prec = [1]; let t = 0, f = 0;
    for (const [, l] of order) { l ? t++ : f++; fpr.push(f / N); tpr.push(t / P); rec.push(t / P); prec.push(t / (t + f)); }
    out.roc_auc = auc(fpr, tpr); out.pr_auc = auc(rec, prec);
  }
  return r4(out);
}

export function compare(uniqTexts, inverse, weights, truth, cfg, maxUnique = 1500) {
  const rows = [];
  for (const features of ["tfidf", "tfidf-char"]) {
    const { vectors } = tfidfVectors(uniqTexts, { mode: features });
    const grid = [["dbscan", 0.15], ["dbscan", 0.3], ["dbscan", 0.5], ["auto", null]];
    for (const [algorithm, eps] of grid) {
      const mem0 = process.memoryUsage().heapUsed;
      const { labels, eps: used, runtime } = runClustering(vectors.slice(0, maxUnique), weights, { algorithm, eps, min_samples: cfg.min_samples });
      const full = inverse.map((u) => (u < labels.length ? labels[u] : -1));
      const X = inverse.map((u) => vectors[u]);
      rows.push({ features, algorithm, params: { eps: Math.round(used * 1000) / 1000 }, runtime_s: Math.round(runtime * 1e4) / 1e4,
        peak_mem_mb: Math.max(0, Math.round((process.memoryUsage().heapUsed - mem0) / 1e4) / 100), ...clusteringMetrics(X, full, truth) });
    }
  }
  return rows;
}
