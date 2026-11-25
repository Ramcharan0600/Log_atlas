from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    """Reserved for multi-user deployments (authentication is not enforced in this version)."""
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    file_id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(600))
    size_bytes: Mapped[int] = mapped_column(Integer)
    encoding: Mapped[str | None] = mapped_column(String(40))
    detected_format: Mapped[str | None] = mapped_column(String(60))
    dataset_name: Mapped[str | None] = mapped_column(String(120))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    labels_path: Mapped[str | None] = mapped_column(String(600))  # sidecar ground-truth labels
    column_map: Mapped[dict | None] = mapped_column(JSON)  # CSV only: log field -> CSV header chosen by the user
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    job_id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(600))
    dataset_name: Mapped[str | None] = mapped_column(String(120))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    file_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    stage: Mapped[str] = mapped_column(String(80), default="Queued")
    error: Mapped[str | None] = mapped_column(Text)
    total_logs: Mapped[int] = mapped_column(Integer, default=0)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processing_started: Mapped[datetime | None] = mapped_column(DateTime)
    processing_completed: Mapped[datetime | None] = mapped_column(DateTime)


class LogTemplate(Base):
    __tablename__ = "log_templates"
    template_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    local_id: Mapped[int] = mapped_column(Integer)  # id within the job (Drain cluster id)
    template_text: Mapped[str] = mapped_column(Text)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # parameter examples etc.
    __table_args__ = (Index("ix_tpl_job_local", "job_id", "local_id"),)


class Cluster(Base):
    __tablename__ = "clusters"
    cluster_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    local_id: Mapped[int] = mapped_column(Integer)  # label within job
    cluster_name: Mapped[str] = mapped_column(String(200))
    cluster_size: Mapped[int] = mapped_column(Integer)
    severity: Mapped[str] = mapped_column(String(10))
    priority: Mapped[str] = mapped_column(String(10), index=True)
    priority_score: Mapped[float] = mapped_column(Float)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # keywords, services, trend, related, reps, factors, template
    __table_args__ = (Index("ix_cluster_job_local", "job_id", "local_id"),)


class LogEntry(Base):
    __tablename__ = "logs"
    log_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    severity: Mapped[str] = mapped_column(String(10))
    service: Mapped[str | None] = mapped_column(String(120))
    component: Mapped[str | None] = mapped_column(String(160))
    host: Mapped[str | None] = mapped_column(String(160))
    ip: Mapped[str | None] = mapped_column(String(64))
    pid: Mapped[str | None] = mapped_column(String(32))
    thread: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(80))
    error_code: Mapped[str | None] = mapped_column(String(32))
    original_message: Mapped[str] = mapped_column(Text)
    normalized_message: Mapped[str] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(Integer)  # local template id
    cluster_id: Mapped[int | None] = mapped_column(Integer)  # local cluster label
    anomaly_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_score: Mapped[float] = mapped_column(Float, default=0.0)
    cluster_truth: Mapped[str | None] = mapped_column(String(120))
    anomaly_truth: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (Index("ix_log_job_cluster", "job_id", "cluster_id"), Index("ix_log_job_sev", "job_id", "severity"),
                      Index("ix_log_job_ts", "job_id", "timestamp"), Index("ix_log_job_service", "job_id", "service"))


class Anomaly(Base):
    __tablename__ = "anomalies"
    anomaly_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    log_id: Mapped[int | None] = mapped_column(Integer)  # representative log
    cluster_id: Mapped[int | None] = mapped_column(Integer)  # local cluster label
    kind: Mapped[str] = mapped_column(String(40))
    anomaly_score: Mapped[float] = mapped_column(Float)
    detection_reason: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime)
    severity: Mapped[str] = mapped_column(String(10), default="Medium")
    impact: Mapped[str] = mapped_column(Text, default="")
    log_ids: Mapped[list] = mapped_column(JSON, default=list)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Insight(Base):
    __tablename__ = "insights"
    insight_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    hypothesis: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    suspected_causes: Mapped[list] = mapped_column(JSON, default=list)
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    confidence_level: Mapped[str] = mapped_column(String(30))
    related_clusters: Mapped[list] = mapped_column(JSON, default=list)
    timeline: Mapped[list] = mapped_column(JSON, default=list)
    disclaimer: Mapped[str] = mapped_column(Text, default="")


class Report(Base):
    __tablename__ = "reports"
    report_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)


class ModelExperiment(Base):
    __tablename__ = "model_experiments"
    experiment_id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_jobs.job_id", ondelete="CASCADE"), index=True)
    dataset_id: Mapped[str | None] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="clustering")  # clustering | anomaly
    algorithm: Mapped[str] = mapped_column(String(40))
    feature_method: Mapped[str] = mapped_column(String(40))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_time: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
