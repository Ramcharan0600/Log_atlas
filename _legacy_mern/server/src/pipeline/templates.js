// Drain-style template miner: fixed-depth prefix tree (length -> first token) with similarity threshold.
export class TemplateMiner {
  constructor({ simTh = 0.5, depthTokens = 1 } = {}) { this.simTh = simTh; this.depthTokens = depthTokens; this.tree = new Map(); this.templates = []; }
  key(toks) { const head = toks.slice(0, this.depthTokens).map((t) => (/\d|^</.test(t) ? "<*>" : t)); return toks.length + "|" + head.join(" "); }
  add(msg) {
    const toks = msg.split(" ").filter(Boolean);
    const k = this.key(toks);
    if (!this.tree.has(k)) this.tree.set(k, []);
    const bucket = this.tree.get(k);
    let best = null, bestSim = -1;
    for (const t of bucket) {
      let same = 0; for (let i = 0; i < toks.length; i++) if (t.tokens[i] === toks[i] || t.tokens[i] === "<*>") same++;
      const sim = same / Math.max(toks.length, 1);
      if (sim > bestSim) { best = t; bestSim = sim; }
    }
    if (best && bestSim >= this.simTh) {
      for (let i = 0; i < toks.length; i++) if (best.tokens[i] !== toks[i]) best.tokens[i] = "<*>";
      best.count++; return best.id;
    }
    const t = { id: this.templates.length + 1, tokens: [...toks], count: 1 };
    bucket.push(t); this.templates.push(t); return t.id;
  }
}

export function mineTemplates(normalized, opts) {
  const m = new TemplateMiner(opts);
  const ids = normalized.map((s) => m.add(s));
  const info = {};
  for (const t of m.templates) {
    const text = t.tokens.join(" ");
    info[t.id] = { template: text, count: t.count, params: [...new Set(text.match(/<[A-Z*]+>/g) || [])] };
  }
  return { ids, info };
}

// Loghub grouping accuracy: a message is correct iff its predicted group equals its true group exactly.
export function groupingAccuracy(pred, truth) {
  const pg = new Map(), tg = new Map();
  pred.forEach((p, i) => { if (!pg.has(p)) pg.set(p, []); pg.get(p).push(i); });
  truth.forEach((t, i) => { if (!tg.has(t)) tg.set(t, new Set()); tg.get(t).add(i); });
  let correct = 0;
  for (const idx of pg.values()) {
    const ts = new Set(idx.map((i) => truth[i]));
    if (ts.size === 1) { const g = tg.get([...ts][0]); if (g.size === idx.length) correct += idx.length; }
  }
  return correct / Math.max(pred.length, 1);
}
