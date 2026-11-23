"""Log template extraction with Drain3 (fixed-depth parse tree) + a regex-only baseline for comparison."""
from __future__ import annotations

import time
from collections import Counter, defaultdict

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


def mine_templates(messages: list[str], sim_th: float = 0.5, depth: int = 4, max_children: int = 100) -> tuple[list[int], dict[int, dict]]:
    """Run Drain3 over normalized messages (streaming, in order).

    Returns (template id per message, {template_id: {template, count, examples, parameters}}).
    Template text is read *after* the full pass, because Drain generalises templates as it sees more lines.
    """
    cfg = TemplateMinerConfig()
    cfg.drain_sim_th = sim_th
    cfg.drain_depth = max(depth, 3)
    cfg.drain_max_children = max_children
    cfg.profiling_enabled = False
    cfg.snapshot_interval_minutes = 10 ** 6
    cfg.parametrize_numeric_tokens = False
    miner = TemplateMiner(config=cfg)
    ids: list[int] = []
    for m in messages:
        ids.append(miner.add_log_message(m)["cluster_id"])
    counts = Counter(ids)
    info: dict[int, dict] = {}
    examples: dict[int, list[str]] = defaultdict(list)
    for tid, m in zip(ids, messages):
        if len(examples[tid]) < 3 and m not in examples[tid]:
            examples[tid].append(m)
    for tid, n in counts.items():
        tpl = miner.drain.id_to_cluster[tid].get_template()
        params: list[list[str]] = []
        for ex in examples[tid][:3]:
            try:
                p = miner.extract_parameters(tpl, ex, exact_matching=False)
                params.append([x.value for x in p] if p else [])
            except Exception:  # parameter extraction is best-effort
                params.append([])
        info[tid] = {"template": tpl, "count": n, "examples": examples[tid], "parameters": params}
    return ids, info


def regex_baseline(messages: list[str]) -> tuple[list[int], dict[int, dict]]:
    """Baseline: the regex-normalized message *is* the template (no generalisation across wording variants)."""
    index: dict[str, int] = {}
    ids = [index.setdefault(m, len(index)) for m in messages]
    counts = Counter(ids)
    return ids, {i: {"template": m, "count": counts[i]} for m, i in index.items()}


def grouping_accuracy(pred: list[int], truth: list) -> float:
    """Loghub 'grouping accuracy': share of logs whose predicted group equals exactly their ground-truth group."""
    pg: dict = defaultdict(set)
    tg: dict = defaultdict(set)
    for i, (p, t) in enumerate(zip(pred, truth)):
        pg[p].add(i)
        tg[t].add(i)
    ok = sum(len(s) for s in pg.values() if s == tg[truth[next(iter(s))]])
    return ok / len(pred) if pred else 0.0


def compare_template_methods(norm_messages: list[str], truth: list | None, sim_th: float = 0.5) -> dict:
    out = {}
    for name, fn in (("drain3", lambda m: mine_templates(m, sim_th)), ("regex_only", regex_baseline)):
        t0 = time.perf_counter()
        ids, info = fn(norm_messages)
        dt = time.perf_counter() - t0
        row = {"n_templates": len(info), "runtime_s": round(dt, 4), "logs_per_s": round(len(norm_messages) / dt) if dt else None}
        if truth is not None:
            row["grouping_accuracy"] = round(grouping_accuracy(ids, truth), 4)
        out[name] = row
    return out
