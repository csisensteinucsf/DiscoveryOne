from __future__ import annotations

import queue
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

JobHandler = Callable[[dict], Any]

_job_handlers: Dict[str, JobHandler] = {}
_job_records: Dict[str, dict] = {}
_job_queue: "queue.Queue[str]" = queue.Queue()
_job_lock = threading.Lock()
_worker_started = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def register_job_handler(job_type: str, handler: JobHandler) -> None:
    if not job_type or not callable(handler):
        raise ValueError("job_type and callable handler are required")
    with _job_lock:
        _job_handlers[job_type] = handler


def _run_job(job_id: str) -> None:
    with _job_lock:
        record = _job_records.get(job_id)
        if not record:
            return
        record["status"] = "running"
        record["started_at"] = _now_iso()
        handler = _job_handlers.get(record.get("job_type") or "")
        payload = deepcopy(record.get("payload") or {})

    if handler is None:
        with _job_lock:
            rec = _job_records.get(job_id)
            if rec:
                rec["status"] = "failed"
                rec["finished_at"] = _now_iso()
                rec["error"] = "No handler registered"
        return

    try:
        result = handler(payload)
        with _job_lock:
            rec = _job_records.get(job_id)
            if rec:
                rec["status"] = "completed"
                rec["finished_at"] = _now_iso()
                rec["result"] = result
    except Exception as exc:
        with _job_lock:
            rec = _job_records.get(job_id)
            if rec:
                rec["status"] = "failed"
                rec["finished_at"] = _now_iso()
                rec["error"] = str(exc)


def _worker() -> None:
    while True:
        job_id = _job_queue.get()
        try:
            _run_job(job_id)
        finally:
            _job_queue.task_done()


def _ensure_worker_started() -> None:
    global _worker_started
    with _job_lock:
        if _worker_started:
            return
        thread = threading.Thread(target=_worker, daemon=True, name="system-job-worker")
        thread.start()
        _worker_started = True


def enqueue_job(job_type: str, payload: Optional[dict] = None, *, actor_id: Optional[int] = None) -> dict:
    if not job_type:
        raise ValueError("job_type is required")
    _ensure_worker_started()
    job_id = uuid4().hex
    record = {
        "job_id": job_id,
        "job_type": job_type,
        "status": "queued",
        "created_at": _now_iso(),
        "started_at": None,
        "finished_at": None,
        "actor_id": actor_id,
        "payload": deepcopy(payload or {}),
        "result": None,
        "error": None,
    }
    with _job_lock:
        _job_records[job_id] = record
    _job_queue.put(job_id)
    return deepcopy(record)


def get_job(job_id: str) -> Optional[dict]:
    with _job_lock:
        rec = _job_records.get(job_id)
        return deepcopy(rec) if rec else None


def list_jobs(*, job_type: Optional[str] = None, limit: int = 100) -> list[dict]:
    safe_limit = max(1, min(int(limit or 100), 1000))
    with _job_lock:
        rows = list(_job_records.values())
    if job_type:
        rows = [r for r in rows if r.get("job_type") == job_type]
    rows.sort(key=lambda r: (r.get("created_at") or "", r.get("job_id") or ""), reverse=True)
    return [deepcopy(r) for r in rows[:safe_limit]]
