// Isolation Forest (Liu et al. 2008). Score in [0,1]; higher = more anomalous.
function rng(seed) { let s = seed >>> 0; return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; }; }
const H = (n) => Math.log(n) + 0.5772156649;
const cFactor = (n) => (n <= 1 ? 0 : 2 * H(n - 1) - (2 * (n - 1)) / n);

function build(X, idx, depth, maxDepth, rand) {
  if (depth >= maxDepth || idx.length <= 1) return { size: idx.length };
  const d = X[0].length, f = Math.floor(rand() * d);
  let lo = Infinity, hi = -Infinity; for (const i of idx) { lo = Math.min(lo, X[i][f]); hi = Math.max(hi, X[i][f]); }
  if (lo === hi) return { size: idx.length };
  const split = lo + rand() * (hi - lo), L = [], R = [];
  for (const i of idx) (X[i][f] < split ? L : R).push(i);
  return { f, split, l: build(X, L, depth + 1, maxDepth, rand), r: build(X, R, depth + 1, maxDepth, rand) };
}
function pathLen(x, node, depth) { return node.size !== undefined ? depth + cFactor(node.size) : pathLen(x, x[node.f] < node.split ? node.l : node.r, depth + 1); }

export function isolationForest(X, { nTrees = 100, sampleSize = 256, seed = 42 } = {}) {
  const rand = rng(seed), n = X.length, psi = Math.min(sampleSize, n), maxDepth = Math.ceil(Math.log2(psi));
  const trees = [];
  for (let t = 0; t < nTrees; t++) {
    const idx = []; for (let i = 0; i < psi; i++) idx.push(Math.floor(rand() * n));
    trees.push(build(X, idx, 0, maxDepth, rand));
  }
  const c = cFactor(psi);
  return X.map((x) => Math.pow(2, -(trees.reduce((s, tr) => s + pathLen(x, tr, 0), 0) / nTrees) / c));
}
