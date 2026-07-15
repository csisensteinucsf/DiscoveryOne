from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from . import models, schemas
from .audit import log_event
from .auth import current_user as get_current_user
from .cases import _sync_case_documentation_counters
from .database import get_db
from .esignature_provider import (
    ESignatureProviderError,
    current_esignature_provider,
    download_completed_document,
    resend_request,
    send_consent_request,
    void_request,
)
from .permissions import ensure_case_editable, ensure_case_visible
from .safe_log import debug_suppressed as _debug_suppressed

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _request_reference(consent: models.CaseConsent) -> tuple[str, str]:
    provider = str(getattr(consent, "provider", "") or "").strip().lower()
    request_id = str(getattr(consent, "request_id", "") or "").strip()
    return provider, request_id


@router.get("/{case_id}/consents", response_model=List[schemas.CaseConsent])
def list_case_consents(
    case_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    rows = (
        db.query(models.CaseConsent)
        .filter(models.CaseConsent.case_id == case_id)
        .order_by(models.CaseConsent.sent_at.desc())
        .all()
    )
    references = [_request_reference(row) for row in rows]
    filenames_by_reference = {
        reference: f"{reference[0]}-{reference[1]}.pdf"
        for reference in references
        if all(reference)
    }
    proof_by_reference: dict[tuple[str, str], models.CaseRequestConsentProof] = {}
    if filenames_by_reference:
        proofs = (
            db.query(models.CaseRequestConsentProof)
            .filter(models.CaseRequestConsentProof.case_id == case_id)
            .filter(models.CaseRequestConsentProof.original_filename.in_(filenames_by_reference.values()))
            .all()
        )
        reference_by_filename = {filename: reference for reference, filename in filenames_by_reference.items()}
        for proof in proofs:
            reference = reference_by_filename.get((getattr(proof, "original_filename", None) or "").strip())
            if reference:
                proof_by_reference[reference] = proof
    payload = []
    for row in rows:
        provider, request_id = _request_reference(row)
        proof = proof_by_reference.get((provider, request_id))
        payload.append({
            "id": row.id,
            "case_id": row.case_id,
            "custodian_id": row.custodian_id,
            "custodian_name": row.custodian_name,
            "custodian_email": row.custodian_email,
            "provider": provider,
            "request_id": request_id,
            "envelope_id": row.envelope_id,
            "status": row.status,
            "record_type": row.record_type,
            "date_from": row.date_from,
            "date_to": row.date_to,
            "sent_at": row.sent_at,
            "last_resent_at": row.last_resent_at,
            "completed_at": row.completed_at,
            "updated_at": row.updated_at,
            "proof_downloaded": bool(proof),
            "proof_id": getattr(proof, "id", None) if proof else None,
        })
    return payload


def _get_consent_or_404(db: Session, case_id: int, consent_id: int) -> models.CaseConsent:
    consent = (
        db.query(models.CaseConsent)
        .filter(models.CaseConsent.id == consent_id, models.CaseConsent.case_id == case_id)
        .first()
    )
    if not consent:
        raise HTTPException(status_code=404, detail="Consent not found")
    return consent


@router.post("/{case_id}/consents")
@router.post("/{case_id}/docusign/consents", include_in_schema=False)
def send_consent_request_route(
    case_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    ensure_case_editable(actor)
    message = (payload.get("message") or "").strip() or None
    record_type = (payload.get("record_type") or "").strip()
    date_from = (payload.get("date_from") or "").strip() or "NA"
    date_to = (payload.get("date_to") or "").strip() or "NA"
    custodians_payload = payload.get("custodians") or []
    if not custodians_payload:
        # backward compatibility: single custodian fields
        custodian_id = payload.get("custodian_id")
        custodian_name = (payload.get("custodian_name") or "").strip()
        custodian_email = (payload.get("custodian_email") or "").strip()
        custodians_payload = [{
            "custodian_id": custodian_id,
            "custodian_name": custodian_name,
            "custodian_email": custodian_email,
        }]
    if not record_type:
        raise HTTPException(status_code=400, detail="Record type is required")
    combined_case_name = case.name
    if getattr(case, "legal_case_name", None):
        combined_case_name = f"{case.legal_case_name} - {case.name}"
    subject = f"Consent request - {combined_case_name}"

    created_consents = []
    now = datetime.now(timezone.utc)
    provider = current_esignature_provider()

    for entry in custodians_payload:
        custodian_id = entry.get("custodian_id")
        custodian_name = (entry.get("custodian_name") or "").strip()
        custodian_email = (entry.get("custodian_email") or "").strip()
        custodian_obj = None
        if custodian_id:
            c = db.query(models.Custodian).filter_by(id=custodian_id, case_id=case_id).first()
            if not c:
                raise HTTPException(status_code=404, detail=f"Custodian {custodian_id} not found for this case")
            custodian_obj = c
            custodian_name = custodian_name or (c.name or "")
            custodian_email = custodian_email or (c.email or "")
        if not custodian_name or not custodian_email:
            raise HTTPException(status_code=400, detail="Custodian name and email are required")
        try:
            request_id = send_consent_request(
                custodian_name=custodian_name,
                custodian_email=custodian_email,
                case_name=combined_case_name,
                subject=subject,
                message=message,
                fields={
                    "record_type": record_type,
                    "date_from": date_from,
                    "date_to": date_to,
                    "case_name": combined_case_name,
                },
                provider=provider,
            )
        except ESignatureProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

        consent = models.CaseConsent(
            case_id=case_id,
            custodian_id=custodian_id,
            custodian_name=custodian_name,
            custodian_email=custodian_email,
            provider=provider,
            envelope_id=request_id,
            status="sent",
            record_type=record_type,
            date_from=date_from,
            date_to=date_to,
            message=message,
            sent_at=now,
            updated_at=now,
        )
        db.add(consent)
        created_consents.append(consent)
        # Mark consent as sent on the custodian record (unless already received)
        try:
            if custodian_obj and (custodian_obj.consent_status or "not sent").lower() != "received":
                custodian_obj.consent_status = "sent"
        except Exception as exc:
            _debug_suppressed("suppressed exception in case_consents.py:6052", exc)
        try:
            log_event(
                db,
                action="consent_request_esignature",
                target_type="case",
                target_id=case_id,
                actor_id=getattr(actor, "id", None),
                details={
                    "case_id": case_id,
                    "case_name": getattr(case, "name", None),
                    "provider": provider,
                    "request_id": request_id,
                    "envelope_id": request_id,
                    "custodian_id": custodian_id,
                    "custodian_name": custodian_name,
                    "custodian_email": custodian_email,
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in case_consents.py:6071", exc)
    db.commit()
    _sync_case_documentation_counters(db, case_id)
    return {"ok": True, "consents": [schemas.CaseConsent.model_validate(c) for c in created_consents]}


@router.post("/{case_id}/consents/{consent_id}/resend")
@router.post("/{case_id}/docusign/consents/{consent_id}/resend", include_in_schema=False)
def resend_consent_request(
    case_id: int,
    consent_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    ensure_case_editable(actor)
    consent = _get_consent_or_404(db, case_id, consent_id)
    provider, request_id = _request_reference(consent)
    if not provider or not request_id:
        raise HTTPException(status_code=400, detail="Consent is missing its provider or request id")
    now = datetime.now(timezone.utc)
    resend_method = None
    try:
        resend_method = resend_request(request_id, provider=provider)
        consent.last_resent_at = now
        consent.updated_at = now
    except ESignatureProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"E-signature provider error: {exc}")
    try:
        log_event(
            db,
            action="consent_resend_esignature",
            target_type="consent",
            target_id=consent.id,
            actor_id=getattr(actor, "id", None),
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "custodian_id": consent.custodian_id,
                "custodian_name": consent.custodian_name,
                "custodian_email": consent.custodian_email,
                "provider": provider,
                "request_id": request_id,
                "envelope_id": consent.envelope_id,
                "resend_method": resend_method,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_consents.py:6121", exc)
    db.commit()
    return {
        "ok": True,
        "status": "resent",
        "provider": provider,
        "request_id": request_id,
        "envelope_id": consent.envelope_id,
        "resend_method": resend_method,
    }


@router.post("/{case_id}/consents/{consent_id}/void")
@router.post("/{case_id}/docusign/consents/{consent_id}/void", include_in_schema=False)
def void_consent_request(
    case_id: int,
    consent_id: int,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    ensure_case_editable(actor)
    consent = _get_consent_or_404(db, case_id, consent_id)
    provider, request_id = _request_reference(consent)
    if not provider or not request_id:
        raise HTTPException(status_code=400, detail="Consent is missing its provider or request id")
    reason = (payload or {}).get("reason") or ""
    try:
        void_request(request_id, reason, provider=provider)
        consent.status = "voided"
        db.add(consent)
        db.commit()
    except ESignatureProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"E-signature provider error: {exc}")
    try:
        log_event(
            db,
            action="consent_void_esignature",
            target_type="consent",
            target_id=consent.id,
            actor_id=actor.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "custodian_id": consent.custodian_id,
                "custodian_name": consent.custodian_name,
                "custodian_email": consent.custodian_email,
                "provider": provider,
                "request_id": request_id,
                "envelope_id": consent.envelope_id,
                "reason": reason or None,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_consents.py:6173", exc)
    return {
        "ok": True,
        "status": "voided",
        "provider": provider,
        "request_id": request_id,
        "envelope_id": consent.envelope_id,
    }


@router.get("/{case_id}/consents/{consent_id}/download")
@router.get("/{case_id}/docusign/consents/{consent_id}/download", include_in_schema=False)
def download_consent_request(
    case_id: int,
    consent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    consent = _get_consent_or_404(db, case_id, consent_id)
    provider, request_id = _request_reference(consent)
    if not provider or not request_id:
        raise HTTPException(status_code=400, detail="Consent is missing its provider or request id")
    try:
        content, filename = download_completed_document(request_id, provider=provider)
    except ESignatureProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"E-signature provider error: {exc}")
    try:
        log_event(
            db,
            action="consent_download_esignature",
            target_type="consent",
            target_id=consent.id,
            actor_id=getattr(actor, "id", None),
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "custodian_id": consent.custodian_id,
                "custodian_name": consent.custodian_name,
                "custodian_email": consent.custodian_email,
                "provider": provider,
                "request_id": request_id,
                "envelope_id": consent.envelope_id,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_consents.py:6216", exc)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type="application/pdf", headers=headers)


