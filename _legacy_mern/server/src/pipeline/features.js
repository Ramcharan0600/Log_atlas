// Model A: TF-IDF over word unigrams+bigrams and char n-grams, projected to a dense L2-normalized vector
// with the hashing trick. Model B ("tfidf-char"): char n-grams only (robust to wording/typos).
const TOKEN_RE = /<\w+>|\b\w\w+\b/g;

function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

export function terms(text, { word = true, char = true, charN = [3, 5] } = {}) {
  const out = [];
  if (word) {
    const w = (text.match(TOKEN_RE) || []).map((x) => x.toLowerCase());
    out.push(...w.map((x) => "w:" + x));
    for (let i = 0; i < w.length - 1; i++) out.push("b:" + w[i] + "_" + w[i + 1]);
  }
  if (char) {
    const s = " " + text.toLowerCase().replace(/<\w+>/g, "#") + " ";
    for (let n = charN[0]; n <= charN[1]; n++) for (let i = 0; i + n <= s.length; i++) out.push("c:" + s.slice(i, i + n));
  }
  return out;
}

export function tfidfVectors(texts, { dim = 512, mode = "tfidf" } = {}) {
  const opts = mode === "tfidf-char" ? { word: false, char: true, charN: [2, 4] } : { word: true, char: true };
  const docs = texts.map((t) => terms(t, opts));
  const df = new Map();
  for (const d of docs) for (const t of new Set(d)) df.set(t, (df.get(t) || 0) + 1);
  const N = texts.length;
  const vectors = docs.map((d) => {
    const tf = new Map(); for (const t of d) tf.set(t, (tf.get(t) || 0) + 1);
    const v = new Float32Array(dim);
    for (const [t, c] of tf) {
      const idf = Math.log((1 + N) / (1 + df.get(t))) + 1;
      const w = (1 + Math.log(c)) * idf * (t.startsWith("c:") ? 0.5 : 1);
      const h = hash(t); v[h % dim] += (h & 0x80000000 ? -1 : 1) * w;
    }
    let n = 0; for (let i = 0; i < dim; i++) n += v[i] * v[i]; n = Math.sqrt(n) || 1;
    for (let i = 0; i < dim; i++) v[i] /= n;
    return v;
  });
  const vocab = [...df.entries()].filter(([t]) => t.startsWith("w:")).sort((a, b) => b[1] - a[1]).slice(0, 50).map(([t]) => t.slice(2));
  return { vectors, vocab };
}

export const dot = (a, b) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * b[i]; return s; };
export const cosDist = (a, b) => 1 - dot(a, b);
export function mean(vs) {
  const m = new Float32Array(vs[0].length);
  for (const v of vs) for (let i = 0; i < m.length; i++) m[i] += v[i];
  let n = 0; for (let i = 0; i < m.length; i++) n += m[i] * m[i]; n = Math.sqrt(n) || 1;
  for (let i = 0; i < m.length; i++) m[i] /= n;
  return m;
}
