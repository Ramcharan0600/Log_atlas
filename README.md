# Atlas — Log Error Clustering, Anomaly Detection & Root-Cause Insights

Upload server/application logs → parse → normalize → mine templates (Drain3) → TF‑IDF or Sentence‑Transformer features → cluster (DBSCAN / HDBSCAN / K‑Means) → detect anomalies (Isolation Forest + rolling z‑score) → prioritise → evidence‑based **potential** root‑cause hypotheses → interactive dashboard and PDF/CSV/JSON reports.

**Stack:** React + TypeScript + Vite + Tailwind + Recharts · FastAPI + Pydantic · SQLAlchemy (SQLite dev / PostgreSQL prod) + Alembic · scikit‑learn, Drain3, sentence‑transformers · Docker Compose.

> Honesty rules built in: observed facts, statistical findings and model predictions are labelled separately; root causes are always "potential, unconfirmed"; evidence strength (Strong/Moderate/Limited) is not a probability; priority is a transparent heuristic; synthetic demo data is always flagged; all metrics come from executed runs.

## Quick start (local)

Requirements: Python 3.11+, Node 20+.

```bash
# backend (http://localhost:8000, docs at /docs)
cd backend
pip install -r requirements.txt          # add: --extra-index-url https://download.pytorch.org/whl/cpu torch   (smaller CPU build)
python -m uvicorn app.main:app --reload --port 8000

# frontend (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Open **Upload & Analysis**, load a dataset (e.g. *BGL (Loghub 2k)* downloads real data, or a bundled *Synthetic* demo) or drop your own file, and press **Start analysis**.
No API key is needed. Sentence‑Transformer weights (`all-MiniLM-L6-v2`) download on first use; if unavailable the app falls back to a **clearly labelled** LSA approximation.

### Docker
```bash
cp .env.example .env
docker compose up --build        # UI http://localhost:8080 · API http://localhost:8000/docs · PostgreSQL included
```

### Tests
```bash
cd backend && python -m pytest            # 48 tests: parsing, preprocessing, templates, features, clustering, anomalies, RCA, API, DB, validation
cd frontend && npm test && npx tsc --noEmit
```

### Reproduce the experiments
```bash
cd backend && python scripts/run_experiments.py      # downloads Loghub samples, writes docs/experiments.md
```

## Project layout
```
backend/app/{api,core,database,models,schemas,services,utils}
backend/app/pipelines/{ingestion,parsing,preprocessing,templates,features,clustering,anomaly_detection,root_cause,summarization,evaluation}
backend/{tests,migrations,scripts,sample_data}
frontend/src/{components,pages,layouts,charts,services,hooks,types,utils}
docs/{architecture,dataset,methodology,experiments,api,testing,deployment}.md
```
`_legacy_mern/` holds the earlier Node/Express prototype; it is unused and can be deleted.

## Configuration
See `.env.example`: database URL, CORS, upload limit, rate limit, masking rules, embedding model, optional `LLM_PROVIDER`/`LLM_API_KEY` (openai | gemini). The LLM only receives a structured fact sheet and its output is rejected if it introduces numbers not in the facts.

## Demonstration workflow
1. Upload & Analysis → *BGL (Loghub 2k)* → Start analysis (≈1 min with embeddings on first run).
2. Overview: counts, timeline, severity, top clusters. 3. Cluster Explorer → open a cluster (template, trend, priority explanation, logs). 4. Anomaly Center → select an anomaly (reason, impact, logs). 5. Root‑Cause Insights → evidence, potential causes, investigation steps. 6. Model Evaluation → TF‑IDF vs embeddings × DBSCAN/HDBSCAN/K‑Means, run your own parameters. 7. Reports → PDF/CSV/JSON.

## Known limitations
- Authentication is not enforced (a `users` table is provisioned). Rate limiting is in‑memory per process.
- Background jobs run in an in‑process thread pool; jobs interrupted by a restart are marked failed. Use a task queue (Celery/RQ) for multi‑instance production.
- Clustering runs on unique normalized messages; very large files rely on that dedup. The comparison grid is capped to the 4,000 most frequent unique messages by default.
- Syslog timestamps carry no year (year 2000 is assumed); mixed-year data disables fine time buckets.
- Root-cause categories come from a transparent keyword knowledge base plus temporal precedence — correlation, not causation.
- Frontend `node_modules` must be installable on your machine; see Troubleshooting in `docs/deployment.md`.
