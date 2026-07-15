import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .auth import current_user as get_current_user
from .database import get_db
from . import case_requests as case_request_core

router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])

def _normalize_request_type(value: str) -> str:
    base = (value or "").strip().lower()
    base = base.replace("-", "_").replace(" ", "_")
    if base == "closecase":
        base = "close_case"
    return base


@router.post("")
async def create_case_request(
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    if not actor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    case_request_core.ensure_case_request_access(actor)
    if case_request_core.is_tester(actor):
        raise HTTPException(status_code=403, detail="Tester accounts cannot submit requests")
    form = await request.form()
    request_type = _normalize_request_type((form.get("request_type") or "").strip())
    payload_raw = form.get("data", "")
    if request_type not in case_request_core.VALID_REQUEST_TYPES:
        raise HTTPException(status_code=400, detail="Invalid request type")
    if case_request_core.MAX_REQUEST_PAYLOAD_BYTES > 0:
        payload_bytes = (payload_raw or "").encode("utf-8")
        if len(payload_bytes) > case_request_core.MAX_REQUEST_PAYLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Request payload size exceeded")
    try:
        body = json.loads(payload_raw or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid request payload")

    case_request_core._enforce_pending_limits(db, actor)

    case_name = body.get("name")
    color = case_request_core._color_from_name(case_name)
    note = body.get("note") or body.get("description")
    ntp_all_sent = bool(body.get("ntp_all_sent"))
    attachment_name = None
    attachment_path = None
    attachment_size = 0

    custodian_file = form.get("custodian_file")
    if custodian_file and hasattr(custodian_file, "filename"):
        attachment_name, attachment_path, attachment_size = case_request_core._save_upload(custodian_file, actor=actor, request=request)

    proof_blobs = await case_request_core._extract_consent_proof_blobs(form, actor=actor, request=request)
    consent_proof_size = sum((blob["size"] for blob in proof_blobs.values()))

    if case_request_core.MAX_PENDING_STORAGE_BYTES > 0:
        current_usage = case_request_core._pending_storage_usage(db, actor.id)
        if current_usage + attachment_size + consent_proof_size > case_request_core.MAX_PENDING_STORAGE_BYTES:
            for cleanup_path in (attachment_path,):
                if not cleanup_path:
                    continue
                try:
                    path = Path(cleanup_path)
                    if path.exists() and case_request_core.CASE_REQUEST_UPLOAD_DIR in path.parents:
                        path.unlink()
                except Exception as exc:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:2749", exc)
            raise HTTPException(
                status_code=429,
                detail="Upload storage limit reached while requests await review. Please wait or contact an administrator.",
            )

    raw_case_id = body.get("case_id")
    case_id = None
    if raw_case_id not in (None, ""):
        try:
            case_id = int(raw_case_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="case_id must be an integer")
    linked_case = None
    if request_type != "new_case":
        if not case_id:
            raise HTTPException(status_code=400, detail="case_id is required for this request type")
        linked_case = db.get(models.Case, case_id)
        if not linked_case:
            raise HTTPException(status_code=404, detail="Case not found")
        case_request_core.ensure_case_visible(linked_case, actor, db)
        case_name = linked_case.name
        color = linked_case.color
    else:
        case_request_core._ensure_case_name_available(db, case_name)

    requested_custodians: Optional[List[Dict[str, Any]]] = None
    if request_type in {"new_case", "custodian"}:
        requested_custodians = case_request_core._collect_custodians_from_payload(body, attachment_path)
        existing_custodian_lookup = case_request_core._custodian_lookup_for_case(db, linked_case.id) if (request_type == "custodian" and linked_case and getattr(linked_case, "id", None)) else None
        case_request_core._ensure_unique_custodian_emails(requested_custodians, existing_lookup=existing_custodian_lookup)

    auto_approve = bool(case_request_core.is_requestor(actor) and request_type == "custodian" and linked_case is not None and getattr(linked_case, "id", None))
    auto_approver = case_request_core._pick_auto_approver(db, linked_case) if auto_approve else None
    reviewed_by_id = getattr(auto_approver, "id", None) if auto_approver else None

    custodian_mode = body.get("custodian_entry_mode")
    if request_type in {"new_case", "custodian"} and custodian_mode == "upload" and not attachment_path:
        raise HTTPException(status_code=400, detail="Custodian upload required")

    record = models.CaseRequest(
        request_type=request_type,
        status="approved" if auto_approve else "pending",
        case_id=linked_case.id if linked_case else None,
        case_name=case_name,
        color=color,
        payload=json.dumps(body, ensure_ascii=False),
        attachment_name=attachment_name,
        attachment_path=attachment_path,
        attachment_bytes=attachment_size,
        requestor_id=actor.id,
        requestor_email=getattr(actor, "email", None),
        ntp_all_sent=ntp_all_sent,
        note=note,
        reviewed_at=datetime.now(timezone.utc) if auto_approve else None,
        reviewed_by_id=reviewed_by_id if auto_approve else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    consents = body.get("consents") or []
    _persist_consent_proofs(db, record, consents, proof_blobs)

    try:
        case_request_core.log_event(
            db,
            action="case_request_submit",
            actor_id=actor.id,
            target_type="case_request",
            target_id=record.id,
            details={
                "request_type": request_type,
                "case_name": case_name,
                "case_id": record.case_id,
                "requestor_email": record.requestor_email,
                "existing_case": bool(record.case_id),
                "category": ("new_case" if request_type == "new_case" else f"{request_type}_update"),
            },
            request=request,
        )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:2825", exc)

    if not auto_approve:
        try:
            case_request_core.notify_case_request_submitted(db, record, request)
        except Exception as exc:
            case_request_core._debug_suppressed("suppressed exception in case_requests.py:2831", exc)
        return case_request_core._serialize_request(record, include_payload=True)

    # Auto-approved custodian requests for requestors:
    # - add custodians immediately so the case view updates
    # - enqueue Purview/ServiceNow automation in the background
    try:
        custodians_payload = requested_custodians if requested_custodians is not None else case_request_core._collect_custodians(record)
        case_request_core._ensure_unique_custodian_emails(
            custodians_payload,
            existing_lookup=case_request_core._custodian_lookup_for_case(db, int(record.case_id)),
        )
        claimant_value = getattr(linked_case, "claimant", None) if linked_case else None
        built_models: list[models.Custodian] = []
        for cust in custodians_payload or []:
            model = case_request_core._custodian_model(int(record.case_id), cust, record.ntp_all_sent, use_ai_review=False)
            if case_request_core._custodian_matches_claimant(
                claimant=claimant_value,
                name=getattr(model, "name", None),
                email=getattr(model, "email", None),
            ):
                model.ntp_status = "na"
                model.consent_status = "na"
            if linked_case:
                case_request_core._apply_consent_not_required_defaults(linked_case, model)
            built_models.append(model)
            db.add(model)
        db.flush()
        for model in built_models:
            case_request_core._sync_custom_preservation(db, model, getattr(model, "_custom_preservation_payload", []) or [])
        built_ids = [int(model.id) for model in built_models if getattr(model, "id", None) is not None]
        if built_ids:
            body["approved_custodian_ids"] = built_ids
            record.payload = json.dumps(body, ensure_ascii=False)
            db.add(record)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception as exc:
            case_request_core._debug_suppressed("suppressed exception in case_requests.py:2866", exc)
        case_request_core.logger.warning("auto_case_request_add_custodians_failed ts=%s request_id=%s error=%s", case_request_core._now_ts(), getattr(record, "id", None), exc)

    try:
        case_request_core.log_event(
            db,
            action="case_request_approve",
            actor_id=reviewed_by_id,
            target_type="case_request",
            target_id=record.id,
            details={
                "type": record.request_type,
                "case_id": record.case_id,
                "case_name": record.case_name,
                "requestor_email": record.requestor_email,
                "auto_approved": True,
            },
            request=request,
        )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:2886", exc)

    try:
        with case_request_core._case_request_auto_hold_lock:
            if int(record.id) not in case_request_core._case_request_auto_hold_threads:
                t = threading.Thread(target=case_request_core._auto_apply_case_request_holds, args=(int(record.id),), daemon=True)
                case_request_core._case_request_auto_hold_threads[int(record.id)] = t
                t.start()
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:2895", exc)

    return case_request_core._serialize_request(record, include_payload=True)
