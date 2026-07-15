from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from . import models
from .audit import log_event
from .permissions import ensure_case_editable
from .safe_log import debug_suppressed as _debug_suppressed
from . import notes_support


def _utcnow():
    return notes_support._utcnow()


def _clip(value, n=140):
    return notes_support._clip(value, n=n)


def _ensure_case(db: Session, case_id: int, user: models.User | None = None) -> models.Case:
    return notes_support._ensure_case(db, case_id, user)


def _sanitize_note(body, fmt):
    return notes_support._sanitize_note(body, fmt)


def _serialize_note(note: models.CaseNote) -> dict:
    return notes_support._serialize_note(note)


def _get_note_or_404(db: Session, case_id: int, note_id: int) -> models.CaseNote:
    return notes_support._get_note_or_404(db, case_id, note_id)


def _remove_attachment_file(attachment: models.CaseNoteAttachment) -> None:
    return notes_support._remove_attachment_file(attachment)


def _sync_case_note_counters(db: Session, case_id: int) -> None:
    return notes_support._sync_case_note_counters(db, case_id)

def _list_internal_audience_notes(
    case_id: int,
    audience: str,
    db: Session,
    user: models.User,
) -> list[dict]:
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    rows = (
        db.query(models.CaseNote)
        .options(
            selectinload(models.CaseNote.attachments).selectinload(models.CaseNoteAttachment.uploaded_by)
        )
        .filter(models.CaseNote.case_id == case_id)
        .filter(func.coalesce(models.CaseNote.audience, "internal") == audience)
        .order_by(models.CaseNote.is_pinned.desc(), models.CaseNote.updated_at.desc())
        .all()
    )
    return [_serialize_note(r) for r in rows]


def _create_internal_audience_note(
    case_id: int,
    audience: str,
    payload: Any,
    db: Session,
    request: Request,
    user: models.User,
) -> dict:
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    body, fmt = _sanitize_note(payload.body, payload.format)
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    now = _utcnow()
    row = models.CaseNote(
        case_id=case_id,
        audience=audience,
        author=payload.author or user.username,
        body=body,
        format=fmt,
        is_pinned=bool(payload.is_pinned),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    _sync_case_note_counters(db, case_id)
    try:
        case = db.get(models.Case, case_id)
        log_event(
            db,
            action="note_update",
            target_type="note",
            target_id=row.id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "note_id": row.id,
                "audience": audience,
                "changes": {
                    "body": {"old": None, "new": _clip(getattr(row, "body", None))},
                    "format": {"old": None, "new": getattr(row, "format", None)},
                    "is_pinned": {"old": False, "new": bool(getattr(row, "is_pinned", False))},
                },
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:create_internal_audience_note", exc)
    db.refresh(row)
    return _serialize_note(row)


def _update_internal_audience_note(
    case_id: int,
    note_id: int,
    audience: str,
    payload: Any,
    db: Session,
    request: Request,
    user: models.User,
) -> dict:
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != audience:
        raise HTTPException(status_code=404, detail="note not found")
    prev_body = getattr(row, 'body', None)
    prev_format = getattr(row, 'format', None)
    prev_pinned = bool(getattr(row, 'is_pinned', False))
    if payload.body is not None or payload.format is not None:
        raw_body = payload.body if payload.body is not None else row.body
        raw_format = payload.format if payload.format is not None else row.format
        clean_body, clean_format = _sanitize_note(raw_body, raw_format)
        if not clean_body:
            raise HTTPException(status_code=400, detail="body required")
        row.body = clean_body
        row.format = clean_format
    if payload.is_pinned is not None:
        row.is_pinned = bool(payload.is_pinned)
    row.updated_at = _utcnow()
    db.commit()
    db.refresh(row)
    try:
        case = db.get(models.Case, case_id)
        changes = {}
        if prev_body != row.body:
            changes["body"] = {"old": _clip(prev_body), "new": _clip(getattr(row, "body", None))}
        if prev_format != row.format:
            changes["format"] = {"old": prev_format, "new": getattr(row, "format", None)}
        new_pinned = bool(getattr(row, "is_pinned", False))
        if prev_pinned != new_pinned:
            changes["is_pinned"] = {"old": prev_pinned, "new": new_pinned}
        if changes:
            log_event(
                db,
                action="note_update",
                target_type="note",
                target_id=row.id,
                actor_id=user.id,
                details={
                    "case_id": case_id,
                    "case_name": getattr(case, "name", None) if case else None,
                    "note_id": row.id,
                    "audience": audience,
                    "changes": changes,
                },
                request=request,
            )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:update_internal_audience_note", exc)
    row = _get_note_or_404(db, case_id, note_id)
    return _serialize_note(row)


def _delete_internal_audience_note(
    case_id: int,
    note_id: int,
    audience: str,
    db: Session,
    request: Request,
    user: models.User,
) -> None:
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != audience:
        raise HTTPException(status_code=404, detail="note not found")
    note_id_int = int(getattr(row, 'id', 0) or 0)
    body_snapshot = _clip(getattr(row, 'body', None))
    fmt_snapshot = getattr(row, 'format', None)
    pinned_snapshot = bool(getattr(row, 'is_pinned', False))
    for attachment in list(getattr(row, "attachments", []) or []):
        _remove_attachment_file(attachment)
    db.delete(row)
    db.commit()
    _sync_case_note_counters(db, case_id)
    try:
        case = db.get(models.Case, case_id)
        log_event(
            db,
            action="note_delete",
            target_type="note",
            target_id=note_id_int,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "note_id": note_id_int,
                "audience": audience,
                "body": body_snapshot,
                "format": fmt_snapshot,
                "is_pinned": pinned_snapshot,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:delete_internal_audience_note", exc)



