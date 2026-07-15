import asyncio
from functools import partial
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .auth import current_user as get_current_user
from .backups import DatabaseBackupManager, backup_encryption_health, notify_missing_backup_key
from .case_import import CaseSpreadsheetImporter
from .case_requests import run_full_custodian_lookup_update
from .database import SessionLocal
from .db_maintenance import get_db_maintenance_status, run_db_maintenance_once
from .emailer import send_email
from .file_security import get_upload_scanner_status, scan_payload, validate_case_import_bytes
from .job_queue import enqueue_job, get_job, list_jobs, register_job_handler
from .notifications import _send_teams_notification
from .permissions import is_sys_admin
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["system"])

BACKUP_RESTORE_CONFIRM_TEXT = "RESTORE"
CASE_IMPORT_MAX_BYTES = int(os.getenv("CASE_IMPORT_MAX_BYTES", str(100 * 1024 * 1024)))
CASE_IMPORT_MAX_FILES = int(os.getenv("CASE_IMPORT_MAX_FILES", "10"))
CASE_IMPORT_TOTAL_MAX_BYTES = int(os.getenv("CASE_IMPORT_TOTAL_MAX_BYTES", str(200 * 1024 * 1024)))
CASE_IMPORT_DECLARED_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "application/x-zip-compressed",
}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _user_display_name(*args, **kwargs):
    from .system_backups import _user_display_name as impl
    return impl(*args, **kwargs)


def _sysadmin_emails(*args, **kwargs):
    from .system_backups import _sysadmin_emails as impl
    return impl(*args, **kwargs)


def _actor_label(*args, **kwargs):
    from .system_backups import _actor_label as impl
    return impl(*args, **kwargs)


def _notify_backup_restore_event(*args, **kwargs):
    from .system_backups import _notify_backup_restore_event as impl
    return impl(*args, **kwargs)


def sys_list_backups(*args, **kwargs):
    from .system_backups import sys_list_backups as impl
    return impl(*args, **kwargs)


def sys_run_backup(*args, **kwargs):
    from .system_backups import sys_run_backup as impl
    return impl(*args, **kwargs)


def sys_delete_backup(*args, **kwargs):
    from .system_backups import sys_delete_backup as impl
    return impl(*args, **kwargs)


def sys_download_backup(*args, **kwargs):
    from .system_backups import sys_download_backup as impl
    return impl(*args, **kwargs)


def sys_restore_backup(*args, **kwargs):
    from .system_backups import sys_restore_backup as impl
    return impl(*args, **kwargs)


def _job_run_full_custodian_lookup(payload: dict) -> dict:
    actor_id = payload.get("actor_id")
    source = payload.get("source") or "manual"
    with SessionLocal() as db:
        return run_full_custodian_lookup_update(
            db,
            actor_id=actor_id,
            source=source,
            mark_bootstrap_complete=False,
            request=None,
        )


try:
    register_job_handler("custodian_full_lookup", _job_run_full_custodian_lookup)
except Exception:
    pass

@router.get("/system/runtime_health", tags=["system"])
def sys_runtime_health(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    scanner_status = get_upload_scanner_status()

    settings = load_system_settings()
    return {
        "schedulers_enabled": (os.getenv("ENABLE_SCHEDULERS") or "1").strip().lower() in {"1", "true", "yes", "on"},
        "upload_scanner": scanner_status,
        "custodian_lookup": {
            "last_run_at": settings.get("custodian_lookup_last_run_at"),
            "bootstrap_completed": bool(settings.get("custodian_lookup_bootstrap_completed")),
        },
        "db_maintenance": get_db_maintenance_status(),
        "jobs": {
            "recent": list_jobs(limit=10),
        },
    }


@router.get("/system/clamav", tags=["system"])
def sys_clamav_monitor(
    days: int = Query(30, ge=1, le=365),
    actor: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    since = datetime.now(timezone.utc) - timedelta(days=days)
    scanner_status = get_upload_scanner_status()
    summary = db.execute(
        text(
            """
            SELECT
              COUNT(*) FILTER (WHERE action = 'upload_scan') AS processed,
              COUNT(*) FILTER (WHERE action = 'upload_scan' AND details->>'verdict' = 'clean') AS clean,
              COUNT(*) FILTER (WHERE action = 'upload_scan' AND details->>'verdict' = 'malicious') AS scan_malicious,
              COUNT(*) FILTER (WHERE action = 'malware_upload_detected') AS malicious,
              COUNT(*) FILTER (
                WHERE action IN (
                  'note_attachment_upload',
                  'case_consent_proof_upload',
                  'case_request_submit',
                  'logo_upload',
                  'backup_restore',
                  'case_import',
                  'tool_email_convert'
                )
              ) AS upload_events
            FROM audit_events
            WHERE created_at >= :since
              AND action IN (
                'upload_scan',
                'malware_upload_detected',
                'note_attachment_upload',
                'case_consent_proof_upload',
                'case_request_submit',
                'logo_upload',
                'backup_restore',
                'case_import',
                'tool_email_convert'
              )
            """
        ),
        {"since": since},
    ).mappings().first() or {}
    daily_rows = db.execute(
        text(
            """
            SELECT
              date_trunc('day', created_at)::date AS day,
              COUNT(*) FILTER (WHERE action = 'upload_scan') AS processed,
              COUNT(*) FILTER (WHERE action = 'malware_upload_detected') AS malicious,
              COUNT(*) FILTER (
                WHERE action IN (
                  'note_attachment_upload',
                  'case_consent_proof_upload',
                  'case_request_submit',
                  'logo_upload',
                  'backup_restore',
                  'case_import',
                  'tool_email_convert'
                )
              ) AS upload_events
            FROM audit_events
            WHERE created_at >= :since
              AND action IN (
                'upload_scan',
                'malware_upload_detected',
                'note_attachment_upload',
                'case_consent_proof_upload',
                'case_request_submit',
                'logo_upload',
                'backup_restore',
                'case_import',
                'tool_email_convert'
              )
            GROUP BY 1
            ORDER BY 1 DESC
            """
        ),
        {"since": since},
    ).mappings().all()
    recent_detections = db.execute(
        text(
            """
            SELECT
              ev.created_at,
              ev.actor_id,
              COALESCE(NULLIF(TRIM(CONCAT(u.first_name, ' ', u.last_name)), ''), u.username, u.email) AS actor_name,
              ev.details->>'filename' AS filename,
              ev.details->>'path' AS path,
              ev.details->>'scanner_detail' AS scanner_detail,
              ev.request_ip
            FROM audit_events ev
            LEFT JOIN users u ON u.id = ev.actor_id
            WHERE ev.created_at >= :since
              AND ev.action = 'malware_upload_detected'
            ORDER BY ev.created_at DESC
            LIMIT 25
            """
        ),
        {"since": since},
    ).mappings().all()
    scan_processed = int(summary.get("processed") or 0)
    upload_events = int(summary.get("upload_events") or 0)
    processed = max(scan_processed, upload_events)
    malicious = max(int(summary.get("malicious") or 0), int(summary.get("scan_malicious") or 0))
    clean = int(summary.get("clean") or 0)
    if scan_processed == 0 and upload_events > 0:
        clean = max(0, processed - malicious)
    return {
        "days": days,
        "since": since.isoformat(),
        "scanner": scanner_status,
        "summary": {
            "processed": processed,
            "clean": clean,
            "malicious": malicious,
            "scan_malicious": int(summary.get("scan_malicious") or 0),
            "blocked": malicious,
            "scan_events": scan_processed,
            "upload_events": upload_events,
        },
        "daily": [
            {
                "date": row["day"].isoformat() if row.get("day") else None,
                "processed": max(int(row.get("processed") or 0), int(row.get("upload_events") or 0)),
                "malicious": int(row.get("malicious") or 0),
            }
            for row in daily_rows
        ],
        "recent_detections": [
            {
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
                "actor_id": row.get("actor_id"),
                "actor_name": row.get("actor_name"),
                "filename": row.get("filename"),
                "path": row.get("path"),
                "scanner_detail": row.get("scanner_detail"),
                "request_ip": row.get("request_ip"),
            }
            for row in recent_detections
        ],
    }


@router.get("/system/jobs", tags=["system"])
def sys_jobs_list(
    job_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=200),
    actor: models.User = Depends(get_current_user),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return {"items": list_jobs(job_type=job_type, limit=limit)}


@router.get("/system/jobs/{job_id}", tags=["system"])
def sys_job_status(
    job_id: str,
    actor: models.User = Depends(get_current_user),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    payload = get_job(job_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Job not found")
    return payload


@router.post("/system/db_maintenance/run", tags=["system"])
def sys_run_db_maintenance(
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    result = run_db_maintenance_once(source="manual")
    try:
        log_event(
            db,
            action="db_maintenance_run",
            target_type="system",
            actor_id=actor.id,
            details={
                "status": result.get("status"),
                "tables": result.get("tables") or [],
                "error": result.get("error"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in reports.py:db_maintenance_run", exc)
    return result


@router.post("/system/custodians/full_lookup", tags=["system"])
def sys_full_custodian_lookup(
    async_mode: bool = Query(False, alias="async"),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    if async_mode:
        job = enqueue_job(
            "custodian_full_lookup",
            {
                "actor_id": getattr(actor, "id", None),
                "source": "manual",
            },
            actor_id=getattr(actor, "id", None),
        )
        try:
            log_event(
                db,
                action="custodian_full_lookup_enqueued",
                target_type="system",
                actor_id=actor.id,
                details={"job_id": job.get("job_id")},
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in reports.py:custodian_full_lookup_enqueued", exc)
        return {
            "status": "queued",
            "job_id": job.get("job_id"),
            "created_at": job.get("created_at"),
        }

    result = run_full_custodian_lookup_update(
        db,
        actor_id=getattr(actor, "id", None),
        source="manual",
        mark_bootstrap_complete=False,
        request=request,
    )
    return result
def _run_case_import_job(files: List[Tuple[str, str]], actor_id: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        importer = CaseSpreadsheetImporter(db)
        payloads: List[Tuple[str, bytes]] = []
        for name, path in files:
            data = Path(path).read_bytes()
            payloads.append((name, data))
        result = importer.import_uploads(payloads)
        try:
            log_event(
                db,
                action="case_import",
                target_type="case",
                actor_id=actor_id,
                details={
                    "import_id": result.get("import_id"),
                    "file_count": len(payloads),
                    "labels": [name for name, _ in payloads],
                },
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in reports.py:1355", exc)
        return result
    finally:
        db.close()


@router.post("/system/import", tags=["system"])
async def sys_import_cases(
    files: List[UploadFile] = File(...),
    actor: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    manifests: List[Tuple[str, str]] = []
    temp_paths: List[str] = []
    total_bytes = 0
    try:
        for idx, upload in enumerate(files, start=1):
            name = upload.filename or f"upload-{idx}.xlsx"
            declared = (upload.content_type or "").lower()
            if declared and declared not in CASE_IMPORT_DECLARED_TYPES:
                raise HTTPException(status_code=415, detail=f"Unsupported content type: {declared}")
            tmp = tempfile.NamedTemporaryFile(delete=False)
            temp_paths.append(tmp.name)
            file_bytes = 0
            try:
                while True:
                    chunk = await upload.read(256 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
                    file_bytes += len(chunk)
                    if CASE_IMPORT_MAX_BYTES > 0 and file_bytes > CASE_IMPORT_MAX_BYTES:
                        raise HTTPException(status_code=413, detail=f"{name} exceeds per-file size limit")
            finally:
                tmp.close()
            if file_bytes == 0:
                Path(tmp.name).unlink(missing_ok=True)
                temp_paths.pop()
                continue
            with Path(tmp.name).open("rb") as fh:
                data = fh.read()
                validate_case_import_bytes(data, max_bytes=CASE_IMPORT_MAX_BYTES)
                try:
                    scan_payload(data, name, request=request, actor=actor)
                except HTTPException as exc:
                    logger.warning("Case import AV scan failed for %s: %s", name, getattr(exc, "detail", exc))
                    raise
                except Exception as exc:
                    logger.exception("Case import AV scan error for %s", name)
                    raise HTTPException(status_code=500, detail="Malware scan failed") from exc
            total_bytes += file_bytes
            if CASE_IMPORT_MAX_FILES > 0 and len(manifests) >= CASE_IMPORT_MAX_FILES:
                raise HTTPException(status_code=413, detail=f"Maximum of {CASE_IMPORT_MAX_FILES} files per import request")
            if CASE_IMPORT_TOTAL_MAX_BYTES > 0 and total_bytes > CASE_IMPORT_TOTAL_MAX_BYTES:
                raise HTTPException(status_code=413, detail="Combined upload size exceeds allowed limit")
            manifests.append((name, tmp.name))
        if not manifests:
            raise HTTPException(status_code=400, detail="Uploaded files were empty")
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, partial(_run_case_import_job, manifests, actor.id))
        return result
    except HTTPException:
        # Already a clean HTTP error; log briefly and bubble up
        logger.warning("Case import failed (HTTP) actor=%s files=%s", getattr(actor, "id", None), [m[0] for m in manifests] if manifests else [])
        raise
    except Exception as exc:
        logger.exception("Case import failed: %s", exc)
        raise HTTPException(status_code=500, detail="Import failed; check server logs for details") from exc
    finally:
        for path in temp_paths:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception as exc:
                _debug_suppressed("suppressed exception in reports.py:1433", exc)













