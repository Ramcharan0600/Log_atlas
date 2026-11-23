// DBSCAN (cosine distance) on unique normalized messages, weighted by repetition count.
// "auto" picks eps from the knee of the sorted k-distance curve.
import { cosDist, mean, dot } from "./features.js";

export function dbscan(X, weights, { eps = 0.3, minSamples = 3 } = {}) {
  const n = X.length, labels = new Int32Array(n).fill(-2);
  const neighbors = (i) => { const r = []; for (let j = 0; j < n; j++) if (cosDist(X[i], X[j]) <= eps) r.push(j); return r; };
  const mass = (idx) => idx.reduce((s, j) => s + weights[j], 0);
  let c = 0;
  for (let i = 0; i < n; i++) {
    if (labels[i] !== -2) continue;
    const nb = neighbors(i);
    if (mass(nb) < minSamples) { labels[i] = -1; continue; }
    labels[i] = c;
    const queue = nb.filter((j) => j !== i);
    while (queue.length) {
      const j = queue.pop();
      if (labels[j] === -1) labels[j] = c;
      if (labels[j] !== -2) continue;
      labels[j] = c;
      const nb2 = neighbors(j);
      if (mass(nb2) >= minSamples) queue.push(...nb2.filter((k) => labels[k] < 0));
    }
    c++;
  }
  return Array.from(labels);
}

export function autoEps(X, k = 3) {
  if (X.length < k + 2) return 0.3;
  const sample = X.length > 800 ? X.filter((_, i) => i % Math.ceil(X.length / 800) === 0) : X;
  const kd = sample.map((a) => sample.map((b) => cosDist(a, b)).sort((x, y) => x - y)[Math.min(k, sample.length - 1)]).sort((a, b) => a - b);
  // knee: point with max distance from line between first and last
  const n = kd.length, x1 = 0, y1 = kd[0], x2 = n - 1, y2 = kd[n - 1];
  let best = 0, bi = Math.floor(n * 0.9);
  for (let i = 0; i < n; i++) { const d = Math.abs((y2 - y1) * i - (x2 - x1) * kd[i] + x2 * y1 - y2 * x1); if (d > best) { best = d; bi = i; } }
  return Math.min(0.6, Math.max(0.08, kd[bi]));
}

export function runClustering(X, weights, cfg) {
  const t0 = performance.now();
  const eps = cfg.algorithm === "auto" ? autoEps(X, cfg.min_samples) : cfg.eps;
  const labels = dbscan(X, weights, { eps, minSamples: cfg.min_samples });
  return { labels, eps, runtime: (performance.now() - t0) / 1000 };
}

// Noise points sharing a template become their own small cluster so they remain inspectable.
export function assignNoiseToTemplates(labels, templateIds) {
  let next = Math.max(-1, ...labels) + 1; const map = new Map();
  return labels.map((l, i) => { if (l !== -1) return l; const t = templateIds[i]; if (!map.has(t)) map.set(t, next++); return map.get(t); });
}

export function representatives(X, idx, k = 3) {
  const c = mean(idx.map((i) => X[i]));
  return [...idx].sort((a, b) => cosDist(X[a], c) - cosDist(X[b], c)).slice(0, k);
}

const STOP = new Set("the a an for to of in on at is and with from by was".split(" "));
export function topKeywords(texts, k = 6) {
  const c = new Map();
  for (const t of texts) for (let w of t.split(/\s+/)) { w = w.replace(/^[.,:;()[\]'"]+|[.,:;()[\]'"]+$/g, "").toLowerCase(); if (w.length > 2 && !STOP.has(w) && !w.startsWith("<")) c.set(w, (c.get(w) || 0) + 1); }
  return [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, k).map(([w]) => w);
}

export function centroidSimilarity(X, labels) {
  const groups = new Map(); labels.forEach((l, i) => { if (!groups.has(l)) groups.set(l, []); groups.get(l).push(X[i]); });
  const keys = [...groups.keys()], C = keys.map((k) => mean(groups.get(k).slice(0, 300)));
  const out = {};
  keys.forEach((k, i) => { out[k] = keys.map((k2, j) => [k2, dot(C[i], C[j])]).filter(([k2]) => k2 !== k).sort((a, b) => b[1] - a[1]).slice(0, 4); });
  return out;
}
