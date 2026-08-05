import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from . import models
from .audit import log_event
from .auth import current_user as get_current_user
from .case_requests import (
    CASE_REQUEST_PROOF_DIR,
    _cleanup_consent_proof_file,
    _custodian_lookup_for_case,
    _find_custodian_for_case,
    _next_consent_status_after_proof_removal,
    _read_consent_proof_blob,
    _serialize_case_consent_proof,
    _write_consent_proof_file,
)
from .cases import _sync_case_documentation_counters
from .database import get_db
from .hold_workflows import resolve_hold_memberships, set_membership_consent_status
from .permissions import ensure_case_request_access, ensure_case_visible, ensure_not_requestor, get_role
from .safe_log import debug_suppressed as _debug_suppressed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])
@router.get("/{request_id}/attachment")
def download_attachment(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    ensure_case_request_access(actor)
    record = db.get(models.CaseRequest, request_id)
    if not record or not record.attachment_path:
        raise HTTPException(status_code=404, detail="Attachment not found")
    role = get_role(actor)
    if role == "requestor":
        if record.requestor_id != actor.id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        case = db.get(models.Case, record.case_id) if record.case_id else None
        if case:
            ensure_case_visible(case, actor, db)
        elif role != "sys_admin":
            raise HTTPException(status_code=403, detail="Access denied")
    path = Path(record.attachment_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment missing")
    try:
        response = FileResponse(
            path,
            filename=record.attachment_name or path.name,
            media_type="application/octet-stream",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment missing")
    except Exception:
        logger.exception("Unable to stream case request attachment")
        raise HTTPException(status_code=500, detail="Unable to stream attachment")
    try:
        log_event(
            db,
            action="case_request_attachment_download",
            actor_id=actor.id,
            target_type="case_request",
            target_id=record.id,
            details={
                "filename": record.attachment_name or path.name,
                "request_type": record.request_type,
                "case_id": record.case_id,
                "case_name": getattr(case, "name", None) if 'case' in locals() and case else None,
                "requestor_id": record.requestor_id,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_files.py:2565", exc)
    return response


@router.get("/{request_id}/consent_attachment")
def download_consent_attachment(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    ensure_case_request_access(actor)
    record = db.get(models.CaseRequest, request_id)
    if not record or not record.consent_attachment_path:
        raise HTTPException(status_code=404, detail="Consent attachment not found")
    role = get_role(actor)
    if role == "requestor":
        if record.requestor_id != actor.id:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        case = db.get(models.Case, record.case_id) if record.case_id else None
        if case:
            ensure_case_visible(case, actor, db)
        elif role != "sys_admin":
            raise HTTPException(status_code=403, detail="Access denied")
    path = Path(record.consent_attachment_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Consent attachment missing")
    try:
        response = FileResponse(
            path,
            filename=record.consent_attachment_name or path.name,
            media_type="application/octet-stream",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Consent attachment missing")
    except Exception:
        logger.exception("Unable to stream case request consent attachment")
        raise HTTPException(status_code=500, detail="Unable to stream attachment")
    try:
        case_name = getattr(record, "case_name", None)
        if not case_name and record.case_id:
            case_obj = db.get(models.Case, record.case_id)
            case_name = getattr(case_obj, "name", None) if case_obj else None
        log_event(
            db,
            action="case_request_consent_attachment_download",
            actor_id=actor.id,
            target_type="case_request",
            target_id=record.id,
            details={
                "filename": record.consent_attachment_name or path.name,
                "case_id": record.case_id,
                "case_name": case_name,
                "requestor_id": record.requestor_id,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_files.py:2623", exc)
    return response


@router.get("/{request_id}/consent_proofs/{proof_id}")
def download_consent_proof(
    request_id: int,
    proof_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    ensure_case_request_access(actor)
    record = db.get(models.CaseRequest, request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    role = get_role(actor)
    if role == "requestor" and record.requestor_id != actor.id:
        raise HTTPException(status_code=403, detail="Access denied")
    elif role != "requestor":
        case = record.case if record.case_id else None
        if case:
            ensure_case_visible(case, actor, db)
        elif role != "sys_admin":
            raise HTTPException(status_code=403, detail="Access denied")
    proof = db.get(models.CaseRequestConsentProof, proof_id)
    if not proof or proof.case_request_id != request_id:
        raise HTTPException(status_code=404, detail="Proof not found")
    if record.case_id and proof.case_id and proof.case_id != record.case_id:
        raise HTTPException(status_code=404, detail="Proof not found")
    path = CASE_REQUEST_PROOF_DIR / proof.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Proof file missing")
    try:
        response = FileResponse(
            path,
            filename=proof.original_filename,
            media_type=proof.content_type or "application/octet-stream",
        )
    except Exception:
        logger.exception("Unable to stream case request proof")
        raise HTTPException(status_code=500, detail="Unable to stream proof")
    try:
        case_name = getattr(record, "case_name", None)
        if not case_name and record.case_id:
            case_obj = db.get(models.Case, record.case_id)
            case_name = getattr(case_obj, "name", None) if case_obj else None
        log_event(
            db,
            action="case_request_consent_proof_download",
            actor_id=actor.id,
            target_type="case_request",
            target_id=record.id,
            details={
                "proof_id": proof.id,
                "custodian_name": getattr(proof, "custodian_name", None),
                "custodian_email": proof.custodian_email,
                "original_filename": proof.original_filename,
                "case_id": record.case_id,
                "case_name": case_name,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_files.py:2685", exc)
    return response

@router.get("/cases/{case_id}/consent_proofs")
def list_case_consent_proofs(
    case_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    custodian_map = _custodian_lookup_for_case(db, case_id)
    rows = (
        db.query(models.CaseRequestConsentProof)
        .options(
            selectinload(models.CaseRequestConsentProof.case_request).selectinload(models.CaseRequest.requestor),
            selectinload(models.CaseRequestConsentProof.uploaded_by),
        )
        .filter(models.CaseRequestConsentProof.case_id == case_id)
        .order_by(models.CaseRequestConsentProof.created_at.desc())
        .all()
    )
    return [_serialize_case_consent_proof(proof, custodian_map) for proof in rows]


@router.post("/cases/{case_id}/consent_proofs")
async def upload_case_consent_proof(
    case_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    ensure_not_requestor(actor)
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    form = await request.form()
    upload = form.get("file")
    if not upload or not hasattr(upload, "filename"):
        raise HTTPException(status_code=400, detail="Consent document is required")
    proof_type = str(form.get("proof_type") or "standard").strip().lower()
    if proof_type not in {"standard", "awoc"}:
        raise HTTPException(status_code=422, detail="proof_type must be standard or awoc")
    custodian_id = None
    custodian = None
    raw_custodian_id = form.get("custodian_id")
    if raw_custodian_id not in (None, "", b"", []):
        try:
            custodian_id = int(raw_custodian_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="custodian_id must be an integer")
        custodian = db.get(models.Custodian, custodian_id)
        if not custodian or custodian.case_id != case_id:
            raise HTTPException(status_code=400, detail="Custodian not found for this case")
    custodian_name = (form.get("custodian_name") or "").strip()
    custodian_email = (form.get("custodian_email") or "").strip()
    if custodian:
        custodian_name = custodian.name or custodian_name
        custodian_email = custodian.email or custodian_email
    if not custodian_name and not custodian_email:
        raise HTTPException(status_code=400, detail="Custodian name or email is required")
    target_custodian = custodian or _find_custodian_for_case(
        db,
        case_id,
        custodian_id=custodian_id,
        email=custodian_email,
        name=custodian_name,
    )
    if target_custodian is None:
        raise HTTPException(status_code=422, detail="Select an existing custodian for this consent proof")
    raw_hold_id = form.get("case_hold_id")
    try:
        case_hold_id = int(raw_hold_id) if raw_hold_id not in (None, "", b"", []) else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="case_hold_id must be an integer")
    selected_hold, memberships = resolve_hold_memberships(
        db,
        case_id=case_id,
        custodian_ids=[int(target_custodian.id)],
        case_hold_id=case_hold_id,
        create_default=False,
    )
    hold_membership = memberships[int(target_custodian.id)]
    blob = await _read_consent_proof_blob(upload, actor=actor, request=request)
    stored_filename: Optional[str] = None
    try:
        stored_filename = _write_consent_proof_file(blob)
        proof = models.CaseRequestConsentProof(
            case_request_id=None,
            case_id=case_id,
            hold_custodian_id=hold_membership.id,
            custodian_name=custodian_name,
            custodian_email=custodian_email,
            stored_filename=stored_filename,
            original_filename=blob["filename"],
            content_type=blob["content_type"],
            size=blob["size"],
            proof_type=proof_type,
            uploaded_by_id=actor.id,
        )
        db.add(proof)
        db.flush()
        set_membership_consent_status(db, hold_membership, "awoc" if proof_type == "awoc" else "received")
        db.commit()
        _sync_case_documentation_counters(db, case_id)
        db.refresh(proof)
    except Exception:
        db.rollback()
        _cleanup_consent_proof_file(stored_filename)
        raise
    try:
        case_name = getattr(case, "name", None)
        log_event(
            db,
            action="case_consent_proof_upload",
            actor_id=actor.id,
            target_type="case",
            target_id=case_id,
            details={
                "proof_id": proof.id,
                "case_hold_id": int(selected_hold.id),
                "hold_custodian_id": int(hold_membership.id),
                "custodian_id": getattr(target_custodian, "id", None),
                "custodian_name": getattr(proof, "custodian_name", None),
                "custodian_email": proof.custodian_email,
                "original_filename": proof.original_filename,
                "proof_type": proof.proof_type,
                "case_id": case_id,
                "case_name": case_name,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_files.py:3980", exc)
    custodian_map = _custodian_lookup_for_case(db, case_id)
    return _serialize_case_consent_proof(proof, custodian_map)


@router.get("/cases/{case_id}/consent_proofs/{proof_id}")
def download_case_consent_proof(
    case_id: int,
    proof_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    proof = db.get(models.CaseRequestConsentProof, proof_id)
    if not proof or proof.case_id != case_id:
        raise HTTPException(status_code=404, detail="Proof not found")
    path = CASE_REQUEST_PROOF_DIR / proof.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Proof file missing")
    try:
        response = FileResponse(
            path,
            filename=proof.original_filename,
            media_type=proof.content_type or "application/octet-stream",
        )
    except Exception:
        logger.exception("Unable to stream case consent proof")
        raise HTTPException(status_code=500, detail="Unable to stream proof")
    try:
        case_name = getattr(case, "name", None)
        log_event(
            db,
            action="case_consent_proof_download",
            actor_id=actor.id,
            target_type="case",
            target_id=case_id,
            details={
                "proof_id": proof.id,
                "custodian_name": getattr(proof, "custodian_name", None),
                "custodian_email": proof.custodian_email,
                "original_filename": proof.original_filename,
                "case_request_id": proof.case_request_id,
                "case_id": case_id,
                "case_name": case_name,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_files.py:4032", exc)
    return response


@router.delete("/cases/{case_id}/consent_proofs/{proof_id}")
def delete_case_consent_proof(
    case_id: int,
    proof_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
):
    ensure_not_requestor(actor)
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    proof = db.get(models.CaseRequestConsentProof, proof_id)
    if not proof or proof.case_id != case_id:
        raise HTTPException(status_code=404, detail="Proof not found")
    if proof.case_request_id:
        raise HTTPException(status_code=400, detail="Proof is managed via an intake request")
    stored_filename = proof.stored_filename
    custodian_email = proof.custodian_email
    custodian_name = proof.custodian_name
    custodian_obj = _find_custodian_for_case(db, case_id, email=custodian_email, name=custodian_name)
    hold_custodian_id = getattr(proof, "hold_custodian_id", None)
    db.delete(proof)
    db.commit()
    if custodian_obj:
        next_status = _next_consent_status_after_proof_removal(
            db,
            case_id,
            custodian=custodian_obj,
            email=custodian_email,
            name=custodian_name,
            hold_custodian_id=hold_custodian_id,
        )
        membership = db.get(models.HoldCustodian, hold_custodian_id) if hold_custodian_id else None
        if membership is not None:
            if membership.consent_status != next_status:
                set_membership_consent_status(db, membership, next_status)
                db.commit()
        elif custodian_obj.consent_status != next_status:
            custodian_obj.consent_status = next_status
            db.commit()
    _sync_case_documentation_counters(db, case_id)
    _cleanup_consent_proof_file(stored_filename)
    try:
        case_name = getattr(case, "name", None)
        log_event(
            db,
            action="case_consent_proof_delete",
            actor_id=actor.id,
            target_type="case",
            target_id=case_id,
            details={
                "proof_id": proof_id,
                "custodian_id": getattr(custodian_obj, "id", None),
                "custodian_name": custodian_name,
                "custodian_email": custodian_email,
                "original_filename": getattr(proof, "original_filename", None),
                "proof_type": getattr(proof, "proof_type", None) or "standard",
                "case_id": case_id,
                "case_name": case_name,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_files.py:4092", exc)
    return Response(status_code=204)

