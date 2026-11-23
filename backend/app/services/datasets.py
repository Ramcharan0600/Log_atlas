"""Dataset management: bundled synthetic demos (clearly marked) and real public Loghub datasets downloaded on demand.

Loghub URLs were verified reachable (HTTP 200) at implementation time:
  https://raw.githubusercontent.com/logpai/loghub/master/<Name>/<Name>_2k.log          (raw logs)
  https://raw.githubusercontent.com/logpai/loghub/master/<Name>/<Name>_2k.log_structured.csv  (ground-truth EventId per line)
"""
from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.models import UploadedFile

LOGHUB = "https://raw.githubusercontent.com/logpai/loghub/master"
LICENSE_LOGHUB = "Research/academic use; see https://github.com/logpai/loghub for terms"

# name -> metadata. kind: 'bundled' (shipped in repo, synthetic) | 'loghub' (downloaded, real)
CATALOG: dict[str, dict] = {
    "Linux (Loghub 2k)": dict(kind="loghub", dir="Linux", lines=2000, labels="template (EventId)", format="syslog", description="Real Linux system log (syslog) sample"),
    "Apache (Loghub 2k)": dict(kind="loghub", dir="Apache", lines=2000, labels="template (EventId)", format="apache_error", description="Real Apache web-server error log sample"),
    "HDFS (Loghub 2k)": dict(kind="loghub", dir="HDFS", lines=2000, labels="template (EventId)", format="hdfs", description="Real Hadoop Distributed File System log sample"),
    "OpenSSH (Loghub 2k)": dict(kind="loghub", dir="OpenSSH", lines=2000, labels="template (EventId)", format="syslog", description="Real OpenSSH server log sample (auth failures, scans)"),
    "BGL (Loghub 2k)": dict(kind="loghub", dir="BGL", lines=2000, labels="template (EventId) + alert/normal anomaly label", format="bgl",
                            description="Real Blue Gene/L supercomputer log sample with per-line alert labels"),
    "HealthApp (Loghub 2k)": dict(kind="loghub", dir="HealthApp", lines=2000, labels="template (EventId)", format="healthapp", description="Real mobile health-app log sample"),
    "Synthetic: application service log": dict(kind="bundled", file="app_service.log", lines=6000, labels="none", format="service_bracketed",
                                               description="Synthetic multi-service app log with an injected DB-pool outage (demo)"),
    "Synthetic: Linux syslog": dict(kind="bundled", file="linux_syslog.log", labels="none", format="syslog", description="Synthetic syslog (demo)"),
    "Synthetic: Nginx access log": dict(kind="bundled", file="nginx_access.log", labels="none", format="apache_nginx_access", description="Synthetic access log (demo)"),
    "Synthetic: labelled events (JSONL)": dict(kind="bundled", file="labeled_events.jsonl", lines=6000, labels="template labels", format="jsonl",
                                               description="Synthetic JSONL with exact cluster ground truth (demo / test)"),
    "Synthetic: labelled anomalies (CSV)": dict(kind="bundled", file="labeled_anomaly.csv", lines=6000, labels="normal/anomaly", format="csv",
                                                description="Synthetic CSV with injected anomalies and labels (demo / test)"),
}


class DatasetError(RuntimeError):
    pass


def catalog_view(db) -> list[dict]:
    st = get_settings()
    loaded = {f.dataset_name: f.file_id for f in db.scalars(select(UploadedFile).where(UploadedFile.dataset_name.is_not(None)))}
    out = []
    for name, m in CATALOG.items():
        out.append({"name": name, "source": "Loghub (real, downloaded on demand)" if m["kind"] == "loghub" else "Bundled synthetic (demo data)",
                    "is_synthetic": m["kind"] == "bundled", "license": LICENSE_LOGHUB if m["kind"] == "loghub" else "MIT (this repository)",
                    "labels": m["labels"], "format": m["format"], "lines": m.get("lines"), "description": m["description"], "loaded_file_id": loaded.get(name),
                    "available_offline": m["kind"] == "bundled" or (Path(st.dataset_dir) / m.get("dir", "") / f"{m.get('dir', '')}_2k.log").exists()})
    return out


def _get(client: httpx.Client, url: str) -> bytes:
    try:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.content
    except httpx.HTTPError as e:
        raise DatasetError(f"Could not download dataset ({type(e).__name__}). Check internet access and try again.") from e


def load_dataset(db, name: str) -> UploadedFile:
    if name not in CATALOG:
        raise DatasetError("Unknown dataset")
    m, st = CATALOG[name], get_settings()
    existing = db.scalar(select(UploadedFile).where(UploadedFile.dataset_name == name))
    if existing and Path(existing.stored_path).exists():
        return existing
    dest = Path(st.upload_dir)
    labels_path = None
    if m["kind"] == "bundled":
        src = Path(st.sample_dir) / m["file"]
        if not src.exists():
            raise DatasetError("Bundled sample file is missing")
        target = dest / f"sample_{m['file']}"
        shutil.copy(src, target)
        fname = m["file"]
    else:
        d = m["dir"]
        ddir = Path(st.dataset_dir) / d
        ddir.mkdir(parents=True, exist_ok=True)
        raw, structured = ddir / f"{d}_2k.log", ddir / f"{d}_2k.log_structured.csv"
        with httpx.Client(timeout=60) as client:
            if not raw.exists():
                raw.write_bytes(_get(client, f"{LOGHUB}/{d}/{d}_2k.log"))
            if not structured.exists():
                structured.write_bytes(_get(client, f"{LOGHUB}/{d}/{d}_2k.log_structured.csv"))
        n_raw = sum(1 for l in raw.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip())
        rows = list(csv.DictReader(io.StringIO(structured.read_text(encoding="utf-8", errors="replace"))))
        if len(rows) != n_raw:
            raise DatasetError(f"Dataset files are inconsistent ({n_raw} raw lines vs {len(rows)} labelled rows); refusing to attach ground truth")
        labels_path = ddir / "labels.json"
        labels_path.write_text(json.dumps([r["EventId"] for r in rows]))
        target = dest / f"dataset_{d}_2k.log"
        shutil.copy(raw, target)
        fname = f"{d}_2k.log"
    f = UploadedFile(filename=fname, stored_path=str(target), size_bytes=target.stat().st_size, dataset_name=name, is_synthetic=m["kind"] == "bundled",
                     labels_path=str(labels_path) if labels_path else None)
    db.add(f)
    db.commit()
    return f
