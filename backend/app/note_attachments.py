from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import models
from .auth import current_user as get_current_user
from .database import get_db
from . import notes as notes_core

router = APIRouter(prefix="/api/cases", tags=["notes"])

def _store_attachment(file: UploadFile, payload: bytes, mime: str) -> tuple[str, str, int]:
    original_name = Path(file.filename or "attachment").name or "attachment"
    ext_map = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
    }
    ext = ext_map.get(mime, Path(original_name).suffix or ".bin")
    stored_name = f"{uuid4().hex}{ext}"
    dest = notes_core.NOTE_ATTACHMENT_DIR / stored_name
    dest.write_bytes(payload)
    return original_name, stored_name, len(payload)


def _ensure_note_attachment_access(note: models.CaseNote, user: models.User, *, write: bool) -> None:
    audience = (getattr(note, "audience", None) or "internal").strip().lower()
    if audience == "active":
        notes_core._ensure_active_note_access(user)
    elif audience == "requestor":
        if write:
            notes_core._ensure_requestor_note_editable(note, user)
    elif audience == "ticket":
        notes_core._ensure_ticket_note_access(user, write=write)
    else:
        notes_core.ensure_case_editable(user)


@router.post("/{case_id}/notes/{note_id}/attachments", response_model=notes_core.AttachmentOut)
def upload_note_attachment(
    case_id: int,
    note_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    notes_core._ensure_case(db, case_id, user)
    note = notes_core._get_note_or_404(db, case_id, note_id)
    _ensure_note_attachment_access(note, user, write=True)
    payload = file.file.read()
    try:
        file.file.close()
    except Exception as exc:
        notes_core._debug_suppressed("suppressed exception in notes.py:758", exc)
    try:
        mime = notes_core.validate_attachment_bytes(
            payload,
            file.filename or "attachment",
            max_bytes=notes_core.NOTE_ATTACHMENT_MAX_BYTES,
            allowed_mime_types=notes_core.NOTE_ATTACHMENT_ALLOWED_MIME,
            unsupported_detail="Only PNG, JPEG, GIF, WebP, PDF, DOC, DOCX, XLSX, or XLS files are allowed for note attachments.",
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
            max_mb = max(1, notes_core.NOTE_ATTACHMENT_MAX_BYTES // (1024 * 1024))
            raise HTTPException(status_code=exc.status_code, detail=f"Attachment too large. Maximum {max_mb} MB per file.") from exc
        raise
    notes_core.scan_payload(payload, file.filename or "attachment", request=request, actor=user)
    original_name, stored_name, size = _store_attachment(file, payload, mime)
    attachment = models.CaseNoteAttachment(
        note_id=note.id,
        stored_filename=stored_name,
        original_filename=original_name,
        content_type=mime,
        size=size,
        uploaded_by_id=getattr(user, "id", None),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    response = notes_core._serialize_attachment(note, attachment)
    try:
        notes_core.log_event(
            db,
            action="note_attachment_upload",
            target_type="note_attachment",
            target_id=attachment.id,
            actor_id=user.id,
            details={
                "case_id": note.case_id,
                "note_id": note.id,
                "attachment_id": attachment.id,
                "filename": original_name,
                "content_type": mime,
                "size": size,
            },
            request=request,
        )
    except Exception as exc:
        notes_core._debug_suppressed("suppressed exception in notes.py:803", exc)
    return response


@router.delete("/{case_id}/notes/{note_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note_attachment(
    case_id: int,
    note_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    notes_core._ensure_case(db, case_id, user)
    note = notes_core._get_note_or_404(db, case_id, note_id)
    _ensure_note_attachment_access(note, user, write=True)
    attachment = notes_core._get_attachment_from_note(note, attachment_id)
    notes_core._remove_attachment_file(attachment)
    db.delete(attachment)
    db.commit()
    try:
        notes_core.log_event(
            db,
            action="note_attachment_delete",
            target_type="note_attachment",
            target_id=attachment_id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "note_id": note_id,
                "attachment_id": attachment_id,
                "filename": attachment.original_filename,
            },
            request=request,
        )
    except Exception as exc:
        notes_core._debug_suppressed("suppressed exception in notes.py:845", exc)
    return


@router.get("/{case_id}/notes/{note_id}/attachments/{attachment_id}/download")
def download_note_attachment(
    case_id: int,
    note_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    case = notes_core._ensure_case(db, case_id, user)
    note = notes_core._get_note_or_404(db, case_id, note_id)
    _ensure_note_attachment_access(note, user, write=False)
    attachment = notes_core._get_attachment_from_note(note, attachment_id)
    path = notes_core.NOTE_ATTACHMENT_DIR / attachment.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="attachment file missing")
    response = FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_filename or f"attachment-{attachment.id}",
    )
    try:
        notes_core.log_event(
            db,
            action="note_attachment_download",
            target_type="note_attachment",
            target_id=attachment.id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "note_id": note_id,
                "attachment_id": attachment.id,
                "filename": attachment.original_filename,
            },
            request=request,
        )
    except Exception as exc:
        notes_core._debug_suppressed("suppressed exception in notes.py:893", exc)
    return response

