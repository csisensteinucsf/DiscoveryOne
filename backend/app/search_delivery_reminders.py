from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .database import SessionLocal
from .emailer import mail_provider_ready, send_email
from .notifications import _app_base_url, render_email_template
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings

_SEARCH_DELIVERY_REMINDER_STARTED = False


def _flag(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_value(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(value if value is not None else default).strip() or str(default)
    try:
        parsed = int(raw)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def load_search_delivery_reminder_settings() -> dict[str, int | bool]:
    notifications = load_system_settings().get("notifications") or {}
    raw = notifications.get("search_delivery_reminders") if isinstance(notifications, dict) else {}
    values = raw if isinstance(raw, dict) else {}
    return {
        "enabled": _flag(values.get("enabled"), True),
        "interval_days": _int_value(values.get("interval_days"), 7, minimum=1, maximum=365),
        "loop_seconds": _int_value(values.get("loop_seconds"), 3600, minimum=300, maximum=86400),
        "batch_size": _int_value(values.get("batch_size"), 25, minimum=1, maximum=500),
    }


def _as_utc(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _is_performed(value) -> bool:
    return str(value or "").strip().lower() == "performed"


def _is_delivery_complete(value) -> bool:
    state = str(value or "").strip().lower()
    return state in {"performed", "not required"}


def _eligible_case_ids(db: Session, *, now_utc: datetime, interval_days: int, batch_size: int) -> list[int]:
    rows = (
        db.query(models.Case.id, models.Case.last_search_delivery_reminder_at)
        .join(models.User, models.User.id == models.Case.analyst_id)
        .join(models.Search, models.Search.case_id == models.Case.id)
        .filter(models.Case.closed.is_(False))
        .filter(models.User.email.isnot(None))
        .filter(func.lower(func.coalesce(models.Search.status_export, "")) == "performed")
        .filter(func.lower(func.coalesce(models.Search.status_delivery, "")).notin_(("performed", "not required")))
        .group_by(models.Case.id, models.Case.last_search_delivery_reminder_at)
        .order_by(models.Case.last_search_delivery_reminder_at.asc().nullsfirst(), models.Case.id.asc())
        .limit(batch_size * 4)
        .all()
    )
    due_ids: list[int] = []
    for case_id, last_sent in rows:
        try:
            cid = int(case_id)
        except (TypeError, ValueError):
            continue
        last_utc = _as_utc(last_sent)
        if last_utc is not None:
            if last_utc + timedelta(days=interval_days) > now_utc:
                continue
        due_ids.append(cid)
        if len(due_ids) >= batch_size:
            break
    return due_ids


def _search_label(search: models.Search) -> str:
    name = (getattr(search, "name", None) or "").strip()
    if name:
        return name
    sid = getattr(search, "id", None)
    return f"Search #{sid}" if sid is not None else "Search"


def _format_search_details(searches: list[models.Search]) -> list[str]:
    lines: list[str] = []
    for idx, search in enumerate(searches, start=1):
        lines.append(f"{idx}. {_search_label(search)}")
        lines.append(
            "   Status: "
            f"search={getattr(search, 'status_search', None) or '-'} | "
            f"export={getattr(search, 'status_export', None) or '-'} | "
            f"delivery={getattr(search, 'status_delivery', None) or '-'}"
        )
        keywords = (getattr(search, "keywords", None) or "").strip()
        senders = (getattr(search, "senders", None) or "").strip()
        recipients = (getattr(search, "recipients", None) or "").strip()
        date_from = (getattr(search, "date_from", None) or "").strip()
        date_to = (getattr(search, "date_to", None) or "").strip()
        additional = (getattr(search, "additional", None) or "").strip()
        if keywords:
            lines.append(f"   Keywords: {keywords}")
        if senders:
            lines.append(f"   Senders: {senders}")
        if recipients:
            lines.append(f"   Recipients: {recipients}")
        if date_from or date_to:
            lines.append(f"   Date range: {date_from or '-'} to {date_to or '-'}")
        if additional:
            lines.append(f"   Additional: {additional}")
        if bool(getattr(search, "export_without_consent", False)):
            lines.append("   Note: Export was completed without consent on file.")
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def _send_case_delivery_reminder(
    db: Session,
    *,
    case: models.Case,
    searches: list[models.Search],
    base_url: str | None,
) -> bool:
    analyst = getattr(case, "analyst", None)
    analyst_email = (getattr(analyst, "email", None) or "").strip()
    if not analyst_email:
        return False

    case_id = getattr(case, "id", None)
    case_name = (getattr(case, "name", None) or "").strip() or f"Case #{case_id}"
    legal = (getattr(case, "legal_case_name", None) or "").strip()
    case_title = f"{case_name} ({legal})" if legal else case_name

    case_link = f"{base_url}/cases/{case_id}" if base_url and case_id else ""
    search_details = "\n".join(_format_search_details(searches))
    subject, body = render_email_template(
        "search_delivery_reminder",
        default_subject="[{app_name}] Delivery reminder for {case_name}",
        default_body=(
            "Reminder: this case has exported searches not yet marked for delivery or set to delivery not required.\n\n"
            "Case: {case_title}\n"
            "Case ID: {case_id}\n\n"
            "Please mark delivery complete in {app_name} once delivery has occurred.\n\n"
            "Case link: {case_link}\n\n"
            "Exported but not delivered searches ({search_count}):\n"
            "{search_details}\n\n"
            "{app_name}"
        ),
        context={
            "case_id": case_id or "",
            "case_name": case_name,
            "case_title": case_title,
            "case_link": case_link,
            "search_count": len(searches),
            "search_details": search_details,
            "analyst_email": analyst_email,
        },
    )
    if not subject or not body:
        return False

    send_email(
        recipients=[analyst_email],
        subject=subject,
        body=body,
        audit_log=False,
    )

    try:
        log_event(
            db,
            action="search_delivery_reminder_email_sent",
            actor_id=None,
            target_type="case",
            target_id=case_id,
            details={
                "case_id": case_id,
                "case_name": case_name,
                "analyst_email": analyst_email,
                "search_ids": [getattr(s, "id", None) for s in searches],
                "search_names": [_search_label(s) for s in searches],
                "search_count": len(searches),
            },
            request=None,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in search_delivery_reminders.py:202", exc)
    return True


def _process_search_delivery_reminders() -> None:
    reminder_settings = load_search_delivery_reminder_settings()
    if not reminder_settings["enabled"]:
        return

    if not mail_provider_ready():
        return

    try:
        base_url = _app_base_url()
    except Exception:
        base_url = None

    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        due_case_ids = _eligible_case_ids(
            db,
            now_utc=now_utc,
            interval_days=int(reminder_settings["interval_days"]),
            batch_size=int(reminder_settings["batch_size"]),
        )
        if not due_case_ids:
            return

        cases = (
            db.query(models.Case)
            .filter(models.Case.id.in_(due_case_ids))
            .all()
        )
        case_by_id = {int(getattr(case, "id")): case for case in cases if getattr(case, "id", None) is not None}

        search_rows = (
            db.query(models.Search)
            .filter(models.Search.case_id.in_(due_case_ids))
            .order_by(models.Search.case_id.asc(), models.Search.id.asc())
            .all()
        )
        by_case: dict[int, list[models.Search]] = {}
        for search in search_rows:
            cid = getattr(search, "case_id", None)
            if cid is None:
                continue
            if not (_is_performed(getattr(search, "status_export", None)) and not _is_delivery_complete(getattr(search, "status_delivery", None))):
                continue
            by_case.setdefault(int(cid), []).append(search)

        changed = False
        for case_id in due_case_ids:
            case = case_by_id.get(int(case_id))
            if not case:
                continue
            pending = by_case.get(int(case_id), [])
            if not pending:
                continue
            try:
                sent = _send_case_delivery_reminder(
                    db,
                    case=case,
                    searches=pending,
                    base_url=base_url,
                )
                if sent:
                    case.last_search_delivery_reminder_at = now_utc
                    changed = True
            except Exception as exc:
                print(f"[search delivery reminder] failed for case {case_id}: {exc}")

        if changed:
            db.commit()
    finally:
        db.close()


def start_search_delivery_reminder_scheduler() -> None:
    global _SEARCH_DELIVERY_REMINDER_STARTED
    if _SEARCH_DELIVERY_REMINDER_STARTED:
        return
    _SEARCH_DELIVERY_REMINDER_STARTED = True

    def _worker() -> None:
        while True:
            try:
                _process_search_delivery_reminders()
            except Exception as exc:  # pragma: no cover
                print(f"[search delivery reminder] worker failure: {exc}")
            settings = load_search_delivery_reminder_settings()
            time.sleep(int(settings["loop_seconds"]))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


