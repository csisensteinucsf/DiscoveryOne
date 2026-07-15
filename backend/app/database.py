# backend/app/database.py
# Central SQLAlchemy engine/session with sane pool defaults for bulk ops.
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from .safe_log import debug_suppressed as _debug_suppressed

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI") or "postgresql+psycopg://postgres:postgres@db:5432/postgres"

# Declarative Base exported for models.py
Base = declarative_base()

# Pool tuning (env-overridable)
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "15"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 minutes
PRE_PING = True

connect_args = {}
is_sqlite = DATABASE_URL.startswith("sqlite")
# SQLite dev/test fallback (not used in prod normally)
if is_sqlite:
    connect_args = {"check_same_thread": False}

engine_kwargs = {
    "future": True,
    "connect_args": connect_args,
}

if is_sqlite:
    # SQLite doesn't support the same pool sizing knobs as Postgres/MySQL and will
    # raise on invalid pool args. For in-memory SQLite, use a StaticPool so the
    # database persists across connections within a process.
    if DATABASE_URL in {"sqlite:///:memory:", "sqlite://"}:
        engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs.update(
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=PRE_PING,
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # avoid stale state churn on large batches
    bind=engine,
)

def get_db():
    """FastAPI dependency. ALWAYS closes the session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception as exc:
            # defensive: never leak the connection
            _debug_suppressed("suppressed exception in database.py:63", exc)

