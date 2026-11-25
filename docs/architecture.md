# Architecture

```
LOG INPUT (TXT/LOG/CSV/JSON/JSONL, bundled demos, Loghub downloads)
  → INGESTION     pipelines/ingestion/reader.py     size/type validation, encoding detection, invalid-line counting, multiline merge
  → COLUMN MAP    (CSV only) user-chosen header -> field mapping stored on uploaded_files.column_map, applied in the reader
  → PARSING       pipelines/parsing/parser.py       pluggable regex formats (Apache/Nginx, Python, Java, syslog, HDFS, BGL, HealthApp, bracketed service, structured CSV/JSON)
  → MASKING       pipelines/preprocessing           emails, phones, tokens, passwords, API keys (opt. IPs, identifiers) BEFORE storage
  → NORMALIZATION pipelines/preprocessing/normalizer.py   <IP> <UUID> <TIME> <PATH> <ID> <NUM> ... (configurable)
  → TEMPLATES     pipelines/templates/miner.py      Drain3 (+ regex-only baseline for comparison)
  → FEATURES      pipelines/features/extractors.py  TF-IDF (word+char n-grams → SVD) | Sentence-Transformers (cached)
  → CLUSTERING    pipelines/clustering/engine.py    DBSCAN | HDBSCAN | K-Means on unique messages; noise → template groups
  → ANOMALIES     pipelines/anomaly_detection       Isolation Forest, rolling z-score (1m/5m/1h), per-cluster spikes, new/rare patterns, error-ratio shift, component outliers
  → ANALYSIS      services/analysis.py              per-cluster stats, trend, related clusters, priority score
  → ROOT CAUSE    pipelines/root_cause              evidence collection, temporal precedence, hypothesis, evidence level, investigation steps
  → SUMMARIES     pipelines/summarization           rule-based; optional LLM rewrite guarded against invented numbers
  → EVALUATION    pipelines/evaluation              supervised/unsupervised metrics, configuration grid, runtime & memory
  → STORAGE       SQLAlchemy models (SQLite/PostgreSQL) + Alembic
  → API           FastAPI (api/routes.py)  →  React dashboard / reports
```

## Key decisions
- **Python backend** for the ML stack (scikit-learn, Drain3, sentence-transformers); the earlier Node prototype is retired.
- **Cluster on unique normalized messages** (frequency-weighted for DBSCAN/K-Means) — logs are extremely repetitive, so this is the main scalability lever (~10–14k logs/s measured on synthetic data).
- **Dense L2-normalised vectors for both feature types** so cosine ≈ euclidean and one clustering code path serves both; TF-IDF is reduced with truncated SVD.
- **Noise handling**: algorithm noise is reported (`raw_noise_ratio`) and then re-attached to the log's Drain template group so every log has a cluster; evaluation reports both views.
- **Jobs**: in-process `ThreadPoolExecutor`; status/progress persisted in `analysis_jobs` and polled by the UI. Stale jobs are failed on restart.
- **Ids**: log/template/cluster rows keep job-local ids (`cluster_id`, `template_id` on logs) plus global primary keys; API exposes cluster PKs.
- **Security**: filename sanitising, extension/size limits, masking before storage, escaped LIKE search, generic 500 responses (stack traces only in server logs), in-memory rate limit, secrets only from environment, React text rendering (no HTML injection).

## Database
Tables: `users` (reserved), `uploaded_files`, `analysis_jobs`, `logs`, `log_templates`, `clusters`, `anomalies`, `insights`, `reports`, `model_experiments`; indexes on (job, cluster/severity/timestamp/service). Migrations: `0001_initial_schema`, `0002_uploaded_files_column_map` (per-file CSV column mapping). SQLite uses `create_all`; PostgreSQL uses `alembic upgrade head`.
