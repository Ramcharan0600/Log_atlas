"""Normalization (typed placeholders for variable fields), noise reduction and sensitive-data masking."""
from __future__ import annotations

import re

# (name, pattern, replacement) - applied in order; order matters (UUID/URL/IP:port before bare numbers)
RULES: list[tuple[str, re.Pattern, str]] = [
    ("uuid", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<UUID>"),
    ("url", re.compile(r"\bhttps?://[^\s\"']+"), "<URL>"),
    ("ip_port", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{1,5}\b"), "<IP>:<PORT>"),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    ("datetime", re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"), "<TIMESTAMP>"),
    ("time", re.compile(r"\b\d{1,2}:\d{2}:\d{2}(?:\.\d+)?\b"), "<TIME>"),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<DATE>"),
    ("hex", re.compile(r"\b0x[0-9a-f]+\b", re.I), "<HEX>"),
    ("blk", re.compile(r"\bblk_-?\d+\b"), "<BLK>"),
    ("path", re.compile(r"(?<![\w<])(?:/[\w.@-]+){2,}/?"), "<PATH>"),
    ("port", re.compile(r"\bport[ =:]+\d{2,5}\b", re.I), "port <PORT>"),
    ("measure", re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s|sec|seconds|min|MB|KB|GB|bytes|%)(?!\w)", re.I), "<NUM>"),
    ("id_after_kw", re.compile(r"\b(user|id|session|order|account|txn|job|pid|tid|thread)[ =:#]+\d+\b", re.I), r"\1 <ID>"),
    ("longnum", re.compile(r"\b\d{4,}\b"), "<ID>"),
    ("num", re.compile(r"(?<![<\w])\d+(?:\.\d+)?(?![\w>])"), "<NUM>"),
]
RULE_NAMES = [r[0] for r in RULES]
ERROR_KEYWORDS = ("error", "fail", "exception", "timeout", "refused", "denied", "fatal", "critical", "unavailable", "crash", "oom", "killed", "panic", "deadlock")

DEFAULT_PREPROCESS = {"lowercase": False, "keep_stack_trace": False, "max_length": 500, "disabled_rules": []}


def normalize(message: str, cfg: dict | None = None) -> str:
    """Replace variable fields with placeholders, preserving error keywords and the message structure.

    >>> normalize("Connection timeout for server 192.168.1.15 at 10:30:22")
    'Connection timeout for server <IP> at <TIME>'
    >>> normalize("Database connection failed for user 1042")
    'Database connection failed for user <ID>'
    """
    c = {**DEFAULT_PREPROCESS, **(cfg or {})}
    t = message if c["keep_stack_trace"] else message.split("\n", 1)[0]
    disabled = set(c["disabled_rules"])
    for name, rx, repl in RULES:
        if name not in disabled:
            t = rx.sub(repl, t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"(<NUM>[ ,]*){2,}", "<NUM> ", t)
    t = re.sub(r"([=\-*_#])\1{3,}", r"\1", t).strip()
    if c["lowercase"]:
        t = re.sub(r"(?<!<)\b[A-Za-z]+\b(?!>)", lambda m: m.group(0).lower(), t)
    return t[: int(c["max_length"])]


# ---- sensitive information masking -------------------------------------------------------------
MASK_RULES: dict[str, tuple[re.Pattern, str]] = {
    "email": (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "<EMAIL>"),
    "phone": (re.compile(r"(?<![\w.:-])(?:\+?\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}\b"), "<PHONE>"),
    "token": (re.compile(r"(?i)\b(bearer|token|jwt|authorization|auth)([=: ]+)(?!<)[A-Za-z0-9._~+/=-]{12,}"), r"\1\2<TOKEN>"),
    "password": (re.compile(r"(?i)\b(password|passwd|pwd|secret)(\s*[=:]\s*)\S+"), r"\1\2<REDACTED>"),
    "apikey": (re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret[_-]?key|apikey)(\s*[=:]\s*)\S+|\b(?:sk|pk|AKIA)[-_A-Za-z0-9]{16,}\b"), r"\1\2<API_KEY>"),
    "ip": (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<MASKED_IP>"),
    "identifier": (re.compile(r"(?i)\b(user(?:name)?|uid|account)([=: ]+)(?!<)[\w.@-]+"), r"\1\2<MASKED_ID>"),
}


def parse_mask_rules(spec: str | list[str] | None) -> list[str]:
    if spec is None:
        return []
    items = spec if isinstance(spec, list) else str(spec).split(",")
    items = [i.strip().lower() for i in items if i.strip()]
    return [] if "none" in items else [i for i in items if i in MASK_RULES]


def mask_sensitive(text: str, rules: list[str]) -> str:
    for r in rules:
        rx, repl = MASK_RULES[r]
        text = rx.sub(repl, text)
    return text
