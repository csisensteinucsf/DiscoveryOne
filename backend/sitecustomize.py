# backend/sitecustomize.py
# Zero‑touch auto‑migrate: Python auto-imports `sitecustomize` if present on sys.path.
# This runs before Uvicorn starts, applies DB migrations once the DB is reachable.
import os, time, logging, importlib

AUTO = os.getenv("AUTO_MIGRATE", "1") not in {"0", "false", "False"}
RETRIES = int(os.getenv("AUTO_MIGRATE_RETRIES", "60"))
DELAY = float(os.getenv("AUTO_MIGRATE_DELAY", "1.5"))

log = logging.getLogger("sitecustomize.migrations")
if AUTO:
    try:
        app_migrations = importlib.import_module("app.migrations")
        app_database = importlib.import_module("app.database")
        engine = getattr(app_database, "engine", None)
        if engine is None:
            raise RuntimeError("app.database.engine is not available")
        ok = False
        for _ in range(RETRIES):
            try:
                with engine.begin() as conn:
                    conn.execute(app_migrations.text("SELECT 1"))
                ok = True
                break
            except Exception:
                time.sleep(DELAY)
        if ok:
            app_migrations.apply_migrations(engine)
            log.info("Auto-migrations completed.")
        else:
            log.warning("DB not reachable after retries; skipping auto-migrations.")
    except Exception as e:
        log.debug("sitecustomize auto-migrate disabled or not applicable: %s", e)
