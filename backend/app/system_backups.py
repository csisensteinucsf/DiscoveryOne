"""System backup management endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .app_branding import app_display_name, branded_subject
from . import models
from .audit import log_event
from .auth import current_user as get_current_user
from .backups import DatabaseBackupManager, backup_encryption_health, notify_missing_backup_key
from .system_admin_config import BackupSettingsPayload, public_backup_settings_config
from .system_settings import load_system_settings, save_system_settings
from .database import SessionLocal
from .emailer import send_email
from .file_security import scan_payload
from .notifications import _send_teams_notification
from .permissions import is_sys_admin
from .safe_log import debug_suppressed as _debug_suppressed

router = APIRouter(prefix="/api", tags=["system"])
BACKUP_RESTORE_CONFIRM_TEXT = "RESTORE"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user_display_name(user: Optional[models.User]) -> str:
    if not user:
        return ""
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    combined = " ".join(part for part in (first, last) if part)
    if combined:
        return combined
    email = getattr(user, "email", None)
    if email:
        return email
    return getattr(user, "username", "") or ""


def _sysadmin_emails(db: Session) -> list[str]:
    rows = (
        db.query(models.User.email)
        .filter(
            or_(
                models.User.role == "sys_admin",
                models.User.is_admin.is_(True),
            ),
            models.User.is_active.is_(True),
        )
        .all()
    )
    out: list[str] = []
    seen: set[str] = set()
    for (email,) in rows:
        addr = (email or "").strip()
        key = addr.lower()
        if addr and key not in seen:
            out.append(addr)
            seen.add(key)
    return out


def _actor_label(actor: Optional[models.User]) -> str:
    if not actor:
        return "unknown"
    name = _user_display_name(actor)
    email = (getattr(actor, "email", None) or "").strip()
    return f"{name} <{email}>" if name and email else (email or name or f"user:{getattr(actor, 'id', 'unknown')}")


def _notify_backup_restore_event(
    db: Session,
    *,
    actor: Optional[models.User],
    request: Optional[Request],
    status: str,
    filename: str,
    size: int,
    detail: str,
) -> None:
    details = {
        "status": status,
        "filename": filename,
        "size": size,
        "detail": detail,
    }
    try:
        log_event(
            db,
            action="backup_restore",
            target_type="backup",
            actor_id=getattr(actor, "id", None),
            details=details,
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_ops.py:backup_restore_audit", exc)
    subject = branded_subject(f"Backup restore {status}")
    body = (
        f"Backup restore {status}.\n\n"
        f"Actor: {_actor_label(actor)}\n"
        f"File: {filename or 'upload'}\n"
        f"Size: {size} bytes\n"
        f"Detail: {detail or '-'}"
    )
    try:
        recipients = _sysadmin_emails(db)
        if recipients:
            send_email(recipients=recipients, subject=subject, body=body)
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_ops.py:backup_restore_email", exc)
    try:
        _send_teams_notification(
            "backup_restore",
            {
                "status": status,
                "actor": _actor_label(actor),
                "filename": filename or "upload",
                "size": size,
                "detail": detail or "-",
            },
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_ops.py:backup_restore_teams", exc)



@router.get("/system/backups", tags=["system"])
def sys_list_backups(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    notify_missing_backup_key()
    mgr = DatabaseBackupManager()
    items = [mgr.serialize_record(rec) for rec in mgr.list_backups()]
    last = items[0] if items else None
    settings = load_system_settings()
    return {
        "items": items,
        "directory": str(mgr.backup_dir),
        "last_backup": last,
        "backup_encryption": backup_encryption_health(),
        "backup_settings": public_backup_settings_config(settings.get("backups")),
    }


@router.post("/system/backups/settings", tags=["system"])
def sys_update_backup_settings(
    payload: BackupSettingsPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    existing = settings.get("backups") if isinstance(settings.get("backups"), dict) else {}
    normalized = public_backup_settings_config({**existing, **payload.dict(exclude_none=True)})
    settings["backups"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_backup_settings_update",
            target_type="system",
            actor_id=actor.id,
            details=normalized,
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_backups.py:settings_audit", exc)
    return {"backup_settings": normalized}


@router.post("/system/backups/run", tags=["system"])
def sys_run_backup(
    payload: dict = Body(default={}),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    mgr = DatabaseBackupManager()
    label = payload.get("label") or "manual"
    try:
        rec = mgr.run_backup(label=label)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    response = {
        "name": rec.name,
        "size": rec.size,
        "created_at": rec.created_at,
        "directory": str(mgr.backup_dir),
        "label": mgr.extract_label(rec.name) or label,
    }
    try:
        log_event(
            db,
            action="backup_run",
            target_type="backup",
            actor_id=actor.id,
            details={
                "file": rec.name,
                "size": rec.size,
                "label": response["label"],
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in reports.py:1223", exc)
    return response


@router.delete("/system/backups/{filename}", tags=["system"])
def sys_delete_backup(
    filename: str,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    mgr = DatabaseBackupManager()
    safe_name = Path(filename).name
    try:
        mgr.delete_backup(safe_name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        log_event(
            db,
            action="backup_delete",
            target_type="backup",
            actor_id=actor.id,
            details={"file": safe_name},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in reports.py:1268", exc)
    return {"ok": True}

@router.get("/system/backups/download/{filename}", tags=["system"])
def sys_download_backup(
    filename: str,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    mgr = DatabaseBackupManager()
    safe_name = Path(filename).name
    target = mgr.backup_dir / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail="Backup not found")
    try:
        log_event(
            db,
            action="backup_download",
            target_type="backup",
            actor_id=actor.id,
            details={"file": safe_name, "size": target.stat().st_size},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in reports.py:1295", exc)
    return FileResponse(target, media_type="application/octet-stream", filename=safe_name)

@router.post("/system/backups/restore", tags=["system"])
def sys_restore_backup(
    file: UploadFile = File(...),
    encryption_key: Optional[str] = Form(default=None),
    confirm_restore: str = Form(default=""),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    data = file.file.read()
    filename = file.filename or "upload"
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    _notify_backup_restore_event(
        db,
        actor=actor,
        request=request,
        status="attempted",
        filename=filename,
        size=len(data),
        detail="Restore request received.",
    )
    scan_payload(data, filename, request=request, actor=actor)
    if (confirm_restore or "").strip() != BACKUP_RESTORE_CONFIRM_TEXT:
        detail = f"Restore confirmation must be exactly {BACKUP_RESTORE_CONFIRM_TEXT!r}."
        _notify_backup_restore_event(
            db,
            actor=actor,
            request=request,
            status="blocked",
            filename=filename,
            size=len(data),
            detail=detail,
        )
        raise HTTPException(status_code=400, detail=detail)
    if not data.startswith(b"BKP1"):
        detail = f"Only encrypted {app_display_name()} backup files can be restored."
        _notify_backup_restore_event(
            db,
            actor=actor,
            request=request,
            status="blocked",
            filename=filename,
            size=len(data),
            detail=detail,
        )
        raise HTTPException(status_code=400, detail=detail)
    mgr = DatabaseBackupManager()
    try:
        mgr.restore_backup(data, encryption_key=encryption_key)
    except RuntimeError as exc:
        detail = str(exc)
        _notify_backup_restore_event(
            db,
            actor=actor,
            request=request,
            status="failed",
            filename=filename,
            size=len(data),
            detail=detail,
        )
        raise HTTPException(status_code=500, detail=detail)
    _notify_backup_restore_event(
        db,
        actor=actor,
        request=request,
        status="completed",
        filename=filename,
        size=len(data),
        detail="Restore completed successfully.",
    )
    return {"ok": True}

