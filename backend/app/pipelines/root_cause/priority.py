"""Transparent, heuristic priority score (0-100) -> Critical / High / Medium / Low.

This is an *explainable heuristic*, not a scientifically validated risk model. Weights are documented in docs/methodology.md.
"""
from __future__ import annotations

import math

WEIGHTS = {"severity": 0.35, "frequency": 0.15, "anomaly": 0.20, "trend": 0.10, "recency": 0.10, "impact": 0.10}
SEV = {"FATAL": 1.0, "ERROR": 0.75, "WARN": 0.4, "INFO": 0.1, "DEBUG": 0.0, "UNKNOWN": 0.2}


def priority_score(level: str, size: int, total: int, anomaly: float, trend_ratio: float, recency: float, n_services: int, total_services: int) -> tuple[float, dict]:
    parts = {
        "severity": SEV.get(level, 0.2),
        "frequency": min(1.0, math.log1p(size) / math.log1p(max(total, 2)) * 1.5),
        "anomaly": float(anomaly),
        "trend": max(0.0, min(1.0, (trend_ratio - 1) / 3)),
        "recency": float(recency),
        "impact": n_services / max(total_services, 1),
    }
    score = 100 * sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
    return round(score, 1), {k: round(v, 3) for k, v in parts.items()}


def priority_label(score: float, level: str) -> str:
    # FATAL alone is not enough for Critical (some systems, e.g. BGL, log FATAL very often): it raises the floor to High
    # and reaches Critical only together with a reasonably high overall score.
    if score >= 70 or (level == "FATAL" and score >= 55):
        return "Critical"
    if score >= 50 or level == "FATAL":
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"


def explain_priority(label: str, level: str, parts: dict, score: float) -> str:
    top = sorted(parts.items(), key=lambda kv: -WEIGHTS[kv[0]] * kv[1])[:3]
    why = ", ".join(f"{k} {v:.2f} (weight {WEIGHTS[k]:.2f})" for k, v in top)
    return (f"{label} priority (score {score}/100, heuristic): dominant factors were {why}. Highest observed severity band: {level}. "
            "The score is a transparent weighted sum for triage and has not been statistically validated.")
