from __future__ import annotations

import io
import json
import logging
import threading
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import case_requests as case_request_core
from . import models
from .audit import log_event
from .email_intake_graph import (
    EmailIntakeSettings,
    delta_messages,
    load_email_intake_settings,
    message_attachments,
)
from .email_intake_matching import (
    NormalizedEmail,
    extract_case_request_payload,
    first_matching_template,
    normalize_graph_message,
)
from .file_security import scan_payload
from .institution import is_organization_email
from .emailconvertor import sanitize_filename

logger = logging.getLogger(__name__)
_poll_lock = threading.Lock()
TERMINAL_STATUSES = {"pending_request", "ignored"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sender_allowed(settings: EmailIntakeSettings, sender: str) -> bool:
    normalized = str(sender or "").strip().lower()
    if not normalized or "@" not in normalized:
        return False
    policy = settings.sender_policy
    if policy == "organization":
        return is_organization_email(normalized)
    if policy == "allowlist":
        domain = normalized.rsplit("@", 1)[-1]
        return normalized in settings.allowed_senders or domain in settings.allowed_sender_domains
    return True


def _template_rows(db: Session) -> list[models.EmailIntakeTemplate]:
    return (
        db.query(models.EmailIntakeTemplate)
        .filter(models.EmailIntakeTemplate.enabled.is_(True))
        .order_by(models.EmailIntakeTemplate.priority.asc(), models.EmailIntakeTemplate.id.asc())
        .all()
    )


def _cursor(db: Session, settings: EmailIntakeSettings) -> models.EmailIntakeCursor:
    row = (
        db.query(models.EmailIntakeCursor)
        .filter(
            func.lower(models.EmailIntakeCursor.mailbox) == settings.mailbox.lower(),
            models.EmailIntakeCursor.folder_id == settings.folder_id,
        )
        .first()
    )
    if row is None:
        row = models.EmailIntakeCursor(
            mailbox=settings.mailbox,
            folder_id=settings.folder_id,
            baseline_pending=not settings.process_existing_on_first_run,
        )
        db.add(row)
        db.flush()
    elif settings.process_existing_on_first_run and row.baseline_pending:
        row.baseline_pending = False
    return row


def _normalized_from_record(record: models.EmailIntakeMessage) -> NormalizedEmail:
    try:
        recipients = tuple(json.loads(record.recipients or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        recipients = ()
    return NormalizedEmail(
        graph_message_id=record.graph_message_id,
        internet_message_id=record.internet_message_id,
        change_key=record.change_key,
        sender=record.sender or "",
        recipients=tuple(str(item) for item in recipients if str(item).strip()),
        subject=record.subject or "",
        body_text=record.body_text or "",
        received_at=record.received_at,
        has_attachments=bool(record.attachment_count),
    )


def _upsert_message(
    db: Session,
    settings: EmailIntakeSettings,
    message: dict[str, Any],
) -> models.EmailIntakeMessage | None:
    if "@removed" in message:
        return None
    normalized = normalize_graph_message(message)
    if not normalized.graph_message_id:
        return None
    row = (
        db.query(models.EmailIntakeMessage)
        .filter(
            func.lower(models.EmailIntakeMessage.mailbox) == settings.mailbox.lower(),
            models.EmailIntakeMessage.graph_message_id == normalized.graph_message_id,
        )
        .first()
    )
    if row is None:
        row = models.EmailIntakeMessage(
            mailbox=settings.mailbox,
            graph_message_id=normalized.graph_message_id,
            status="received",
        )
        db.add(row)
    row.internet_message_id = normalized.internet_message_id
    row.change_key = normalized.change_key
    row.sender = normalized.sender
    row.recipients = json.dumps(list(normalized.recipients))
    row.subject = normalized.subject
    row.received_at = normalized.received_at
    row.body_text = normalized.body_text
    if normalized.has_attachments and not row.attachment_count:
        row.attachment_count = 1
    db.commit()
    db.refresh(row)
    return row


def _request_attachment_zip(
    settings: EmailIntakeSettings,
    message: models.EmailIntakeMessage,
) -> tuple[str | None, str | None, int, int]:
    if not message.attachment_count:
        return None, None, 0, 0
    attachments = message_attachments(settings, message.graph_message_id)
    supported = [item for item in attachments if item.get("supported")]
    unsupported = [item for item in attachments if not item.get("supported") and not item.get("is_inline")]
    if unsupported:
        names = ", ".join(str(item.get("name") or "attachment") for item in unsupported[:5])
        raise RuntimeError(f"Unsupported Graph attachment type cannot be scanned: {names}")
    if not supported:
        return None, None, 0, len(attachments)

    output = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(supported, start=1):
            content = item.get("content")
            if not isinstance(content, bytes):
                continue
            original = sanitize_filename(item.get("name"), default=f"attachment-{index}", max_length=180)
            safe_name = original
            suffix = 2
            while safe_name.lower() in used_names:
                path = Path(original)
                safe_name = f"{path.stem}-{suffix}{path.suffix}"
                suffix += 1
            used_names.add(safe_name.lower())
            scan_payload(content, safe_name, request=None, actor=None)
            archive.writestr(safe_name, content)
    payload = output.getvalue()
    if case_request_core.MAX_UPLOAD_BYTES > 0 and len(payload) > case_request_core.MAX_UPLOAD_BYTES:
        raise RuntimeError("Email attachments exceed the configured request upload limit")
    scan_payload(payload, "email-attachments.zip", request=None, actor=None)
    directory = case_request_core.CASE_REQUEST_UPLOAD_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stored_name = f"email_{uuid.uuid4().hex}_attachments.zip"
    target = directory / stored_name
    target.write_bytes(payload)
    return "email-attachments.zip", str(target), len(payload), len(attachments)


def _available_case_name(db: Session, requested: str, message: models.EmailIntakeMessage) -> str:
    base = str(requested or "Email intake request").strip()[:255] or "Email intake request"
    candidates = [base]
    received = message.received_at or _utcnow()
    candidates.append(f"{base[:235]} ({received:%Y-%m-%d})")
    candidates.append(f"{base[:235]} ({message.id})")
    for candidate in candidates:
        try:
            case_request_core._ensure_case_name_available(db, candidate)
            return candidate
        except HTTPException as exc:
            if exc.status_code != 409:
                raise
    raise RuntimeError("Unable to reserve a unique case name for the email")


def _create_pending_request(
    db: Session,
    settings: EmailIntakeSettings,
    message: models.EmailIntakeMessage,
    template: models.EmailIntakeTemplate,
    email: NormalizedEmail,
) -> models.CaseRequest:
    payload = extract_case_request_payload(
        template,
        email,
        requestor_from_sender=settings.requestor_from_sender,
    )
    payload["name"] = _available_case_name(db, payload.get("name") or "", message)
    if not str(payload.get("legal_case_name") or "").strip():
        payload["legal_case_name"] = payload["name"]
    payload["email_intake"]["message_record_id"] = message.id
    payload["email_intake"]["template_id"] = template.id
    payload["email_intake"]["template_name"] = template.name

    attachment_name = None
    attachment_path = None
    attachment_bytes = 0
    attachment_count = 0
    try:
        attachment_name, attachment_path, attachment_bytes, attachment_count = _request_attachment_zip(settings, message)
        requestor_email = email.sender if settings.requestor_from_sender else settings.mailbox
        record = models.CaseRequest(
            request_type="new_case",
            status="pending",
            case_id=None,
            case_name=payload["name"],
            color=case_request_core._color_from_name(payload["name"]),
            payload=json.dumps(payload, ensure_ascii=False),
            attachment_name=attachment_name,
            attachment_path=attachment_path,
            attachment_bytes=attachment_bytes,
            requestor_id=None,
            requestor_email=requestor_email,
            ntp_all_sent=False,
            note=f"Email Intake from {email.sender or 'unknown sender'}: {email.subject or '(no subject)'}",
        )
        db.add(record)
        db.flush()
        message.case_request_id = record.id
        message.template_id = template.id
        message.status = "pending_request"
        message.attachment_count = attachment_count
        message.last_error = None
        message.next_retry_at = None
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        if attachment_path:
            try:
                target = Path(attachment_path).resolve()
                root = case_request_core.CASE_REQUEST_UPLOAD_DIR.resolve()
                if root in target.parents:
                    target.unlink(missing_ok=True)
            except Exception:
                logger.exception("email intake attachment cleanup failed")
        raise

    try:
        log_event(
            db,
            action="email_intake_case_request_created",
            actor_id=None,
            target_type="case_request",
            target_id=record.id,
            details={
                "email_intake_message_id": message.id,
                "template_id": template.id,
                "template_name": template.name,
                "sender": email.sender,
                "subject": email.subject,
                "attachment_count": attachment_count,
            },
            request=None,
        )
    except Exception:
        logger.exception("email intake audit event failed")
    try:
        case_request_core.notify_case_request_submitted(db, record, None)
    except Exception:
        logger.exception("email intake case request notification failed")
    return record


def _mark_failed(db: Session, message_id: int, exc: Exception) -> None:
    db.rollback()
    row = db.get(models.EmailIntakeMessage, int(message_id))
    if row is None:
        return
    row.status = "failed"
    row.attempts = int(row.attempts or 0) + 1
    row.last_attempt_at = _utcnow()
    row.last_error = str(exc)[:4000]
    delay_minutes = min(1440, 2 ** min(row.attempts, 10))
    row.next_retry_at = _utcnow() + timedelta(minutes=delay_minutes)
    db.commit()


def process_message(
    db: Session,
    message: models.EmailIntakeMessage,
    settings: EmailIntakeSettings | None = None,
) -> dict[str, Any]:
    settings = settings or load_email_intake_settings()
    if message.status in TERMINAL_STATUSES and message.case_request_id:
        return {"message_id": message.id, "status": message.status, "case_request_id": message.case_request_id}
    email = _normalized_from_record(message)
    message.last_attempt_at = _utcnow()
    if not _sender_allowed(settings, email.sender):
        message.status = "ignored"
        message.last_error = "Sender rejected by Email Intake policy"
        message.next_retry_at = None
        db.commit()
        return {"message_id": message.id, "status": message.status}

    template = first_matching_template(_template_rows(db), email)
    if template is None:
        message.status = "unmatched"
        message.template_id = None
        message.last_error = "No enabled Email Intake template matched"
        message.next_retry_at = None
        db.commit()
        return {"message_id": message.id, "status": message.status}

    try:
        record = _create_pending_request(db, settings, message, template, email)
        return {"message_id": message.id, "status": "pending_request", "case_request_id": record.id}
    except Exception as exc:
        _mark_failed(db, int(message.id), exc)
        raise


def poll_mailbox(
    db: Session,
    *,
    settings: EmailIntakeSettings | None = None,
) -> dict[str, Any]:
    settings = settings or load_email_intake_settings()
    if not settings.ready:
        raise RuntimeError("Email Intake is disabled or its Graph mailbox configuration is incomplete")
    if not _poll_lock.acquire(blocking=False):
        raise RuntimeError("An Email Intake poll is already running")
    try:
        cursor = _cursor(db, settings)
        cursor.last_polled_at = _utcnow()
        db.commit()
        messages, next_cursor, caught_up = delta_messages(settings, cursor.delta_link)
        baseline_only = bool(cursor.baseline_pending) and not settings.process_existing_on_first_run
        results: list[dict[str, Any]] = []
        if not baseline_only:
            for raw in messages:
                row = _upsert_message(db, settings, raw)
                if row is None:
                    continue
                if row.status in TERMINAL_STATUSES or row.status == "unmatched":
                    results.append({"message_id": row.id, "status": row.status, "duplicate": True})
                    continue
                try:
                    results.append(process_message(db, row, settings))
                except Exception as exc:
                    logger.exception("email intake message processing failed message_id=%s", row.id)
                    results.append({"message_id": row.id, "status": "failed", "error": str(exc)[:500]})

        cursor = _cursor(db, settings)
        cursor.delta_link = next_cursor or cursor.delta_link
        cursor.baseline_pending = bool(baseline_only and not caught_up)
        cursor.last_success_at = _utcnow()
        cursor.last_error = None
        cursor.last_error_at = None
        db.commit()
        return {
            "mailbox": settings.mailbox,
            "received": len(messages),
            "processed": len(results),
            "baseline_skipped": len(messages) if baseline_only else 0,
            "baseline_pending": bool(cursor.baseline_pending),
            "results": results,
        }
    except Exception as exc:
        db.rollback()
        try:
            cursor = _cursor(db, settings)
            cursor.last_error = str(exc)[:4000]
            cursor.last_error_at = _utcnow()
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        _poll_lock.release()


def retry_due_messages(db: Session, *, limit: int = 10) -> int:
    settings = load_email_intake_settings()
    if not settings.ready:
        return 0
    rows = (
        db.query(models.EmailIntakeMessage)
        .filter(
            models.EmailIntakeMessage.status == "failed",
            models.EmailIntakeMessage.next_retry_at.isnot(None),
            models.EmailIntakeMessage.next_retry_at <= _utcnow(),
        )
        .order_by(models.EmailIntakeMessage.next_retry_at.asc())
        .limit(max(1, min(int(limit), 100)))
        .all()
    )
    attempted = 0
    for row in rows:
        attempted += 1
        try:
            process_message(db, row, settings)
        except Exception:
            logger.exception("email intake retry failed message_id=%s", row.id)
    return attempted


def serialize_template(template: models.EmailIntakeTemplate) -> dict[str, Any]:
    def parsed(value: Any, fallback: Any) -> Any:
        try:
            result = json.loads(str(value or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback
        return result if isinstance(result, type(fallback)) else fallback

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "enabled": bool(template.enabled),
        "priority": int(template.priority or 100),
        "sender_pattern": template.sender_pattern or "",
        "recipient_pattern": template.recipient_pattern or "",
        "subject_pattern": template.subject_pattern or "",
        "body_markers": parsed(template.body_markers, []),
        "field_markers": parsed(template.field_markers, {}),
        "default_values": parsed(template.default_values, {}),
        "hold_name": template.hold_name or None,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


def serialize_message(message: models.EmailIntakeMessage, *, include_body: bool = False) -> dict[str, Any]:
    try:
        recipients = json.loads(message.recipients or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        recipients = []
    return {
        "id": message.id,
        "mailbox": message.mailbox,
        "graph_message_id": message.graph_message_id,
        "internet_message_id": message.internet_message_id,
        "status": message.status,
        "template_id": message.template_id,
        "template_name": message.template.name if message.template else None,
        "case_request_id": message.case_request_id,
        "sender": message.sender,
        "recipients": recipients,
        "subject": message.subject,
        "received_at": message.received_at.isoformat() if message.received_at else None,
        "body_text": (message.body_text or "") if include_body else None,
        "body_preview": (message.body_text or "")[:500],
        "attachment_count": int(message.attachment_count or 0),
        "attempts": int(message.attempts or 0),
        "last_attempt_at": message.last_attempt_at.isoformat() if message.last_attempt_at else None,
        "next_retry_at": message.next_retry_at.isoformat() if message.next_retry_at else None,
        "last_error": message.last_error,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "updated_at": message.updated_at.isoformat() if message.updated_at else None,
    }


def intake_status(db: Session) -> dict[str, Any]:
    settings = load_email_intake_settings()
    cursor = None
    if settings.mailbox and settings.folder_id:
        cursor = (
            db.query(models.EmailIntakeCursor)
            .filter(
                func.lower(models.EmailIntakeCursor.mailbox) == settings.mailbox.lower(),
                models.EmailIntakeCursor.folder_id == settings.folder_id,
            )
            .first()
        )
    counts = {
        str(status): int(count)
        for status, count in db.query(models.EmailIntakeMessage.status, func.count(models.EmailIntakeMessage.id)).group_by(models.EmailIntakeMessage.status).all()
    }
    return {
        "enabled": settings.enabled,
        "ready": settings.ready,
        "mailbox": settings.mailbox,
        "folder_id": settings.folder_id,
        "poll_interval_seconds": settings.poll_interval_seconds,
        "counts": counts,
        "last_polled_at": cursor.last_polled_at.isoformat() if cursor and cursor.last_polled_at else None,
        "last_success_at": cursor.last_success_at.isoformat() if cursor and cursor.last_success_at else None,
        "last_error": cursor.last_error if cursor else None,
        "last_error_at": cursor.last_error_at.isoformat() if cursor and cursor.last_error_at else None,
        "cursor_initialized": bool(cursor and cursor.delta_link),
        "baseline_pending": bool(cursor and cursor.baseline_pending),
    }
