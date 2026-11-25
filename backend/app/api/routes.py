"""REST API. Thin handlers: validation + DB queries; heavy lifting lives in services/ and pipelines/."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models import AnalysisJob, Anomaly, Cluster, Insight, LogEntry, LogTemplate, ModelExperiment, Report, UploadedFile
from app.pipelines.ingestion.reader import IngestionError, csv_columns, file_ext, read_records, validate_column_map, validate_file
from app.schemas import ColumnMapping, ExperimentRequest, LoadDataset, StartAnalysis
from app.services import datasets as ds
from app.services import jobs
from app.services import reports as rep
from app.services.analysis import run_experiments

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


# ---------- helpers -------------------------------------------------------------------------------
def iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def get_job(db: Session, job_id: int) -> AnalysisJob:
    job = db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Analysis job not found")
    return job


def require_done(job: AnalysisJob) -> AnalysisJob:
    if job.status != "completed":
        raise HTTPException(409, f"Analysis is {job.status}; results are not available yet")
    return job


def job_out(j: AnalysisJob, full: bool = False) -> dict:
    s = dict(j.stats or {})
    if not full:
        s.pop("evaluation", None)
    return {"id": j.job_id, "filename": j.filename, "dataset_name": j.dataset_name, "is_synthetic": j.is_synthetic, "status": j.status, "progress": j.progress, "stage": j.stage,
            "error": j.error, "total_logs": j.total_logs, "config": j.configuration, "stats": s, "created_at": iso(j.created_at), "started_at": iso(j.processing_started),
            "completed_at": iso(j.processing_completed)}


def cluster_out(c: Cluster, brief: bool = True) -> dict:
    d = c.details or {}
    base = {"id": c.cluster_id, "local_id": c.local_id, "job_id": c.job_id, "name": c.cluster_name, "size": c.cluster_size, "severity": c.severity, "priority": c.priority,
            "priority_score": c.priority_score, "first_seen": iso(c.first_seen), "last_seen": iso(c.last_seen), "is_anomalous": c.is_anomalous, "keywords": d.get("keywords", []),
            "services": d.get("services", {}), "template": d.get("template"), "summary": c.summary, "trend_ratio": d.get("trend_ratio")}
    if not brief:
        base.update(representatives=d.get("representatives", []), levels=d.get("levels", {}), trend=d.get("trend", []), related=d.get("related", []),
                    priority_factors=d.get("priority_factors", {}), priority_explanation=d.get("priority_explanation"), summary_source=d.get("summary_source", "rule"),
                    n_unique_messages=d.get("n_unique_messages"))
    return base


def log_out(l: LogEntry, cnames: dict[int, str] | None = None, tpl: dict[int, str] | None = None, cpk: dict[int, int] | None = None) -> dict:
    return {"id": l.log_id, "line_no": l.line_no, "timestamp": iso(l.timestamp), "severity": l.severity, "service": l.service, "component": l.component, "host": l.host, "ip": l.ip,
            "pid": l.pid, "thread": l.thread, "request_id": l.request_id, "error_code": l.error_code, "original_message": l.original_message, "normalized_message": l.normalized_message,
            "template_id": l.template_id, "template": (tpl or {}).get(l.template_id), "cluster_id": l.cluster_id, "cluster_name": (cnames or {}).get(l.cluster_id), "cluster_pk": (cpk or {}).get(l.cluster_id),
            "anomaly_flag": l.anomaly_flag, "anomaly_score": l.anomaly_score}


def like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def filtered_logs(job_id: int, q=None, severity=None, service=None, cluster=None, anomaly=None, start=None, end=None, template=None):
    st = select(LogEntry).where(LogEntry.job_id == job_id)
    if q:
        st = st.where(or_(LogEntry.original_message.like(like(q), escape="\\"), LogEntry.normalized_message.like(like(q), escape="\\")))
    if severity:
        st = st.where(LogEntry.severity.in_([s.strip().upper() for s in severity.split(",")]))
    if service:
        st = st.where(LogEntry.service == service)
    if cluster is not None:
        st = st.where(LogEntry.cluster_id == cluster)
    if anomaly is not None:
        st = st.where(LogEntry.anomaly_flag == anomaly)
    if start:
        st = st.where(LogEntry.timestamp >= start)
    if end:
        st = st.where(LogEntry.timestamp <= end)
    if template is not None:
        st = st.where(LogEntry.template_id == template)
    return st


def paginate(db: Session, stmt, page: int, size: int, order):
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    items = db.scalars(stmt.order_by(*order).offset((page - 1) * size).limit(size)).all()
    return total, items


# ---------- health / datasets / upload ------------------------------------------------------------
@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat() + "Z"}


@router.get("/datasets")
def list_datasets(db: Session = Depends(get_db)):
    return ds.catalog_view(db)


@router.post("/datasets/load")
def load_dataset(body: LoadDataset, db: Session = Depends(get_db)):
    try:
        f = ds.load_dataset(db, body.name)
    except ds.DatasetError as e:
        raise HTTPException(502 if "download" in str(e).lower() else 400, str(e)) from e
    return {"file_id": f.file_id, "filename": f.filename, "dataset_name": f.dataset_name, "is_synthetic": f.is_synthetic,
            "preview": jobs.preview_file(f.stored_path, f.filename, labels=[1] if f.labels_path else None)}


@router.post("/logs/upload")
async def upload(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    st = get_settings()
    if len(files) > 20:
        raise HTTPException(400, "At most 20 files per upload")
    out = []
    for up in files:
        name = Path(up.filename or "upload.log").name[:200]
        data = await up.read(st.max_upload_mb * 1024 * 1024 + 1)
        try:
            validate_file(name, len(data), st.max_upload_mb)
            stored = Path(st.upload_dir) / f"{uuid.uuid4().hex}_{name}"
            stored.write_bytes(data)
            prev = jobs.preview_file(str(stored), name)
        except IngestionError as e:
            out.append({"filename": name, "error": str(e)})
            continue
        f = UploadedFile(filename=name, stored_path=str(stored), size_bytes=len(data), encoding=prev["encoding"], detected_format=prev["detected_format"])
        db.add(f)
        db.commit()
        out.append({"file_id": f.file_id, "filename": name, "size_bytes": len(data), "preview": prev})
    if not any("file_id" in o for o in out):
        raise HTTPException(400, "; ".join(f"{o['filename']}: {o['error']}" for o in out))
    return out


@router.get("/files/{file_id}/preview")
def file_preview(file_id: int, n: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)):
    f = db.get(UploadedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    return {"file_id": f.file_id, "dataset_name": f.dataset_name, "is_synthetic": f.is_synthetic, "column_map": f.column_map,
            **jobs.preview_file(f.stored_path, f.filename, n, [1] if f.labels_path else None, f.column_map)}


def _csv_file(db: Session, file_id: int) -> UploadedFile:
    f = db.get(UploadedFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    if file_ext(f.filename) != "csv":
        raise HTTPException(400, "Column mapping is only available for CSV files")
    return f


@router.get("/files/{file_id}/columns")
def file_columns(file_id: int, db: Session = Depends(get_db)):
    """CSV headers, sample rows, the auto-suggested mapping and the mapping currently saved for this file."""
    f = _csv_file(db, file_id)
    try:
        info = csv_columns(Path(f.stored_path).read_bytes())
    except IngestionError as e:
        raise HTTPException(400, str(e)) from e
    return {"file_id": f.file_id, "current_mapping": f.column_map, **info}


@router.put("/files/{file_id}/column-map")
def set_column_map(file_id: int, body: ColumnMapping, db: Session = Depends(get_db)):
    """Save which CSV column feeds which log field; returns a fresh preview parsed with that mapping."""
    f = _csv_file(db, file_id)
    try:
        headers = csv_columns(Path(f.stored_path).read_bytes())["headers"]
        f.column_map = validate_column_map(body.mapping, headers)
        db.commit()
        prev = jobs.preview_file(f.stored_path, f.filename, 20, [1] if f.labels_path else None, f.column_map)
    except IngestionError as e:
        db.rollback()
        raise HTTPException(400, str(e)) from e
    return {"file_id": f.file_id, "column_map": f.column_map, "preview": prev}


# ---------- analysis jobs -------------------------------------------------------------------------
@router.post("/analysis/start", status_code=202)
def start_analysis(body: StartAnalysis, db: Session = Depends(get_db)):
    try:
        job = jobs.create_job(db, body.file_ids, body.config.model_dump(exclude_none=True))
    except IngestionError as e:
        raise HTTPException(404, str(e)) from e
    jobs.submit(job.job_id)
    return job_out(job)


@router.get("/analysis")
def list_jobs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    total, items = paginate(db, select(AnalysisJob), page, page_size, [AnalysisJob.job_id.desc()])
    return {"total": total, "page": page, "items": [job_out(j) for j in items]}


@router.get("/analysis/{job_id}")
def get_analysis(job_id: int, db: Session = Depends(get_db)):
    return job_out(get_job(db, job_id), full=False)


@router.get("/analysis/{job_id}/status")
def job_status(job_id: int, db: Session = Depends(get_db)):
    j = get_job(db, job_id)
    return {"id": j.job_id, "status": j.status, "progress": j.progress, "stage": j.stage, "error": j.error}


@router.delete("/analysis/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    j = get_job(db, job_id)
    if j.status == "running":
        raise HTTPException(409, "Cannot delete a running job")
    for m in (LogEntry, LogTemplate, Cluster, Anomaly, Insight, ModelExperiment, Report):
        db.query(m).filter(m.job_id == job_id).delete()
    db.delete(j)
    db.commit()
    return Response(status_code=204)


def _timeline_df(db: Session, job_id: int) -> pd.DataFrame:
    rows = db.execute(select(LogEntry.timestamp, LogEntry.severity, LogEntry.anomaly_flag).where(LogEntry.job_id == job_id, LogEntry.timestamp.is_not(None))).all()
    return pd.DataFrame(rows, columns=["timestamp", "severity", "anomaly"])


@router.get("/analysis/{job_id}/timeline")
def timeline(job_id: int, freq: str = Query("auto", pattern="^(auto|1min|5min|15min|1h|1d)$"), db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    df = _timeline_df(db, job_id)
    if df.empty:
        return {"freq": None, "points": []}
    if freq == "auto":
        span_h = (df.timestamp.max() - df.timestamp.min()).total_seconds() / 3600
        freq = "1min" if span_h <= 2 else "5min" if span_h <= 12 else "1h" if span_h <= 96 else "1d"
    df["bucket"] = df.timestamp.dt.floor({"1min": "1min", "5min": "5min", "15min": "15min", "1h": "1h", "1d": "1D"}[freq])
    df["err"] = df.severity.isin(["ERROR", "FATAL"])
    g = df.groupby("bucket").agg(total=("severity", "size"), errors=("err", "sum"), anomalies=("anomaly", "sum")).reset_index()
    return {"freq": freq, "points": [{"t": r.bucket.isoformat(), "total": int(r.total), "errors": int(r.errors), "anomalies": int(r.anomalies)} for r in g.itertuples()]}


@router.get("/analysis/{job_id}/summary")
def summary(job_id: int, db: Session = Depends(get_db)):
    j = get_job(db, job_id)
    s = j.stats or {}
    top = db.scalars(select(Cluster).where(Cluster.job_id == job_id).order_by(Cluster.priority_score.desc()).limit(8)).all()
    an = db.scalars(select(Anomaly).where(Anomaly.job_id == job_id).order_by(Anomaly.anomaly_score.desc()).limit(6)).all()
    recent = db.scalars(select(AnalysisJob).order_by(AnalysisJob.job_id.desc()).limit(6)).all()
    return {"job": job_out(j), "total_logs": s.get("total_logs", j.total_logs), "n_clusters": s.get("n_clusters", 0), "critical": s.get("critical", 0), "anomalies": s.get("anomalies", 0),
            "n_templates": s.get("n_templates", 0), "levels": s.get("levels", {}), "services": s.get("services", {}), "error_services": s.get("error_services", {}),
            "time_range": s.get("time_range", []), "top_clusters": [cluster_out(c) for c in top], "recent_anomalies": [anomaly_out(a) for a in an], "recent_jobs": [job_out(x) for x in recent],
            "is_synthetic": j.is_synthetic}


# ---------- logs ----------------------------------------------------------------------------------
@router.get("/analysis/{job_id}/logs")
def logs(job_id: int, q: str | None = None, severity: str | None = None, service: str | None = None, cluster: int | None = None, anomaly: bool | None = None,
         start: datetime | None = None, end: datetime | None = None, template: int | None = None, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
         db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    total, items = paginate(db, filtered_logs(job_id, q, severity, service, cluster, anomaly, start, end, template), page, page_size, [LogEntry.timestamp, LogEntry.log_id])
    cls = db.scalars(select(Cluster).where(Cluster.job_id == job_id)).all()
    cn, cpk = {c.local_id: c.cluster_name for c in cls}, {c.local_id: c.cluster_id for c in cls}
    tp = {t.local_id: t.template_text for t in db.scalars(select(LogTemplate).where(LogTemplate.job_id == job_id, LogTemplate.local_id.in_({i.template_id for i in items})))}
    return {"total": total, "page": page, "page_size": page_size, "items": [log_out(i, cn, tp, cpk) for i in items]}


@router.get("/analysis/{job_id}/facets")
def facets(job_id: int, db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    sv = [r[0] for r in db.execute(select(LogEntry.service).where(LogEntry.job_id == job_id).group_by(LogEntry.service).order_by(func.count().desc()).limit(100)) if r[0]]
    cl = [{"id": c.local_id, "name": c.cluster_name} for c in db.scalars(select(Cluster).where(Cluster.job_id == job_id).order_by(Cluster.cluster_size.desc()))]
    return {"services": sv, "severities": ["FATAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"], "clusters": cl}


@router.get("/analysis/{job_id}/templates")
def templates(job_id: int, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    total, items = paginate(db, select(LogTemplate).where(LogTemplate.job_id == job_id), page, page_size, [LogTemplate.occurrence_count.desc()])
    return {"total": total, "items": [{"id": t.local_id, "template": t.template_text, "count": t.occurrence_count, "examples": t.meta.get("examples", []),
                                      "parameters": t.meta.get("parameters", [])} for t in items]}


# ---------- clusters ------------------------------------------------------------------------------
@router.get("/analysis/{job_id}/clusters")
def clusters(job_id: int, priority: str | None = None, q: str | None = None, anomalous: bool | None = None, db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    st = select(Cluster).where(Cluster.job_id == job_id)
    if priority:
        st = st.where(Cluster.priority == priority.capitalize())
    if q:
        st = st.where(Cluster.cluster_name.like(like(q), escape="\\"))
    if anomalous is not None:
        st = st.where(Cluster.is_anomalous == anomalous)
    return [cluster_out(c) for c in db.scalars(st.order_by(Cluster.priority_score.desc()))]


def get_cluster(db: Session, cluster_id: int) -> Cluster:
    c = db.get(Cluster, cluster_id)
    if not c:
        raise HTTPException(404, "Cluster not found")
    return c


@router.get("/clusters/{cluster_id}")
def cluster_detail(cluster_id: int, db: Session = Depends(get_db)):
    c = get_cluster(db, cluster_id)
    out = cluster_out(c, brief=False)
    rel_ids = [r["cluster_key"] for r in out["related"]]
    rel = {x.local_id: x for x in db.scalars(select(Cluster).where(Cluster.job_id == c.job_id, Cluster.local_id.in_(rel_ids)))} if rel_ids else {}
    out["related"] = [{"id": rel[r["cluster_key"]].cluster_id, "name": rel[r["cluster_key"]].cluster_name, "similarity": r["similarity"]} for r in out["related"] if r["cluster_key"] in rel]
    out["anomalies"] = [anomaly_out(a) for a in db.scalars(select(Anomaly).where(Anomaly.job_id == c.job_id, Anomaly.cluster_id == c.local_id).order_by(Anomaly.anomaly_score.desc()).limit(10))]
    return out


@router.get("/clusters/{cluster_id}/logs")
def cluster_logs(cluster_id: int, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), q: str | None = None, db: Session = Depends(get_db)):
    c = get_cluster(db, cluster_id)
    total, items = paginate(db, filtered_logs(c.job_id, q=q, cluster=c.local_id), page, page_size, [LogEntry.timestamp, LogEntry.log_id])
    return {"total": total, "page": page, "page_size": page_size, "items": [log_out(i, {c.local_id: c.cluster_name}, None, {c.local_id: c.cluster_id}) for i in items]}


# ---------- anomalies / insights / evaluation -----------------------------------------------------
def anomaly_out(a: Anomaly) -> dict:
    return {"id": a.anomaly_id, "kind": a.kind, "score": a.anomaly_score, "reason": a.detection_reason, "detected_at": iso(a.timestamp), "cluster": a.cluster_id,
            "severity": a.severity, "impact": a.impact, "n_logs": len(a.log_ids or []), "job_id": a.job_id}


@router.get("/analysis/{job_id}/anomalies")
def anomalies(job_id: int, kind: str | None = None, min_score: float = Query(0, ge=0, le=1), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
              db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    st = select(Anomaly).where(Anomaly.job_id == job_id, Anomaly.anomaly_score >= min_score)
    if kind:
        st = st.where(Anomaly.kind.like(like(kind), escape="\\"))
    total, items = paginate(db, st, page, page_size, [Anomaly.anomaly_score.desc()])
    cn = {c.local_id: (c.cluster_id, c.cluster_name) for c in db.scalars(select(Cluster).where(Cluster.job_id == job_id))}
    out = []
    for a in items:
        d = anomaly_out(a)
        d["cluster"], d["cluster_name"] = cn.get(a.cluster_id, (None, None))
        out.append(d)
    kinds = [r[0] for r in db.execute(select(Anomaly.kind).where(Anomaly.job_id == job_id).group_by(Anomaly.kind))]
    return {"total": total, "items": out, "kinds": kinds}


@router.get("/analysis/{job_id}/anomalies/{anomaly_id}")
def anomaly_detail(job_id: int, anomaly_id: int, db: Session = Depends(get_db)):
    a = db.get(Anomaly, anomaly_id)
    if not a or a.job_id != job_id:
        raise HTTPException(404, "Anomaly not found")
    cn = {c.local_id: c for c in db.scalars(select(Cluster).where(Cluster.job_id == job_id))}
    items = db.scalars(select(LogEntry).where(LogEntry.log_id.in_((a.log_ids or [])[:50])).order_by(LogEntry.timestamp)).all()
    d = anomaly_out(a)
    c = cn.get(a.cluster_id)
    d["cluster"], d["cluster_name"] = (c.cluster_id, c.cluster_name) if c else (None, None)
    d["trend"] = c.details.get("trend", []) if c else []
    d["logs"] = [log_out(i, {k: v.cluster_name for k, v in cn.items()}, None, {k: v.cluster_id for k, v in cn.items()}) for i in items]
    return d


@router.get("/analysis/{job_id}/insights")
def insights(job_id: int, db: Session = Depends(get_db)):
    require_done(get_job(db, job_id))
    cn = {c.local_id: (c.cluster_id, c.cluster_name) for c in db.scalars(select(Cluster).where(Cluster.job_id == job_id))}
    out = []
    for i in db.scalars(select(Insight).where(Insight.job_id == job_id).order_by(Insight.insight_id)):
        out.append({"id": i.insight_id, "title": i.title, "hypothesis": i.hypothesis, "summary": i.summary, "evidence": i.evidence, "suspected_causes": i.suspected_causes,
                    "recommendations": i.recommended_actions, "confidence": i.confidence_level, "timeline": i.timeline, "disclaimer": i.disclaimer,
                    "cluster": cn.get(i.cluster_id, (None, None))[0],
                    "related_clusters": [{"id": cn[k][0], "name": cn[k][1]} for k in i.related_clusters if k in cn]})
    return out


@router.get("/analysis/{job_id}/evaluation")
def evaluation(job_id: int, db: Session = Depends(get_db)):
    j = require_done(get_job(db, job_id))
    ev = (j.stats or {}).get("evaluation") or {}
    exps = db.scalars(select(ModelExperiment).where(ModelExperiment.job_id == job_id).order_by(ModelExperiment.experiment_id.desc()).limit(100)).all()
    return {"evaluation": ev, "is_synthetic": j.is_synthetic, "dataset": j.dataset_name or j.filename, "config": j.configuration,
            "experiments": [{"id": e.experiment_id, "kind": e.kind, "algorithm": e.algorithm, "features": e.feature_method, "parameters": e.parameters, "metrics": e.metrics,
                             "execution_time": e.execution_time, "created_at": iso(e.created_at)} for e in exps]}


@router.post("/analysis/{job_id}/evaluation/run")
def run_evaluation(job_id: int, body: ExperimentRequest, db: Session = Depends(get_db)):
    """Re-run the TF-IDF/embeddings x DBSCAN/HDBSCAN/K-Means grid with user-chosen parameters; results are stored as experiments."""
    j = require_done(get_job(db, job_id))
    rows = db.execute(select(LogEntry.normalized_message, LogEntry.cluster_truth).where(LogEntry.job_id == job_id)).all()
    idx: dict[str, int] = {}
    inverse = np.array([idx.setdefault(r[0], len(idx)) for r in rows])
    uniq = list(idx)
    weights = np.bincount(inverse, minlength=len(uniq)).astype(float)
    truth = [r[1] for r in rows] if rows and sum(r[1] is not None for r in rows) > 0.9 * len(rows) else None
    params = body.model_dump()
    res = run_experiments(uniq, inverse, weights, truth, {**params, "evaluation_max_unique": params["max_unique"]})
    for g in res["grid"]:
        if "error" not in g:
            db.add(ModelExperiment(job_id=job_id, dataset_id=j.dataset_name or j.filename, kind="clustering", algorithm=g["algorithm"], feature_method=g["features"],
                                   parameters={**g["parameters"], "requested": params}, metrics=g["metrics"], execution_time=g["cluster_seconds"] + g["feature_seconds"]))
    db.commit()
    return res


# ---------- export --------------------------------------------------------------------------------
@router.get("/analysis/{job_id}/export")
def export(job_id: int, format: str = Query("json", pattern="^(json|csv|pdf)$"), db: Session = Depends(get_db)):
    j = require_done(get_job(db, job_id))
    data = rep.collect(db, j)
    fn, mime = {"json": (rep.to_json, "application/json"), "csv": (rep.to_csv, "text/csv"), "pdf": (rep.to_pdf, "application/pdf")}[format]
    content = fn(data)
    db.add(Report(job_id=job_id, format=format, size_bytes=len(content)))
    db.commit()
    return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="atlas_job{job_id}.{format}"'})
