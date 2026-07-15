from __future__ import annotations

import os
from typing import Iterable, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .app_branding import app_administrators_label, app_display_name, branded_subject
from .emailer import send_email
from .preservation_catalog import configured_builtin_hold_fields
from .integration_settings import decrypt_secret
from .system_settings import load_system_settings
from .database import SessionLocal
from .safe_log import debug_suppressed as _debug_suppressed


_ALLOW_INSECURE_DEV = (os.getenv("ALLOW_INSECURE_DEV") or "").strip().lower() in {"1", "true", "yes", "on"}
_DEV_FALLBACK = "https://localhost:10443"


def _legacy_env_enabled() -> bool:
    try:
        return not bool(load_system_settings().get("initial_setup_completed"))
    except Exception:
        return True


def _legacy_env_deployment_config() -> dict:
    base = (os.getenv("APP_BASE_URL") or "").strip().rstrip("/")
    if base and "://" not in base:
        base = f"https://{base}"
    hosts = {
        host.strip().lower()
        for host in (os.getenv("APP_ALLOWED_HOSTS") or "").split(",")
        if host.strip()
    }
    if base:
        parsed = urlparse(base)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return {"app_base_url": base, "allowed_hosts": hosts}

_DEFAULT_TEAMS_TEMPLATES = {
    "case_request_submitted": "New {request_type} request from {requestor} for {case_label}. Review: {link}",
    "admin_help": "Login assistance requested by {identifier} (IP: {ip}). Note: {note}",
    "registration_request": "New account registration request from {name} <{email}>. Review in System > Account Requests.",
    "backup_key_missing": "Backup encryption key missing; container deployments generate and persist one automatically.",
    "backup_restore": "Backup restore {status} by {actor}. File: {filename}. Detail: {detail}",
    "malware_upload_detected": "Upload blocked: {filename} (user: {user}, ip: {ip})",
    "consent_completed": "Consent completed for {case_label}. Custodian: {custodian_name} <{custodian_email}>. Case: {case_link}",
    "ticket_assigned": "Ticket assigned: {ticket} ({ticket_category}) -> {assigned_to}. Case: {case_label}. Ticket: {ticket_link}",
    "ticket_completed": "Ticket completed: {ticket} ({ticket_category}). Case: {case_label}. Ticket: {ticket_link}",
}


class _SafeTemplateContext(dict):
    def __missing__(self, key):
        return ""


def _app_display_name() -> str:
    return app_display_name()

def render_email_template(
    event: str,
    *,
    default_subject: str,
    default_body: str,
    context: Optional[dict] = None,
) -> tuple[Optional[str], Optional[str]]:
    notifications = load_system_settings().get("notifications") or {}
    email = notifications.get("email") or {}
    events = email.get("events") or {}
    event_cfg = events.get(event) or {}
    if not event_cfg and event == "external_ticket_assignee_details":
        event_cfg = events.get("servicenow_ticket_assignee_details") or {}
    if event_cfg.get("enabled", True) is False:
        return None, None
    ctx = _SafeTemplateContext({"app_name": _app_display_name(), **(context or {})})
    subject_template = event_cfg.get("subject") or default_subject
    body_template = event_cfg.get("body") or default_body
    try:
        subject = subject_template.format_map(ctx)
    except Exception:
        subject = default_subject.format_map(ctx)
    try:
        body = body_template.format_map(ctx)
    except Exception:
        body = default_body.format_map(ctx)
    return subject, body
def _teams_config() -> dict:
    settings = load_system_settings()
    notifications = settings.get("notifications") or {}
    teams = notifications.get("teams") or {}
    webhook = decrypt_secret(teams.get("webhook_url"))
    if not settings.get("initial_setup_completed") and not webhook:
        webhook = (os.getenv("SYSADMIN_ANALYST_TEAMS_WEBHOOK") or "").strip()
    events = teams.get("events") or {}
    return {"webhook_url": webhook, "events": events}


def _deployment_config() -> dict:
    try:
        deployment = (load_system_settings().get("deployment") or {})
    except Exception as exc:
        _debug_suppressed("suppressed exception in notifications.py:deployment_config", exc)
        deployment = {}
    base = (deployment.get("app_base_url") or "").strip().rstrip("/")
    if base and "://" not in base:
        base = f"https://{base}"
    hosts = {
        str(host or "").strip().lower()
        for host in (deployment.get("allowed_hosts") or [])
        if str(host or "").strip()
    }
    if base:
        parsed = urlparse(base)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return {"app_base_url": base, "allowed_hosts": hosts}


def _send_teams_notification(event: str, context: Optional[dict] = None) -> None:
    cfg = _teams_config()
    webhook = (cfg.get("webhook_url") or "").strip()
    if not webhook:
        return
    event_cfg = (cfg.get("events") or {}).get(event) or {}
    if not event_cfg.get("enabled", False):
        return
    template = event_cfg.get("template") or _DEFAULT_TEAMS_TEMPLATES.get(event) or ""
    ctx = context or {}
    try:
        message = template.format(**ctx)
    except Exception:
        message = template or f"{event} notification"
    payload = {"text": message}
    try:
        httpx.post(webhook, json=payload, timeout=5.0)
    except Exception as exc:
        print(f"[notify] teams send failed for {event}: {exc}")


def _host_is_allowed(host: Optional[str]) -> bool:
    if not host:
        return False
    host = host.lower()
    deployment = _deployment_config()
    allowed_hosts = set(deployment.get("allowed_hosts") or set())
    if _legacy_env_enabled():
        allowed_hosts.update(_legacy_env_deployment_config().get("allowed_hosts") or set())
    if host in allowed_hosts:
        return True
    if _ALLOW_INSECURE_DEV and (host.endswith(".localhost") or host in {"localhost", "127.0.0.1"}):
        return True
    return False


def _app_base_url(request: Optional[Request] = None) -> str:
    deployment = _deployment_config()
    deployment_base = deployment.get("app_base_url") or ""
    if deployment_base:
        return deployment_base
    if _legacy_env_enabled():
        env_base = _legacy_env_deployment_config().get("app_base_url") or ""
        if env_base:
            return env_base
    if request is not None:
        try:
            base = str(request.base_url).rstrip("/")
            parsed = urlparse(base)
            if _host_is_allowed(parsed.hostname):
                return base
        except Exception as exc:
            _debug_suppressed("suppressed exception in notifications.py:94", exc)
    if _ALLOW_INSECURE_DEV:
        return _DEV_FALLBACK
    raise RuntimeError("Public app URL must be configured in System > Branding before sending external links safely")


def _recipient_emails(users: Iterable[models.User]) -> List[str]:
    out: List[str] = []
    for user in users:
        email = (getattr(user, "email", None) or "").strip()
        if email:
            out.append(email)
    # deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for addr in out:
        if addr.lower() in seen:
            continue
        unique.append(addr)
        seen.add(addr.lower())
    return unique


def _send_notification(*, recipients: List[str], subject: str, body: str) -> None:
    if not recipients:
        return
    try:
        send_email(
            recipients=recipients,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        # do not interrupt primary request flow; log to stdout
        print(f"[notify] email send failed: {exc}")


def notify_case_request_submitted(
    db: Session,
    record: models.CaseRequest,
    request: Optional[Request] = None,
) -> None:
    recipients = _recipient_emails(
        db.query(models.User)
        .filter(
            (models.User.role.in_(("sys_admin", "analyst"))) |
            (models.User.is_admin.is_(True))
        )
        .all()
    )
    base = _app_base_url(request)
    link = f"{base}/requests"
    subject = branded_subject(f"New {record.request_type.replace('_', ' ').title()} request")
    case_label = record.case_name or (record.case_id and f"Case #{record.case_id}") or "New matter"
    body = (
        f"A new {record.request_type} request has been submitted.\n"
        f"Case: {case_label}\n"
        f"Requestor: {record.requestor_email or record.requestor_id or 'unknown'}\n"
        f"Status: {record.status}\n\n"
        f"Review this request: {link}"
    )
    if recipients:
        _send_notification(recipients=recipients, subject=subject, body=body)
    try:
        _send_teams_notification(
            "case_request_submitted",
            {
                "request_type": record.request_type.replace("_", " ").title(),
                "case_label": case_label,
                "requestor": record.requestor_email or record.requestor_id or "unknown",
                "status": record.status,
                "link": link,
            },
        )
    except Exception as exc:
        print(f"[notify] teams case request failed: {exc}")


def notify_case_request_outcome(
    db: Session,
    record: models.CaseRequest,
    *,
    approved: bool,
    request: Optional[Request] = None,
) -> None:
    email = (record.requestor_email or "").strip()
    if not email:
        user = record.requestor
        if user:
            email = (getattr(user, "email", None) or "").strip()
    if not email:
        return
    base = _app_base_url(request)
    if record.case_id:
        link = f"{base}/cases/{record.case_id}"
    else:
        link = f"{base}/requests"
    status = "approved" if approved else "declined"
    case = db.get(models.Case, record.case_id) if record.case_id else None
    details = record.decline_reason.strip() if (record.decline_reason and not approved) else ""
    case_label = record.case_name or (record.case_id and f"Case #{record.case_id}") or "Your request"
    legal_label = (getattr(case, "legal_case_name", None) or "").strip() if case else ""
    descriptor = f"{case_label} - {legal_label}" if legal_label else case_label
    subject = branded_subject(f"Your case request was {status}: {descriptor}")
    body_lines = [
        f"{descriptor} has been {status}.",
        "",
    ]
    if details:
        body_lines.extend(["Reason:", details, ""])
    body_lines.append(f"View in {app_display_name()}: {link}")
    body = "\n".join(body_lines)
    _send_notification(recipients=[email], subject=subject, body=body)


def _custodian_entry_label(name: object, email: object = None) -> str:
    name_text = str(name or "").strip()
    email_text = str(email or "").strip()
    if name_text and email_text:
        return f"{name_text} <{email_text}>"
    return name_text or email_text or "Unknown custodian"


def _custodian_entry_lines(entries: list[str], *, limit: int = 25) -> list[str]:
    if not entries:
        return ["- None"]
    lines = [f"- {item}" for item in entries[:limit]]
    remaining = len(entries) - limit
    if remaining > 0:
        lines.append(f"- ... and {remaining} more")
    return lines


def _configured_hold_status_keys() -> list[tuple[str, str]]:
    fields = configured_builtin_hold_fields(enabled_only=True)
    if not fields:
        fields = [
            ("email", "holds_email", "Email"),
            ("onedrive", "holds_onedrive", "OneDrive"),
            ("gdrive", "holds_gdrive", "Google Drive"),
            ("box", "holds_box", "Box"),
            ("slack", "holds_slack", "Slack"),
        ]
    return [
        (field.removeprefix("holds_"), label)
        for _source_key, field, label in fields
        if field.startswith("holds_")
    ]


def notify_case_request_custodian_count_mismatch(
    db: Session,
    record: models.CaseRequest,
    *,
    requested_count: int,
    created_count: int,
    submitted_custodians: Optional[list[dict]] = None,
    actual_custodians: Optional[list[models.Custodian]] = None,
    request: Optional[Request] = None,
) -> None:
    if requested_count == created_count:
        return
    recipients = _recipient_emails(
        db.query(models.User)
        .filter(
            (models.User.role.in_(("sys_admin", "analyst"))) |
            (models.User.is_admin.is_(True))
        )
        .all()
    )
    if not recipients:
        return

    case = db.get(models.Case, record.case_id) if record.case_id else None
    base = _app_base_url(request)
    link = f"{base}/cases/{record.case_id}" if record.case_id else f"{base}/requests"
    case_label = record.case_name or (record.case_id and f"Case #{record.case_id}") or "New matter"
    legal_label = (getattr(case, "legal_case_name", None) or "").strip() if case else ""
    descriptor = f"{case_label} - {legal_label}" if legal_label else case_label

    submitted_entries = [
        _custodian_entry_label(item.get("name"), item.get("email"))
        for item in (submitted_custodians or [])
        if isinstance(item, dict)
    ]
    actual_entries = [
        _custodian_entry_label(getattr(item, "name", None), getattr(item, "email", None))
        for item in (actual_custodians or [])
    ]

    subject = branded_subject(f"Custodian count mismatch for {case_label}")
    body_lines = [
        "A new case request was approved, but the number of custodians submitted in the request does not match the number currently on the created case.",
        "",
        f"Case: {descriptor}",
        f"Requestor: {record.requestor_email or record.requestor_id or 'unknown'}",
        f"Request ID: {record.id}",
        f"Submitted custodians: {requested_count}",
        f"Custodians on case: {created_count}",
        "",
        "Submitted custodians:",
        *_custodian_entry_lines(submitted_entries),
        "",
        "Custodians on created case:",
        *_custodian_entry_lines(actual_entries),
        "",
        f"Review this case: {link}",
    ]
    _send_notification(recipients=recipients, subject=subject, body="\n".join(body_lines))


def notify_case_request_hold_status(
    db: Session,
    record: models.CaseRequest,
    custodian_ids: List[int],
    *,
    request: Optional[Request] = None,
    base_url: Optional[str] = None,
) -> None:
    if record.request_type not in {"new_case", "custodian"}:
        return
    email = (record.requestor_email or "").strip()
    if not email:
        user = record.requestor
        if user:
            email = (getattr(user, "email", None) or "").strip()
    if not email:
        return
    if not custodian_ids:
        return
    case = db.get(models.Case, record.case_id) if record.case_id else None
    case_label = record.case_name or (record.case_id and f"Case #{record.case_id}") or "Your case"
    legal_label = (getattr(case, "legal_case_name", None) or "").strip() if case else ""
    descriptor = f"{case_label} - {legal_label}" if legal_label else case_label
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = _app_base_url(request)
    link = f"{base}/cases/{record.case_id}" if record.case_id else f"{base}/requests"

    custodians = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == record.case_id)
        .filter(models.Custodian.id.in_(custodian_ids))
        .all()
    )
    if not custodians:
        return

    hold_keys = _configured_hold_status_keys()

    def _hold_status(cust: models.Custodian, key: str) -> str:
        active = bool(getattr(cust, f"holds_{key}", False))
        pending = bool(getattr(cust, f"holds_{key}_pending", False))
        failed = bool(getattr(cust, f"holds_{key}_failed", False))
        released = bool(getattr(cust, f"holds_{key}_released", False))
        if released:
            return "released"
        if failed:
            return "failed"
        if pending:
            return "pending"
        if active:
            return "completed"
        return "off"

    total = len(custodians)
    on_hold_count = 0
    any_hold = False
    lines: List[str] = []
    summary: dict[str, dict[str, int]] = {}

    for cust in custodians:
        name = (getattr(cust, "name", None) or "").strip()
        cust_email = (getattr(cust, "email", None) or "").strip()
        label = name or cust_email or f"Custodian {getattr(cust, 'id', '')}".strip()
        statuses: list[tuple[str, str]] = []
        requested_statuses = []
        for key, label_name in hold_keys:
            status = _hold_status(cust, key)
            if status != "off":
                any_hold = True
                statuses.append((label_name, status))
                requested_statuses.append(status)
                bucket = summary.setdefault(label_name, {})
                bucket[status] = bucket.get(status, 0) + 1
        display = label
        if name and cust_email:
            display = f"{name} <{cust_email}>"
        elif cust_email:
            display = cust_email
        lines.append(f"{display}:")
        if not statuses:
            lines.append("  - No holds requested")
        else:
            for hold_label, st in statuses:
                lines.append(f"  - {hold_label}: {st}")
            if all(st == "completed" for st in requested_statuses):
                on_hold_count += 1
        lines.append("")

    if not any_hold:
        return

    subject = branded_subject(f"Hold status update for {descriptor}")
    summary_lines: List[str] = []
    for label_name in [label for _, label in hold_keys]:
        bucket = summary.get(label_name) or {}
        if not bucket:
            continue
        parts = []
        for status in ("completed", "pending", "failed", "released"):
            if bucket.get(status):
                parts.append(f"{status}: {bucket[status]}")
        if parts:
            summary_lines.append(f"- {label_name}: " + ", ".join(parts))
    body = "\n".join(
        [
            f"{on_hold_count} of {total} custodians have all requested holds completed",
            "",
            "Summary by hold type:",
            *(summary_lines or ["(no holds requested)"]),
            "",
            "Hold status by custodian:",
            *(lines[:-1] if lines and lines[-1] == "" else lines),
            "",
            f"View case: {link}",
        ]
    )
    _send_notification(recipients=[email], subject=subject, body=body)


def notify_case_requestor_hold_status(
    db: Session,
    case: models.Case,
    *,
    request: Optional[Request] = None,
    base_url: Optional[str] = None,
    custodian_ids: Optional[List[int]] = None,
    reason: Optional[str] = None,
) -> None:
    recipient = (getattr(case, "requestor", None) or "").strip()
    if not recipient:
        # Fall back to primary requestor entries (if present)
        try:
            entries = getattr(case, "requestors", []) or []
        except Exception:
            entries = []
        for row in entries:
            email = (getattr(row, "email", None) or "").strip()
            if email and bool(getattr(row, "is_primary", False)):
                recipient = email
                break
        if not recipient and entries:
            email = (getattr(entries[0], "email", None) or "").strip()
            if email:
                recipient = email
    if not recipient:
        return

    case_id = getattr(case, "id", None)
    case_label = getattr(case, "name", None) or (f"Case #{case_id}" if case_id else "Case")
    legal_label = (getattr(case, "legal_case_name", None) or "").strip()
    descriptor = f"{case_label} - {legal_label}" if legal_label else case_label

    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = _app_base_url(request)
    link = f"{base}/cases/{case_id}" if case_id else f"{base}/cases"

    q = db.query(models.Custodian).filter(models.Custodian.case_id == case_id)
    if custodian_ids:
        q = q.filter(models.Custodian.id.in_(custodian_ids))
    custodians = q.all()
    if not custodians:
        return

    hold_keys = _configured_hold_status_keys()

    def _hold_status(cust: models.Custodian, key: str) -> str:
        active = bool(getattr(cust, f"holds_{key}", False))
        pending = bool(getattr(cust, f"holds_{key}_pending", False))
        failed = bool(getattr(cust, f"holds_{key}_failed", False))
        released = bool(getattr(cust, f"holds_{key}_released", False))
        if released:
            return "released"
        if failed:
            return "failed"
        if pending:
            return "pending"
        if active:
            return "completed"
        return "off"

    total = len(custodians)
    on_hold_count = 0
    any_hold = False
    lines: List[str] = []
    summary: dict[str, dict[str, int]] = {}

    for cust in custodians:
        name = (getattr(cust, "name", None) or "").strip()
        cust_email = (getattr(cust, "email", None) or "").strip()
        label = name or cust_email or f"Custodian {getattr(cust, 'id', '')}".strip()
        statuses: list[tuple[str, str]] = []
        requested_statuses = []
        for key, label_name in hold_keys:
            status = _hold_status(cust, key)
            if status != "off":
                any_hold = True
                statuses.append((label_name, status))
                requested_statuses.append(status)
                bucket = summary.setdefault(label_name, {})
                bucket[status] = bucket.get(status, 0) + 1
        display = label
        if name and cust_email:
            display = f"{name} <{cust_email}>"
        elif cust_email:
            display = cust_email
        lines.append(f"{display}:")
        if not statuses:
            lines.append("  - No holds requested")
        else:
            for hold_label, st in statuses:
                lines.append(f"  - {hold_label}: {st}")
            if all(st == "completed" for st in requested_statuses):
                on_hold_count += 1
        lines.append("")

    if not any_hold:
        return

    subject = branded_subject(f"Hold status update for {descriptor}")
    if reason:
        subject = branded_subject(f"Hold status update for {descriptor} ({reason})")
    summary_lines: List[str] = []
    for label_name in [label for _, label in hold_keys]:
        bucket = summary.get(label_name) or {}
        if not bucket:
            continue
        parts = []
        for status in ("completed", "pending", "failed", "released"):
            if bucket.get(status):
                parts.append(f"{status}: {bucket[status]}")
        if parts:
            summary_lines.append(f"- {label_name}: " + ", ".join(parts))
    body = "\n".join(
        [
            f"{on_hold_count} of {total} custodians have all requested holds completed",
            "",
            "Summary by hold type:",
            *(summary_lines or ["(no holds requested)"]),
            "",
            "Hold status by custodian:",
            *(lines[:-1] if lines and lines[-1] == "" else lines),
            "",
            f"View case: {link}",
        ]
    )
    _send_notification(recipients=[recipient], subject=subject, body=body)


def _user_primary_email(user: Optional[models.User]) -> Optional[str]:
    if not user:
        return None
    email = (getattr(user, "email", None) or "").strip()
    return email or None


def notify_case_requestor_case_event(
    case: models.Case,
    *,
    event: str,
    request: Optional[Request] = None,
) -> None:
    recipient = (getattr(case, "requestor", None) or "").strip()
    if not recipient:
        return
    case_id = getattr(case, "id", None)
    case_label = getattr(case, "name", None) or (f"Case #{case_id}" if case_id else "Case")
    legal_label = (getattr(case, "legal_case_name", None) or "").strip()
    descriptor = f"{case_label} - {legal_label}" if legal_label else case_label
    if event == "closed":
        subject = branded_subject(f"Case {descriptor} closed")
        body = (
            f"{descriptor} has been closed.\n\n"
            f"If you did not expect this action, contact the {app_administrators_label()} as soon as possible."
        )
    elif event == "deleted":
        subject = branded_subject(f"Case {descriptor} deleted")
        body = (
            f"{descriptor} was deleted from {app_display_name()}.\n\n"
            f"If this was not anticipated, contact the {app_administrators_label()} immediately."
        )
    else:
        return
    _send_notification(recipients=[recipient], subject=subject, body=body)


def notify_user_password_change(*args, **kwargs):
    from .notifications_security import notify_user_password_change as impl
    return impl(*args, **kwargs)


def notify_user_mfa_change(*args, **kwargs):
    from .notifications_security import notify_user_mfa_change as impl
    return impl(*args, **kwargs)


def notify_malware_upload_detected(*args, **kwargs):
    from .notifications_security import notify_malware_upload_detected as impl
    return impl(*args, **kwargs)
