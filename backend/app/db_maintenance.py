from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict

from .database import engine
from .system_settings import load_system_settings, save_system_settings

DB_MAINTENANCE_ENABLED = (os.getenv("DB_MAINTENANCE_ENABLED") or "1").strip().lower() in {"1", "true", "yes", "on"}
DB_MAINTENANCE_INTERVAL_HOURS = float(os.getenv("DB_MAINTENANCE_INTERVAL_HOURS", "24"))
DB_MAINTENANCE_KEY = "db_maintenance"
DB_MAINTENANCE_TABLES = [
    "audit_events",
    "case_requests",
    "custodians",
    "searches",
    "case_consents",
    "case_notes",
    "ntp_reminders",
]

_state_lock = threading.Lock()
_scheduler_started = False
_state: Dict[str, Any] = {
    "enabled": DB_MAINTENANCE_ENABLED,
    "interval_hours": DB_MAINTENANCE_INTERVAL_HOURS,
    "last_started_at": None,
    "last_finished_at": None,
    "last_status": None,
    "last_error": None,
    "last_source": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_state() -> None:
    try:
        settings = load_system_settings()
        settings[DB_MAINTENANCE_KEY] = {
            "last_started_at": _state.get("last_started_at"),
            "last_finished_at": _state.get("last_finished_at"),
            "last_status": _state.get("last_status"),
            "last_error": _state.get("last_error"),
            "last_source": _state.get("last_source"),
        }
        save_system_settings(settings)
    except Exception:
        # best effort persistence only
        pass


def run_db_maintenance_once(*, source: str = "manual") -> Dict[str, Any]:
    with _state_lock:
        _state["last_started_at"] = _now_iso()
        _state["last_status"] = "running"
        _state["last_error"] = None
        _state["last_source"] = source

    tables_done = []
    try:
        with engine.begin() as conn:
            for table in DB_MAINTENANCE_TABLES:
                conn.exec_driver_sql(f"ANALYZE {table};")
                tables_done.append(table)
        with _state_lock:
            _state["last_finished_at"] = _now_iso()
            _state["last_status"] = "completed"
            _state["last_error"] = None
        _persist_state()
        return {
            "status": "completed",
            "source": source,
            "tables": tables_done,
            "started_at": _state.get("last_started_at"),
            "finished_at": _state.get("last_finished_at"),
        }
    except Exception as exc:
        with _state_lock:
            _state["last_finished_at"] = _now_iso()
            _state["last_status"] = "failed"
            _state["last_error"] = str(exc)
        _persist_state()
        return {
            "status": "failed",
            "source": source,
            "tables": tables_done,
            "error": str(exc),
            "started_at": _state.get("last_started_at"),
            "finished_at": _state.get("last_finished_at"),
        }


def get_db_maintenance_status() -> Dict[str, Any]:
    try:
        settings = load_system_settings()
        persisted = settings.get(DB_MAINTENANCE_KEY) or {}
    except Exception:
        persisted = {}
    with _state_lock:
        out = dict(_state)
    for key in ("last_started_at", "last_finished_at", "last_status", "last_error", "last_source"):
        if not out.get(key) and persisted.get(key) is not None:
            out[key] = persisted.get(key)
    return out


def start_db_maintenance_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    if not DB_MAINTENANCE_ENABLED:
        return

    interval_seconds = max(300.0, DB_MAINTENANCE_INTERVAL_HOURS * 3600.0)

    def _worker() -> None:
        while True:
            try:
                run_db_maintenance_once(source="scheduled")
            except Exception:
                pass
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_worker, daemon=True, name="db-maintenance-scheduler")
    thread.start()
