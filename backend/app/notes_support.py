from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import bleach
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from . import models
from . import notes as notes_core


def _utcnow() -> datetime:
    # CaseNote columns are naive DateTime; keep stored values as UTC-naive while avoiding datetime.utcnow().
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clip(s, n=140):
    try:
        t = (s or "")
        if len(t) <= n:
            return t
        return t[:n] + "..."
    except Exception:
        return ""


def _ensure_case(db: Session, case_id: int, user: models.User | None = None) -> models.Case:
    obj = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Case not found")
    if user is not None:
        notes_core.ensure_case_visible(obj, user, db)
    return obj


def _attachments_url(case_id: int, note_id: int, attachment_id: int) -> str:
    return f"/api/cases/{case_id}/notes/{note_id}/attachments/{attachment_id}/download"


def _serialize_attachment(note: models.CaseNote, attachment: models.CaseNoteAttachment) -> dict:
    if not attachment:
        return {}
    uploader = getattr(getattr(attachment, "uploaded_by", None), "username", None)
    return {
        "id": attachment.id,
        "filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size": attachment.size,
        "uploaded_by": uploader,
        "uploaded_at": attachment.created_at or note.updated_at,
        "url": _attachments_url(note.case_id, note.id, attachment.id),
    }


def _sanitize_note(body: Optional[str], fmt: Optional[str]) -> tuple[str, str]:
    text = (body or "").strip()
    format_value = (fmt or "plain").strip().lower()
    if format_value not in notes_core.ALLOWED_NOTE_FORMATS:
        format_value = "plain"
    if format_value == "html":
        cleaned = bleach.clean(
            text,
            tags=notes_core.NOTE_ALLOWED_TAGS,
            attributes=notes_core.NOTE_ALLOWED_ATTRS,
            protocols=notes_core.NOTE_ALLOWED_PROTOCOLS,
            strip=True,
        )
        return cleaned, "html"
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
    return cleaned, "plain"


def _serialize_note(note: models.CaseNote) -> dict:
    attachments = [
        _serialize_attachment(note, att)
        for att in getattr(note, "attachments", []) or []
    ]
    return {
        "id": note.id,
        "case_id": note.case_id,
        "audience": getattr(note, "audience", None) or "internal",
        "author": note.author,
        "body": note.body,
        "format": note.format,
        "is_pinned": note.is_pinned,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "attachments": attachments,
    }


def _get_note_or_404(db: Session, case_id: int, note_id: int) -> models.CaseNote:
    note = (
        db.query(models.CaseNote)
        .options(
            selectinload(models.CaseNote.attachments).selectinload(models.CaseNoteAttachment.uploaded_by)
        )
        .filter(models.CaseNote.id == note_id, models.CaseNote.case_id == case_id)
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    return note


def _user_matches_note_author(note: models.CaseNote, user: models.User) -> bool:
    author = (getattr(note, "author", None) or "").strip().lower()
    if not author:
        return False
    username = (getattr(user, "username", None) or "").strip().lower()
    email = (getattr(user, "email", None) or "").strip().lower()
    return author in {username, email}


def _ensure_requestor_note_editable(note: models.CaseNote, user: models.User) -> None:
    try:
        notes_core.ensure_case_editable(user)
        return
    except Exception as exc:
        notes_core._debug_suppressed("suppressed exception in notes_support.py:122", exc)
    if _user_matches_note_author(note, user):
        return
    raise HTTPException(status_code=403, detail="Only the author can modify this requestor note")


def _ensure_ticket_note_access(user: models.User) -> None:
    if notes_core.is_requestor(user):
        raise HTTPException(status_code=403, detail="Requestor accounts cannot access ticket notes")


def _ensure_active_note_access(user: models.User) -> None:
    if not notes_core.is_sys_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _get_attachment_from_note(note: models.CaseNote, attachment_id: int) -> models.CaseNoteAttachment:
    for att in getattr(note, "attachments", []) or []:
        if att.id == attachment_id:
            return att
    raise HTTPException(status_code=404, detail="attachment not found")


def _remove_attachment_file(attachment: models.CaseNoteAttachment) -> None:
    if not attachment or not getattr(attachment, "stored_filename", None):
        return
    try:
        path = notes_core.NOTE_ATTACHMENT_DIR / attachment.stored_filename
        if path.exists():
            path.unlink()
    except Exception as exc:
        notes_core._debug_suppressed("suppressed exception in notes_support.py:151", exc)


def _sync_case_note_counters(db: Session, case_id: int) -> None:
    try:
        rows = (
            db.query(
                func.coalesce(models.CaseNote.audience, "internal").label("audience"),
                func.count(models.CaseNote.id).label("count"),
            )
            .filter(models.CaseNote.case_id == case_id)
            .group_by(func.coalesce(models.CaseNote.audience, "internal"))
            .all()
        )
        counts = {"internal": 0, "requestor": 0, "ticket": 0}
        for audience, count in rows:
            key = str(audience or "internal").strip().lower() or "internal"
            if key in counts:
                try:
                    counts[key] = int(count or 0)
                except Exception:
                    counts[key] = 0
        case = db.get(models.Case, case_id)
        if not case:
            return
        case.notes_internal_count = counts["internal"]
        case.notes_requestor_count = counts["requestor"]
        case.notes_ticket_count = counts["ticket"]
        db.add(case)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception as rollback_exc:
            notes_core._debug_suppressed("suppressed exception in notes_support.py:rollback_note_counter_sync", rollback_exc)
        notes_core._debug_suppressed("suppressed exception in notes_support.py:sync_case_note_counters", exc)
