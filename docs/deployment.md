# Deployment & troubleshooting

**Docker Compose** (`docker-compose.yml`): `db` (PostgreSQL 16), `backend` (runs `alembic upgrade head`, then uvicorn), `frontend` (nginx serving the build and proxying `/api` to the backend). Set `POSTGRES_PASSWORD`, `CORS_ORIGINS`, optional LLM variables in `.env`. The Docker build was not executed in the authoring environment; run `docker compose up --build` and report issues.

**Split hosting**
- Frontend → Vercel (root `frontend/`, build `npm run build`, output `dist`, env `VITE_API_URL=https://<backend>`); `vercel.json` rewrites SPA routes.
- Backend → any container host (Render/Railway/Fly.io) using `backend/Dockerfile`; set `DATABASE_URL=postgresql+psycopg://...` (managed PostgreSQL), `CORS_ORIGINS=<frontend origin>`, a persistent volume for `/app/data` (uploads, embedding cache, HF model cache). Allow ≥2 GB RAM for sentence-transformers or set `EMBEDDINGS_ENABLED=false`.
- Multi-instance deployments need a shared job queue and rate limiter (not provided).

**Troubleshooting**
- `ENOSPC` / `parser.ps1 ENOENT` during `npm install` on Windows: the drive is full or a shim write failed; free space or install `node_modules` on another drive and junction it.
- Embeddings fall back to LSA: no internet / HF blocked; the UI warns on the Evaluation page.
- Large files: limit is `MAX_UPLOAD_MB` (default 50).
