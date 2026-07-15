from __future__ import annotations

import hashlib
import html
import json
import os
import re
import secrets
import logging
import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.orm import Session, selectinload
import bleach
from bleach.sanitizer import ALLOWED_PROTOCOLS as BLEACH_PROTOCOLS
from .safe_log import debug_suppressed as _debug_suppressed
try:  # bleach >=6
    from bleach.css_sanitizer import CSSSanitizer  # type: ignore
except Exception:  # pragma: no cover
    CSSSanitizer = None  # type: ignore

from . import models
from .app_branding import app_display_name as _shared_app_display_name
from .audit import log_event
from .auth import current_user as get_current_user
from .database import SessionLocal, get_db
from .emailer import mail_provider_ready, send_email
from .notifications import _app_base_url
from .permissions import ensure_case_visible, ensure_case_editable, is_requestor, is_tech
from .system_settings import load_system_settings
from .institution import is_organization_email, load_institution_settings, organization_domains, organization_domain_label
from .integration_settings import decrypt_secret
from .ntp_reminder_scheduler import start_ntp_reminder_scheduler


router = APIRouter(prefix="/api", tags=["ntp"])
logger = logging.getLogger(__name__)

def app_display_name() -> str:
    return _shared_app_display_name(fallback_env_names=("ACK_BRAND_NAME", "APP_DISPLAY_NAME", "APP_NAME"))

def app_tagline() -> str:
    try:
        settings = load_system_settings()
        branding = settings.get("branding") or {}
        stored = str(branding.get("app_tagline") or "").strip()
        if stored:
            return stored
        if settings.get("initial_setup_completed"):
            return "eDiscovery Case Manager"
    except Exception:
        pass
    return os.getenv("ACK_BRAND_TAGLINE") or "eDiscovery Case Manager"


def _ntp_value(key: str, env_name: str, default: str = "") -> str:
    try:
        settings = load_system_settings()
    except Exception:
        settings = {}
    ntp_settings = settings.get("ntp") if isinstance(settings.get("ntp"), dict) else {}
    value = ntp_settings.get(key)
    if value is not None and value != "":
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value or "").strip()
    if settings.get("initial_setup_completed"):
        return str(default or "").strip()
    return (os.getenv(env_name) or default).strip()


def _ntp_int(key: str, env_name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _ntp_value(key, env_name, str(default))
    try:
        parsed = int(raw)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _ntp_bool(key: str, env_name: str, default: bool = False) -> bool:
    raw = _ntp_value(key, env_name, "1" if default else "0")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def ntp_ack_automate_url() -> str:
    return _ntp_value("ack_automate_url", "NTP_ACK_AUTOMATE_URL")


def ntp_ack_automate_secret() -> str:
    raw = _ntp_value("ack_automate_secret", "NTP_ACK_AUTOMATE_SECRET")
    return decrypt_secret(raw) if raw.startswith("enc:v1:") else raw


def ntp_reminder_interval_days() -> int:
    return _ntp_int("reminder_interval_days", "NTP_REMINDER_INTERVAL_DAYS", 14, minimum=1, maximum=365)


def ntp_reminder_duration_days() -> int:
    return _ntp_int("reminder_duration_days", "NTP_REMINDER_DURATION_DAYS", 90, minimum=1, maximum=3650)


def ntp_reminder_loop_seconds() -> int:
    return _ntp_int("reminder_loop_seconds", "NTP_REMINDER_LOOP_SECONDS", 900, minimum=30, maximum=86400)


def ntp_default_archive_bcc() -> str:
    configured = _ntp_value("archive_bcc_address", "NTP_DEFAULT_ARCHIVE_BCC").lower()
    return configured


def ntp_reserved_archive_bcc_addresses() -> set[str]:
    raw = _ntp_value("reserved_archive_bcc_addresses", "NTP_RESERVED_ARCHIVE_BCC_ADDRESSES")
    return {addr.strip().lower() for addr in raw.split(",") if addr.strip()}


def ntp_archive_copy_required() -> bool:
    return _ntp_bool("archive_copy_required", "NTP_ARCHIVE_COPY_REQUIRED", False)



_ALLOWED_TEMPLATE_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "a", "span", "div", "b", "i", "u", "mark"]
_ALLOWED_TEMPLATE_ATTRS = {
    "a": ["href", "title", "rel"],
    "span": ["style", "data-highlight"],
    "mark": ["style", "data-highlight"],
}
_ALLOWED_TEMPLATE_PROTOCOLS = tuple(set(BLEACH_PROTOCOLS) | {"http", "https", "mailto"})
_ALLOWED_TEMPLATE_STYLES = ["background-color", "padding", "color", "font-weight", "font-style", "text-decoration"]
_HIGHLIGHT_STYLE = "background-color:#fef08a;padding:0 2px;"

_CSS_SANITIZER = None
if CSSSanitizer:
    try:
        _CSS_SANITIZER = CSSSanitizer(
            allowed_css_properties=_ALLOWED_TEMPLATE_STYLES,
            allowed_svg_properties=[],
        )
    except Exception:
        _CSS_SANITIZER = None


def _ntp_rendering():
    from . import ntp_rendering
    return ntp_rendering


def _normalize_highlight_markers(value: str) -> str:
    return _ntp_rendering()._normalize_highlight_markers(value)


def _sanitize_template_html(value: Optional[str]) -> str:
    return _ntp_rendering()._sanitize_template_html(value)


def _apply_highlight_style(html: str) -> str:
    return _ntp_rendering()._apply_highlight_style(html)


def _normalize_group_name(value: Optional[str]) -> Optional[str]:
    return _ntp_rendering()._normalize_group_name(value)


def _user_group(user: Optional[models.User]) -> Optional[str]:
    return _ntp_rendering()._user_group(user)


def _template_group_names(template: models.NTPTemplate) -> List[str]:
    return _ntp_rendering()._template_group_names(template)


def _apply_template_groups(template: models.NTPTemplate, groups: Optional[List[str]]) -> None:
    return _ntp_rendering()._apply_template_groups(template, groups)


def _template_allows_user(template: models.NTPTemplate, user: models.User) -> bool:
    return _ntp_rendering()._template_allows_user(template, user)


def _templates_for_user(db: Session, user: models.User) -> List[models.NTPTemplate]:
    return _ntp_rendering()._templates_for_user(db, user)


def _acknowledgement_page(title: str, message: str, *, status_code: int = 200) -> HTMLResponse:
    return _ntp_rendering()._acknowledgement_page(title, message, status_code=status_code)


def _render_template(text: str, context: Dict[str, str]) -> str:
    return _ntp_rendering()._render_template(text, context)


def _strip_tags(value: str) -> str:
    return _ntp_rendering()._strip_tags(value)


def _render_bodies(template_text: str, context: Dict[str, str]) -> tuple[str, str]:
    return _ntp_rendering()._render_bodies(template_text, context)


def _merge_cc_lists(*sources: Optional[str]) -> List[str]:
    return _ntp_rendering()._merge_cc_lists(*sources)


def _required_ntp_archive_bcc() -> str:
    return _ntp_rendering()._required_ntp_archive_bcc()


def _normalize_template_bcc_for_storage(raw: Optional[str]) -> List[str]:
    return _ntp_rendering()._normalize_template_bcc_for_storage(raw)


def _merge_bcc_lists(*sources: Optional[str]) -> List[str]:
    return _ntp_rendering()._merge_bcc_lists(*sources)


def _hash_ntp_token(value: str) -> str:
    return _ntp_rendering()._hash_ntp_token(value)


def _create_ntp_token(
    db: Session,
    *,
    case_id: int,
    custodian_id: int,
    template_id: Optional[int],
) -> tuple[models.NTPTargetToken, str]:
    return _ntp_rendering()._create_ntp_token(db, case_id=case_id, custodian_id=custodian_id, template_id=template_id)


def _normalize_variables(raw: Dict[str, str]) -> Dict[str, str]:
    return _ntp_rendering()._normalize_variables(raw)


def _pretty_email_address(value: Optional[str]) -> str:
    return _ntp_rendering()._pretty_email_address(value)


def _build_ntp_context(
    case: models.Case,
    custodian: models.Custodian,
    requestor_label: str,
    ack_link: str,
    ack_display: str,
    variables: Dict[str, str],
) -> Dict[str, str]:
    return _ntp_rendering()._build_ntp_context(case, custodian, requestor_label, ack_link, ack_display, variables)


def _parse_email_list(raw: Optional[str]) -> List[str]:
    return _ntp_rendering()._parse_email_list(raw)


class TemplatePayload(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)
    description: Optional[str] = None
    cc: Optional[str] = None
    is_default: bool = False
    high_importance: bool = False
    groups: List[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("groups", mode="before")
    @classmethod
    def _clean_groups(cls, value):
        items = value or []
        if not isinstance(items, list):
            return []
        cleaned = []
        seen = set()
        for entry in items:
            norm = _normalize_group_name(entry)
            if norm and norm not in seen:
                cleaned.append(norm)
                seen.add(norm)
        return cleaned


class SendNTPPayload(BaseModel):
    template_id: int
    reminder_template_id: Optional[int] = None
    custodian_ids: List[int] = Field(min_length=1)
    variables: Dict[str, str] = Field(default_factory=dict)
    reminder_interval_days: Optional[int] = Field(default=None, gt=0)
    reminder_duration_days: Optional[int] = Field(default=None, gt=0)

class PreviewNTPPayload(BaseModel):
    template_id: int
    custodian_ids: List[int] = Field(min_length=1)
    variables: Dict[str, str] = Field(default_factory=dict)

class NTPReminderUpdatePayload(BaseModel):
    interval_days: Optional[int] = Field(default=None, gt=0)
    duration_days: Optional[int] = Field(default=None, gt=0)
    enabled: Optional[bool] = None


class NTPReminderBulkUpdatePayload(NTPReminderUpdatePayload):
    custodian_ids: list[int] = Field(default_factory=list)


class PowerAutomateAckPayload(BaseModel):
    token: str = Field(min_length=8)
    secret: str = Field(min_length=8)
    metadata: Optional[Dict[str, str]] = None


def _template_response(
    template: models.NTPTemplate,
    *,
    user: Optional[models.User] = None,
    default_reminder_id: Optional[int] = None,
) -> Dict[str, any]:
    default_id = getattr(user, "ntp_default_template_id", None) if user else None
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "subject": template.subject,
        "body": template.body,
        "cc": getattr(template, "cc", "") or "",
        "archive_copy_address": _required_ntp_archive_bcc(),
        "is_default": bool(default_id and template.id == default_id),
        "is_default_reminder": bool(default_reminder_id and template.id == default_reminder_id),
        "high_importance": bool(getattr(template, "high_importance", False)),
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        "groups": _template_group_names(template),
    }

def _reminder_response(reminder: models.NTPReminder) -> Dict[str, any]:
    return {
        "id": reminder.id,
        "case_id": reminder.case_id,
        "custodian_id": reminder.custodian_id,
        "template_id": reminder.template_id,
        "template_name": reminder.template.name if reminder.template else None,
        "interval_days": reminder.interval_days,
        "next_send_at": reminder.next_send_at.isoformat() if reminder.next_send_at else None,
        "stop_after": reminder.stop_after.isoformat() if reminder.stop_after else None,
        "last_sent_at": reminder.last_sent_at.isoformat() if reminder.last_sent_at else None,
        "send_count": reminder.send_count,
        "status": reminder.status,
        "created_at": reminder.created_at.isoformat() if reminder.created_at else None,
        "updated_at": reminder.updated_at.isoformat() if reminder.updated_at else None,
    }


def list_ntp_templates(*args, **kwargs):
    from .ntp_templates import list_ntp_templates as _impl
    return _impl(*args, **kwargs)

def get_last_ntp_send(*args, **kwargs):
    from .ntp_history import get_last_ntp_send as _impl
    return _impl(*args, **kwargs)


def _load_case_ntp_history_payload(*args, **kwargs):
    from .ntp_history import _load_case_ntp_history_payload as _impl
    return _impl(*args, **kwargs)


def get_case_ntp_history(*args, **kwargs):
    from .ntp_history import get_case_ntp_history as _impl
    return _impl(*args, **kwargs)


def _ntp_history_csv_response(*args, **kwargs):
    from .ntp_history import _ntp_history_csv_response as _impl
    return _impl(*args, **kwargs)


def export_case_ntp_history_csv(*args, **kwargs):
    from .ntp_history import export_case_ntp_history_csv as _impl
    return _impl(*args, **kwargs)


def _resolve_actor_email_for_ntp_history_report(*args, **kwargs):
    from .ntp_history import _resolve_actor_email_for_ntp_history_report as _impl
    return _impl(*args, **kwargs)


def _compose_ntp_history_report(*args, **kwargs):
    from .ntp_history import _compose_ntp_history_report as _impl
    return _impl(*args, **kwargs)


def email_case_ntp_history_report(*args, **kwargs):
    from .ntp_history import email_case_ntp_history_report as _impl
    return _impl(*args, **kwargs)

def create_ntp_template(*args, **kwargs):
    from .ntp_templates import create_ntp_template as _impl
    return _impl(*args, **kwargs)


def update_ntp_template(*args, **kwargs):
    from .ntp_templates import update_ntp_template as _impl
    return _impl(*args, **kwargs)


def delete_ntp_template(*args, **kwargs):
    from .ntp_templates import delete_ntp_template as _impl
    return _impl(*args, **kwargs)


def list_ntp_groups(*args, **kwargs):
    from .ntp_templates import list_ntp_groups as _impl
    return _impl(*args, **kwargs)


def _to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

def _custodians_for_case(db: Session, case_id: int, custodian_ids: List[int]) -> List[models.Custodian]:
    rows = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id, models.Custodian.id.in_(custodian_ids))
        .all()
    )
    if len(rows) != len(set(custodian_ids)):
        found_ids = {c.id for c in rows}
        missing = [cid for cid in custodian_ids if cid not in found_ids]
        raise HTTPException(status_code=404, detail=f"Custodians not found: {missing}")
    return rows


@router.post("/cases/{case_id}/ntp/preview")
def preview_ntp_notice(
    case_id: int,
    payload: PreviewNTPPayload,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, user, db)
    if is_requestor(user) and not _user_group(user):
        raise HTTPException(status_code=403, detail="Requestor accounts must belong to a group to preview NTPs.")
    if not is_requestor(user):
        ensure_case_editable(user)
    template = (
        db.query(models.NTPTemplate)
        .options(selectinload(models.NTPTemplate.groups))
        .filter(models.NTPTemplate.id == payload.template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if not _template_allows_user(template, user):
        raise HTTPException(status_code=403, detail="Template is not available for your group")
    custodians = _custodians_for_case(db, case_id, payload.custodian_ids)
    if not custodians:
        raise HTTPException(status_code=400, detail="Select at least one custodian")
    preview_custodian = custodians[0]
    if not (preview_custodian.email or "").strip():
        raise HTTPException(status_code=400, detail=f"Custodian '{preview_custodian.name}' is missing an email address")

    base_url = _app_base_url(request)
    friendly_ack = _ack_display_url(base_url)
    ack_link = _build_ack_link(base_url, "preview-token")
    sanitized_variables = _normalize_variables(payload.variables or {})
    context = _build_ntp_context(
        case,
        preview_custodian,
        case.requestor or "",
        ack_link,
        friendly_ack,
        sanitized_variables,
    )
    subject = _render_template(template.subject, context)
    text_body, html_body = _render_bodies(template.body, context)
    cc_values = _merge_cc_lists(getattr(template, "cc", ""), sanitized_variables.get("cc"))
    bcc_values = _merge_bcc_lists(getattr(template, "bcc", ""), sanitized_variables.get("bcc"))
    return {
        "template_id": template.id,
        "template_name": template.name,
        "subject": subject,
        "text_body": text_body,
        "html_body": html_body,
        "recipient": {
            "id": preview_custodian.id,
            "name": preview_custodian.name,
            "email": _pretty_email_address(preview_custodian.email),
        },
        "recipient_count": len(custodians),
        "cc": cc_values,
        "bcc": bcc_values,
        "archive_copy_address": bcc_values[0] if bcc_values else _required_ntp_archive_bcc(),
        "ack_link": ack_link,
        "is_preview": True,
    }


@router.post("/cases/{case_id}/ntp/send", status_code=202)
def send_ntp_notices(
    case_id: int,
    payload: SendNTPPayload,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, user, db)
    if not is_requestor(user):
        ensure_case_editable(user)
    if is_requestor(user):
        if not _user_group(user):
            raise HTTPException(status_code=403, detail="Requestor accounts must belong to a group to send NTPs.")
    else:
        ensure_case_editable(user)
    template = (
        db.query(models.NTPTemplate)
        .options(selectinload(models.NTPTemplate.groups))
        .filter(models.NTPTemplate.id == payload.template_id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if not _template_allows_user(template, user):
        raise HTTPException(status_code=403, detail="Template is not available for your group")
    reminder_template = None
    if payload.reminder_template_id:
        reminder_template = (
            db.query(models.NTPTemplate)
            .options(selectinload(models.NTPTemplate.groups))
            .filter(models.NTPTemplate.id == payload.reminder_template_id)
            .first()
        )
        if not reminder_template:
            raise HTTPException(status_code=404, detail="Reminder template not found")
        if not _template_allows_user(reminder_template, user):
            raise HTTPException(status_code=403, detail="Reminder template is not available for your group")
    interval_days = payload.reminder_interval_days or ntp_reminder_interval_days()
    duration_days = payload.reminder_duration_days or ntp_reminder_duration_days()
    interval_days = max(1, int(interval_days))
    duration_days = max(1, int(duration_days))
    custodians = _custodians_for_case(db, case_id, payload.custodian_ids)
    if not custodians:
        raise HTTPException(status_code=400, detail="Select at least one custodian")
    base_url = _app_base_url(request)
    friendly_ack = _ack_display_url(base_url)
    requestor_label = case.requestor or ""
    if not mail_provider_ready():
        raise HTTPException(status_code=503, detail="Mail provider is not configured")
    actor_email = (getattr(user, "email", None) or "").strip()
    if not actor_email:
        # Fallback: some deployments use username as email
        actor_email = (getattr(user, "username", None) or "").strip()
    if "@" not in actor_email:
        actor_email = ""
    actor_email = _pretty_email_address(actor_email)
    sanitized_variables = _normalize_variables(payload.variables or {})
    results = []
    now = datetime.now(timezone.utc)
    template_name = template.name
    reminder_template_name = reminder_template.name if reminder_template else None
    invalid = [
        cust
        for cust in custodians
        if organization_domains() and not is_organization_email(getattr(cust, "email", None))
    ]
    if invalid:
        names = ", ".join([(cust.name or cust.email or "Unknown") for cust in invalid])
        raise HTTPException(
            status_code=400,
            detail=f"NTP not allowed for non-organization custodians ({organization_domain_label()}): {names}",
        )
    blocked = []
    for cust in custodians:
        status = (getattr(cust, "employment_status", "") or "").strip().lower()
        ntp_status = (getattr(cust, "ntp_status", "") or "").strip().lower()
        if status.startswith("separated") or ntp_status == "na":
            blocked.append(cust)
    if blocked:
        names = ", ".join([(cust.name or cust.email or "Unknown") for cust in blocked])
        raise HTTPException(status_code=400, detail=f"that custodian is separated or listed as NA for NTPs: {names}")
    for custodian in custodians:
        if not (custodian.email or "").strip():
            raise HTTPException(status_code=400, detail=f"Custodian '{custodian.name}' is missing an email address")
        token, token_value = _create_ntp_token(
            db,
            case_id=case.id,
            custodian_id=custodian.id,
            template_id=template.id,
        )
        ack_link = _build_ack_link(base_url, token_value)
        ack_display = friendly_ack
        context = _build_ntp_context(case, custodian, requestor_label, ack_link, ack_display, sanitized_variables)
        subject = _render_template(template.subject, context)
        text_body, html_body = _render_bodies(template.body, context)
        deduped_cc = _merge_cc_lists(getattr(template, "cc", ""), sanitized_variables.get("cc"))
        deduped_bcc = _merge_bcc_lists(getattr(template, "bcc", ""), sanitized_variables.get("bcc"))
        recipient_email = _pretty_email_address(custodian.email)
        importance = "high" if bool(getattr(template, "high_importance", False)) else None
        archive_copy_sent = bool(deduped_bcc)
        archive_copy_error = None
        try:
            send_email(
                recipients=[recipient_email],
                subject=subject,
                body=text_body,
                html=html_body,
                from_override=actor_email or None,
                reply_to=[actor_email] if actor_email else None,
                cc=deduped_cc or None,
                bcc=deduped_bcc or None,
                importance=importance,
                audit_log=False,
            )
        except Exception as exc:
            if deduped_bcc and not ntp_archive_copy_required():
                archive_copy_sent = False
                archive_copy_error = str(exc)
                _debug_suppressed("suppressed exception in ntp.py:send_ntp_notices_bcc_retry", exc)
                send_email(
                    recipients=[recipient_email],
                    subject=subject,
                    body=text_body,
                    html=html_body,
                    from_override=actor_email or None,
                    reply_to=[actor_email] if actor_email else None,
                    cc=deduped_cc or None,
                    importance=importance,
                    audit_log=False,
                )
            else:
                raise
        custodian.ntp_status = "sent"
        custodian.ntp_sent_at = now
        custodian.ntp_template_name = template_name
        if reminder_template:
            _create_ntp_reminder(
                db=db,
                token=token,
                case=case,
                custodian=custodian,
                reminder_template=reminder_template,
                variables=sanitized_variables,
                now=now,
                interval_days=interval_days,
                duration_days=duration_days,
            )
        try:
            log_event(
                db,
                action="ntp_email_sent",
                target_type="case",
                target_id=case.id,
                actor_id=getattr(user, "id", None),
                details={
                    "case_id": case.id,
                    "case_name": getattr(case, "name", None),
                    "custodian_id": custodian.id,
                    "custodian_name": custodian.name,
                    "custodian_email": recipient_email,
                    "template_id": template.id,
                    "template_name": template_name,
                    "reminder_template_id": getattr(reminder_template, "id", None),
                    "reminder_template_name": reminder_template_name,
                    "subject": subject,
                    "cc_count": len(deduped_cc) if deduped_cc else 0,
                    "bcc_count": len(deduped_bcc) if deduped_bcc else 0,
                    "archive_copy_recipient": deduped_bcc[0] if deduped_bcc else None,
                    "archive_copy_recipients": deduped_bcc,
                    "archive_copy_sent": archive_copy_sent,
                    "archive_copy_error": archive_copy_error,
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in ntp.py:957", exc)
        results.append({"custodian_id": custodian.id, "ack_link": ack_link})
    db.commit()
    return {"sent": len(results)}



def _create_ntp_reminder(
    db: Session,
    token: models.NTPTargetToken,
    case: models.Case,
    custodian: models.Custodian,
    reminder_template: models.NTPTemplate,
    variables: Dict[str, str],
    now: datetime,
    interval_days: int,
    duration_days: int,
) -> None:
    reminder = models.NTPReminder(
        case_id=case.id,
        custodian_id=custodian.id,
        template_id=reminder_template.id,
        token_id=token.id,
        variables=json.dumps(variables or {}),
        interval_days=interval_days,
        next_send_at=now + timedelta(days=interval_days),
        stop_after=now + timedelta(days=duration_days),
    )
    db.add(reminder)

@router.get("/cases/{case_id}/ntp/reminders")
def list_case_ntp_reminders(
    case_id: int,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, user, db)
    query = (
        db.query(models.NTPReminder)
        .options(selectinload(models.NTPReminder.template))
        .filter(models.NTPReminder.case_id == case_id)
    )
    if not include_inactive:
        query = query.filter(models.NTPReminder.status == "active")
    reminders = query.order_by(models.NTPReminder.next_send_at.asc()).all()
    return [_reminder_response(r) for r in reminders]


def _update_case_ntp_reminders_for_custodian(
    *,
    case_id: int,
    custodian_id: int,
    payload: NTPReminderUpdatePayload,
    db: Session,
) -> list[models.NTPReminder]:
    if payload.enabled is True:
        custodian = db.get(models.Custodian, custodian_id)
        if custodian and (custodian.ntp_status or "").strip().lower() == "acknowledged":
            raise HTTPException(
                status_code=409,
                detail="Custodian already acknowledged the NTP; reminders will not be reactivated.",
            )
    statuses = ["active"]
    if payload.enabled is True:
        statuses.append("cancelled")
    reminders = (
        db.query(models.NTPReminder)
        .options(selectinload(models.NTPReminder.template))
        .filter(
            models.NTPReminder.case_id == case_id,
            models.NTPReminder.custodian_id == custodian_id,
            models.NTPReminder.status.in_(statuses),
        )
        .all()
    )
    if not reminders:
        raise HTTPException(
            status_code=404,
            detail="No reminders found" if payload.enabled is True else "No active reminders found",
        )
    updates: Dict[str, any] = {}
    now = datetime.now(timezone.utc)
    if payload.interval_days is not None:
        updates["interval_days"] = int(payload.interval_days)
        updates["next_send_at"] = now + timedelta(days=int(payload.interval_days))
    if payload.duration_days is not None:
        updates["stop_after"] = now + timedelta(days=int(payload.duration_days))
    if payload.enabled is not None:
        updates["status"] = "active" if payload.enabled else "cancelled"
    if updates:
        for reminder in reminders:
            prior_status = (reminder.status or "").strip().lower()
            for key, value in updates.items():
                setattr(reminder, key, value)
            if payload.enabled is True and prior_status != "active":
                if "next_send_at" not in updates:
                    interval_days = int(reminder.interval_days or ntp_reminder_interval_days())
                    reminder.next_send_at = now + timedelta(days=max(1, interval_days))
                if "stop_after" not in updates:
                    stop_after = reminder.stop_after
                    if not stop_after or _to_aware_utc(stop_after) <= now:
                        reminder.stop_after = now + timedelta(days=ntp_reminder_duration_days())
    return reminders


@router.put("/cases/{case_id}/ntp/reminders/{custodian_id}")
def update_case_ntp_reminders(
    case_id: int,
    custodian_id: int,
    payload: NTPReminderUpdatePayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if is_tech(user):
        raise HTTPException(status_code=403, detail="Tech accounts cannot manage NTP reminders")
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, user, db)
    reminders = _update_case_ntp_reminders_for_custodian(
        case_id=case_id,
        custodian_id=custodian_id,
        payload=payload,
        db=db,
    )
    if reminders:
        db.commit()
        for reminder in reminders:
            db.refresh(reminder)
    return [_reminder_response(r) for r in reminders]


@router.put("/cases/{case_id}/ntp/reminders")
def bulk_update_case_ntp_reminders(
    case_id: int,
    payload: NTPReminderBulkUpdatePayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if is_tech(user):
        raise HTTPException(status_code=403, detail="Tech accounts cannot manage NTP reminders")
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, user, db)
    custodian_ids = []
    seen = set()
    for raw_id in payload.custodian_ids or []:
        try:
            custodian_id = int(raw_id)
        except Exception:
            continue
        if custodian_id <= 0 or custodian_id in seen:
            continue
        seen.add(custodian_id)
        custodian_ids.append(custodian_id)
    if not custodian_ids:
        raise HTTPException(status_code=400, detail="Custodian ids are required")
    update_payload = NTPReminderUpdatePayload(
        interval_days=payload.interval_days,
        duration_days=payload.duration_days,
        enabled=payload.enabled,
    )
    touched: list[models.NTPReminder] = []
    updated_custodian_ids: list[int] = []
    errors: list[str] = []
    for custodian_id in custodian_ids:
        try:
            reminders = _update_case_ntp_reminders_for_custodian(
                case_id=case_id,
                custodian_id=custodian_id,
                payload=update_payload,
                db=db,
            )
        except HTTPException as exc:
            errors.append(f"{custodian_id}: {getattr(exc, 'detail', 'Unable to update reminders')}")
            continue
        touched.extend(reminders)
        updated_custodian_ids.append(custodian_id)
    if touched:
        db.commit()
        for reminder in touched:
            db.refresh(reminder)
    return {
        "updated_count": len(updated_custodian_ids),
        "failed_count": len(errors),
        "updated_custodian_ids": updated_custodian_ids,
        "errors": errors,
    }



def acknowledge_ntp(token: str):
    result = _process_ntp_ack(token)
    return _acknowledgement_page(
        result["title"],
        result["message"],
        status_code=result["http_status"],
    )


@router.post("/ntp/ack/automate")
def acknowledge_ntp_via_automate(payload: PowerAutomateAckPayload):
    ack_secret = ntp_ack_automate_secret()
    if not ack_secret:
        raise HTTPException(
            status_code=503,
            detail="Power Automate integration is not configured",
        )
    if payload.secret.strip() != ack_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")
    result = _process_ntp_ack(payload.token)
    return {
        "status": result["status"],
        "title": result["title"],
        "message": result["message"],
    }


def _complete_reminders_for_token(
    db: Session,
    token_id: int,
    *,
    case_id: Optional[int] = None,
    custodian_id: Optional[int] = None,
) -> None:
    try:
        updated = (
            db.query(models.NTPReminder)
            .filter(
                models.NTPReminder.token_id == token_id,
                models.NTPReminder.status == "active",
            )
            .update({"status": "completed"}, synchronize_session=False)
        )
        if updated == 0 and case_id is not None and custodian_id is not None:
            (
                db.query(models.NTPReminder)
                .filter(
                    models.NTPReminder.case_id == case_id,
                    models.NTPReminder.custodian_id == custodian_id,
                    models.NTPReminder.status == "active",
                )
                .update({"status": "completed"}, synchronize_session=False)
            )
    except Exception as exc:
        _debug_suppressed("suppressed exception in ntp.py:1130", exc)


def _build_ack_link(base_url: str, token_value: str) -> str:
    default_link = f"{base_url}/api/ntp/ack/{token_value}"
    template = ntp_ack_automate_url()
    if not template:
        return default_link
    if "{token}" in template:
        return template.replace("{token}", token_value)
    separator = "&" if "?" in template else "?"
    return f"{template}{separator}token={token_value}"


def _ack_display_url(base_url: str) -> str:
    configured = _ntp_value("ack_display_url", "NTP_ACK_DISPLAY_URL")
    if configured:
        return configured
    return f"{base_url.rstrip('/')}/ntp/ack"


def _support_contact_text() -> str:
    institution = load_institution_settings()
    support_email = str(institution.get("support_email") or "").strip()
    team = f"{app_display_name()} team"
    return f"{team} at {support_email}" if support_email else team


def _process_ntp_ack(token: str) -> Dict[str, str]:
    db = SessionLocal()
    try:
        hashed_token = _hash_ntp_token(token)
        row = (
            db.query(models.NTPTargetToken)
            .filter(models.NTPTargetToken.token == hashed_token)
            .first()
        )
        rehashed = False
        if not row:
            row = (
                db.query(models.NTPTargetToken)
                .filter(models.NTPTargetToken.token == token)
                .first()
            )
            if row:
                row.token = hashed_token
                db.flush()
                rehashed = True
        if not row:
            return {
                "status": "not_found",
                "title": "Link invalid or expired",
                "message": f"We could not locate this acknowledgement link. Please contact the {_support_contact_text()} if you need assistance.",
                "http_status": 404,
            }
        already = row.used_at is not None
        custodian = row.custodian
        if not already:
            now = datetime.now(timezone.utc)
            row.used_at = now
            if custodian:
                custodian.ntp_status = "acknowledged"
                custodian.ntp_acknowledged_at = now
            _complete_reminders_for_token(
                db,
                row.id,
                case_id=row.case_id,
                custodian_id=row.custodian_id,
            )
            db.commit()
            try:
                case_obj = getattr(row, "case", None)
                log_event(
                    db,
                    action="ntp_acknowledged",
                    target_type="custodian",
                    target_id=row.custodian_id,
                    actor_id=None,
                    details={
                        "case_id": getattr(case_obj, "id", None) or row.case_id,
                        "case_name": getattr(case_obj, "name", None),
                        "custodian_id": row.custodian_id,
                        "custodian_name": getattr(custodian, "name", None),
                        "custodian_email": getattr(custodian, "email", None),
                        "token_id": row.id,
                    },
                )
            except Exception as exc:
                _debug_suppressed("suppressed exception in ntp.py:1204", exc)
            return {
                "status": "recorded",
                "title": "Your response has been recorded.",
                "message": "Thank you for confirming. You may now close this page.",
                "http_status": 200,
            }
        if rehashed:
            db.commit()
        return {
            "status": "already",
            "title": "This notice was already acknowledged.",
            "message": "No further action is required.",
            "http_status": 200,
        }
    finally:
        db.close()


