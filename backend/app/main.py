import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import update

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.ratelimit import RateLimitMiddleware
from app.database.session import SessionLocal, init_db
from app.models import AnalysisJob

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("logmind")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:  # jobs interrupted by a restart can never finish: mark them failed instead of leaving them "running"
        db.execute(update(AnalysisJob).where(AnalysisJob.status.in_(["queued", "running"])).values(status="failed", stage="Failed", error="Interrupted by server restart"))
        db.commit()
    yield


app = FastAPI(title="Atlas", version="1.0.0", lifespan=lifespan,
              description="Server log error clustering, anomaly detection and evidence-based root-cause insights.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"], expose_headers=["Content-Disposition"])
app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
app.include_router(router)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("unhandled error")  # stack trace stays in server logs only
    return JSONResponse({"detail": "Internal server error"}, status_code=500)
