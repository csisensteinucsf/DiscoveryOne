from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .app_branding import app_display_name, branded_subject
from .audit import log_event
from .database import SessionLocal
from .emailer import mail_provider_ready, send_email
from .login_history import last_login_map
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings, save_system_settings

_ACCOUNT_REVIEW_STARTED = False
_ACCOUNT_REVIEW_SETTINGS_KEY = "account_review"
_DEFAULT_INTERVAL_DAYS = 120
_DEFAULT_CHECK_INTERVAL_HOURS = 12.0


def _review_settings() -> dict:
    settings = load_system_settings()
    block = settings.get(_ACCOUNT_REVIEW_SETTINGS_KEY) or {}
    if not isinstance(block, dict):
        block = {}
    return block


def _review_enabled() -> bool:
    block = _review_settings()
    enabled = block.get("enabled")
    if enabled is None:
        return True
    return bool(enabled)


def _review_interval_days() -> int:
    block = _review_settings()
    try:
        return max(1, min(3650, int(block.get("interval_days") or _DEFAULT_INTERVAL_DAYS)))
    except Exception:
        return _DEFAULT_INTERVAL_DAYS


def _review_check_interval_seconds() -> float:
    block = _review_settings()
    try:
        hours = float(block.get("check_interval_hours") or _DEFAULT_CHECK_INTERVAL_HOURS)
    except Exception:
        hours = _DEFAULT_CHECK_INTERVAL_HOURS
    return max(3600.0, min(168.0 * 3600.0, hours * 3600.0))


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _last_sent_at() -> Optional[datetime]:
    return _parse_dt((_review_settings().get("last_sent_at") or None))


def _mark_sent(sent_at: datetime) -> None:
    settings = load_system_settings()
    block = settings.get(_ACCOUNT_REVIEW_SETTINGS_KEY) or {}
    if not isinstance(block, dict):
        block = {}
    block["last_sent_at"] = sent_at.astimezone(timezone.utc).isoformat()
    block.setdefault("enabled", True)
    block.setdefault("interval_days", _review_interval_days())
    settings[_ACCOUNT_REVIEW_SETTINGS_KEY] = block
    save_system_settings(settings)


def _role_label(user: models.User) -> str:
    role = (getattr(user, "role", None) or ("sys_admin" if getattr(user, "is_admin", False) else "analyst") or "").strip()
    return role or "analyst"


def _display_name(user: models.User) -> str:
    first = (getattr(user, "first_name", None) or "").strip()
    last = (getattr(user, "last_name", None) or "").strip()
    full = " ".join(part for part in (first, last) if part)
    return full or (getattr(user, "username", None) or "").strip() or f"User {getattr(user, 'id', '?')}"


def _sys_admin_recipients(db: Session) -> list[str]:
    rows = (
        db.query(models.User.email)
        .filter(models.User.email.isnot(None))
        .filter(
            (func.lower(func.coalesce(models.User.role, "")) == "sys_admin")
            | (models.User.is_admin.is_(True))
        )
        .all()
    )
    recipients: list[str] = []
    seen: set[str] = set()
    for (email,) in rows:
        addr = (email or "").strip()
        if not addr:
            continue
        key = addr.lower()
        if key in seen:
            continue
        seen.add(key)
        recipients.append(addr)
    return recipients


def _account_rows(db: Session) -> list[dict]:
    users = db.query(models.User).order_by(models.User.username.asc(), models.User.id.asc()).all()
    login_map = last_login_map(db, [getattr(user, "id", None) for user in users if getattr(user, "id", None) is not None])

    items: list[dict] = []
    for user in users:
        user_id = getattr(user, "id", None)
        last_login = login_map.get(str(user_id)) if user_id is not None else None
        items.append(
            {
                "id": user_id,
                "name": _display_name(user),
                "username": (getattr(user, "username", None) or "").strip(),
                "email": (getattr(user, "email", None) or "").strip() or None,
                "role": _role_label(user),
                "local_auth_only": bool(getattr(user, "local_auth_only", False)),
                "last_login": last_login,
            }
        )
    return items


def _fmt_dt(value: Optional[datetime]) -> str:
    if not value:
        return "Never"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _build_review_email(*, items: list[dict], interval_days: int, generated_at: datetime) -> tuple[str, str]:
    date_label = generated_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
    subject = branded_subject(f"Account access review required ({date_label})")
    lines = [
        f"{app_display_name()} account review reminder.",
        "",
        f"This review is sent every {interval_days} days to system administrators.",
        "Please review each account below and confirm the user still requires access, the assigned role is still appropriate, and any local-only account still has a justified business need.",
        "If access is no longer required, remove the account or reduce privileges in System > Users.",
        "",
        f"Generated: {_fmt_dt(generated_at)}",
        f"Account count: {len(items)}",
        "",
        "Accounts:",
    ]
    for item in items:
        lines.append(
            "- "
            + " | ".join(
                [
                    item.get("name") or item.get("username") or "(unnamed)",
                    item.get("email") or item.get("username") or "(no email)",
                    f"role={item.get('role') or 'analyst'}",
                    f"local_only={'yes' if item.get('local_auth_only') else 'no'}",
                    f"last_login={_fmt_dt(item.get('last_login'))}",
                ]
            )
        )
    lines.extend([
        "",
        "Review checklist:",
        f"- Confirm the person or service account still requires {app_display_name()} access.",
        "- Confirm the assigned role matches least privilege.",
        "- Confirm local-only authentication remains necessary where enabled.",
        "- Remove accounts that are no longer authorized.",
        "",
        app_display_name(),
    ])
    return subject, "\n".join(lines)


def send_account_review_if_due(*, force: bool = False) -> bool:
    if not _review_enabled():
        return False

    if not mail_provider_ready():
        return False

    interval_days = _review_interval_days()
    now = datetime.now(timezone.utc)
    last_sent_at = _last_sent_at()
    if not force and last_sent_at and now < (last_sent_at + timedelta(days=interval_days)):
        return False

    db = SessionLocal()
    try:
        recipients = _sys_admin_recipients(db)
        if not recipients:
            return False
        items = _account_rows(db)
        subject, body = _build_review_email(items=items, interval_days=interval_days, generated_at=now)
        send_email(
            recipients=recipients,
            subject=subject,
            body=body,
            audit_log=False,
        )
        _mark_sent(now)
        try:
            log_event(
                db,
                action="account_review_email_sent",
                actor_id=None,
                target_type="user",
                target_id=None,
                details={
                    "recipient_count": len(recipients),
                    "recipients": recipients,
                    "account_count": len(items),
                    "interval_days": interval_days,
                    "sent_at": now.isoformat(),
                    "sample": [
                        {
                            "id": item.get("id"),
                            "username": item.get("username"),
                            "email": item.get("email"),
                            "role": item.get("role"),
                            "last_login": item.get("last_login").isoformat() if item.get("last_login") else None,
                        }
                        for item in items[:25]
                    ],
                },
                request=None,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in account_reviews.py:audit", exc)
        return True
    finally:
        try:
            db.close()
        except Exception as exc:
            _debug_suppressed("suppressed exception in account_reviews.py:close", exc)


def start_account_review_scheduler() -> None:
    global _ACCOUNT_REVIEW_STARTED
    if _ACCOUNT_REVIEW_STARTED:
        return
    _ACCOUNT_REVIEW_STARTED = True

    def _worker() -> None:
        while True:
            try:
                send_account_review_if_due()
                time.sleep(_review_check_interval_seconds())
            except Exception as exc:  # pragma: no cover
                print(f"[account review] scheduler failure: {exc}")
                time.sleep(3600)

    thread = threading.Thread(target=_worker, daemon=True, name="account-review-scheduler")
    thread.start()
