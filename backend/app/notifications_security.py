"""User security and malware notification helpers."""

from __future__ import annotations

from typing import List, Optional

from fastapi import Request

from . import models
from .app_branding import app_administrators_label, app_display_name, branded_subject
from . import notifications as notify_core
from .database import SessionLocal


def user_primary_email(user: Optional[models.User]) -> Optional[str]:
    if not user:
        return None
    email = (getattr(user, "email", None) or "").strip()
    return email or None


def _password_alert() -> str:
    return f"Your {app_display_name()} password was changed. If this wasn't you, contact the {app_administrators_label()} as soon as possible."


def _mfa_alert() -> str:
    return f"Your {app_display_name()} MFA settings were changed. If this wasn't you, contact the {app_administrators_label()} as soon as possible."


def notify_user_password_change(user: models.User) -> None:
    email = user_primary_email(user)
    if not email:
        return
    notify_core._send_notification(
        recipients=[email],
        subject=branded_subject("Your password was changed"),
        body=_password_alert(),
    )


def notify_user_mfa_change(user: models.User) -> None:
    email = user_primary_email(user)
    if not email:
        return
    notify_core._send_notification(
        recipients=[email],
        subject=branded_subject("Your MFA settings were updated"),
        body=_mfa_alert(),
    )


def notify_malware_upload_detected(
    filename: str,
    *,
    detail: Optional[str] = None,
    actor: Optional[models.User] = None,
    request: Optional[Request] = None,
) -> None:
    """
    Alert sys_admin users and the configured Teams channel when AV flags an upload.
    Non-blocking: all errors are swallowed after logging to stdout.
    """
    user_label = None
    if actor:
        user_label = (
            getattr(actor, "username", None)
            or getattr(actor, "email", None)
            or getattr(actor, "id", None)
        )
    ip = None
    try:
        if request and getattr(request, "client", None):
            ip = getattr(request.client, "host", None)
    except Exception:
        ip = None
    detail = (detail or "").strip()
    # Load sys_admin recipients; fall back silently if unavailable.
    recipients: List[str] = []
    db = None
    try:
        db = SessionLocal()
        admins = (
            db.query(models.User)
            .filter(
                (models.User.role == "sys_admin")
                | (models.User.is_admin.is_(True))
            )
            .all()
        )
        recipients = notify_core._recipient_emails(admins)
    except Exception as exc:
        print(f"[notify] malware alert: failed to load admin recipients: {exc}")
    finally:
        try:
            if db is not None:
                db.close()
        except Exception as exc:
            notify_core._debug_suppressed("suppressed exception in notifications.py:586", exc)

    context = {
        "filename": filename or "upload",
        "user": user_label or "unknown",
        "ip": ip or "unknown",
        "detail": detail,
    }
    lines = [
        "A malware scan blocked an uploaded file.",
        f"File: {context['filename']}",
    ]
    if user_label:
        lines.append(f"User: {user_label}")
    if ip:
        lines.append(f"IP: {ip}")
    if detail:
        lines.append(f"Detail: {detail[:500]}")
    body = "\n".join(lines)
    if recipients:
        notify_core._send_notification(
            recipients=recipients,
            subject=branded_subject("Malware detected in upload"),
            body=body,
        )
    try:
        notify_core._send_teams_notification("malware_upload_detected", context)
    except Exception as exc:
        print(f"[notify] malware teams send failed: {exc}")
