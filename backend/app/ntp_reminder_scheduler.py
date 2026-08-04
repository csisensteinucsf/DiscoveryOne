from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .database import SessionLocal
from .emailer import mail_provider_ready, send_email
from .notifications import _app_base_url
from .runtime_paths import runtime_file
from .safe_log import debug_suppressed as _debug_suppressed

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None

NTP_SCHEDULER_LOCK_FILE = os.getenv("NTP_SCHEDULER_LOCK_FILE", runtime_file("ediscovery_ntp_scheduler.lock"))

_REMINDER_SCHEDULER_STARTED = False
_REMINDER_LOCK_FD: Optional[int] = None


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _handle_reminder_send(
    db: Session,
    reminder: models.NTPReminder,
    base_url: str,
    now: datetime,
) -> None:
    from . import ntp as ntp_helpers

    if reminder.status != "active":
        return
    now = _to_aware_utc(now)
    stop_after = reminder.stop_after
    if stop_after is not None:
        stop_after = _to_aware_utc(stop_after)
    if stop_after and stop_after <= now:
        reminder.status = "completed"
        return
    custodian = reminder.custodian
    case = reminder.case
    template = reminder.template
    if not (custodian and case and template):
        reminder.status = "cancelled"
        return
    hold_membership = getattr(reminder, "hold_custodian", None)
    ntp_status = (
        getattr(hold_membership, "ntp_status", None)
        if hold_membership is not None
        else getattr(custodian, "ntp_status", None)
    )
    if ntp_status and ntp_status.lower() == "acknowledged":
        reminder.status = "completed"
        return
    if not (custodian.email or "").strip():
        reminder.status = "cancelled"
        return
    new_token, token_value = ntp_helpers._create_ntp_token(
        db,
        case_id=case.id,
        custodian_id=custodian.id,
        template_id=template.id,
        hold_custodian_id=getattr(reminder, "hold_custodian_id", None),
    )
    reminder.token_id = new_token.id
    ack_link = ntp_helpers._build_ack_link(base_url, token_value)
    try:
        variables = json.loads(reminder.variables or "{}")
    except Exception:
        variables = {}
    friendly_ack = ntp_helpers._ack_display_url(base_url)
    sanitized_variables = ntp_helpers._normalize_variables(variables or {})
    context = ntp_helpers._build_ntp_context(case, custodian, case.requestor or "", ack_link, friendly_ack, sanitized_variables)
    subject = ntp_helpers._render_template(template.subject, context)
    text_body, html_body = ntp_helpers._render_bodies(template.body, context)
    cc_values = ntp_helpers._merge_cc_lists(getattr(template, "cc", ""), sanitized_variables.get("cc"))
    bcc_values = ntp_helpers._merge_bcc_lists(getattr(template, "bcc", ""), sanitized_variables.get("bcc"))
    recipient_email = ntp_helpers._pretty_email_address(custodian.email)
    try:
        importance = "high" if bool(getattr(template, "high_importance", False)) else None
        archive_copy_sent = bool(bcc_values)
        archive_copy_error = None
        try:
            send_email(
                recipients=[recipient_email],
                subject=subject,
                body=text_body,
                html=html_body,
                cc=cc_values or None,
                bcc=bcc_values or None,
                importance=importance,
                audit_log=False,
            )
        except Exception as exc:
            if bcc_values and not ntp_helpers.ntp_archive_copy_required():
                archive_copy_sent = False
                archive_copy_error = str(exc)
                _debug_suppressed("suppressed exception in ntp_reminder_scheduler.py:_handle_reminder_send_bcc_retry", exc)
                send_email(
                    recipients=[recipient_email],
                    subject=subject,
                    body=text_body,
                    html=html_body,
                    cc=cc_values or None,
                    importance=importance,
                    audit_log=False,
                )
            else:
                raise
    except Exception as exc:
        print(f"[ntp reminder] failed to send reminder {reminder.id}: {exc}")
        return
    reminder.last_sent_at = now
    reminder.send_count = (reminder.send_count or 0) + 1
    next_at = now + timedelta(days=reminder.interval_days or ntp_helpers.ntp_reminder_interval_days())
    if stop_after and next_at >= stop_after:
        reminder.status = "completed"
    else:
        reminder.next_send_at = next_at
    try:
        log_event(
            db,
            action="ntp_reminder_email_sent",
            target_type="custodian",
            target_id=reminder.custodian_id,
            actor_id=None,
            details={
                "reminder_id": reminder.id,
                "custodian_id": reminder.custodian_id,
                "hold_id": getattr(hold_membership, "hold_id", None),
                "hold_custodian_id": getattr(reminder, "hold_custodian_id", None),
                "custodian_name": getattr(custodian, "name", None),
                "custodian_email": recipient_email,
                "case_id": getattr(case, "id", None),
                "case_name": getattr(case, "name", None),
                "template_id": reminder.template_id,
                "template_name": getattr(template, "name", None),
                "bcc_count": len(bcc_values) if bcc_values else 0,
                "archive_copy_recipient": bcc_values[0] if bcc_values else None,
                "archive_copy_recipients": bcc_values,
                "archive_copy_sent": archive_copy_sent,
                "archive_copy_error": archive_copy_error,
            },
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in ntp_reminder_scheduler.py:log_event", exc)


def _process_due_reminders() -> None:
    db = SessionLocal()
    try:
        while True:
            now = datetime.now(timezone.utc)
            reminders = (
                db.query(models.NTPReminder)
                .filter(
                    models.NTPReminder.status == "active",
                    models.NTPReminder.next_send_at <= now,
                )
                .order_by(models.NTPReminder.next_send_at.asc())
                .limit(20)
                .all()
            )
            if not reminders:
                break
            if not mail_provider_ready():
                break
            base_url = _app_base_url()
            for reminder in reminders:
                try:
                    _handle_reminder_send(db, reminder, base_url, now)
                except Exception as exc:
                    print(f"[ntp reminder] error processing reminder {reminder.id}: {exc}")
            db.commit()
    finally:
        db.close()


def _acquire_ntp_scheduler_lock() -> bool:
    global _REMINDER_LOCK_FD
    lock_path = (NTP_SCHEDULER_LOCK_FILE or "").strip()
    if not lock_path or fcntl is None:
        return True
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return True
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _REMINDER_LOCK_FD = fd
        return True
    except (BlockingIOError, OSError):
        try:
            os.close(fd)
        except OSError:
            pass
        return False


def start_ntp_reminder_scheduler() -> None:
    global _REMINDER_SCHEDULER_STARTED
    if _REMINDER_SCHEDULER_STARTED:
        return
    if not _acquire_ntp_scheduler_lock():
        print("[ntp reminder] another process holds the scheduler lock; skipping start")
        return
    _REMINDER_SCHEDULER_STARTED = True

    def _worker():
        from . import ntp as ntp_helpers

        while True:
            try:
                _process_due_reminders()
            except Exception as exc:
                print(f"[ntp reminder] worker failure: {exc}")
            time.sleep(max(30, ntp_helpers.ntp_reminder_loop_seconds()))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
