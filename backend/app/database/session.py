from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {})
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _pragmas(conn, _):  # concurrency for background jobs writing while the API reads
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """SQLite (dev): create tables directly. Other databases (PostgreSQL): schema is managed by `alembic upgrade head`."""
    from app import models  # noqa: F401  (register tables)
    if _is_sqlite:
        Base.metadata.create_all(engine)
