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


def read_records(data: bytes, filename: str) -> ReadResult:
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
