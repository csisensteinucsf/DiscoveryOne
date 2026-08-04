from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .auth import require_admin
from .database import get_db
from .email_intake_graph import EmailIntakeGraphError, load_email_intake_settings, test_connection
from .email_intake_matching import (
    ALLOWED_EXTRACTED_FIELDS,
    extract_case_request_payload,
    normalize_graph_message,
    template_matches,
)
from .email_intake_service import (
    intake_status,
    poll_mailbox,
    process_message,
    serialize_message,
    serialize_template,
)

router = APIRouter(
    prefix="/api/system/email-intake",
    tags=["system-email-intake"],
    dependencies=[Depends(require_admin)],
)


class EmailIntakeTemplatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    enabled: bool = True
    priority: int = Field(default=100, ge=1, le=10000)
    sender_pattern: str | None = Field(default=None, max_length=512)
    recipient_pattern: str | None = Field(default=None, max_length=512)
    subject_pattern: str | None = Field(default=None, max_length=512)
    body_markers: list[str] = Field(default_factory=list, max_length=25)
    field_markers: dict[str, str] = Field(default_factory=dict)
    default_values: dict[str, Any] = Field(default_factory=dict)
    hold_name: str = Field(default="Hold A", min_length=1, max_length=255)

    @field_validator("body_markers")
    @classmethod
    def validate_body_markers(cls, values: list[str]) -> list[str]:
        cleaned = [str(value or "").strip() for value in values if str(value or "").strip()]
        if any(len(value) > 255 for value in cleaned):
            raise ValueError("Each body marker must be 255 characters or fewer")
        return cleaned

    @field_validator("field_markers")
    @classmethod
    def validate_field_markers(cls, values: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        for key, value in values.items():
            if key not in ALLOWED_EXTRACTED_FIELDS:
                raise ValueError(f"Unsupported extracted field: {key}")
            marker = str(value or "").strip()
            if marker:
                cleaned[key] = marker[:255]
        return cleaned

    @field_validator("default_values")
    @classmethod
    def validate_default_values(cls, values: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(values) - ALLOWED_EXTRACTED_FIELDS)
        if unknown:
            raise ValueError(f"Unsupported default fields: {', '.join(unknown)}")
        return {key: value for key, value in values.items() if value not in (None, "")}


class EmailSample(BaseModel):
    sender: str = Field(min_length=3, max_length=320)
    recipients: list[str] = Field(default_factory=list, max_length=50)
    subject: str = Field(default="", max_length=2000)
    body: str = Field(default="", max_length=200_000)
    body_content_type: str = Field(default="text", pattern="^(?i:text|html)$")
    received_at: datetime | None = None


class EmailIntakeTemplateTestPayload(BaseModel):
    template_id: int | None = Field(default=None, gt=0)
    template: EmailIntakeTemplatePayload | None = None
    sample: EmailSample


class CursorResetPayload(BaseModel):
    confirm: bool = False


def _validate_match_scope(payload: EmailIntakeTemplatePayload) -> None:
    if not any(
        [
            str(payload.sender_pattern or "").strip(),
            str(payload.recipient_pattern or "").strip(),
            str(payload.subject_pattern or "").strip(),
            payload.body_markers,
        ]
    ):
        raise HTTPException(status_code=422, detail="A template needs at least one sender, recipient, subject, or body match condition")


def _apply_template_payload(model: models.EmailIntakeTemplate, payload: EmailIntakeTemplatePayload) -> None:
    model.name = payload.name.strip()
    model.description = str(payload.description or "").strip() or None
    model.enabled = payload.enabled
    model.priority = payload.priority
    model.sender_pattern = str(payload.sender_pattern or "").strip() or None
    model.recipient_pattern = str(payload.recipient_pattern or "").strip() or None
    model.subject_pattern = str(payload.subject_pattern or "").strip() or None
    model.body_markers = json.dumps(payload.body_markers, ensure_ascii=False)
    model.field_markers = json.dumps(payload.field_markers, ensure_ascii=False)
    model.default_values = json.dumps(payload.default_values, ensure_ascii=False)
    model.hold_name = payload.hold_name.strip()


def _template_namespace(payload: EmailIntakeTemplatePayload) -> SimpleNamespace:
    return SimpleNamespace(
        id=0,
        enabled=payload.enabled,
        priority=payload.priority,
        sender_pattern=payload.sender_pattern,
        recipient_pattern=payload.recipient_pattern,
        subject_pattern=payload.subject_pattern,
        body_markers=json.dumps(payload.body_markers),
        field_markers=json.dumps(payload.field_markers),
        default_values=json.dumps(payload.default_values),
        hold_name=payload.hold_name,
    )


@router.get("/status")
def get_email_intake_status(db: Session = Depends(get_db)):
    return intake_status(db)


@router.post("/test-connection")
def test_email_intake_connection():
    try:
        return {"ok": True, **test_connection(load_email_intake_settings())}
    except EmailIntakeGraphError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/poll")
def run_email_intake_poll(db: Session = Depends(get_db)):
    try:
        return poll_mailbox(db)
    except (EmailIntakeGraphError, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/cursor/reset")
def reset_email_intake_cursor(
    payload: CursorResetPayload,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
    request: Request = None,
):
    if not payload.confirm:
        raise HTTPException(status_code=422, detail="Confirmation is required")
    settings = load_email_intake_settings()
    deleted = 0
    if settings.mailbox and settings.folder_id:
        deleted = (
            db.query(models.EmailIntakeCursor)
            .filter(
                func.lower(models.EmailIntakeCursor.mailbox) == settings.mailbox.lower(),
                models.EmailIntakeCursor.folder_id == settings.folder_id,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
    log_event(
        db,
        action="email_intake_cursor_reset",
        actor_id=actor.id,
        target_type="email_intake",
        target_id=None,
        details={"mailbox": settings.mailbox, "folder_id": settings.folder_id, "deleted": deleted},
        request=request,
    )
    return {"ok": True, "deleted": deleted}


@router.get("/templates")
def list_email_intake_templates(db: Session = Depends(get_db)):
    rows = db.query(models.EmailIntakeTemplate).order_by(models.EmailIntakeTemplate.priority.asc(), models.EmailIntakeTemplate.id.asc()).all()
    return [serialize_template(row) for row in rows]


@router.post("/templates")
def create_email_intake_template(
    payload: EmailIntakeTemplatePayload,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
    request: Request = None,
):
    _validate_match_scope(payload)
    existing = db.query(models.EmailIntakeTemplate.id).filter(func.lower(models.EmailIntakeTemplate.name) == payload.name.strip().lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An Email Intake template with this name already exists")
    model = models.EmailIntakeTemplate(created_by_id=actor.id)
    _apply_template_payload(model, payload)
    db.add(model)
    try:
        db.commit()
        db.refresh(model)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An Email Intake template with this name already exists")
    log_event(db, action="email_intake_template_created", actor_id=actor.id, target_type="email_intake_template", target_id=model.id, details={"name": model.name}, request=request)
    return serialize_template(model)


@router.put("/templates/{template_id}")
def update_email_intake_template(
    template_id: int,
    payload: EmailIntakeTemplatePayload,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
    request: Request = None,
):
    _validate_match_scope(payload)
    model = db.get(models.EmailIntakeTemplate, template_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Email Intake template not found")
    duplicate = (
        db.query(models.EmailIntakeTemplate.id)
        .filter(
            models.EmailIntakeTemplate.id != model.id,
            func.lower(models.EmailIntakeTemplate.name) == payload.name.strip().lower(),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="An Email Intake template with this name already exists")
    _apply_template_payload(model, payload)
    db.commit()
    db.refresh(model)
    log_event(db, action="email_intake_template_updated", actor_id=actor.id, target_type="email_intake_template", target_id=model.id, details={"name": model.name}, request=request)
    return serialize_template(model)


@router.delete("/templates/{template_id}")
def delete_email_intake_template(
    template_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
    request: Request = None,
):
    model = db.get(models.EmailIntakeTemplate, template_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Email Intake template not found")
    name = model.name
    db.delete(model)
    db.commit()
    log_event(db, action="email_intake_template_deleted", actor_id=actor.id, target_type="email_intake_template", target_id=template_id, details={"name": name}, request=request)
    return {"ok": True}


@router.post("/templates/test")
def test_email_intake_template(payload: EmailIntakeTemplateTestPayload, db: Session = Depends(get_db)):
    if payload.template_id:
        template = db.get(models.EmailIntakeTemplate, payload.template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="Email Intake template not found")
    elif payload.template is not None:
        _validate_match_scope(payload.template)
        template = _template_namespace(payload.template)
    else:
        raise HTTPException(status_code=422, detail="Provide template_id or an unsaved template")
    sample = payload.sample
    graph_message = {
        "id": "template-test",
        "internetMessageId": "template-test@example.invalid",
        "receivedDateTime": (sample.received_at or datetime.now(timezone.utc)).isoformat(),
        "from": {"emailAddress": {"address": sample.sender}},
        "toRecipients": [{"emailAddress": {"address": value}} for value in sample.recipients],
        "subject": sample.subject,
        "body": {"contentType": sample.body_content_type, "content": sample.body},
        "hasAttachments": False,
    }
    email = normalize_graph_message(graph_message)
    matched, failures = template_matches(template, email)
    settings = load_email_intake_settings()
    extracted = extract_case_request_payload(template, email, requestor_from_sender=settings.requestor_from_sender)
    return {"matched": matched, "failures": failures, "extracted": extracted}


@router.get("/messages")
def list_email_intake_messages(
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.EmailIntakeMessage)
    if status:
        query = query.filter(models.EmailIntakeMessage.status == status.strip().lower())
    total = query.count()
    rows = query.order_by(models.EmailIntakeMessage.received_at.desc(), models.EmailIntakeMessage.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [serialize_message(row) for row in rows]}


@router.get("/messages/{message_id}")
def get_email_intake_message(message_id: int, db: Session = Depends(get_db)):
    row = db.get(models.EmailIntakeMessage, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Email Intake message not found")
    return serialize_message(row, include_body=True)


@router.post("/messages/{message_id}/retry")
def retry_email_intake_message(
    message_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
    request: Request = None,
):
    row = db.get(models.EmailIntakeMessage, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Email Intake message not found")
    if row.case_request_id:
        raise HTTPException(status_code=409, detail="This email already created a pending case request")
    row.status = "received"
    row.last_error = None
    row.next_retry_at = None
    db.commit()
    try:
        result = process_message(db, row)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    log_event(db, action="email_intake_message_retried", actor_id=actor.id, target_type="email_intake_message", target_id=row.id, details={"result": result}, request=request)
    return result


@router.post("/messages/{message_id}/ignore")
def ignore_email_intake_message(
    message_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(require_admin),
    request: Request = None,
):
    row = db.get(models.EmailIntakeMessage, message_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Email Intake message not found")
    if row.case_request_id:
        raise HTTPException(status_code=409, detail="This email already created a pending case request")
    row.status = "ignored"
    row.last_error = "Ignored by administrator"
    row.next_retry_at = None
    db.commit()
    log_event(db, action="email_intake_message_ignored", actor_id=actor.id, target_type="email_intake_message", target_id=row.id, details={"subject": row.subject}, request=request)
    return serialize_message(row)