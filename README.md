# Atlas: Log Clustering, Anomaly Detection and Root-Cause Triage

Atlas reads application and server logs and tells you which problems matter. It groups thousands of similar error lines into a small number of clusters, flags unusual behaviour such as spikes and brand-new error patterns, ranks everything by priority, and suggests evidence-backed, clearly unconfirmed root-cause hypotheses. Results are explored in an interactive dashboard and can be exported as PDF, CSV or JSON.

![Overview dashboard](docs/images/overview.jpg)

**Full documentation:** [`docs/Atlas_Documentation.pdf`](docs/Atlas_Documentation.pdf) (regenerate with `python backend/scripts/build_docs_pdf.py`). Topic pages live in [`docs/`](docs).

## What it does

1. **Ingest**: TXT, LOG, CSV, JSON and JSONL files up to 50 MB (configurable). Encoding is detected, multi-line stack traces are merged, bad lines are counted rather than silently dropped.
2. **Parse**: pulls timestamp, severity, service, host, IP, request id and message out of Apache/Nginx, Python, Java, syslog, HDFS, BGL, HealthApp and custom bracketed formats. CSV and JSON use their own fields. A CSV with unusual headers can be mapped column by column in the UI.
3. **Mask**: emails, phone numbers, tokens, passwords and API keys are masked before anything is written to the database.
4. **Normalize and mine templates**: variable parts become placeholders (`<IP>`, `<NUM>`, `<UUID>` and so on) and Drain3 collapses lines such as `Payment failed for order 1001` and `...order 1002` into one template.
5. **Vectorize**: TF-IDF (word plus character n-grams) or Sentence-Transformer embeddings.
6. **Cluster**: DBSCAN (default), HDBSCAN or K-Means on the unique messages. Noise is re-attached to template groups so every log belongs to a cluster.
7. **Detect anomalies**: Isolation Forest, rolling z-score spikes (1 min, 5 min, 1 h), per-cluster spikes, new and rare patterns, error-ratio shifts and component outliers. Each anomaly stores a human-readable reason.
8. **Prioritise**: a transparent heuristic score gives each cluster Critical, High, Medium or Low, and the UI shows the factor breakdown.
9. **Explain**: root-cause hypotheses with typed evidence (observed fact, statistical finding, model prediction), possible upstream triggers and suggested investigation steps. An optional LLM can rewrite summaries but never invent numbers.
10. **Evaluate and report**: compares TF-IDF vs embeddings across the three algorithms, using ground truth when the data has labels, and exports reports.

| Clusters | Anomalies |
|---|---|
| ![Cluster explorer](docs/images/clusters.jpg) | ![Anomaly center](docs/images/anomalies.jpg) |
| **Root-cause insights** | **Model evaluation** |
| ![Root-cause insights](docs/images/insights.jpg) | ![Model evaluation](docs/images/evaluation.jpg) |

## Dashboard pages

| Page | Purpose |
|---|---|
| Overview | counts, log volume and error timeline, severity split, top clusters, recent anomalies |
| Log Explorer | search and filter every log by text, severity, service, cluster, anomaly flag and time range |
| Cluster Explorer | all clusters with priority, size, severity, time range and services; each opens a detail page with template, trend, priority explanation and member logs |
| Anomaly Center | detected anomalies with score, reason, impact and the logs involved |
| Root-Cause Insights | hypotheses, evidence, potential causes, investigation steps, timeline |
| Model Evaluation | feature and algorithm comparison, supervised and unsupervised metrics, runtime and memory, custom parameter runs |
| Upload and Analysis | file upload, CSV column mapping, dataset catalog, analysis configuration, live progress |
| Reports | PDF, CSV and JSON export |

Light and dark themes are both supported.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts, React Router |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| ML and NLP | scikit-learn (DBSCAN, HDBSCAN, K-Means, Isolation Forest), Drain3, sentence-transformers, pandas, NumPy |
| Database | PostgreSQL (recommended), SQLite for quick local runs |
| Reports | ReportLab |
| Packaging | Docker Compose, nginx |

## Quick start

Requirements: Python 3.11+ and Node 20+. PostgreSQL is optional for a first run, because SQLite is the default.

```bash
# backend: http://localhost:8000, API docs at /docs
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# frontend: http://localhost:5173, proxies /api to :8000
cd frontend
npm install
npm run dev
```

Open **Upload and Analysis**, load a dataset (a bundled *Synthetic* one works offline, *BGL (Loghub 2k)* downloads real data) or drop your own file, then press **Start analysis**. No API key is needed. Sentence-Transformer weights download on first use; if that is not possible, a clearly labelled LSA approximation is used instead.

## Using PostgreSQL (and pgAdmin)

1. In pgAdmin, connect to your server, expand it, right-click **Databases, Create, Database** and create one (for example `atlas`).
2. Put the connection string in `.env` at the project root (it is git-ignored):

   ```
   DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/atlas
   ```

   If the password contains special characters, URL-encode them (`@` becomes `%40`).
3. Create the tables, then start the backend as usual:

   ```bash
   cd backend
   python -m alembic upgrade head
   python -m uvicorn app.main:app --port 8000
   ```

4. In pgAdmin refresh **atlas, Schemas, public, Tables**. Everything the UI shows comes from these tables, so new uploads and analyses appear in both places.

| Table | Holds |
|---|---|
| `uploaded_files` | stored files, detected format and encoding, optional CSV column map |
| `analysis_jobs` | each run: status, progress, configuration, statistics |
| `logs` | every parsed log line with its template, cluster and anomaly flag |
| `log_templates` | mined templates and counts |
| `clusters` | named clusters with priority, size and time range |
| `anomalies` | detected anomalies with reason and impact |
| `insights` | root-cause hypotheses and evidence |
| `model_experiments` | stored evaluation runs |
| `reports` | generated report records |
| `users` | reserved for multi-user deployments (authentication is not enforced) |

With SQLite the tables are created automatically at startup. With PostgreSQL the schema is managed by Alembic only.

## Importing a CSV with your own column names

Standard headers (`timestamp`, `level`, `service`, `message`, and similar) are recognised automatically. For anything else:

1. Upload the CSV on the **Upload and Analysis** page.
2. Open **Map CSV columns** on the file card. Atlas suggests a mapping from the header names.
3. Choose which column feeds each field: `message` (required), `timestamp`, `level`, `service`, `component`, `host`, `ip`, `pid`, `thread`, `request_id`, `error_code`, `label`.
4. Press **Apply mapping**. The preview refreshes with the extracted fields. The mapping is saved with the file and used when you start the analysis.

A `label` column holding `normal` or `anomaly` is treated as anomaly ground truth; other values are treated as cluster truth.

## Docker

```bash
cp .env.example .env
docker compose up --build        # UI http://localhost:8080, API http://localhost:8000/docs, PostgreSQL included
```

The backend container runs `alembic upgrade head` before starting. The Docker build has not been exercised in the authoring environment, so please report any problems.

## Configuration

Set in `.env` (backend reads `../.env` or `backend/.env`). See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | local SQLite file | `postgresql+psycopg://user:password@host:5432/db` for PostgreSQL |
| `CORS_ORIGINS` | localhost dev ports | allowed browser origins |
| `MAX_UPLOAD_MB` | 50 | upload size limit |
| `RATE_LIMIT_PER_MINUTE` | 600 | in-memory request limit (0 disables) |
| `MASK_RULES` | `email,phone,token,password,apikey` | also `ip`, `identifier`, or `none` |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | any Hugging Face sentence-embedding model |
| `EMBEDDINGS_ENABLED` | true | set false to skip embeddings entirely |
| `HF_TOKEN` | empty | only for private or gated models |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | empty | optional summary rewriting (`openai` or `gemini`) |
| `VITE_API_URL` | proxied | frontend build-time backend URL when hosted separately |

Secrets belong only in `.env`, never in code.

## API

Interactive docs at `http://localhost:8000/docs`. All routes are under `/api`. Highlights:

| Method | Path | Purpose |
|---|---|---|
| POST | `/logs/upload` | validate and store files |
| GET, PUT | `/files/{id}/columns`, `/files/{id}/column-map` | inspect CSV headers, save a column mapping |
| POST | `/analysis/start` | start a background analysis (returns 202) |
| GET | `/analysis/{id}/status` | poll progress |
| GET | `/analysis/{id}/summary`, `/timeline`, `/logs`, `/clusters`, `/anomalies`, `/insights`, `/evaluation` | dashboard data |
| GET | `/analysis/{id}/export?format=pdf\|csv\|json` | report download |

The full table is in [`docs/api.md`](docs/api.md).

## Project layout

```
backend/app/{api,core,database,models,schemas,services,utils}
backend/app/pipelines/{ingestion,parsing,preprocessing,templates,features,clustering,
                       anomaly_detection,root_cause,summarization,evaluation}
backend/{tests,migrations,scripts,sample_data}
frontend/src/{components,pages,layouts,charts,services,hooks,types,utils}
docs/            architecture, methodology, dataset, API, testing, deployment, experiments, PDF
```

`_legacy_mern/` holds the earlier Node and Express prototype. It is unused and can be deleted.

## Tests

```bash
cd backend && python -m pytest             # 50 tests, offline, isolated SQLite database
cd frontend && npm test && npx tsc --noEmit
```

The backend suite covers parsing, preprocessing, templates, features, clustering, anomalies, root-cause logic, the full API workflow, secret masking and CSV column mapping. UI flows are not covered by automated browser tests.

## Reproducing the experiments

```bash
cd backend && python scripts/run_experiments.py      # downloads Loghub samples, writes docs/experiments.md
```

Findings from the executed runs on six real Loghub 2k samples (single run, small samples, see [`docs/experiments_findings.md`](docs/experiments_findings.md)):

- Drain3 beat regex-only template extraction on most datasets (for example Apache 1.000 vs 0.582 grouping accuracy).
- TF-IDF matched or beat sentence embeddings on clustering ARI for these template-driven logs.
- DBSCAN with a k-distance eps was more stable than HDBSCAN, which labelled a large share of points as noise.
- On BGL, a severity-only baseline detected alerts better than Isolation Forest. Content-based unsupervised detection was weak on that sample.

## Design principles

- Observed facts, statistical findings and model predictions are labelled separately.
- Root causes are always "potential, unconfirmed". Evidence strength (Strong, Moderate, Limited) is a count of independent signals, not a probability.
- Priority is a transparent heuristic and its factors are shown.
- Synthetic demo data is always flagged in the UI, in job records and in reports.
- Every metric shown comes from an executed run on the selected data.
- Sensitive values are masked before storage. Filenames are sanitised, uploads are size and type limited, search is escaped, 5xx responses never include stack traces.

## Limitations

- Jobs run in an in-process thread pool. A multi-instance deployment would need a shared queue and rate limiter.
- There is no authentication; the `users` table is reserved for later.
- Priority weights are heuristic and not validated against operator judgement.
- Evaluation used small samples. Do not extrapolate the numbers to full-scale datasets.
- The embedding model needs internet access on first use, with an LSA fallback when it is unavailable.

## Demo workflow

1. Upload and Analysis, load *Synthetic: application service log* (offline) or *BGL (Loghub 2k)*, press Start analysis.
2. Overview: counts, timeline, severity, top clusters.
3. Cluster Explorer: open a cluster to see its template, trend, priority explanation and logs.
4. Anomaly Center: select an anomaly for its reason, impact and logs.
5. Root-Cause Insights: evidence, potential causes, investigation steps.
6. Model Evaluation: compare feature and algorithm combinations or run your own parameters.
7. Reports: download PDF, CSV or JSON.

## Further reading

[Architecture](docs/architecture.md) · [Methodology](docs/methodology.md) · [Datasets](docs/dataset.md) · [API](docs/api.md) · [Testing](docs/testing.md) · [Deployment](docs/deployment.md) · [Experiments](docs/experiments.md) · [Findings](docs/experiments_findings.md)
