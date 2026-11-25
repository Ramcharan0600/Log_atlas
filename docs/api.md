# API

Interactive docs: `http://localhost:8000/docs` (OpenAPI at `/openapi.json`). All routes are under `/api`. Errors are `{"detail": "..."}`; 5xx never contains a stack trace.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/datasets` | catalog (real vs synthetic flag, licence, labels) |
| POST | `/datasets/load` `{name}` | copy/download dataset, returns `file_id` + preview |
| POST | `/logs/upload` (multipart `files`) | validate + store; returns per-file preview or error |
| GET | `/files/{file_id}/preview` | parsed preview, format, encoding, timestamp parse rate (uses the saved column map for CSV) |
| GET | `/files/{file_id}/columns` | CSV only: headers, sample rows, suggested field mapping, currently saved mapping |
| PUT | `/files/{file_id}/column-map` `{mapping}` | CSV only: save which CSV column feeds which log field (`message` required); returns a fresh preview |
| POST | `/analysis/start` `{file_ids, config}` | start background job (202) |
| GET | `/analysis` | history (paginated) |
| GET | `/analysis/{id}` · `/status` | job + progress |
| DELETE | `/analysis/{id}` | remove job and results |
| GET | `/analysis/{id}/summary` · `/timeline?freq=` | dashboard data |
| GET | `/analysis/{id}/logs` | filters: `q, severity, service, cluster, anomaly, start, end, template, page, page_size` |
| GET | `/analysis/{id}/facets` · `/templates` | filter options, mined templates |
| GET | `/analysis/{id}/clusters` | filters: `priority, q, anomalous` |
| GET | `/clusters/{cluster_id}` · `/clusters/{cluster_id}/logs` | detail, member logs |
| GET | `/analysis/{id}/anomalies` · `/anomalies/{anomaly_id}` | list (`kind, min_score`), detail with logs |
| GET | `/analysis/{id}/insights` | root-cause hypotheses |
| GET | `/analysis/{id}/evaluation` | evaluation + stored experiments |
| POST | `/analysis/{id}/evaluation/run` | execute the feature×algorithm grid with chosen parameters |
| GET | `/analysis/{id}/export?format=pdf\|csv\|json` | downloadable report |

Analysis `config` fields (validated): `features` tfidf|embeddings, `algorithm` dbscan|hdbscan|kmeans, `eps`, `min_samples`, `min_cluster_size`, `n_clusters`, `sim_threshold`, `contamination`, `z_threshold`, `lowercase`, `keep_stack_trace`, `run_evaluation`, `evaluation_max_unique`, `mask_rules`, `disabled_rules`. The effective config (with `random_seed`) is stored on the job for reproducibility.
