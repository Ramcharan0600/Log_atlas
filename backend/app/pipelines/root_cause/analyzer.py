"""Evidence-based POTENTIAL root-cause hypotheses. Never claims confirmation; labels evidence strength, not probability."""
from __future__ import annotations

DISCLAIMER = ("This is a POTENTIAL root cause inferred statistically from log evidence. It is not confirmed; "
              "verify with metrics, traces and system owners before acting.")

# (keywords, category, investigation steps) - first match wins; keyword lists are intentionally transparent.
KB = [
    (["database", " db ", "sql", "jdbc", "postgres", "mysql", "mongo", "connection pool", "pool exhausted", "deadlock"], "Database connectivity / capacity",
     ["Check database availability and failover status.", "Inspect connection pool usage and limits.", "Review database CPU, memory and slow-query logs.", "Check network latency between application and database."]),
    (["out of memory", "outofmemory", "oom", "heap", "memory", "alloc"], "Memory exhaustion",
     ["Check container/host memory limits and usage trend.", "Inspect heap dumps / GC logs.", "Look for leaks introduced by recent deployments."]),
    (["disk", "no space", "quota", "filesystem", "i/o error"], "Storage exhaustion / I-O failure",
     ["Check disk usage and I/O health on affected hosts.", "Review log rotation and temp-file cleanup."]),
    (["refused", "unreachable", "dns", "resolve", "network", "socket", "connection reset"], "Network / service discovery",
     ["Verify the target service is running and listening.", "Check DNS and service discovery.", "Review firewall / security-group changes."]),
    (["auth", "permission", "denied", "unauthorized", "forbidden", "token", "certificate", "password", "login"], "Authentication / authorization",
     ["Check credential / certificate expiry.", "Review recent permission changes.", "Inspect identity-provider health and brute-force indicators."]),
    (["timeout", "timed out", "deadline", "slow"], "Upstream latency / timeouts",
     ["Identify the upstream dependency that is timing out.", "Review network latency and packet loss.", "Check timeout and retry configuration."]),
    (["nullpointer", "null", "typeerror", "exception", "traceback", "segfault"], "Application code defect",
     ["Inspect stack traces of representative logs.", "Correlate onset with recent deployments.", "Reproduce with the failing input in staging."]),
    (["500", "502", "503", "504", "bad gateway", "unavailable"], "Service unavailability",
     ["Check health of backend instances behind the load balancer.", "Review autoscaling events and restarts."]),
    (["parity", "ecc", "machine check", "hardware", "kernel panic", "dtlb"], "Hardware / kernel fault",
     ["Inspect hardware diagnostics (ECC, parity, machine-check) for the affected nodes.", "Check whether failures concentrate on specific hosts/racks."]),
]


def categorize(text: str) -> tuple[str, list[str]]:
    low = f" {text.lower()} "
    for kws, cat, steps in KB:
        if any(k in low for k in kws):
            return cat, steps
    return "Unclassified error pattern", ["Review representative logs and the extracted template.", "Correlate onset with deployments and infrastructure changes."]


def _hhmm(d) -> str:
    return d.strftime("%H:%M")


def build_insights(clusters: list[dict], anomalies: list[dict], max_insights: int = 8) -> list[dict]:
    """clusters: dicts from the cluster-analysis step (needs levels, template, services, first/last_seen, trend_ratio, related, summary...)."""
    # only clusters where errors are a meaningful share of the events (mixed benign clusters would yield spurious hypotheses)
    err = [c for c in clusters if (c["levels"].get("ERROR", 0) + c["levels"].get("FATAL", 0)) >= max(1, 0.2 * c["size"])]
    err.sort(key=lambda c: -c["priority_score"])
    out = []
    for c in err[:max_insights]:
        cat, steps = categorize(c["template"])
        if cat.startswith("Unclassified"):
            cat, steps = categorize(" ".join(c["representatives"][:2]))
        ev: list[dict] = []
        strength = 0
        ev.append({"type": "observed", "text": f"{c['size']:,} related log entries grouped into this cluster."})
        if c["size"] >= 20:
            strength += 1
        if c["first_seen"]:
            ev.append({"type": "observed", "text": f"The cluster began at approximately {c['first_seen']:%Y-%m-%d %H:%M} and last occurred {c['last_seen']:%Y-%m-%d %H:%M}."})
        if c["trend_ratio"] > 1.5:
            ev.append({"type": "statistical", "text": f"Event frequency in the latter half of the window was {c['trend_ratio']:.1f}x the first half (+{(c['trend_ratio'] - 1) * 100:.0f}%)."})
            strength += 1
        svcs = list(c["services"])
        if len(svcs) > 1:
            ev.append({"type": "observed", "text": f"{len(svcs)} services experienced similar failures: {', '.join(svcs[:5])}."})
            strength += 1
        ev.append({"type": "observed", "text": f"Dominant template: \"{c['template'][:140]}\"."})
        for a in [a for a in anomalies if a.get("cluster_key") == c["cluster_key"]][:3]:
            ev.append({"type": "model", "text": a["reason"]})
            strength += 1
        timeline, preceding = [], []
        if c["first_seen"]:
            for o in clusters:
                if o["cluster_key"] == c["cluster_key"] or not o["first_seen"]:
                    continue
                dt = (c["first_seen"] - o["first_seen"]).total_seconds()
                if 0 < dt <= 600 and o["levels"].get("INFO", 0) < o["size"]:
                    preceding.append(o)
            preceding.sort(key=lambda o: o["first_seen"])
            for o in preceding[:4]:
                timeline.append({"time": o["first_seen"].isoformat(), "event": f"Preceding: {o['name']} ({o['size']} events)"})
                ev.append({"type": "statistical", "text": f"Preceded by '{o['name']}' starting {_hhmm(o['first_seen'])}; temporal ordering only, possible upstream trigger."})
            if preceding:
                strength += 1
            timeline.append({"time": c["first_seen"].isoformat(), "event": f"First occurrence: {c['name']}"})
            timeline.append({"time": c["last_seen"].isoformat(), "event": "Last occurrence"})
        out.append({
            "cluster_key": c["cluster_key"],
            "title": f"{cat}: {c['name']}",
            "hypothesis": f"Potential root cause: {cat.lower()} affecting {', '.join(svcs[:3]) or 'unknown services'}. Not confirmed.",
            "summary": c["summary"], "evidence": ev,
            "suspected_causes": [cat] + ([f"Upstream trigger candidate: {preceding[0]['name']}"] if preceding else []),
            "confidence": "Strong evidence" if strength >= 4 else "Moderate evidence" if strength >= 2 else "Limited evidence",
            "related_clusters": list(dict.fromkeys([c["cluster_key"]] + [r["cluster_key"] for r in c["related"][:3]] + [o["cluster_key"] for o in preceding[:2]])),
            "timeline": timeline,
            "recommendations": steps + (["Inspect recent deployments and config changes around the onset time."] if c["first_seen"] else []),
            "disclaimer": DISCLAIMER,
        })
    return out
