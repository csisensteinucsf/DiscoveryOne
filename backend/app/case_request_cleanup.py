import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import or_


_cleanup_scheduler_started = False


def cleanup_old_pending_requests(
    *,
    pending_cleanup_days: float,
    session_factory: Callable[[], Any],
    models: Any,
    remove_attachment: Callable[..., None],
    log_event: Callable[..., None],
    debug_suppressed: Callable[[str, Exception], None],
) -> None:
    if pending_cleanup_days <= 0:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=pending_cleanup_days)
    db = session_factory()
    try:
        rows = (
            db.query(models.CaseRequest)
            .filter(models.CaseRequest.status == "pending")
            .filter(models.CaseRequest.created_at <= cutoff)
            .filter(
                or_(
                    models.CaseRequest.attachment_path.isnot(None),
                    models.CaseRequest.consent_attachment_path.isnot(None),
                )
            )
            .all()
        )
        if not rows:
            return
        removed: list[dict] = []
        for row in rows:
            try:
                removed.append(
                    {
                        "request_id": getattr(row, "id", None),
                        "request_type": getattr(row, "request_type", None),
                        "case_id": getattr(row, "case_id", None),
                        "case_name": getattr(row, "case_name", None),
                        "created_at": str(getattr(row, "created_at", "") or ""),
                        "attachment_removed": bool(getattr(row, "attachment_path", None)),
                        "consent_attachment_removed": bool(getattr(row, "consent_attachment_path", None)),
                        "consent_proofs_removed": len(getattr(row, "consent_proofs", []) or []),
                    }
                )
            except Exception as exc:
                debug_suppressed("suppressed exception in case_request_cleanup.cleanup_old_pending_requests", exc)
            remove_attachment(row, remove_consent_proofs=True)
        db.commit()
        try:
            log_event(
                db,
                action="case_request_cleanup",
                actor_id=None,
                target_type="system",
                target_id=None,
                details={
                    "cutoff_days": pending_cleanup_days,
                    "requests_cleaned": len(removed),
                    "requests": removed,
                },
                request=None,
            )
        except Exception as exc:
            debug_suppressed("suppressed exception in case_request_cleanup.log_event", exc)
    except Exception as exc:
        print(f"[case_request cleanup] failed: {exc}")
        db.rollback()
    finally:
        db.close()


def start_case_request_cleanup(
    *,
    pending_cleanup_days: float,
    pending_cleanup_interval_hours: float,
    cleanup_func: Callable[[], None],
) -> None:
    global _cleanup_scheduler_started
    if _cleanup_scheduler_started:
        return
    if pending_cleanup_days <= 0:
        return

    _cleanup_scheduler_started = True

    def _worker() -> None:
        interval_seconds = max(1.0, pending_cleanup_interval_hours) * 3600
        while True:
            try:
                cleanup_func()
            except Exception as exc:
                print(f"[case_request cleanup] scheduled job failed: {exc}")
            time.sleep(interval_seconds)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
