import os
import sys
from glob import glob
from pathlib import Path
from sqlalchemy import create_engine, text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

CORE_DATA_TABLES = (
    "users",
    "cases",
    "custodians",
    "case_requests",
    "searches",
    "audit_events",
)


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(text("SELECT to_regclass(:table_name) IS NOT NULL"), {"table_name": f"public.{table_name}"}).scalar()
    )


def _table_has_rows(conn, table_name: str) -> bool:
    if not _table_exists(conn, table_name):
        return False
    return bool(conn.execute(text(f"SELECT EXISTS (SELECT 1 FROM {table_name} LIMIT 1)")).scalar())


def _has_applied_migrations(conn) -> bool:
    if not _table_exists(conn, "migrations"):
        return False
    return bool(conn.execute(text("SELECT EXISTS (SELECT 1 FROM migrations LIMIT 1)")).scalar())


def _looks_like_empty_install(engine) -> bool:
    """
    Treat an empty database, including one that got baseline tables during a
    failed first startup, as a fresh install. Fresh installs should use the
    current ORM schema and should not replay old data backfill migrations.
    """
    with engine.begin() as conn:
        if _has_applied_migrations(conn):
            return False
        return not any(_table_has_rows(conn, table) for table in CORE_DATA_TABLES)


def create_baseline_schema(engine) -> None:
    """
    Fresh installs need the ORM baseline tables before legacy additive SQL
    migrations run. Older deployments already have these tables, so this is
    intentionally idempotent.
    """
    from app.models import Base

    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
              id BIGSERIAL PRIMARY KEY,
              actor_id    INTEGER,
              action      TEXT NOT NULL,
              target_type TEXT,
              target_id   INTEGER,
              details     JSONB,
              request_ip  TEXT,
              user_agent TEXT,
              created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              event_hash TEXT
            );
            CREATE INDEX IF NOT EXISTS audit_events_created_at_idx ON audit_events (created_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS audit_events_actor_id_idx   ON audit_events (actor_id);
            CREATE INDEX IF NOT EXISTS audit_events_target_idx     ON audit_events (target_type, target_id);
            CREATE UNIQUE INDEX IF NOT EXISTS audit_events_event_hash_idx ON audit_events (event_hash);
            """
        )


def mark_migrations_applied(engine, files) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
        )
        for path in files:
            conn.execute(
                text("INSERT INTO migrations (filename) VALUES (:f) ON CONFLICT (filename) DO NOTHING"),
                {"f": Path(path).name},
            )


def main() -> None:
    disable = (os.getenv("DISABLE_AUTO_MIGRATIONS") or "").lower() in {"1", "true", "yes", "on"}
    if disable:
        print("[migrations] Skipped (DISABLE_AUTO_MIGRATIONS set).")
        return

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[migrations] Skipped (DATABASE_URL not set).")
        return

    migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
    files = sorted(glob(str(migrations_dir / "*.sql")))
    if not files:
        print("[migrations] No migrations found.")
        return

    engine = create_engine(db_url, future=True)
    empty_install = _looks_like_empty_install(engine)
    create_baseline_schema(engine)
    if empty_install:
        mark_migrations_applied(engine, files)
        print(f"[migrations] Fresh install: created baseline schema and recorded {len(files)} migration(s) as applied.")
        return

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())"
        )
        applied = {row[0] for row in conn.execute(text("SELECT filename FROM migrations"))}
        to_apply = [f for f in files if Path(f).name not in applied]

        if not to_apply:
            print("[migrations] No pending migrations.")
            return

        print(f"[migrations] Applying {len(to_apply)} migration(s)...")
        for path in to_apply:
            fname = Path(path).name
            sql = Path(path).read_text(encoding="utf-8")
            conn.exec_driver_sql(sql)
            conn.execute(text("INSERT INTO migrations (filename) VALUES (:f)"), {"f": fname})
            print(f"[migrations] Applied {fname}")
        print("[migrations] Done.")


if __name__ == "__main__":
    main()
