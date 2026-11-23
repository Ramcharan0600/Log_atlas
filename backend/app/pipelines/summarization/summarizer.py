"""Hybrid summarization: Layer 1 deterministic rule-based text from verified statistics; Layer 2 optional LLM rewrite.

The LLM only receives a small structured fact sheet (never raw logs), and its answer is rejected (falling back to Layer 1)
if it contains a number that is not present in the fact sheet.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

log = logging.getLogger(__name__)


def facts_for(c: dict) -> dict:
    return {
        "cluster_name": c["name"], "events": c["size"], "highest_severity": c["severity"], "priority": c["priority"],
        "template": c["template"][:200], "services": list(c["services"])[:5], "first_seen": c["first_seen"].isoformat() if c["first_seen"] else None,
        "last_seen": c["last_seen"].isoformat() if c["last_seen"] else None, "keywords": c["keywords"][:6], "anomalous": c["is_anomalous"],
        "trend_ratio_second_vs_first_half": round(c["trend_ratio"], 2),
    }


def rule_summary(c: dict) -> str:
    parts = [f"{c['size']:,} log events share the pattern \"{c['template'][:110]}\"."]
    if c["services"]:
        top = list(c["services"].items())[:3]
        parts.append("Mostly from " + ", ".join(f"{s} ({n})" for s, n in top) + ".")
    parts.append(f"Highest severity band: {c['severity']}; priority: {c['priority']}.")
    if c["first_seen"]:
        parts.append(f"Observed between {c['first_seen']:%Y-%m-%d %H:%M} and {c['last_seen']:%Y-%m-%d %H:%M}.")
    if c["trend_ratio"] > 1.5:
        parts.append(f"Frequency in the second half of the window was {c['trend_ratio']:.1f}x the first half.")
    if c["is_anomalous"]:
        parts.append("Anomaly detectors flagged this cluster.")
    return " ".join(parts)


def _numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", s.replace(",", "")))


def llm_enhance(summary: str, c: dict, provider: str, api_key: str, model: str = "", timeout: float = 20.0) -> tuple[str, str]:
    """Returns (text, source) where source is 'rule' or 'llm:<provider>'. Any failure => rule summary."""
    if not provider or not api_key:
        return summary, "rule"
    facts = facts_for(c)
    prompt = ("Rewrite the following verified facts as 2-3 clear sentences for an on-call engineer. Use ONLY the facts provided. "
              "Do not add numbers, services, causes or recommendations that are not in the facts. Do not claim a root cause is confirmed.\n"
              f"FACTS: {json.dumps(facts)}\nBASELINE SUMMARY: {summary}")
    try:
        if provider == "openai":
            r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=timeout, headers={"Authorization": f"Bearer {api_key}"},
                           json={"model": model or "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 220})
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
        elif provider == "huggingface":  # OpenAI-compatible Hugging Face router; `model` is required (e.g. an instruct model id)
            if not model:
                return summary, "rule"
            r = httpx.post("https://router.huggingface.co/v1/chat/completions", timeout=timeout, headers={"Authorization": f"Bearer {api_key}"},
                           json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 220})
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
        elif provider == "gemini":
            m = model or "gemini-1.5-flash"
            r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent", timeout=timeout, headers={"x-goog-api-key": api_key},
                           json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 220}})
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            return summary, "rule"
        allowed = _numbers(json.dumps(facts) + summary)
        if not text or not _numbers(text) <= allowed:
            log.warning("LLM summary rejected (introduced unverified numbers); using rule-based summary")
            return summary, "rule"
        return text, f"llm:{provider}"
    except Exception as e:  # noqa: BLE001 - never fail the analysis because the optional LLM failed
        log.warning("LLM enhancement failed (%s); using rule-based summary", type(e).__name__)
        return summary, "rule"
