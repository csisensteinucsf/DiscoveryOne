import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_hold_status_email_lock = threading.Lock()
_hold_status_email_timers: dict[int, threading.Timer] = {}


def send_case_request_hold_status_email(
    record_id: int,
    custodian_ids: list[int],
    *,
    base_url: Optional[str] = None,
    session_factory,
    models,
    notify_case_request_hold_status: Callable,
    now_ts: Callable[[], str],
    debug_suppressed: Callable[[str, Exception], None],
) -> None:
    if not custodian_ids:
        return
    db = session_factory()
    try:
        record = db.get(models.CaseRequest, record_id)
        if not record:
            return
        notify_case_request_hold_status(
            db,
            record,
            custodian_ids,
            base_url=base_url,
        )
    except Exception as exc:
        logger.warning(
            "case_request_hold_email_failed ts=%s record=%s error=%s",
            now_ts(),
            record_id,
            exc,
        )
    finally:
        try:
            db.close()
        except Exception as exc:
            debug_suppressed("suppressed exception in case_request_hold_emails.send_case_request_hold_status_email", exc)


def schedule_case_request_hold_status_email(
    record_id: int,
    custodian_ids: list[int],
    *,
    base_url: Optional[str] = None,
    delay_seconds: float,
    send_func: Callable[..., None],
    debug_suppressed: Callable[[str, Exception], None],
) -> None:
    if delay_seconds <= 0:
        send_func(record_id, custodian_ids, base_url=base_url)
        return

    def _run() -> None:
        with _hold_status_email_lock:
            _hold_status_email_timers.pop(record_id, None)
        send_func(record_id, custodian_ids, base_url=base_url)

    with _hold_status_email_lock:
        existing = _hold_status_email_timers.get(record_id)
        if existing:
            try:
                existing.cancel()
            except Exception as exc:
                debug_suppressed("suppressed exception in case_request_hold_emails.timer_cancel", exc)
        timer = threading.Timer(delay_seconds, _run)
        timer.daemon = True
        _hold_status_email_timers[record_id] = timer
        timer.start()
