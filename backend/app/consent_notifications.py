from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from .safe_log import debug_suppressed as _debug_suppressed

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .app_branding import app_display_name, branded_subject
from .audit import log_event
from .database import SessionLocal
from .emailer import mail_provider_ready, send_email
from .notifications import _app_base_url, _send_teams_notification
from .system_settings import load_system_settings

_WEEKLY_STARTED = False


def _consent_notification_settings() -> dict:
    try:
        notifications = load_system_settings().get("notifications") or {}
        block = notifications.get("consent_notifications") or {}
    except Exception:
        block = {}
    return block if isinstance(block, dict) else {}


def _bounded_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def consent_completed_email_enabled() -> bool:
    return bool(_consent_notification_settings().get("completed_email_enabled", True))


def consent_weekly_pending_enabled() -> bool:
    return bool(_consent_notification_settings().get("weekly_pending_enabled", True))


def consent_weekly_schedule() -> dict:
    settings = _consent_notification_settings()
    return {
        "weekday": _bounded_int(settings.get("weekly_weekday"), 4, minimum=0, maximum=6),
        "hour": _bounded_int(settings.get("weekly_hour"), 8, minimum=0, maximum=23),
        "minute": _bounded_int(settings.get("weekly_minute"), 0, minimum=0, maximum=59),
        "timezone": str(settings.get("weekly_timezone") or "UTC").strip() or "UTC",
    }


def _tz() -> timezone | object:
    name = consent_weekly_schedule()["timezone"]
    if not name or name.upper() == "UTC":
        return timezone.utc
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _next_weekday_morning(
    *,
    now: datetime,
    weekday: int,
    hour: int,
    minute: int,
    tzinfo,
) -> datetime:
    if now.tzinfo is None:
        now = now.replace(tzinfo=tzinfo)
    now_local = now.astimezone(tzinfo)
    target = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - target.weekday()) % 7
    if days_ahead == 0 and target <= now_local:
        days_ahead = 7
    return target + timedelta(days=days_ahead)


def _analyst_display(user: Optional[models.User]) -> str:
    if not user:
        return ""
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    full = " ".join(x for x in (first, last) if x)
    return full or (getattr(user, "username", "") or "").strip()


def notify_case_analyst_consent_completed(
    db: Session,
    *,
    consent: models.CaseConsent,
    request=None,
) -> None:
    if not consent_completed_email_enabled():
        return
    if not mail_provider_ready():
        return

    case_id = getattr(consent, "case_id", None)
    if not case_id:
        return
    case = db.get(models.Case, case_id)
    if not case:
        return
    analyst = getattr(case, "analyst", None)
    if not analyst and getattr(case, "analyst_id", None):
        try:
            analyst = db.get(models.User, case.analyst_id)
        except Exception:
            analyst = None
    analyst_email = (getattr(analyst, "email", None) or "").strip()
    if not analyst_email:
        return

    case_label = getattr(case, "name", None) or f"Case #{case_id}"
    custodian_name = (getattr(consent, "custodian_name", None) or "").strip()
    custodian_email = (getattr(consent, "custodian_email", None) or "").strip()
    request_id = (getattr(consent, "request_id", None) or "").strip()
    provider = (getattr(consent, "provider", None) or "").strip()
    record_type = (getattr(consent, "record_type", None) or "").strip()
    date_from = (getattr(consent, "date_from", None) or "").strip()
    date_to = (getattr(consent, "date_to", None) or "").strip()

    link = None
    try:
        base = _app_base_url(request)
        link = f"{base}/cases/{case_id}"
    except Exception:
        link = None

    subject = branded_subject(f"Consent completed for {case_label}")
    lines = [
        "An e-signature consent request was completed.",
        "",
        f"Case: {case_label} (ID: {case_id})",
    ]
    if custodian_name or custodian_email:
        lines.append(f"Custodian: {custodian_name} <{custodian_email}>" if custodian_email else f"Custodian: {custodian_name}")
    if record_type:
        lines.append(f"Record type: {record_type}")
    if date_from or date_to:
        lines.append(f"Date range: {date_from or '-'} to {date_to or '-'}")
    if request_id:
        lines.append(f"Request ID: {request_id}")
    if link:
        lines.extend(["", f"Open case: {link}"])
    lines.extend(["", app_display_name()])
    body = "\n".join(lines)
    send_email(recipients=[analyst_email], subject=subject, body=body, audit_log=False)
    try:
        log_event(
            db,
            action="consent_completed_email_sent",
            actor_id=None,
            target_type="consent",
            target_id=getattr(consent, "id", None),
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "consent_id": getattr(consent, "id", None),
                "provider": provider or None,
                "request_id": request_id or None,
                "envelope_id": request_id or None,
                "status": (getattr(consent, "status", None) or "").strip() or None,
                "custodian_id": getattr(consent, "custodian_id", None),
                "custodian_name": custodian_name or None,
                "custodian_email": custodian_email or None,
                "recipient": analyst_email,
                "recipient_display": _analyst_display(analyst) or None,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in consent_notifications.py:149", exc)
    try:
        _send_teams_notification(
            "consent_completed",
            {
                "case_id": case_id,
                "case_label": case_label,
                "case_name": case_label,
                "legal_case_name": (getattr(case, "legal_case_name", None) or "").strip(),
                "custodian_name": custodian_name or "",
                "custodian_email": custodian_email or "",
                "record_type": record_type or "",
                "date_from": date_from or "",
                "date_to": date_to or "",
                "provider": provider,
                "request_id": request_id,
                "envelope_id": request_id,
                "status": (getattr(consent, "status", None) or "").strip(),
                "case_link": link or "",
            },
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in consent_notifications.py:169", exc)


def _weekly_pending_summary() -> None:
    if not consent_weekly_pending_enabled():
        return
    if not mail_provider_ready():
        return

    db = SessionLocal()
    try:
        rows = (
            db.query(models.CaseConsent, models.Case, models.User)
            .join(models.Case, models.Case.id == models.CaseConsent.case_id)
            .outerjoin(models.User, models.User.id == models.Case.analyst_id)
            .filter(models.Case.closed.is_(False))
            .filter(models.CaseConsent.case_id.isnot(None))
            .filter(func.lower(func.coalesce(models.CaseConsent.status, "")).in_(("sent", "delivered")))
            .order_by(models.Case.id.asc(), models.CaseConsent.sent_at.asc().nulls_last(), models.CaseConsent.id.asc())
            .all()
        )
        if not rows:
            return

        by_analyst: dict[str, list[tuple[models.CaseConsent, models.Case]]] = defaultdict(list)
        for consent, case, analyst in rows:
            email = (getattr(analyst, "email", None) or "").strip()
            if not email:
                continue
            by_analyst[email].append((consent, case))

        if not by_analyst:
            return

        link_base = None
        try:
            link_base = _app_base_url()
        except Exception:
            link_base = None

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for analyst_email, items in by_analyst.items():
            subject = branded_subject(f"Weekly pending consents ({today})")
            lines = [
                "Weekly summary of pending e-signature consents (status: Sent/Delivered) for your open cases.",
                "",
            ]
            for consent, case in items:
                case_id = getattr(case, "id", None)
                case_name = getattr(case, "name", None) or (f"Case #{case_id}" if case_id else "Case")
                status = (getattr(consent, "status", None) or "").strip()
                cust_name = (getattr(consent, "custodian_name", None) or "").strip()
                cust_email = (getattr(consent, "custodian_email", None) or "").strip()
                request_id = (getattr(consent, "request_id", None) or "").strip()
                sent_at = getattr(consent, "sent_at", None)
                updated_at = getattr(consent, "updated_at", None)

                lines.append(f"- {case_name} (ID: {case_id})")
                if cust_name or cust_email:
                    lines.append(f"  Custodian: {cust_name} <{cust_email}>" if cust_email else f"  Custodian: {cust_name}")
                lines.append(f"  Status: {status or '-'}")
                if sent_at:
                    lines.append(f"  Sent: {sent_at}")
                if updated_at:
                    lines.append(f"  Last update: {updated_at}")
                if request_id:
                    lines.append(f"  Request ID: {request_id}")
                if link_base and case_id:
                    lines.append(f"  Link: {link_base}/cases/{case_id}")
                lines.append("")

            lines.extend([app_display_name()])
            body = "\n".join(lines).rstrip() + "\n"
            send_email(recipients=[analyst_email], subject=subject, body=body, audit_log=False)
            try:
                sample: list[dict] = []
                for consent, case in (items[:25] if items else []):
                    sample.append(
                        {
                            "case_id": getattr(case, "id", None),
                            "case_name": getattr(case, "name", None),
                            "consent_id": getattr(consent, "id", None),
                            "status": (getattr(consent, "status", None) or "").strip() or None,
                            "custodian_id": getattr(consent, "custodian_id", None),
                            "custodian_name": (getattr(consent, "custodian_name", None) or "").strip() or None,
                            "custodian_email": (getattr(consent, "custodian_email", None) or "").strip() or None,
                            "provider": (getattr(consent, "provider", None) or "").strip() or None,
                            "request_id": (getattr(consent, "request_id", None) or "").strip() or None,
                            "envelope_id": (getattr(consent, "envelope_id", None) or "").strip() or None,
                        }
                    )
                log_event(
                    db,
                    action="consent_weekly_pending_email_sent",
                    actor_id=None,
                    target_type=None,
                    target_id=None,
                    details={
                        "recipient": analyst_email,
                        "pending_count": len(items),
                        "sample": sample,
                    },
                    request=None,
                )
            except Exception as exc:
                _debug_suppressed("suppressed exception in consent_notifications.py:273", exc)
    finally:
        try:
            db.close()
        except Exception as exc:
            _debug_suppressed("suppressed exception in consent_notifications.py:278", exc)


def start_weekly_pending_consent_scheduler() -> None:
    global _WEEKLY_STARTED
    if _WEEKLY_STARTED:
        return
    _WEEKLY_STARTED = True

    def _worker() -> None:
        while True:
            try:
                schedule = consent_weekly_schedule()
                tzinfo = _tz()
                now = datetime.now(timezone.utc)
                next_run = _next_weekday_morning(
                    now=now,
                    weekday=schedule["weekday"],
                    hour=schedule["hour"],
                    minute=schedule["minute"],
                    tzinfo=tzinfo,
                )
                sleep_for = max(1.0, (next_run.astimezone(timezone.utc) - now).total_seconds())
                time.sleep(sleep_for)
                _weekly_pending_summary()
            except Exception as exc:  # pragma: no cover
                print(f"[consents] weekly scheduler failure: {exc}")
                time.sleep(3600)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
