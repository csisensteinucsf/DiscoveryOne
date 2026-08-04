# app/notes.py
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from uuid import uuid4
import os

from fastapi import Request, APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload
import bleach
from bleach.sanitizer import ALLOWED_PROTOCOLS as BLEACH_PROTOCOLS

from .database import get_db
from . import models
from .auth import current_user as get_current_user
from .audit import log_event
from .permissions import ensure_case_visible, ensure_case_editable, is_requestor, is_sys_admin
from .system_settings import DATA_DIR
from .file_security import scan_payload, validate_attachment_bytes
from .safe_log import debug_suppressed as _debug_suppressed
from .notes_audience import (
    _create_internal_audience_note,
    _delete_internal_audience_note,
    _list_internal_audience_notes,
    _update_internal_audience_note,
)

# ----------------------
# Pydantic Schemas (local to this router for minimal churn)

def _notes_support():
    from . import notes_support
    return notes_support


def _utcnow() -> datetime:
    return _notes_support()._utcnow()


# local helper to avoid dumping huge note bodies into audit rows
def _clip(s, n=140):
    return _notes_support()._clip(s, n=n)

try:
    # Pydantic v2
    from pydantic import BaseModel, Field, ConfigDict
    V2 = True
except Exception:
    from pydantic import BaseModel, Field
    V2 = False

class NoteBase(BaseModel):
    body: str = Field(min_length=1)
    format: str = "plain"
    is_pinned: bool = False

class NoteCreate(NoteBase):
    author: Optional[str] = None

class NoteUpdate(BaseModel):
    body: Optional[str] = None
    format: Optional[str] = None
    is_pinned: Optional[bool] = None

class AttachmentOut(BaseModel):
    id: int
    filename: str
    content_type: Optional[str]
    size: int
    url: str
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    if V2:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True

class NoteOut(BaseModel):
    id: int
    case_id: int
    audience: str = "internal"
    author: Optional[str]
    body: str
    format: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
    attachments: List[AttachmentOut] = []
    if V2:
        model_config = ConfigDict(from_attributes=True)
    else:
        class Config:
            orm_mode = True

# ----------------------
# Router
# ----------------------
router = APIRouter(prefix="/api/cases", tags=["notes"])

NOTE_ATTACHMENT_DIR = Path(os.getenv("NOTE_ATTACHMENT_DIR") or (DATA_DIR / "note_attachments"))
NOTE_ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
NOTE_ATTACHMENT_MAX_BYTES = int(os.getenv("NOTE_ATTACHMENT_MAX_BYTES", str(5 * 1024 * 1024)))
NOTE_ATTACHMENT_ALLOWED_MIME = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}
NOTE_ALLOWED_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "a", "span"]
NOTE_ALLOWED_ATTRS = {"a": ["href", "title", "rel"]}
NOTE_ALLOWED_PROTOCOLS = tuple(set(BLEACH_PROTOCOLS) | {"http", "https", "mailto"})
ALLOWED_NOTE_FORMATS = {"plain", "html"}

def _ensure_case(db: Session, case_id: int, user: models.User | None = None) -> models.Case:
    return _notes_support()._ensure_case(db, case_id, user)


def _attachments_url(case_id: int, note_id: int, attachment_id: int) -> str:
    return _notes_support()._attachments_url(case_id, note_id, attachment_id)


def _serialize_attachment(note: models.CaseNote, attachment: models.CaseNoteAttachment) -> dict:
    return _notes_support()._serialize_attachment(note, attachment)


def _sanitize_note(body: Optional[str], fmt: Optional[str]) -> tuple[str, str]:
    return _notes_support()._sanitize_note(body, fmt)


def _serialize_note(note: models.CaseNote) -> dict:
    return _notes_support()._serialize_note(note)


def _get_note_or_404(db: Session, case_id: int, note_id: int) -> models.CaseNote:
    return _notes_support()._get_note_or_404(db, case_id, note_id)


def _user_matches_note_author(note: models.CaseNote, user: models.User) -> bool:
    return _notes_support()._user_matches_note_author(note, user)


def _ensure_requestor_note_editable(note: models.CaseNote, user: models.User) -> None:
    return _notes_support()._ensure_requestor_note_editable(note, user)


def _ensure_ticket_note_access(user: models.User, *, write: bool = False) -> None:
    return _notes_support()._ensure_ticket_note_access(user, write=write)


def _ensure_active_note_access(user: models.User) -> None:
    return _notes_support()._ensure_active_note_access(user)


def _get_attachment_from_note(note: models.CaseNote, attachment_id: int) -> models.CaseNoteAttachment:
    return _notes_support()._get_attachment_from_note(note, attachment_id)


def _remove_attachment_file(attachment: models.CaseNoteAttachment) -> None:
    return _notes_support()._remove_attachment_file(attachment)


def _sync_case_note_counters(db: Session, case_id: int) -> None:
    return _notes_support()._sync_case_note_counters(db, case_id)


@router.get("/{case_id}/notes", response_model=List[NoteOut])
def list_notes(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    rows = (
        db.query(models.CaseNote)
        .options(
            selectinload(models.CaseNote.attachments).selectinload(models.CaseNoteAttachment.uploaded_by)
        )
        .filter(models.CaseNote.case_id == case_id)
        .filter(func.coalesce(models.CaseNote.audience, "internal") == "internal")
        .order_by(models.CaseNote.is_pinned.desc(), models.CaseNote.updated_at.desc())
        .all()
    )
    return [_serialize_note(r) for r in rows]

@router.get("/{case_id}/notes/counts")
def note_counts(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    case = _ensure_case(db, case_id, user)
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
        if key not in counts:
            continue
        try:
            counts[key] = int(count or 0)
        except Exception:
            counts[key] = 0

    stored_internal = int(getattr(case, "notes_internal_count", 0) or 0)
    stored_requestor = int(getattr(case, "notes_requestor_count", 0) or 0)
    stored_ticket = int(getattr(case, "notes_ticket_count", 0) or 0)
    if (
        stored_internal != counts["internal"]
        or stored_requestor != counts["requestor"]
        or stored_ticket != counts["ticket"]
    ):
        try:
            case.notes_internal_count = counts["internal"]
            case.notes_requestor_count = counts["requestor"]
            case.notes_ticket_count = counts["ticket"]
            db.add(case)
            db.commit()
        except Exception as exc:
            try:
                db.rollback()
            except Exception as rollback_exc:
                _debug_suppressed("suppressed exception in notes.py:rollback_note_counts_repair", rollback_exc)
            _debug_suppressed("suppressed exception in notes.py:note_counts_repair", exc)

    if is_requestor(user):
        counts["internal"] = 0
        counts["ticket"] = 0
    return counts
@router.post("/{case_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(case_id: int, payload: NoteCreate, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    body, fmt = _sanitize_note(payload.body, payload.format)
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    now = _utcnow()
    row = models.CaseNote(
        case_id=case_id,
        audience="internal",
        author=user.username,
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
                "changes": {
                    "body": {"old": None, "new": _clip(getattr(row, "body", None))},
                    "format": {"old": None, "new": getattr(row, "format", None)},
                    "is_pinned": {"old": False, "new": bool(getattr(row, "is_pinned", False))},
                },
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:279", exc)
    db.refresh(row)
    return _serialize_note(row)

@router.put("/{case_id}/notes/{note_id}", response_model=NoteOut)
def update_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != "internal":
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
                    "changes": changes,
                },
                request=request,
            )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:338", exc)
    # Reload with attachments for response
    row = _get_note_or_404(db, case_id, note_id)
    return _serialize_note(row)

@router.patch("/{case_id}/notes/{note_id}", response_model=NoteOut)
def patch_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return update_note(case_id, note_id, payload, db=db, request=request, user=user)
@router.delete("/{case_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(case_id: int, note_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != "internal":
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
                "body": body_snapshot,
                "format": fmt_snapshot,
                "is_pinned": pinned_snaps    },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:delete_internal_audience_note", exc)


@router.get("/{case_id}/evidence_tracking", response_model=List[NoteOut])
def list_evidence_tracking_notes(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    return _list_internal_audience_notes(case_id, "evidence_tracking", db, user)


@router.post("/{case_id}/evidence_tracking", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_evidence_tracking_note(case_id: int, payload: NoteCreate, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    return _create_internal_audience_note(case_id, "evidence_tracking", payload, db, request, user)


@router.put("/{case_id}/evidence_tracking/{note_id}", response_model=NoteOut)
def update_evidence_tracking_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return _update_internal_audience_note(case_id, note_id, "evidence_tracking", payload, db, request, user)


@router.patch("/{case_id}/evidence_tracking/{note_id}", response_model=NoteOut)
def patch_evidence_tracking_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return _update_internal_audience_note(case_id, note_id, "evidence_tracking", payload, db, request, user)


@router.delete("/{case_id}/evidence_tracking/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence_tracking_note(case_id: int, note_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _delete_internal_audience_note(case_id, note_id, "evidence_tracking", db, request, user)
    return


@router.get("/{case_id}/final_report", response_model=List[NoteOut])
def list_final_report_notes(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    return _list_internal_audience_notes(case_id, "final_report", db, user)


@router.post("/{case_id}/final_report", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_final_report_note(case_id: int, payload: NoteCreate, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    return _create_internal_audience_note(case_id, "final_report", payload, db, request, user)


@router.put("/{case_id}/final_report/{note_id}", response_model=NoteOut)
def update_final_report_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return _update_internal_audience_note(case_id, note_id, "final_report", payload, db, request, user)


@router.patch("/{case_id}/final_report/{note_id}", response_model=NoteOut)
def patch_final_report_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return _update_internal_audience_note(case_id, note_id, "final_report", payload, db, request, user)


@router.delete("/{case_id}/final_report/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_final_report_note(case_id: int, note_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _delete_internal_audience_note(case_id, note_id, "final_report", db, request, user)
    return


@router.get("/{case_id}/active_notes", response_model=List[NoteOut])
def list_active_notes(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_active_note_access(user)
    return _list_internal_audience_notes(case_id, "active", db, user)


@router.post("/{case_id}/active_notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_active_note(case_id: int, payload: NoteCreate, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_active_note_access(user)
    return _create_internal_audience_note(case_id, "active", payload, db, request, user)


@router.put("/{case_id}/active_notes/{note_id}", response_model=NoteOut)
def update_active_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _ensure_active_note_access(user)
    return _update_internal_audience_note(case_id, note_id, "active", payload, db, request, user)


@router.patch("/{case_id}/active_notes/{note_id}", response_model=NoteOut)
def patch_active_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _ensure_active_note_access(user)
    return _update_internal_audience_note(case_id, note_id, "active", payload, db, request, user)


@router.delete("/{case_id}/active_notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_active_note(case_id: int, note_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_active_note_access(user)
    _delete_internal_audience_note(case_id, note_id, "active", db, request, user)
    return


@router.get("/{case_id}/ticket_notes", response_model=List[NoteOut])
def list_ticket_notes(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    _ensure_ticket_note_access(user)
    rows = (
        db.query(models.CaseNote)
        .options(
            selectinload(models.CaseNote.attachments).selectinload(models.CaseNoteAttachment.uploaded_by)
        )
        .filter(models.CaseNote.case_id == case_id)
        .filter(func.coalesce(models.CaseNote.audience, "internal") == "ticket")
        .order_by(models.CaseNote.is_pinned.desc(), models.CaseNote.updated_at.desc())
        .all()
    )
    return [_serialize_note(r) for r in rows]


@router.post("/{case_id}/ticket_notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_ticket_note(case_id: int, payload: NoteCreate, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    _ensure_ticket_note_access(user, write=True)
    body, fmt = _sanitize_note(payload.body, payload.format)
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    now = _utcnow()
    row = models.CaseNote(
        case_id=case_id,
        audience="ticket",
        author=user.username,
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
                "audience": "ticket",
                "changes": {
                    "body": {"old": None, "new": _clip(getattr(row, "body", None))},
                    "format": {"old": None, "new": getattr(row, "format", None)},
                    "is_pinned": {"old": False, "new": bool(getattr(row, "is_pinned", False))},
                },
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:449", exc)
    db.refresh(row)
    return _serialize_note(row)


@router.put("/{case_id}/ticket_notes/{note_id}", response_model=NoteOut)
def update_ticket_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _ensure_case(db, case_id, user)
    _ensure_ticket_note_access(user, write=True)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != "ticket":
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
                    "audience": "ticket",
                    "changes": changes,
                },
                request=request,
            )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:510", exc)
    row = _get_note_or_404(db, case_id, note_id)
    return _serialize_note(row)


@router.patch("/{case_id}/ticket_notes/{note_id}", response_model=NoteOut)
def patch_ticket_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return update_ticket_note(case_id, note_id, payload, db=db, request=request, user=user)


@router.delete("/{case_id}/ticket_notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket_note(case_id: int, note_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    _ensure_ticket_note_access(user, write=True)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != "ticket":
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
                "audience": "ticket",
                "body": body_snapshot,
                "format": fmt_snapshot,
                "is_pinned": pinned_snapshot,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:561", exc)
    return


@router.get("/{case_id}/requestor_notes", response_model=List[NoteOut])
def list_requestor_notes(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    rows = (
        db.query(models.CaseNote)
        .options(
            selectinload(models.CaseNote.attachments).selectinload(models.CaseNoteAttachment.uploaded_by)
        )
        .filter(models.CaseNote.case_id == case_id)
        .filter(func.coalesce(models.CaseNote.audience, "internal") == "requestor")
        .order_by(models.CaseNote.is_pinned.desc(), models.CaseNote.updated_at.desc())
        .all()
    )
    return [_serialize_note(r) for r in rows]


@router.post("/{case_id}/requestor_notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_requestor_note(case_id: int, payload: NoteCreate, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    body, fmt = _sanitize_note(payload.body, payload.format)
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    now = _utcnow()
    row = models.CaseNote(
        case_id=case_id,
        audience="requestor",
        author=user.username,
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
            action="requestor_note_create",
            target_type="note",
            target_id=row.id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "note_id": row.id,
                "audience": "requestor",
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:617", exc)
    db.refresh(row)
    return _serialize_note(_get_note_or_404(db, case_id, row.id))


@router.put("/{case_id}/requestor_notes/{note_id}", response_model=NoteOut)
def update_requestor_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _ensure_case(db, case_id, user)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != "requestor":
        raise HTTPException(status_code=404, detail="note not found")
    _ensure_requestor_note_editable(row, user)
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
    try:
        case = db.get(models.Case, case_id)
        log_event(
            db,
            action="requestor_note_update",
            target_type="note",
            target_id=row.id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "note_id": row.id,
                "audience": "requestor",
                "changes": {
                    "body": {"old": _clip(prev_body), "new": _clip(getattr(row, "body", None))} if prev_body != row.body else None,
                    "format": {"old": prev_format, "new": getattr(row, "format", None)} if prev_format != row.format else None,
                    "is_pinned": {"old": prev_pinned, "new": bool(getattr(row, "is_pinned", False))} if prev_pinned != bool(getattr(row, "is_pinned", False)) else None,
                },
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:672", exc)
    row = _get_note_or_404(db, case_id, note_id)
    return _serialize_note(row)


@router.patch("/{case_id}/requestor_notes/{note_id}", response_model=NoteOut)
def patch_requestor_note(
    case_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    return update_requestor_note(case_id, note_id, payload, db=db, request=request, user=user)


@router.delete("/{case_id}/requestor_notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_requestor_note(case_id: int, note_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(get_current_user)):
    _ensure_case(db, case_id, user)
    row = _get_note_or_404(db, case_id, note_id)
    if (getattr(row, "audience", None) or "internal") != "requestor":
        raise HTTPException(status_code=404, detail="note not found")
    _ensure_requestor_note_editable(row, user)
    note_id_int = int(getattr(row, 'id', 0) or 0)
    for attachment in list(getattr(row, "attachments", []) or []):
        _remove_attachment_file(attachment)
    db.delete(row)
    db.commit()
    _sync_case_note_counters(db, case_id)
    try:
        case = db.get(models.Case, case_id)
        log_event(
            db,
            action="requestor_note_delete",
            target_type="note",
            target_id=note_id_int,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "note_id": note_id_int,
                "audience": "requestor",
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in notes.py:717", exc)
    return


def _store_attachment(*args, **kwargs):
    from .note_attachments import _store_attachment as _impl
    return _impl(*args, **kwargs)


def upload_note_attachment(*args, **kwargs):
    from .note_attachments import upload_note_attachment as _impl
    return _impl(*args, **kwargs)


def delete_note_attachment(*args, **kwargs):
    from .note_attachments import delete_note_attachment as _impl
    return _impl(*args, **kwargs)


def download_note_attachment(*args, **kwargs):
    from .note_attachments import download_note_attachment as _impl
    return _impl(*args, **kwargs)
