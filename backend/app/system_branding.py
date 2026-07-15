import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .auth import current_user as get_current_user
from .database import SessionLocal
from .file_security import scan_payload, validate_logo_bytes
from .permissions import is_sys_admin
from .safe_log import debug_suppressed as _debug_suppressed
from .system_admin_config import public_logo_url as _public_logo_url, safe_logo_name as _safe_logo_name
from .system_settings import LOGO_DIR, load_system_settings, save_system_settings

router = APIRouter(prefix="/api", tags=["system"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==================================================
#                 SYSTEM / BRANDING API
# ==================================================

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg"}
LOGO_MAX_BYTES = int(os.getenv("LOGO_MAX_BYTES", str(2 * 1024 * 1024)))
@router.post("/system/logos", tags=["system"])
def sys_upload_logo(
    file: UploadFile = File(...),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    data = load_system_settings()
    logo_id = uuid4().hex[:8]
    safe_name = f"{logo_id}_{_safe_logo_name(file.filename or 'logo.png')}"
    dest = LOGO_DIR / safe_name
    declared = (file.content_type or "").lower()
    if declared and declared not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported Media Type")
    payload = file.file.read()
    try:
        file.file.close()
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_branding.py:1049", exc)
    validate_logo_bytes(payload, max_bytes=LOGO_MAX_BYTES)
    scan_payload(payload, safe_name, request=request, actor=actor)
    dest.write_bytes(payload)
    entry = {"id": logo_id, "filename": safe_name}
    data.setdefault("logos", []).append(entry)
    save_system_settings(data)
    entry["url"] = _public_logo_url(safe_name)
    try:
        log_event(
            db,
            action="logo_upload",
            target_type="logo",
            actor_id=actor.id,
            details={
                "logo_id": logo_id,
                "filename": safe_name,
                "original_filename": file.filename or None,
                "content_type": declared or "unknown",
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_branding.py:1072", exc)
    return {"ok": True, "logo": entry}

@router.post("/system/logos/upload", tags=["system"])
def sys_upload_logo_legacy(
    file: UploadFile = File(...),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    """
    Backwards-compatible alias; legacy frontends used /logos/upload.
    """
    return sys_upload_logo(file, actor, request, db)

@router.post("/system/logos/select", tags=["system"])
def sys_select_logo(
    payload: dict = Body(...),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    logo_id = payload.get("logo_id")
    s = load_system_settings()
    ids = {l["id"] for l in s.get("logos", [])}
    if logo_id is not None and logo_id not in ids:
        raise HTTPException(status_code=404, detail="Logo not found")
    s["active_logo"] = logo_id
    save_system_settings(s)
    try:
        log_event(
            db,
            action="logo_select",
            target_type="logo",
            actor_id=actor.id,
            details={"logo_id": logo_id},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_branding.py:1115", exc)
    return {"ok": True, "active_logo_id": logo_id}

@router.delete("/system/logos/{logo_id}", tags=["system"])
def sys_delete_logo(
    logo_id: str,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    s = load_system_settings()
    logos = s.get("logos", [])
    remaining = []
    deleted = None
    for l in logos:
        if l["id"] == logo_id:
            deleted = l
        else:
            remaining.append(l)
    if not deleted:
        raise HTTPException(status_code=404, detail="Logo not found")
    try:
        f = LOGO_DIR / deleted["filename"]
        if f.exists():
            os.remove(f)
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_branding.py:1143", exc)
    if s.get("active_logo") == logo_id:
        s["active_logo"] = remaining[0]["id"] if remaining else None
    s["logos"] = remaining
    save_system_settings(s)
    try:
        log_event(
            db,
            action="logo_delete",
            target_type="logo",
            actor_id=actor.id,
            details={"logo_id": logo_id, "filename": deleted.get("filename")},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_branding.py:1158", exc)
    return {"ok": True, "deleted": logo_id, "active_logo_id": s.get("active_logo")}

@router.get("/system/logo/{filename}", tags=["system"])
def sys_serve_logo(filename: str):
    # Only allow plain filenames (no path components) to prevent traversal
    safe_name = Path(filename).name
    f = LOGO_DIR / safe_name
    if not f.exists() or not f.is_file():
        raise HTTPException(status_code=404, detail="Logo not found")
    ext = f.suffix.lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    return FileResponse(f, media_type=media_type)



