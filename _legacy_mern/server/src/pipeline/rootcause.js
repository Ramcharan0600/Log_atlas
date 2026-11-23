// Evidence-based POTENTIAL root causes. Never claims confirmation; labels evidence strength.
export const DISCLAIMER = "This is a POTENTIAL root cause inferred statistically from log evidence. It is not confirmed; verify with metrics, traces and system owners before acting.";

const KB = [
  [["database", "db ", "sql", "jdbc", "postgres", "mysql", "mongo", "connection pool", "pool exhausted"], "Database connectivity / capacity",
    ["Check database availability and failover status.", "Inspect connection pool usage and limits.", "Review database CPU, memory and slow-query logs.", "Check network latency between app and DB."]],
  [["timeout", "timed out", "deadline"], "Upstream latency / timeouts", ["Identify the upstream dependency that is timing out.", "Review network latency and packet loss.", "Check timeout and retry configuration."]],
  [["out of memory", "outofmemory", "oom", "heap", "memory"], "Memory exhaustion", ["Check container/host memory limits and usage trend.", "Inspect heap dumps / GC logs.", "Look for leaks introduced by recent deployments."]],
  [["disk", "no space", "quota", "filesystem"], "Storage exhaustion", ["Check disk usage on affected hosts.", "Review log rotation and temp-file cleanup."]],
  [["refused", "unreachable", "dns", "resolve", "network"], "Network / service discovery", ["Verify the target service is running and listening.", "Check DNS and service discovery.", "Review firewall / security group changes."]],
  [["auth", "permission", "denied", "unauthorized", "forbidden", "token", "certificate", "password"], "Authentication / authorization", ["Check credential / certificate expiry.", "Review recent permission changes.", "Inspect identity provider health."]],
  [["nullpointer", "null", "typeerror", "exception", "traceback"], "Application code defect", ["Inspect stack traces of representative logs.", "Correlate onset with recent deployments.", "Reproduce with the failing input in staging."]],
  [["500", "502", "503", "504", "bad gateway", "unavailable"], "Service unavailability", ["Check health of backend instances behind the load balancer.", "Review autoscaling events and restarts."]],
];

export function categorize(text) {
  const low = text.toLowerCase();
  for (const [kws, cat, steps] of KB) if (kws.some((k) => low.includes(k))) return [cat, steps];
  return ["Unclassified error pattern", ["Review representative logs and the extracted template.", "Correlate onset with deployments and infrastructure changes."]];
}

const hhmm = (d) => d.toISOString().slice(11, 16);

export function buildInsights(clusters, anomalies, max = 8) {
  const errC = clusters.filter((c) => (c.levels.ERROR || 0) + (c.levels.FATAL || 0) > 0).sort((a, b) => b.priority_score - a.priority_score);
  return errC.slice(0, max).map((c) => {
    const [cat, steps] = categorize(c.template + " " + c.representatives.slice(0, 2).join(" "));
    const ev = []; let strength = 0;
    ev.push({ type: "observed", text: `${c.size.toLocaleString()} related log entries grouped into this cluster.` }); if (c.size >= 20) strength++;
    if (c.first_seen) ev.push({ type: "observed", text: `The cluster began at approximately ${c.first_seen.toISOString().slice(0, 16).replace("T", " ")} and last occurred ${hhmm(c.last_seen)}.` });
    if (c.trend_ratio > 1.5) { ev.push({ type: "statistical", text: `Error frequency increased ${Math.round(100 * (c.trend_ratio - 1))}% in the latter half of the window.` }); strength++; }
    const svcs = Object.keys(c.services);
    if (svcs.length > 1) { ev.push({ type: "observed", text: `${svcs.length} services experienced similar failures: ${svcs.slice(0, 5).join(", ")}.` }); strength++; }
    ev.push({ type: "observed", text: `Dominant template: "${c.template.slice(0, 140)}".` });
    for (const a of anomalies.filter((a) => a.cluster_key === c.cluster_key).slice(0, 3)) { ev.push({ type: "model", text: a.reason }); strength++; }
    const timeline = [], preceding = [];
    if (c.first_seen) {
      for (const o of clusters) {
        const dt = c.first_seen - (o.first_seen || 0);
        if (o.cluster_key !== c.cluster_key && o.first_seen && dt > 0 && dt <= 600e3 && (o.levels.INFO || 0) < o.size) preceding.push(o);
      }
      preceding.sort((a, b) => a.first_seen - b.first_seen).slice(0, 4).forEach((o) => {
        timeline.push({ time: o.first_seen.toISOString(), event: `Preceding: ${o.name} (${o.size} events)` });
        ev.push({ type: "statistical", text: `Preceded by '${o.name}' starting ${hhmm(o.first_seen)} — possible upstream trigger.` });
      });
      if (preceding.length) strength++;
      timeline.push({ time: c.first_seen.toISOString(), event: `First occurrence: ${c.name}` }, { time: c.last_seen.toISOString(), event: "Last occurrence" });
    }
    return {
      title: `${cat}: ${c.name}`,
      hypothesis: `Potential root cause: ${cat.toLowerCase()} affecting ${svcs.slice(0, 3).join(", ") || "unknown services"}.`,
      summary: c.summary.text, evidence: ev,
      confidence: strength >= 4 ? "Strong evidence" : strength >= 2 ? "Moderate evidence" : "Limited evidence",
      related_clusters: [c.cluster_key, ...c.related.slice(0, 3).map((r) => r.cluster_key), ...preceding.slice(0, 2).map((o) => o.cluster_key)],
      timeline, recommendations: [...steps, ...(c.first_seen ? ["Inspect recent deployments around the onset time."] : [])], disclaimer: DISCLAIMER,
    };
  });
}
