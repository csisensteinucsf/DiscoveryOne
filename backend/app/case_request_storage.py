from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from . import case_requests as case_request_core
from . import models
from .database import SessionLocal


async def _read_consent_proof_blob(file: UploadFile, *, actor: models.User, request: Request) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Consent document cannot be empty")
    try:
        await file.close()
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_request_storage.py:20", exc)
    if case_request_core.MAX_CONSENT_UPLOAD_BYTES > 0 and len(data) > case_request_core.MAX_CONSENT_UPLOAD_BYTES:
        max_mb = max(1, case_request_core.MAX_CONSENT_UPLOAD_BYTES // (1024 * 1024))
        raise HTTPException(status_code=413, detail=f"Consent document exceeds size limit ({max_mb} MB).")
    filename = file.filename or "consent"
    ext = Path(filename).suffix.lower()
    if ext not in case_request_core.CONSENT_ATTACHMENT_EXTS:
        raise HTTPException(status_code=415, detail="Unsupported consent document type (expected .msg, .eml, or .pdf)")
    case_request_core.scan_payload(data, filename, request=request, actor=actor)
    return {
        "filename": filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": len(data),
        "data": data,
    }


def _write_consent_proof_file(blob: dict) -> str:
    token = f"consent_{uuid.uuid4().hex}_{case_request_core._safe_filename(blob['filename'])}"
    dest = case_request_core.CASE_REQUEST_PROOF_DIR / token
    dest.write_bytes(blob["data"])
    return token


def _pending_storage_usage(db: Session, user_id: int) -> int:
    attachment_total = (
        db.query(func.coalesce(func.sum(models.CaseRequest.attachment_bytes), 0))
        .filter(
            models.CaseRequest.requestor_id == user_id,
            models.CaseRequest.status == "pending",
        )
        .scalar()
        or 0
    )
    proof_total = (
        db.query(func.coalesce(func.sum(models.CaseRequestConsentProof.size), 0))
        .join(models.CaseRequest, models.CaseRequest.id == models.CaseRequestConsentProof.case_request_id)
        .filter(
            models.CaseRequest.requestor_id == user_id,
            models.CaseRequest.status == "pending",
        )
        .scalar()
        or 0
    )
    return int(attachment_total + proof_total)


def _cleanup_file(path_value: str | None, allowed_dir: Path) -> None:
    if not path_value:
        return
    try:
        target = Path(path_value)
        if target.is_file() and allowed_dir in target.parents:
            target.unlink()
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_request_storage.py:76", exc)


def _cleanup_consent_proof_file(stored_filename: str | None) -> None:
    if not stored_filename:
        return
    try:
        proof_path = case_request_core.CASE_REQUEST_PROOF_DIR / stored_filename
        if proof_path.exists():
            proof_path.unlink()
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_request_storage.py:86", exc)


def _remove_attachment(record: models.CaseRequest, remove_consent_proofs: bool = True) -> None:
    _cleanup_file(record.attachment_path, case_request_core.CASE_REQUEST_UPLOAD_DIR)
    record.attachment_path = None
    record.attachment_name = None
    record.attachment_bytes = 0
    _cleanup_file(record.consent_attachment_path, case_request_core.CASE_REQUEST_UPLOAD_DIR)
    record.consent_attachment_path = None
    record.consent_attachment_name = None
    record.consent_attachment_bytes = 0
    if remove_consent_proofs and getattr(record, "consent_proofs", None):
        for proof in list(record.consent_proofs or []):
            _cleanup_consent_proof_file(proof.stored_filename)
            record.consent_proofs.remove(proof)


def sync_case_request_attachment_bytes(limit: int = 200) -> None:
    db = SessionLocal()
    try:
        while True:
            rows = (
                db.query(models.CaseRequest)
                .filter(
                    or_(
                        and_(
                            models.CaseRequest.attachment_path.isnot(None),
                            models.CaseRequest.attachment_bytes <= 0,
                        ),
                        and_(
                            models.CaseRequest.consent_attachment_path.isnot(None),
                            models.CaseRequest.consent_attachment_bytes <= 0,
                        ),
                    )
                )
                .limit(limit)
                .all()
            )
            if not rows:
                break
            for row in rows:
                if row.attachment_path and (not row.attachment_bytes or row.attachment_bytes <= 0):
                    try:
                        path = Path(row.attachment_path)
                        if path.exists():
                            row.attachment_bytes = path.stat().st_size
                        else:
                            row.attachment_bytes = 0
                    except Exception:
                        row.attachment_bytes = 0
                if row.consent_attachment_path and (not row.consent_attachment_bytes or row.consent_attachment_bytes <= 0):
                    try:
                        path = Path(row.consent_attachment_path)
                        if path.exists():
                            row.consent_attachment_bytes = path.stat().st_size
                        else:
                            row.consent_attachment_bytes = 0
                    except Exception:
                        row.consent_attachment_bytes = 0
            db.commit()
    except Exception as exc:
        print(f"[case_request] attachment sync failed: {exc}")
        db.rollback()
    finally:
        db.close()
