"""Pluggable log parser. Each format is a named regex (+ optional post-processor); unknown lines fall back to heuristics.

Add a format by appending a `LogFormat` to FORMATS - no other code changes needed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.pipelines.ingestion.reader import RawRecord

LEVELS = ["FATAL", "CRITICAL", "ERROR", "WARN", "WARNING", "NOTICE", "INFO", "DEBUG", "TRACE"]
LEVEL_MAP = {"WARNING": "WARN", "CRITICAL": "FATAL", "NOTICE": "INFO", "TRACE": "DEBUG", "SEVERE": "ERROR", "ERR": "ERROR",
             "ALERT": "FATAL", "EMERG": "FATAL", "FAILURE": "ERROR", "FAILED": "ERROR", "WARN": "WARN", "ERROR": "ERROR"}
CANON = {"FATAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"}
LEVEL_RE = re.compile(r"\b(" + "|".join(LEVELS) + r")\b", re.I)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
REQ_RE = re.compile(r"\b(?:req(?:uest)?[_-]?id|trace[_-]?id)[=: ]+([\w-]+)", re.I)
CODE_RE = re.compile(r"\b(?:code|errno|status)[=: ]+(\d{3,5})\b|\b([A-Z]{2,5}-?\d{3,5})\b")
TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?|\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}"
                   r"|\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}|\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}|\d{6} \d{6}|\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+)")
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def parse_timestamp(s) -> datetime | None:
    """Return a naive-UTC datetime or None. Never raises."""
    if s is None or s == "":
        return None
    if isinstance(s, datetime):
        return s.replace(tzinfo=None) if s.tzinfo is None else s.astimezone(timezone.utc).replace(tzinfo=None)
    s = str(s).strip()
    try:
        if re.fullmatch(r"\d{9,10}(\.\d+)?", s):
            return datetime.fromtimestamp(float(s), tz=timezone.utc).replace(tzinfo=None)
        if re.fullmatch(r"\d{12,13}", s):
            return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc).replace(tzinfo=None)
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})\.(\d{2})\.(\d{2})(?:\.(\d+))?", s)  # BGL
        if m:
            g = [int(x) for x in m.groups()[:6]]
            return datetime(*g, int((m.group(7) or "0")[:6].ljust(6, "0")))
        m = re.match(r"^(\d{4})(\d{2})(\d{2})-(\d{1,2}):(\d{2}):(\d{2}):(\d+)$", s)  # HealthApp: 20171223-22:15:29:606
        if m:
            g = [int(x) for x in m.groups()[:6]]
            return datetime(*g, int(m.group(7)[:3].ljust(3, "0")) * 1000)
        m = re.match(r"^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:[.,](\d+))?\s*(Z|[+-]\d{2}:?\d{2})?", s)
        if m:
            g = [int(x) for x in m.groups()[:6]]
            dt = datetime(*g, int((m.group(7) or "0")[:6].ljust(6, "0")))
            tz = m.group(8)
            if tz and tz != "Z":
                sign = 1 if tz[0] == "+" else -1
                digits = tz[1:].replace(":", "")
                dt = dt - sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4]))
            return dt
        m = re.match(r"^(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2})", s)
        if m and m.group(2) in MONTHS:
            return datetime(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)), int(m.group(4)), int(m.group(5)), int(m.group(6)))
        m = re.match(r"^(\w{3})\s+(\d{1,2}) (\d{2}):(\d{2}):(\d{2})", s)
        if m and m.group(1) in MONTHS:
            return datetime(2000, MONTHS[m.group(1)], int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))  # syslog has no year
        m = re.match(r"^(\d{2})(\d{2})(\d{2}) (\d{2})(\d{2})(\d{2})$", s)
        if m:
            g = [int(x) for x in m.groups()]
            return datetime(2000 + g[0], *g[1:])
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def _apache_post(d: dict) -> dict:
    st = int(d.get("status") or 0)
    d["level"] = "ERROR" if st >= 500 else "WARN" if st >= 400 else "INFO"
    d["error_code"] = str(st)
    d["message"] = f"{d.get('method')} {d.get('path')} {st}"
    d["service"] = "web"
    return d


def _bgl_post(d: dict) -> dict:
    d["anomaly_label"] = "normal" if d.pop("alert", "-") == "-" else "anomaly"
    d["service"] = d.get("service")
    return d


@dataclass
class LogFormat:
    name: str
    regex: re.Pattern
    post: Callable[[dict], dict] | None = None
    description: str = ""


FORMATS: list[LogFormat] = [
    LogFormat("apache_nginx_access", re.compile(r'^(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] "(?P<method>\w+) (?P<path>\S+)[^"]*" (?P<status>\d{3}) \S+'), _apache_post,
              "Apache/Nginx combined access log"),
    LogFormat("apache_error", re.compile(r"^\[(?P<timestamp>[^\]]+)\] \[(?:(?P<component>\w+):)?(?P<level>\w+)\](?: \[pid (?P<pid>\d+)(?::tid (?P<thread>\d+))?\])?"
                                         r"(?: \[client (?P<ip>[\d.]+)(?::\d+)?\])? (?P<message>.*)$", re.S), None, "Apache error log"),
    LogFormat("bgl", re.compile(r"^(?P<alert>\S+) (?P<epoch>\d{9,10}) (?P<date>\d{4}\.\d{2}\.\d{2}) (?P<host>\S+) (?P<timestamp>\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+) "
                                r"(?P<node>\S+) (?P<service>\w+) (?P<component>\w+) (?P<level>\w+) (?P<message>.*)$", re.S), _bgl_post, "Blue Gene/L supercomputer log (Loghub)"),
    LogFormat("python_logging", re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,.]\d+) - (?P<component>[\w.]+) - (?P<level>\w+) - (?P<message>.*)$", re.S), None, "Python logging"),
    LogFormat("java_log4j", re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[,.]?\d*)\s+(?P<level>[A-Z]+)\s+\[(?P<thread>[^\]]+)\]\s+(?P<component>[\w.$]+)\s*[-:]\s*(?P<message>.*)$", re.S),
              None, "Java log4j/logback"),
    LogFormat("service_bracketed", re.compile(r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?)\s+\[?(?P<level>[A-Za-z]+)\]?\s+\[?(?P<service>[\w.-]+)\]?(?:\[(?P<pid>\d+)\])?:?\s+(?P<message>.*)$", re.S),
              None, "Application server: timestamp LEVEL [service][pid] message"),
    LogFormat("hdfs", re.compile(r"^(?P<timestamp>\d{6} \d{6}) (?P<pid>\d+) (?P<level>\w+) (?P<component>[\w.$]+): (?P<message>.*)$", re.S), None, "HDFS (Loghub)"),
    LogFormat("healthapp", re.compile(r"^(?P<timestamp>\d{8}-\d{1,2}:\d{2}:\d{2}:\d+)\|(?P<component>[^|]+)\|(?P<pid>\d+)\|(?P<message>.*)$", re.S), None, "Android HealthApp (Loghub)"),
    LogFormat("syslog", re.compile(r"^(?P<timestamp>\w{3}\s+\d{1,2} \d{2}:\d{2}:\d{2}) (?P<host>\S+) (?P<service>[\w./()-]+?)(?:\[(?P<pid>\d+)\])?: (?P<message>.*)$", re.S), None, "Linux syslog"),
]


def detect_format(sample: list[str]) -> str:
    best, best_n = "generic", 0
    for f in FORMATS:
        n = sum(1 for s in sample if f.regex.match(s))
        if n > best_n:
            best, best_n = f.name, n
    return best if best_n >= max(1, len(sample) * 0.3) else "generic"


def normalize_level(level, msg: str) -> str:
    lv = str(level or "").strip().upper()
    if lv in LEVEL_MAP:
        lv = LEVEL_MAP[lv]
    if lv not in CANON:
        m = LEVEL_RE.search(msg or "")
        if m:
            lv = LEVEL_MAP.get(m.group(1).upper(), m.group(1).upper())
        elif re.search(r"exception|fail|fatal|refused|timeout|error", msg or "", re.I):
            lv = "ERROR"
        else:
            lv = "UNKNOWN"
    return lv if lv in CANON else "UNKNOWN"


@dataclass
class ParsedLog:
    line_no: int
    message: str
    timestamp: datetime | None = None
    level: str = "UNKNOWN"
    service: str | None = None
    component: str | None = None
    host: str | None = None
    ip: str | None = None
    pid: str | None = None
    thread: str | None = None
    request_id: str | None = None
    error_code: str | None = None
    cluster_truth: str | None = None
    anomaly_truth: str | None = None
    source: str = ""
    # filled by later stages
    normalized: str = ""
    template_id: int = -1
    cluster_id: int = -1
    anomaly_score: float = 0.0
    is_anomaly: bool = False
    extra: dict = field(default_factory=dict)


_BINARY = {"normal", "anomaly", "anomalous", "0", "1", "true", "false", "-", "ok", "abnormal"}


def _anomaly_value(v) -> str | None:
    s = str(v).strip().lower()
    if s in ("", "none", "nan"):
        return None
    return "normal" if s in ("normal", "0", "false", "-", "ok") else "anomaly"


def parse_record(rec: RawRecord, fmt_hint: str = "generic", source: str = "") -> ParsedLog:
    d: dict = {}
    anomaly_truth = cluster_truth = None
    if rec.fields is not None:
        f = rec.fields
        g = lambda *ks: next((f[k] for k in ks if f.get(k) not in (None, "")), None)  # noqa: E731
        d = dict(timestamp=g("timestamp", "time", "@timestamp", "date", "datetime"), level=g("level", "severity", "loglevel", "levelname"),
                 service=g("service", "app", "application", "service_name"), component=g("component", "logger", "module", "class"),
                 host=g("host", "hostname"), ip=g("ip", "client_ip", "remote_addr"), pid=g("pid", "process_id"), thread=g("thread", "thread_id"),
                 request_id=g("request_id", "trace_id", "req_id"), error_code=g("error_code", "status", "code"), message=rec.text)
        lab = g("label", "anomaly", "is_anomaly", "anomaly_label")
        if lab is not None:
            if str(lab).strip().lower() in _BINARY:
                anomaly_truth = _anomaly_value(lab)
            else:
                cluster_truth = str(lab)
        if g("cluster_label", "template_label", "event_id") is not None:
            cluster_truth = str(g("cluster_label", "template_label", "event_id"))
    else:
        ordered = sorted(FORMATS, key=lambda x: 0 if x.name == fmt_hint else 1)
        for fm in ordered:
            m = fm.regex.match(rec.text)
            if m:
                d = {k: v for k, v in m.groupdict().items() if v is not None}
                if fm.post:
                    d = fm.post(d)
                break
        if not d:
            m = TS_RE.search(rec.text)
            if m:
                d = {"timestamp": m.group(1), "message": re.sub(r"^[\s\-:|\]]+", "", rec.text[m.end():])}
            else:
                d = {"message": rec.text}
        anomaly_truth = d.pop("anomaly_label", None)
    msg = str(d.get("message") if d.get("message") not in (None, "") else rec.text)
    first = msg.split("\n")[0]
    code = d.get("error_code")
    if not code:
        m = CODE_RE.search(first)
        code = (m.group(1) or m.group(2)) if m else None
    ip = d.get("ip")
    if not ip:
        m = IP_RE.search(first)
        ip = m.group(0) if m else None
    rid = d.get("request_id")
    if not rid:
        m = REQ_RE.search(first)
        rid = m.group(1) if m else None
    return ParsedLog(line_no=rec.line_no, message=msg, timestamp=parse_timestamp(d.get("timestamp")), level=normalize_level(d.get("level"), msg),
                     service=_s(d.get("service")), component=_s(d.get("component")), host=_s(d.get("host")), ip=_s(ip), pid=_s(d.get("pid")),
                     thread=_s(d.get("thread")), request_id=_s(rid), error_code=_s(code), cluster_truth=cluster_truth, anomaly_truth=anomaly_truth, source=source)


def _s(v) -> str | None:
    return None if v in (None, "") else str(v)[:160]
