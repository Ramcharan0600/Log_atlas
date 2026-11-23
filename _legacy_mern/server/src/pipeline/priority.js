// Transparent weighted score (0-100) -> Critical / High / Medium / Low.
export const WEIGHTS = { severity: 0.35, frequency: 0.15, anomaly: 0.2, trend: 0.1, recency: 0.1, impact: 0.1 };
const SEV = { FATAL: 1, ERROR: 0.75, WARN: 0.4, INFO: 0.1, DEBUG: 0, UNKNOWN: 0.2 };

export function priorityScore({ level, size, total, anomaly, trendRatio, recency, nServices, totalServices }) {
  const parts = {
    severity: SEV[level] ?? 0.2,
    frequency: Math.min(1, (Math.log1p(size) / Math.log1p(Math.max(total, 2))) * 1.5),
    anomaly, trend: Math.max(0, Math.min(1, (trendRatio - 1) / 3)), recency, impact: nServices / Math.max(totalServices, 1),
  };
  const score = 100 * Object.entries(WEIGHTS).reduce((s, [k, w]) => s + w * parts[k], 0);
  return { score: Math.round(score * 10) / 10, parts };
}

export function priorityLabel(score, level) {
  if (level === "FATAL" || score >= 70) return "Critical";
  if (score >= 50) return "High";
  if (score >= 30) return "Medium";
  return "Low";
}
