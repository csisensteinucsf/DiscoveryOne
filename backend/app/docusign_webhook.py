from __future__ import annotations

import base64
import hashlib
import hmac
import os
import json
import re
import uuid
from defusedxml import ElementTree as ET  # type: ignore
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import func

from .database import get_db
from . import models
from .audit import log_event
from .consent_notifications import notify_case_analyst_consent_completed
from .esignature_provider import ESignatureProviderError, download_completed_document
from .file_security import scan_payload
from .integration_settings import config_value
from .safe_log import debug_suppressed as _debug_suppressed

router = APIRouter(prefix="/api/docusign", tags=["docusign"])
CASE_REQUEST_UPLOAD_DIR = Path(os.getenv("CASE_REQUEST_UPLOAD_DIR", "/app/case_request_uploads"))
CASE_REQUEST_PROOF_DIR = CASE_REQUEST_UPLOAD_DIR / "consent_proofs"
CASE_REQUEST_PROOF_DIR.mkdir(parents=True, exist_ok=True)


def _parse_connect_keys() -> List[str]:
    raw_many = config_value("docusign", "connect_keys", "DOCUSIGN_CONNECT_KEYS")
    if raw_many:
        keys = [k.strip() for k in raw_many.split(",") if k.strip()]
        if keys:
            return keys
    raw_single = config_value("docusign", "connect_key", "DOCUSIGN_CONNECT_KEY")
    if raw_single:
        return [raw_single]
    return []


def _verify_signature(body: bytes, signature_headers: List[str]) -> None:
    keys = _parse_connect_keys()
    if not keys:
        # Fail closed when the shared secret is not configured
        raise HTTPException(status_code=401, detail="DocuSign Connect key not configured")
    if not signature_headers:
        raise HTTPException(status_code=401, detail="Missing DocuSign signature header")

    def _expected_for_key(k: str) -> Optional[tuple[str, Optional[str]]]:
        try:
            key_bytes = k.encode("utf-8")
            digest = hmac.new(key_bytes, body, hashlib.sha256).digest()
            expected = base64.b64encode(digest).decode("ascii")
        except Exception:
            return None
        alt_expected = None
        try:
            decoded = base64.b64decode(k, validate=True)
            alt_digest = hmac.new(decoded, body, hashlib.sha256).digest()
            alt_expected = base64.b64encode(alt_digest).decode("ascii")
        except Exception:
            alt_expected = None
        return expected, alt_expected

    # Try each configured key until one matches
    for key in keys:
        res = _expected_for_key(key)
        if not res:
            continue
        expected, alt_expected = res
        for provided in signature_headers:
            match = hmac.compare_digest(expected, provided)
            alt_match = alt_expected and hmac.compare_digest(alt_expected, provided)
            if match or alt_match:
                return

    raise HTTPException(status_code=401, detail="Invalid DocuSign signature")


def _event_to_status(event_raw: Any) -> Optional[str]:
    event = str(event_raw or "").strip().lower()
    if not event:
        return None
    if event.startswith("envelope-"):
        return event.replace("envelope-", "", 1)
    if event.startswith("recipient-"):
        return event.replace("recipient-", "", 1)
    if event in {"sent", "delivered", "completed", "declined", "voided"}:
        return event
    return None


def _safe_filename(name: str) -> str:
    base = Path(name or "consent.pdf").name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return safe or "consent.pdf"


def _sync_case_consent_proof_count(db: Session, case_id: int) -> None:
    case = db.get(models.Case, case_id)
    if not case:
        return
    case.consent_proof_count = int(
        db.query(func.count(models.CaseRequestConsentProof.id))
        .filter(models.CaseRequestConsentProof.case_id == case_id)
        .scalar()
        or 0
    )
    db.add(case)
    db.commit()


def _existing_docusign_proof(db: Session, *, case_id: int, envelope_id: str) -> Optional[models.CaseRequestConsentProof]:
    filename = f"docusign-{envelope_id}.pdf"
    return (
        db.query(models.CaseRequestConsentProof)
        .filter(models.CaseRequestConsentProof.case_id == case_id)
        .filter(models.CaseRequestConsentProof.original_filename == filename)
        .first()
    )


def _save_completed_docusign_pdf(
    db: Session,
    *,
    consent: models.CaseConsent,
    custodian: Optional[models.Custodian],
    request: Request,
) -> Optional[models.CaseRequestConsentProof]:
    case_id = int(getattr(consent, "case_id", 0) or 0)
    envelope_id = (getattr(consent, "envelope_id", None) or "").strip()
    if not case_id or not envelope_id:
        return None
    existing = _existing_docusign_proof(db, case_id=case_id, envelope_id=envelope_id)
    if existing:
        return existing

    pdf_bytes, _remote_filename = download_completed_document(
        envelope_id,
        provider="docusign",
    )
    filename = f"docusign-{envelope_id}.pdf"
    scan_payload(pdf_bytes, filename, request=request, actor=None)
    stored_filename = f"consent_{uuid.uuid4().hex}_{_safe_filename(filename)}"
    dest = CASE_REQUEST_PROOF_DIR / stored_filename
    dest.write_bytes(pdf_bytes)

    proof = models.CaseRequestConsentProof(
        case_request_id=None,
        case_id=case_id,
        custodian_name=(getattr(consent, "custodian_name", None) or "").strip() or getattr(custodian, "name", None),
        custodian_email=(getattr(consent, "custodian_email", None) or "").strip() or getattr(custodian, "email", None),
        stored_filename=stored_filename,
        original_filename=filename,
        content_type="application/pdf",
        size=len(pdf_bytes),
        uploaded_by_id=None,
    )
    try:
        db.add(proof)
        if custodian:
            custodian.consent_status = "received"
            db.add(custodian)
        db.commit()
        _sync_case_consent_proof_count(db, case_id)
        db.refresh(proof)
        return proof
    except Exception:
        db.rollback()
        try:
            dest.unlink(missing_ok=True)
        except Exception as exc:
            _debug_suppressed("suppressed exception deleting failed DocuSign consent PDF", exc)
        raise


@router.post("/webhook")
async def docusign_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    sigs: List[str] = []
    try:
        for name, value in request.headers.raw:
            try:
                name_dec = name.decode("latin-1").lower()
                if name_dec.startswith("x-docusign-signature"):
                    sigs.append(value.decode("latin-1").strip())
            except (UnicodeDecodeError, AttributeError):
                continue
    except Exception as exc:
        _debug_suppressed("suppressed exception in docusign_webhook.py:100", exc)
    if not sigs:
        # Fall back to single header key if raw headers unavailable
        single = request.headers.get("X-DocuSign-Signature-1")
        if single:
            sigs.append(single.strip())
    _verify_signature(body, sigs)

    # Payload can be XML (classic Connect) or JSON (Connect / event notifications)
    envelope_id = None
    status = None
    completed_raw = None
    parsed = None

    content_type = (request.headers.get("Content-Type") or "").lower()
    if "json" in content_type or body.strip().startswith(b"{"):
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            data = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
            envelope_summary = data.get("envelopeSummary") if isinstance(data.get("envelopeSummary"), dict) else {}
            envelope_id = (
                data.get("envelopeId")
                or data.get("envelope_id")
                or envelope_summary.get("envelopeId")
                or parsed.get("envelopeId")
            )
            status = data.get("status") or envelope_summary.get("status") or parsed.get("status")
            completed_raw = (
                data.get("completedDateTime")
                or data.get("completed")
                or envelope_summary.get("completedDateTime")
                or parsed.get("completedDateTime")
            )
            if not status:
                status = _event_to_status(parsed.get("event") or data.get("event"))
    else:
        try:
            root = ET.fromstring(body)
        except Exception:
            # accept but ignore malformed payloads to avoid retries
            return {"ok": True}

        def _find_text(xpath: str) -> Optional[str]:
            el = root.find(xpath)
            if el is not None and el.text:
                return el.text.strip()
            return None

        envelope_id = _find_text(".//EnvelopeID") or _find_text(".//EnvelopeId")
        status = _find_text(".//Status")
        completed_raw = _find_text(".//CompletedDateTime") or _find_text(".//Completed")

    if not envelope_id:
        return {"ok": True}

    consent = (
        db.query(models.CaseConsent)
        .filter(models.CaseConsent.envelope_id == envelope_id)
        .filter(models.CaseConsent.provider == "docusign")
        .first()
    )
    if not consent:
        return {"ok": True}

    prev_status = (getattr(consent, "status", None) or "").strip()

    custodian_obj = None
    if consent.custodian_id:
        custodian_obj = db.query(models.Custodian).filter_by(id=consent.custodian_id, case_id=consent.case_id).first()
    elif consent.custodian_email:
        email_norm = (consent.custodian_email or "").strip().lower()
        if email_norm:
            custodian_obj = (
                db.query(models.Custodian)
                .filter(models.Custodian.case_id == consent.case_id)
                .filter(func.lower(models.Custodian.email) == email_norm)
                .first()
            )

    if status:
        consent.status = status
    now = datetime.now(timezone.utc)
    new_status = (status or prev_status or "").strip()
    if new_status and new_status.lower() == "completed":
        if completed_raw:
            try:
                consent.completed_at = datetime.fromisoformat(str(completed_raw).replace("Z", "+00:00"))
            except Exception:
                consent.completed_at = now
        else:
            consent.completed_at = now
        # Mark custodian consent as received
        try:
            if custodian_obj and (custodian_obj.consent_status or "").lower() != "received":
                custodian_obj.consent_status = "received"
        except Exception as exc:
            _debug_suppressed("suppressed exception in docusign_webhook.py:198", exc)
    consent.updated_at = now
    db.add(consent)
    db.commit()
    saved_proof = None
    if new_status and new_status.lower() == "completed":
        try:
            saved_proof = _save_completed_docusign_pdf(
                db,
                consent=consent,
                custodian=custodian_obj,
                request=request,
            )
        except ESignatureProviderError as exc:
            _debug_suppressed("DocuSign completed PDF download failed", exc)
        except HTTPException as exc:
            _debug_suppressed("DocuSign completed PDF scan/save blocked", exc)
        except Exception as exc:
            _debug_suppressed("DocuSign completed PDF save failed", exc)
    try:
        if prev_status != new_status:
            case = None
            try:
                case = db.get(models.Case, getattr(consent, "case_id", None))
            except Exception:
                case = None
            log_event(
                db,
                action="consent_status_update_docusign",
                actor_id=None,
                target_type="consent",
                target_id=getattr(consent, "id", None),
                details={
                    "case_id": getattr(consent, "case_id", None),
                    "case_name": getattr(case, "name", None) if case else None,
                    "consent_id": getattr(consent, "id", None),
                    "envelope_id": envelope_id,
                    "status_old": prev_status,
                    "status_new": new_status,
                    "completed_at": getattr(consent, "completed_at", None).isoformat() if getattr(consent, "completed_at", None) else None,
                    "custodian_id": getattr(consent, "custodian_id", None) or getattr(custodian_obj, "id", None),
                    "custodian_name": (getattr(consent, "custodian_name", None) or "").strip() or getattr(custodian_obj, "name", None),
                    "custodian_email": (getattr(consent, "custodian_email", None) or "").strip() or getattr(custodian_obj, "email", None),
                    "proof_id": getattr(saved_proof, "id", None),
                    "source": "docusign_webhook",
                },
                request=request,
            )
            if saved_proof:
                log_event(
                    db,
                    action="case_consent_proof_upload",
                    actor_id=None,
                    target_type="case",
                    target_id=getattr(consent, "case_id", None),
                    details={
                        "proof_id": getattr(saved_proof, "id", None),
                        "custodian_id": getattr(consent, "custodian_id", None) or getattr(custodian_obj, "id", None),
                        "custodian_name": getattr(saved_proof, "custodian_name", None),
                        "custodian_email": getattr(saved_proof, "custodian_email", None),
                        "original_filename": getattr(saved_proof, "original_filename", None),
                        "case_id": getattr(consent, "case_id", None),
                        "case_name": getattr(case, "name", None) if case else None,
                        "envelope_id": envelope_id,
                        "source": "docusign_webhook",
                    },
                    request=request,
                )
    except Exception as exc:
        _debug_suppressed("suppressed exception in docusign_webhook.py:231", exc)
    try:
        if (prev_status or "").lower() != "completed" and (new_status or "").lower() == "completed":
            notify_case_analyst_consent_completed(db, consent=consent, request=request)
    except Exception as exc:
        _debug_suppressed("suppressed exception in docusign_webhook.py:236", exc)
    return {"ok": True}
