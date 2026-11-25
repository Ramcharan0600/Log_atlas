"""File validation, encoding detection and reading of TXT/LOG/CSV/JSON/JSONL into raw records."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

import chardet

ALLOWED_EXT = ("txt", "log", "csv", "json", "jsonl")
MSG_KEYS = ("message", "msg", "log", "text", "content", "event")


class IngestionError(ValueError):
    """Raised for files that can't be accepted; message is safe to show to end users."""


@dataclass
class RawRecord:
    line_no: int
    text: str
    fields: dict | None = None  # structured sources (CSV/JSON)


@dataclass
class ReadResult:
    records: list[RawRecord] = field(default_factory=list)
    encoding: str = "utf-8"
    invalid_lines: int = 0
    structured: bool = False


def file_ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def validate_file(name: str, size: int, max_mb: int = 50) -> None:
    ext = file_ext(name)
    if ext not in ALLOWED_EXT:
        raise IngestionError(f"Unsupported file type '.{ext}'. Allowed: {', '.join(ALLOWED_EXT)}")
    if size == 0:
        raise IngestionError("File is empty")
    if size > max_mb * 1024 * 1024:
        raise IngestionError(f"File exceeds the {max_mb} MB limit")


def decode(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace"), "utf-16"
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if b"\x00" in data[:4096]:
        raise IngestionError("File looks binary, not a text log")
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        enc = chardet.detect(data[:200_000]).get("encoding") or "latin-1"
        try:
            return data.decode(enc), enc.lower()
        except (UnicodeDecodeError, LookupError):
            return data.decode("latin-1"), "latin-1"


def _from_obj(line_no: int, obj: dict) -> RawRecord:
    lower = {str(k).lower(): v for k, v in obj.items()}
    key = next((k for k in MSG_KEYS if k in lower), None)
    return RawRecord(line_no, str(lower[key]) if key else json.dumps(obj, default=str), lower)


def _continuation(line: str) -> bool:
    s = line.lstrip()
    if s.startswith(("Caused by", "Traceback", "... ")) or re.match(r"^at [\w$.<>]+\(", s):
        return True
    return bool(re.match(r"^[ \t]", line)) and not re.match(r"^\d", s)


def merge_multiline(lines: list[str]) -> list[RawRecord]:
    """Stack traces / indented continuation lines are merged into the previous record."""
    out: list[RawRecord] = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if out and _continuation(line):
            out[-1].text += "\n" + line.rstrip()
        else:
            out.append(RawRecord(i, line.rstrip()))
    return out


# Log fields a CSV column can be mapped to, with header names that are auto-suggested for each.
MAPPABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "@timestamp", "date", "datetime", "event time", "event_time", "created_at", "logged_at"),
    "level": ("level", "severity", "loglevel", "log_level", "levelname", "priority"),
    "service": ("service", "app", "application", "service_name", "source", "system"),
    "component": ("component", "logger", "module", "class"),
    "host": ("host", "hostname", "server", "node"),
    "ip": ("ip", "client_ip", "remote_addr", "ip_address"),
    "pid": ("pid", "process_id", "process"),
    "thread": ("thread", "thread_id"),
    "request_id": ("request_id", "trace_id", "req_id", "correlation_id"),
    "error_code": ("error_code", "status", "code", "status_code"),
    "message": ("message", "msg", "log", "text", "content", "event", "description", "details"),
    "label": ("label", "anomaly", "is_anomaly", "anomaly_label"),
}


def csv_columns(data: bytes, sample: int = 5) -> dict:
    """Header names, a few sample rows and a suggested field mapping for a CSV file."""
    text, _ = decode(data)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestionError("CSV has no header row")
    headers = [h for h in reader.fieldnames if h is not None]
    rows = []
    for row in reader:
        rows.append({h: (row.get(h) or "")[:200] for h in headers})
        if len(rows) >= sample:
            break
    lower = {h.strip().lower(): h for h in headers}
    suggested = {}
    for target, names in MAPPABLE_FIELDS.items():
        hit = next((lower[n] for n in names if n in lower), None)
        if hit and hit not in suggested.values():
            suggested[target] = hit
    return {"headers": headers, "sample_rows": rows, "suggested_mapping": suggested, "fields": list(MAPPABLE_FIELDS)}


def validate_column_map(mapping: dict, headers: list[str]) -> dict:
    """Keep only known fields mapped to existing, non-empty headers; a message column is mandatory."""
    clean = {}
    for target, header in (mapping or {}).items():
        if target not in MAPPABLE_FIELDS:
            raise IngestionError(f"Unknown field '{target}'")
        if header in (None, ""):
            continue
        if header not in headers:
            raise IngestionError(f"Column '{header}' not found in the CSV")
        clean[target] = header
    if "message" not in clean:
        raise IngestionError("Map a CSV column to 'message': it is the text that gets clustered")
    return clean


def _apply_map(row: dict, column_map: dict) -> dict:
    out = dict(row)
    for target, header in column_map.items():
        if header in row:
            out[target] = row[header]
    return out


def read_records(data: bytes, filename: str, column_map: dict | None = None) -> ReadResult:
    text, enc = decode(data)
    ext = file_ext(filename)
    res = ReadResult(encoding=enc)
    if ext == "csv":
        res.structured = True
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise IngestionError("CSV has no header row")
        for i, row in enumerate(reader, 1):
            if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                continue
            row = {k: v for k, v in row.items() if k is not None}
            if column_map:
                row = _apply_map(row, column_map)
            res.records.append(_from_obj(i, row))
    elif ext in ("json", "jsonl"):
        res.structured = True
        stripped = text.strip()
        if stripped.startswith("["):
            try:
                arr = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise IngestionError(f"Invalid JSON: {e.msg} (line {e.lineno})") from e
            for i, o in enumerate(arr, 1):
                res.records.append(_from_obj(i, o) if isinstance(o, dict) else RawRecord(i, str(o)))
        else:
            for i, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    res.invalid_lines += 1
                    continue
                res.records.append(_from_obj(i, o) if isinstance(o, dict) else RawRecord(i, str(o)))
    else:
        res.records = merge_multiline(text.splitlines())
    return res
