export const fmtTime = (s?: string | null) => (s ? new Date(s + (s.endsWith("Z") || /[+-]\d\d:?\d\d$/.test(s) ? "" : "Z")).toLocaleString(undefined, { timeZone: "UTC", hour12: false }) + " UTC" : "—");
export const fmtShort = (s: string) => { const d = new Date(s + "Z"); return isNaN(d.getTime()) ? s : d.toISOString().slice(5, 16).replace("T", " "); };
export const fmtNum = (n?: number | null, d = 3) => (n == null || Number.isNaN(n) ? "—" : Number.isInteger(n) ? n.toLocaleString() : n.toFixed(d));
export const pct = (n?: number | null) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
export const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

export const SEV_COLORS: Record<string, string> = { FATAL: "hsl(var(--crit))", ERROR: "hsl(var(--high))", WARN: "hsl(var(--med))", INFO: "hsl(var(--low))", DEBUG: "hsl(var(--dim))", UNKNOWN: "hsl(var(--line))" };
export const KIND_LABEL: Record<string, string> = {
  isolation_forest: "Isolation Forest outlier", new_pattern: "New error pattern", cluster_spike: "Cluster volume spike", severity_shift: "Error-ratio shift",
  rare_template: "Rare error template", component: "Abnormal component", frequency_spike_1min: "Error spike (1 min)", frequency_spike_5min: "Error spike (5 min)", frequency_spike_1h: "Error spike (1 h)",
};
export const kindLabel = (k: string) => KIND_LABEL[k] || k;
