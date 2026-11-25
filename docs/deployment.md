# Deployment & troubleshooting

**Demo on Render + Vercel (free tiers)**
1. Push the repo to GitHub.
2. Render: *New, Blueprint*, choose the repo. `render.yaml` creates the API (`atlas-api`); create the free PostgreSQL database in the dashboard first and paste its URL when the blueprint asks for DATABASE_URL. The API runs `alembic upgrade head` on start, and the app converts Render's `postgresql://` URL to the `postgresql+psycopg://` form automatically. Open `https://<service>.onrender.com/api/health` to confirm.
3. Vercel: *Add New, Project*, same repo, Root Directory `frontend`, environment variable `VITE_API_URL=https://<service>.onrender.com` (no trailing slash, no `/api`). Deploy.
4. Back on Render, set `CORS_ORIGINS` on `atlas-api` to the exact Vercel URL (no trailing slash) and let it redeploy.
5. To inspect the hosted data, register a server in pgAdmin with the database's *External* connection details from Render.
Demo limits: embeddings are off (512 MB RAM), the free API sleeps after 15 idle minutes (first request takes about a minute), uploaded files live on an ephemeral disk and disappear on redeploy (add a paid persistent disk at `/app/data` to keep them), the free database expires after 30 days, and there is no login, so everyone sees every analysis.

**Docker Compose** (`docker-compose.yml`): `db` (PostgreSQL 16), `backend` (runs `alembic upgrade head`, then uvicorn), `frontend` (nginx serving the build and proxying `/api` to the backend). Set `POSTGRES_PASSWORD`, `CORS_ORIGINS`, optional LLM variables in `.env`. The Docker build was not executed in the authoring environment; run `docker compose up --build` and report issues.

**Split hosting**
- Frontend → Vercel (root `frontend/`, build `npm run build`, output `dist`, env `VITE_API_URL=https://<backend>`); `vercel.json` rewrites SPA routes.
- Backend → any container host (Render/Railway/Fly.io) using `backend/Dockerfile`; set `DATABASE_URL=postgresql+psycopg://...` (managed PostgreSQL), `CORS_ORIGINS=<frontend origin>`, a persistent volume for `/app/data` (uploads, embedding cache, HF model cache). Allow ≥2 GB RAM for sentence-transformers or set `EMBEDDINGS_ENABLED=false`.
- Multi-instance deployments need a shared job queue and rate limiter (not provided).

**Troubleshooting**
- `ENOSPC` / `parser.ps1 ENOENT` during `npm install` on Windows: the drive is full or a shim write failed; free space or install `node_modules` on another drive and junction it.
- Embeddings fall back to LSA: no internet / HF blocked; the UI warns on the Evaluation page.
- Large files: limit is `MAX_UPLOAD_MB` (default 50).
