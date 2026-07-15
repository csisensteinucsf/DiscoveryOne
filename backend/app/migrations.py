# backend/app/migrations.py
"""Idempotent DB bootstrap + .sql migration runner (Postgres + SQLAlchemy)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import text, inspect
from sqlalchemy.engine import Engine
from .safe_log import debug_suppressed as _debug_suppressed

logger = logging.getLogger(__name__)

# `backend/migrations` directory
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
APPLY_MIGRATIONS = os.getenv("APPLY_MIGRATIONS", "1") not in {"0", "false", "False"}
ADVISORY_LOCK_KEY = int(os.getenv("MIGRATIONS_LOCK_KEY", "4281731"))


def _sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _iter_sql_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        logger.info("No migrations dir at %s", MIGRATIONS_DIR)
        return []
    return sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file())


def _ensure_tracking_table(engine: Engine) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        filename   TEXT PRIMARY KEY,
        checksum   TEXT NOT NULL,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    with engine.begin() as conn:
        conn.execute(text(sql))


def _get_applied(engine: Engine) -> dict[str, tuple[str, str]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT filename, checksum, to_char(applied_at, 'YYYY-MM-DD""T""HH24:MI:SSZ') FROM schema_migrations")
        ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def _advisory_lock(conn) -> None:
    conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY})


def _advisory_unlock(conn) -> None:
    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})


def _try_get_base() -> Optional[object]:
    try:
        from .models import Base as ModelsBase  # type: ignore
        return ModelsBase
    except Exception as exc:
        _debug_suppressed("suppressed exception in migrations.py:65", exc)
    try:
        from .database import Base as DBBase  # type: ignore
        return DBBase
    except Exception as exc:
        _debug_suppressed("suppressed exception in migrations.py:70", exc)
    return None


def _bootstrap_create_all(engine: Engine) -> None:
    inspector = inspect(engine)
    if inspector.get_table_names():
        return
    base = _try_get_base()
    if not base:
        logger.warning("Could not find declarative Base; skipping metadata bootstrap.")
        return
    logger.info("Empty DB detected – creating tables from SQLAlchemy models...")
    base.metadata.create_all(bind=engine)
    logger.info("Metadata create_all complete.")


def apply_migrations(engine: Engine) -> None:
    if not APPLY_MIGRATIONS:
        logger.info("APPLY_MIGRATIONS disabled; skipping migrations.")
        return

    _bootstrap_create_all(engine)

    files = list(_iter_sql_files())
    if not files:
        logger.info("No .sql migrations to apply.")
        return

    _ensure_tracking_table(engine)
    applied = _get_applied(engine)

    to_apply = []
    for f in files:
        digest = _sha256_bytes(f.read_bytes())
        prev = applied.get(f.name)
        if prev:
            prev_digest, _when = prev
            if prev_digest != digest:
                raise RuntimeError(
                    f"Checksum mismatch for already-applied migration {f.name}. "
                    f"Applied={prev_digest}, current={digest}. Add a new migration instead of editing."
                )
        else:
            to_apply.append(f)

    if not to_apply:
        logger.info("All migrations already applied.")
        return

    logger.info("Applying %d migration(s): %s", len(to_apply), ", ".join(p.name for p in to_apply))
    with engine.begin() as conn:
        _advisory_lock(conn)
        try:
            for f in to_apply:
                conn.execute(text(f.read_text()))
                conn.execute(
                    text("INSERT INTO schema_migrations (filename, checksum) VALUES (:fn, :cs)"),
                    {"fn": f.name, "cs": _sha256_bytes(f.read_bytes())},
                )
        finally:
            _advisory_unlock(conn)
    logger.info("Migrations applied successfully.")
