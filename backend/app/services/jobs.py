"""Background job execution: read files -> parse -> analyze -> persist. Status/progress are written to the DB for polling."""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from sqlalchemy import insert, select

from app.core.config import get_settings
from app.database.session import SessionLocal
from app.models import Anomaly, AnalysisJob, Cluster, Insight, LogEntry, LogTemplate, ModelExperiment, UploadedFile
from app.pipelines.ingestion.reader import IngestionError, read_records
from app.pipelines.parsing.parser import ParsedLog, detect_format, parse_record
from app.pipelines.preprocessing.normalizer import mask_sensitive, parse_mask_rules
from app.services.analysis import DEFAULT_CONFIG, analyze

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="analysis")
_insert_lock = threading.Lock()


def parse_files(files: list[dict], mask_spec: str | list[str] | None = None) -> tuple[list[ParsedLog], dict]:
    """files: [{name, data(bytes), labels(list|None)}]. Returns (rows, meta). Sensitive values are masked *before* anything is stored."""
    rules = parse_mask_rules(mask_spec)
    rows: list[ParsedLog] = []
    meta = {"files": [], "invalid_lines": 0, "masking": rules}
    for f in files:
        res = read_records(f["data"], f["name"], f.get("column_map"))
        fmt = "structured" if res.structured else detect_format([r.text for r in res.records[:200]])
        labels = f.get("labels")
        if labels is not None and len(labels) != len(res.records):
            labels = None  # misaligned ground truth must never be attached silently
            meta.setdefault("warnings", []).append(f"{f['name']}: ground-truth labels ignored (record count mismatch)")
        for k, rec in enumerate(res.records):
            p = parse_record(rec, fmt, f["name"])
            if labels is not None and k < len(labels) and p.cluster_truth is None:
                p.cluster_truth = str(labels[k])
            if rules:
                p.message = mask_sensitive(p.message, rules)
            rows.append(p)
        meta["files"].append({"name": f["name"], "encoding": res.encoding, "format": fmt, "records": len(res.records), "invalid_lines": res.invalid_lines})
        meta["invalid_lines"] += res.invalid_lines
    if not rows:
        raise IngestionError("No parsable log records found in the uploaded file(s)")
    for r in rows:
        r.service = r.service or r.component or "unknown"
    return rows, meta


def preview_file(path: str, name: str, n: int = 20, labels: list | None = None, column_map: dict | None = None) -> dict:
    data = Path(path).read_bytes()
    res = read_records(data, name, column_map)
    fmt = "structured" if res.structured else detect_format([r.text for r in res.records[:200]])
    sample = [parse_record(r, fmt, name) for r in res.records[:500]]
    parsed_ts = sum(1 for p in sample if p.timestamp)
    levels = {}
    for p in sample:
        levels[p.level] = levels.get(p.level, 0) + 1
    return {"filename": name, "encoding": res.encoding, "detected_format": fmt, "n_records": len(res.records), "invalid_lines": res.invalid_lines,
            "timestamp_parse_rate": round(parsed_ts / len(sample), 3) if sample else 0, "level_distribution_sample": levels,
            "has_ground_truth": bool(labels) or any(p.cluster_truth or p.anomaly_truth for p in sample),
            "rows": [{"line_no": p.line_no, "timestamp": p.timestamp.isoformat() if p.timestamp else None, "level": p.level, "service": p.service,
                      "component": p.component, "message": p.message[:300]} for p in sample[:n]]}


def create_job(db, file_ids: list[int], config: dict) -> AnalysisJob:
    files = db.scalars(select(UploadedFile).where(UploadedFile.file_id.in_(file_ids))).all()
    if not files or len(files) != len(set(file_ids)):
        raise IngestionError("One or more files were not found")
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in config.items() if k in DEFAULT_CONFIG or k in ("disabled_rules", "mask_rules")}}
    job = AnalysisJob(filename=", ".join(f.filename for f in files)[:600], dataset_name=files[0].dataset_name, is_synthetic=any(f.is_synthetic for f in files),
                      file_ids=file_ids, configuration=cfg, status="queued")
    db.add(job)
    db.commit()
    return job


def submit(job_id: int, wait: bool = False) -> None:
    fut = _executor.submit(run_job, job_id)
    if wait:
        fut.result()


def _set(job_id: int, **kw) -> None:
    with SessionLocal() as db:
        db.query(AnalysisJob).filter(AnalysisJob.job_id == job_id).update(kw)
        db.commit()


def run_job(job_id: int) -> None:
    st = get_settings()
    try:
        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            files = db.scalars(select(UploadedFile).where(UploadedFile.file_id.in_(job.file_ids))).all()
            cfg = dict(job.configuration)
            payload = []
            for f in files:
                labels = json.loads(Path(f.labels_path).read_text()) if f.labels_path and Path(f.labels_path).exists() else None
                payload.append({"name": f.filename, "data": Path(f.stored_path).read_bytes(), "labels": labels, "column_map": f.column_map})
            file_objs = {f.file_id: f for f in files}
        _set(job_id, status="running", stage="Parsing logs", progress=0.05, processing_started=datetime.utcnow(), error=None)
        rows, meta = parse_files(payload, cfg.get("mask_rules", st.mask_rules))
        with SessionLocal() as db:
            for f in db.scalars(select(UploadedFile).where(UploadedFile.file_id.in_(list(file_objs)))):
                m = next((x for x in meta["files"] if x["name"] == f.filename), None)
                if m:
                    f.encoding, f.detected_format = m["encoding"], m["format"]
            db.commit()
        _set(job_id, stage="Normalizing", progress=0.15, total_logs=len(rows))
        res = analyze(rows, cfg, lambda p, s: _set(job_id, progress=p, stage=s),
                      {"llm_provider": st.llm_provider, "llm_api_key": st.llm_api_key, "llm_model": st.llm_model})
        _persist(job_id, res, meta)
        _set(job_id, status="completed", stage="Done", progress=1.0, processing_completed=datetime.utcnow(),
             stats={**res["stats"], "invalid_lines": meta["invalid_lines"], "files": meta["files"], "masking": meta["masking"], "evaluation": res["evaluation"]})
    except IngestionError as e:
        log.warning("job %s rejected: %s", job_id, e)
        _set(job_id, status="failed", stage="Failed", error=str(e))
    except Exception as e:  # noqa: BLE001 - job runner boundary: record a safe message, keep details in server logs only
        log.exception("job %s failed", job_id)
        _set(job_id, status="failed", stage="Failed", error=f"Analysis failed ({type(e).__name__}). See server logs for details.")


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _persist(job_id: int, res: dict, meta: dict) -> None:
    rows: list[ParsedLog] = res["rows"]
    with _insert_lock, SessionLocal() as db:
        # replace results if the job is re-run
        for model in (LogEntry, LogTemplate, Cluster, Anomaly, Insight, ModelExperiment):
            db.query(model).filter(model.job_id == job_id).delete()
        base = (db.scalar(select(LogEntry.log_id).order_by(LogEntry.log_id.desc()).limit(1)) or 0) + 1
        for ch_i, chunk in enumerate(_chunks(rows, 5000)):
            off = ch_i * 5000
            db.execute(insert(LogEntry), [dict(
                log_id=base + off + k, job_id=job_id, line_no=r.line_no, timestamp=r.timestamp, severity=r.level, service=r.service, component=r.component, host=r.host,
                ip=r.ip, pid=r.pid, thread=r.thread, request_id=r.request_id, error_code=r.error_code, original_message=r.message[:5000], normalized_message=r.normalized,
                template_id=r.template_id, cluster_id=r.cluster_id, anomaly_flag=r.is_anomaly, anomaly_score=round(r.anomaly_score, 4),
                cluster_truth=r.cluster_truth, anomaly_truth=r.anomaly_truth) for k, r in enumerate(chunk)])
        db.execute(insert(LogTemplate), [dict(job_id=job_id, local_id=tid, template_text=t["template"], occurrence_count=t["count"],
                                              meta={"examples": t.get("examples", []), "parameters": t.get("parameters", [])}) for tid, t in res["templates"].items()])
        for c in res["clusters"]:
            db.add(Cluster(job_id=job_id, local_id=c["cluster_key"], cluster_name=c["name"], cluster_size=c["size"], severity=c["severity"], priority=c["priority"],
                           priority_score=c["priority_score"], first_seen=c["first_seen"], last_seen=c["last_seen"], is_anomalous=c["is_anomalous"], summary=c["summary"],
                           details={k: c[k] for k in ("keywords", "representatives", "template", "services", "levels", "trend", "trend_ratio", "related", "priority_factors",
                                                      "priority_explanation", "summary_source", "n_unique_messages", "template_ids")}))
        for a in res["anomalies"]:
            idx = a["log_idx"]
            db.add(Anomaly(job_id=job_id, log_id=(base + idx[0]) if idx else None, cluster_id=a.get("cluster_key"), kind=a["kind"], anomaly_score=round(a["score"], 4),
                           detection_reason=a["reason"], timestamp=a.get("detected_at"), severity=a["severity"], impact=a["impact"], log_ids=[base + i for i in idx[:200]]))
        for i in res["insights"]:
            db.add(Insight(job_id=job_id, cluster_id=i["cluster_key"], title=i["title"], hypothesis=i["hypothesis"], summary=i["summary"], evidence=i["evidence"],
                           suspected_causes=i["suspected_causes"], recommended_actions=i["recommendations"], confidence_level=i["confidence"],
                           related_clusters=i["related_clusters"], timeline=i["timeline"], disclaimer=i["disclaimer"]))
        job = db.get(AnalysisJob, job_id)
        ev = res["evaluation"]
        for g in ev.get("comparison", {}).get("grid", []):
            if "error" in g:
                continue
            db.add(ModelExperiment(job_id=job_id, dataset_id=job.dataset_name or job.filename, kind="clustering", algorithm=g["algorithm"], feature_method=g["features"],
                                   parameters=g["parameters"], metrics=g["metrics"], execution_time=g["cluster_seconds"] + g["feature_seconds"]))
        for name, m in (ev.get("anomaly") or {}).items():
            db.add(ModelExperiment(job_id=job_id, dataset_id=job.dataset_name or job.filename, kind="anomaly", algorithm=name, feature_method="log-features", parameters={}, metrics=m,
                                   execution_time=ev["timings_s"].get("anomaly", 0)))
        db.commit()
