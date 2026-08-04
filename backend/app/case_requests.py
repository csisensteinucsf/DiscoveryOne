from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
import time
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from io import BytesIO

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel, ConfigDict, Field
from .safe_log import debug_suppressed as _debug_suppressed
from openpyxl import load_workbook

from .audit import log_event
from .auth import current_user as get_current_user
from .cases import (
    _require_employee_id,
    _configured_ticket_default_customer_id,
    _normalize_employee_id_digits,
    _normalize_requestor_entries,
    _apply_case_requestors,
    create_case_in_purview,
    apply_purview_holds,
    _schedule_preservation_status_poll,
    _schedule_purview_status_poll,
    get_purview_status,
    _normalize_request_ticket_entries,
    _sync_legacy_request_tickets,
    _apply_request_holds,
    _apply_consent_not_required_defaults,
    _derive_employment_status_from_end_date,
    _sync_case_documentation_counters,
    _extract_custom_preservation_payload,
    _custom_preservation_key,
    _sync_custom_preservation,
)
from . import schemas
from .case_naming import _case_naming_mode, _unique_case_name, _next_created_date_case_name
from .database import get_db, SessionLocal
from .file_security import scan_payload, sniff_mime
from . import models
from .permissions import ensure_case_visible, ensure_case_request_access, ensure_case_request_reviewer, ensure_not_requestor, get_role, is_requestor, is_tester
from .notifications import (
    _app_base_url,
    notify_case_request_custodian_count_mismatch,
    notify_case_request_hold_status,
    notify_case_request_outcome,
    notify_case_request_submitted,
)
from .models import CaseRequestConsentProof

from .identity_review import apply_custodian_name_email_review
from .institution import is_organization_email
from .person_lookup import person_lookup_enabled, person_lookup_provider_name
from . import case_request_settings as _case_request_settings
from . import case_request_hold_automation as _hold_automation
from . import case_request_lookup_refresh as _lookup_refresh
from . import case_request_slack_holds as _slack_hold_helpers
from . import case_request_auto_apply as _auto_apply
from .person_lookup_matching import (
    _best_token_similarity,
    _build_lookup_display_name,
    _coerce_lookup_bool,
    _coerce_lookup_text,
    _has_strong_lookup_match,
    _is_exact_first_last_lookup_match,
    _match_has_lookup_department,
    _match_has_lookup_email,
    _match_has_lookup_job,
    _match_has_organization_lookup_email,
    _match_is_current_employee,
    _name_variants,
    _normalize_lookup_external_id,
    _normalize_lookup_email,
    _normalize_person_label,
    _person_label_tokens,
    _pick_lookup_match,
    _rank_lookup_matches,
    _run_configured_person_lookup,
    _score_lookup_match,
    _single_token_fallback_candidates,
    _split_name,
    _three_name_variants,
    _token_similarity,
)
router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])

CASE_REQUEST_UPLOAD_DIR = Path(os.getenv("CASE_REQUEST_UPLOAD_DIR", "/app/case_request_uploads"))
CASE_REQUEST_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.getenv("CASE_REQUEST_MAX_UPLOAD_BYTES", "5242880"))
VALID_REQUEST_TYPES = {"new_case", "custodian", "search", "close_case"}
MAX_PENDING_STORAGE_BYTES = int(os.getenv("CASE_REQUEST_PENDING_MAX_BYTES", str(200 * 1024 * 1024)))
MAX_PENDING_REQUESTS_PER_USER = int(os.getenv("CASE_REQUEST_PENDING_MAX_PER_USER", "25"))
MAX_CONSENT_UPLOAD_BYTES = int(os.getenv("CASE_REQUEST_CONSENT_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
CONSENT_ATTACHMENT_EXTS = {".msg", ".eml", ".pdf"}
CASE_REQUEST_PROOF_DIR = CASE_REQUEST_UPLOAD_DIR / "consent_proofs"
CASE_REQUEST_PROOF_DIR.mkdir(parents=True, exist_ok=True)
MAX_REQUEST_PAYLOAD_BYTES = int(os.getenv("CASE_REQUEST_MAX_PAYLOAD_BYTES", "262144"))
CASE_REQUEST_CUSTODIAN_MAX_ROWS = int(os.getenv("CASE_REQUEST_CUSTODIAN_MAX_ROWS", "50000"))
CASE_REQUEST_CUSTODIAN_MAX_COLS = int(os.getenv("CASE_REQUEST_CUSTODIAN_MAX_COLS", "50"))
def case_request_stats_requestor_show_global() -> bool:
    return _case_request_settings.requestor_stats_show_global()


def case_request_hold_automation_allow_override() -> bool:
    return _case_request_settings.hold_automation_allow_override()


def case_request_auto_rubrik_restore_for_separated_email_holds() -> bool:
    return _case_request_settings.auto_rubrik_restore_for_separated_email_holds()


def case_request_pending_cleanup_days() -> float:
    return _case_request_settings.pending_cleanup_days()


def case_request_pending_cleanup_interval_hours() -> float:
    return _case_request_settings.pending_cleanup_interval_hours()


def case_request_hold_status_email_delay_seconds() -> float:
    return _case_request_settings.hold_status_email_delay_seconds()


def preservation_auto_apply_max_attempts() -> int:
    return _case_request_settings.preservation_auto_apply_max_attempts()


def preservation_auto_apply_delay_seconds() -> float:
    return _case_request_settings.preservation_auto_apply_delay_seconds()


def preservation_status_max_seconds() -> float:
    return _case_request_settings.preservation_status_max_seconds()


def preservation_status_interval_seconds() -> float:
    return _case_request_settings.preservation_status_interval_seconds()


def purview_auto_apply_max_attempts() -> int:
    return preservation_auto_apply_max_attempts()


def purview_auto_apply_delay_seconds() -> float:
    return preservation_auto_apply_delay_seconds()


def purview_approval_status_max_seconds() -> float:
    return preservation_status_max_seconds()


def purview_approval_status_interval_seconds() -> float:
    return preservation_status_interval_seconds()
ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger(__name__)


def _now_ts() -> str:
    try:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""

_hold_status_email_lock = threading.Lock()
_hold_status_email_timers: dict[int, threading.Timer] = {}
_case_request_auto_hold_threads: dict[int, threading.Thread] = {}
_case_request_auto_hold_lock = threading.Lock()


def _custodian_matches_claimant(*, claimant: str | None, name: str | None, email: str | None) -> bool:
    claim = _normalize_person_label(claimant)
    if not claim or claim in {"na", "n/a"}:
        return False
    email_norm = _normalize_person_label(email)
    if "@" in claim and email_norm and email_norm == claim:
        return True
    name_norm = _normalize_person_label(name)
    if not name_norm:
        return False
    if name_norm == claim:
        return True
    if len(claim) >= 4 and (claim in name_norm or name_norm in claim):
        return True
    return False


def _pick_auto_approver(db: Session, case: Optional[models.Case]) -> Optional[models.User]:
    return _hold_automation.pick_auto_approver(db, case)


def _has_hold(model: models.Custodian, attr: str) -> bool:
    return _hold_automation.has_hold(model, attr)


def _allow_hold_automation(model: models.Custodian) -> bool:
    return _hold_automation.allow_hold_automation(model)


def _has_usable_email(model: models.Custodian) -> bool:
    return _hold_automation.has_usable_email(model)


def _provider_email_hold_complete(model: models.Custodian) -> bool:
    return _hold_automation.provider_email_hold_complete(model)


def _purview_email_hold_complete(model: models.Custodian) -> bool:
    return _provider_email_hold_complete(model)


def _clear_rubrik_restore_hold_flags(model: models.Custodian) -> None:
    return _hold_automation.clear_rubrik_restore_hold_flags(model)


def _filter_rubrik_targets_after_preservation(db: Session, rubrik_targets: list[models.Custodian]) -> list[models.Custodian]:
    return _hold_automation.filter_rubrik_targets_after_preservation(db, rubrik_targets)


def _filter_rubrik_targets_after_purview(db: Session, rubrik_targets: list[models.Custodian]) -> list[models.Custodian]:
    return _filter_rubrik_targets_after_preservation(db, rubrik_targets)

def _apply_slack_hold_sync_state(custodian: models.Custodian, *, enable: bool) -> None:
    return _slack_hold_helpers.apply_slack_hold_sync_state(custodian, enable=enable)


def _apply_slack_hold_sync_failure_state(custodian: models.Custodian, *, enable: bool) -> None:
    return _slack_hold_helpers.apply_slack_hold_sync_failure_state(custodian, enable=enable)


def _sync_slack_hold_for_custodian_or_raise(
    case: models.Case,
    custodian: models.Custodian,
    *,
    enable: bool,
    email_override: Optional[str] = None,
    db: Optional[Session] = None,
    actor_id: Optional[int] = None,
    request: Request = None,
    source: str = "case_request_approve",
    continue_on_user_not_found: bool = False,
) -> None:
    return _slack_hold_helpers.sync_slack_hold_for_custodian_or_raise(
        case,
        custodian,
        enable=enable,
        email_override=email_override,
        db=db,
        actor_id=actor_id,
        request=request,
        source=source,
        continue_on_user_not_found=continue_on_user_not_found,
    )
def _auto_apply_case_request_holds(request_id: int) -> None:
    return _auto_apply.auto_apply_case_request_holds(
        request_id,
        session_factory=SessionLocal,
        auto_hold_threads=_case_request_auto_hold_threads,
        auto_hold_lock=_case_request_auto_hold_lock,
        schedule_hold_status_email=_schedule_case_request_hold_status_email,
    )
def _send_case_request_hold_status_email(
    record_id: int,
    custodian_ids: list[int],
    *,
    base_url: Optional[str] = None,
) -> None:
    return _case_request_module("case_request_hold_emails").send_case_request_hold_status_email(
        record_id,
        custodian_ids,
        base_url=base_url,
        session_factory=SessionLocal,
        models=models,
        notify_case_request_hold_status=notify_case_request_hold_status,
        now_ts=_now_ts,
        debug_suppressed=_debug_suppressed,
    )


def _schedule_case_request_hold_status_email(
    record_id: int,
    custodian_ids: list[int],
    *,
    base_url: Optional[str] = None,
) -> None:
    return _case_request_module("case_request_hold_emails").schedule_case_request_hold_status_email(
        record_id,
        custodian_ids,
        base_url=base_url,
        delay_seconds=case_request_hold_status_email_delay_seconds(),
        send_func=_send_case_request_hold_status_email,
        debug_suppressed=_debug_suppressed,
    )
NO_EMAIL_PLACEHOLDER = "NoEmail"
UNMATCHED_EMAIL_PLACEHOLDER = "UNMATCHED"


class CustodianLookupItem(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    model_config = ConfigDict(extra="ignore")


class CustodianLookupRequest(BaseModel):
    custodians: List[CustodianLookupItem] = Field(default_factory=list)
    model_config = ConfigDict(extra="ignore")


def _safe_filename(name: Optional[str]) -> str:
    return _case_request_module("case_request_custodian_uploads")._safe_filename(name)


def _decode_text_table_payload(payload: bytes) -> str:
    return _case_request_module("case_request_custodian_uploads")._decode_text_table_payload(payload)


def _normalize_header(value: Optional[str]) -> str:
    return _case_request_module("case_request_custodian_uploads")._normalize_header(value)


def _parse_uploaded_custodians_from_bytes(payload: bytes, filename: Optional[str]) -> List[Dict[str, Any]]:
    return _case_request_module("case_request_custodian_uploads")._parse_uploaded_custodians_from_bytes(payload, filename)


def _validate_custodian_upload_bytes(payload: bytes, filename: Optional[str], *, max_bytes: int) -> None:
    return _case_request_module("case_request_custodian_uploads")._validate_custodian_upload_bytes(payload, filename, max_bytes=max_bytes)


def _save_upload(file: UploadFile, *, actor: models.User, request: Request) -> tuple[str, str, int]:
    return _case_request_module("case_request_custodian_uploads")._save_upload(file, actor=actor, request=request)


async def parse_custodian_file(*args, **kwargs):
    return await _case_request_module("case_request_custodian_uploads").parse_custodian_file(*args, **kwargs)


async def _read_consent_proof_blob(file: UploadFile, *, actor: models.User, request: Request) -> dict:
    return await _case_request_module("case_request_storage")._read_consent_proof_blob(file, actor=actor, request=request)


def _write_consent_proof_file(blob: dict) -> str:
    return _case_request_module("case_request_storage")._write_consent_proof_file(blob)


def _pending_storage_usage(db: Session, user_id: int) -> int:
    return _case_request_module("case_request_storage")._pending_storage_usage(db, user_id)


def _enforce_pending_limits(db: Session, user: models.User) -> None:
    pending_count = (
        db.query(func.count(models.CaseRequest.id))
        .filter(
            models.CaseRequest.requestor_id == user.id,
            models.CaseRequest.status == "pending",
        )
        .scalar()
        or 0
    )
    if MAX_PENDING_REQUESTS_PER_USER > 0 and pending_count >= MAX_PENDING_REQUESTS_PER_USER:
        raise HTTPException(status_code=429, detail="Too many pending requests. Please wait for review before submitting new ones.")
    if MAX_PENDING_STORAGE_BYTES > 0:
        usage = _pending_storage_usage(db, user.id)
        if usage >= MAX_PENDING_STORAGE_BYTES:
            raise HTTPException(
                status_code=429,
                detail="Upload storage limit reached while requests await review. Please wait or contact an administrator.",
            )


def _payload_dict(record: models.CaseRequest) -> Dict[str, Any]:
    if not record.payload:
        return {}
    try:
        return json.loads(record.payload)
    except Exception:
        return {}


def _serialize_request(
    record: models.CaseRequest,
    include_payload: bool = False,
    include_proofs: bool = True,
) -> Dict[str, Any]:
    data = {
        "id": record.id,
        "request_type": record.request_type,
        "status": record.status,
        "case_id": record.case_id,
        "case_name": record.case_name,
        "color": record.color,
        "requestor": {
            "id": record.requestor_id,
            "email": record.requestor_email,
            "username": getattr(record.requestor, "username", None),
        },
        "ntp_all_sent": record.ntp_all_sent,
        "note": record.note,
        "attachment_name": record.attachment_name,
        "consent_attachment_name": record.consent_attachment_name,
        "consent_attachment_url": f"/api/case_requests/{record.id}/consent_attachment" if record.consent_attachment_path else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        "reviewed_by": {
            "id": record.reviewed_by_id,
            "username": getattr(record.reviewer, "username", None),
        } if record.reviewed_by_id else None,
        "decline_reason": record.decline_reason,
    }
    if include_payload:
        data["payload"] = _payload_dict(record)
    if include_proofs:
        proofs = []
        for proof in getattr(record, "consent_proofs", []) or []:
            proofs.append({
                "id": proof.id,
                "custodian_name": proof.custodian_name,
                "custodian_email": proof.custodian_email,
                "original_filename": proof.original_filename,
                "size": proof.size,
                "url": f"/api/case_requests/{record.id}/consent_proofs/{proof.id}",
            })
        if proofs:
            data["consent_proofs"] = proofs
    data["case_deleted"] = bool(record.case_deleted)
    return data


def _request_query_with_related(query):
    return query.options(
        selectinload(models.CaseRequest.requestor),
        selectinload(models.CaseRequest.reviewer),
        selectinload(models.CaseRequest.consent_proofs),
    )


def _ensure_case_name_available(db: Session, name: str, *, exclude_request_id: Optional[int] = None) -> None:
    if not name:
        raise HTTPException(status_code=400, detail="Case name is required")
    exists = db.query(models.Case).filter(models.Case.name == name).first()
    if exists:
        raise HTTPException(status_code=409, detail="Case name already exists")
    pending_query = (
        db.query(models.CaseRequest)
        .filter(models.CaseRequest.status == "pending")
        .filter(models.CaseRequest.request_type == "new_case")
        .filter(func.lower(models.CaseRequest.case_name) == name.lower())
    )
    if exclude_request_id:
        pending_query = pending_query.filter(models.CaseRequest.id != exclude_request_id)
    pending = pending_query.first()
    if pending:
        raise HTTPException(status_code=409, detail="Case name currently reserved")


def _color_from_name(name: Optional[str]) -> Optional[str]:
    if not name or "-" not in name:
        return None
    return name.split("-", 1)[1]


def _lookup_matches_for_identity(name: str, cursor=None) -> tuple[list[dict], Optional[str]]:
    return _lookup_refresh.lookup_matches_for_identity(name, cursor=cursor)


def _lookup_matches_for_query(query: str, *, email: Optional[str] = None, cursor=None) -> tuple[list[dict], Optional[str]]:
    return _lookup_refresh.lookup_matches_for_query(
        query,
        email=email,
        cursor=cursor,
    )

def _apply_person_lookup_match_to_custodian(
    custodian: models.Custodian,
    match: dict,
    *,
    overwrite_name: bool = True,
    clear_override: bool = False,
    lookup_at: Optional[datetime] = None,
    use_ai_review: bool = False,
) -> None:
    return _lookup_refresh.apply_person_lookup_match_to_custodian(
        custodian,
        match,
        overwrite_name=overwrite_name,
        clear_override=clear_override,
        lookup_at=lookup_at,
        use_ai_review=use_ai_review,
    )


def _parse_uploaded_custodians(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        payload = file_path.read_bytes()
    except Exception:
        return []
    try:
        return _parse_uploaded_custodians_from_bytes(payload, file_path.name)
    except HTTPException:
        return []
    except Exception:
        return []


def _collect_custodians_from_payload(
    payload: Optional[Dict[str, Any]],
    attachment_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    payload = payload or {}
    custs: List[Dict[str, Any]] = []
    for item in payload.get("custodians", []) or []:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        custs.append(
            {
                "name": name,
                "email": (item.get("email") or "").strip() or None,
                "notes": item.get("notes"),
                "holds": item.get("holds") or {},
                "ntp_status": (item.get("ntp_status") or "").strip().lower(),
                "consent_received": bool(item.get("consent_received")),
                "employment_end_date": item.get("employment_end_date") or item.get("employee_end_date"),
                "person_lookup_overridden": bool(item.get("person_lookup_overridden") or item.get("lookup_override")),
                "external_id": item.get("external_id") or item.get("employee_id") or item.get("person_id"),
                "display_name": item.get("display_name"),
                "first_name": item.get("first_name"),
                "last_name": item.get("last_name"),
                "department_id": item.get("department_id"),
                "department": item.get("department") or item.get("department_name"),
                "title": item.get("title") or item.get("job_title_official"),
                "current_employee": item.get("current_employee"),
            }
        )
    if payload.get("custodian_entry_mode") == "upload":
        custs.extend(_parse_uploaded_custodians(attachment_path))
    return custs


def _collect_custodians(request: models.CaseRequest) -> List[Dict[str, Any]]:
    return _collect_custodians_from_payload(_payload_dict(request), request.attachment_path)


def _normalize_custodian_email_key(email: Any) -> str:
    value = str(email or "").strip().lower()
    if value in {"", NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        return ""
    return value


def _ensure_unique_custodian_emails(
    custodians: Optional[List[Dict[str, Any]]],
    *,
    existing_lookup: Optional[Dict[str, models.Custodian]] = None,
) -> None:
    seen: Dict[str, str] = {}
    for item in custodians or []:
        email_raw = str((item or {}).get("email") or "").strip()
        email_key = _normalize_custodian_email_key(email_raw)
        if not email_key:
            continue
        display_email = email_raw or email_key
        if email_key in seen:
            raise HTTPException(status_code=409, detail=f"Duplicate custodian email in request: {display_email}")
        if existing_lookup and email_key in existing_lookup:
            raise HTTPException(status_code=409, detail=f"Custodian with email {display_email} is already assigned to this case")
        seen[email_key] = display_email


async def _extract_consent_proof_blobs(form, *, actor: models.User, request: Request) -> Dict[str, dict]:
    blobs = {}
    for key, value in form.multi_items():
        if not key.startswith("consent_proof_"):
            continue
        if not hasattr(value, "filename"):
            continue
        cust_id = key.replace("consent_proof_", "", 1)
        blob = await _read_consent_proof_blob(value, actor=actor, request=request)
        blobs[cust_id] = blob
    return blobs


def _persist_consent_proofs(
    db: Session,
    record: models.CaseRequest,
    consents: Optional[List[Dict[str, Any]]],
    proof_blobs: Dict[str, dict],
) -> None:
    if not consents or not proof_blobs:
        return
    for consent in consents:
        cust_id = consent.get("custodian_id")
        blob = proof_blobs.get(cust_id)
        if not blob:
            continue
        stored = _write_consent_proof_file(blob)
        proof = models.CaseRequestConsentProof(
            case_request_id=record.id,
            case_id=record.case_id,
            custodian_name=consent.get("name"),
            custodian_email=consent.get("email"),
            stored_filename=stored,
            original_filename=blob["filename"],
            content_type=blob["content_type"],
            size=blob["size"],
            uploaded_by_id=record.requestor_id,
        )
        db.add(proof)
    db.commit()
    if record.case_id:
        _sync_case_documentation_counters(db, int(record.case_id))


def _assign_request_proofs_to_default_hold(db: Session, record: models.CaseRequest) -> None:
    if not record.case_id:
        return
    case = db.get(models.Case, int(record.case_id))
    if case is None:
        return
    from .case_holds import ensure_default_hold
    from .hold_workflows import set_membership_consent_status

    hold = ensure_default_hold(db, case, assign_existing=True)
    db.flush()
    for proof in list(getattr(record, "consent_proofs", []) or []):
        proof.case_id = int(record.case_id)
        custodian = _find_custodian_for_case(
            db,
            int(record.case_id),
            email=getattr(proof, "custodian_email", None),
            name=getattr(proof, "custodian_name", None),
        )
        if custodian is not None:
            membership = (
                db.query(models.HoldCustodian)
                .filter(
                    models.HoldCustodian.hold_id == hold.id,
                    models.HoldCustodian.custodian_id == custodian.id,
                )
                .first()
            )
            if membership is not None:
                proof.hold_custodian_id = membership.id
                set_membership_consent_status(db, membership, "received")
        db.add(proof)
    db.flush()

def _custodian_lookup_for_case(db: Session, case_id: int) -> Dict[str, models.Custodian]:
    custodians = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id)
        .all()
    )
    lookup: Dict[str, models.Custodian] = {}
    for cust in custodians:
        email = (cust.email or "").strip().lower()
        if email in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
            continue
        if email:
            lookup[email] = cust
    return lookup


def _find_custodian_for_case(
    db: Session,
    case_id: int,
    custodian_id: Optional[int] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
) -> Optional[models.Custodian]:
    """
    Locate a custodian for the given case by id, email, or name (in that order).
    """
    base_q = db.query(models.Custodian).filter(models.Custodian.case_id == case_id)
    if custodian_id:
        cust = base_q.filter(models.Custodian.id == custodian_id).first()
        if cust:
            return cust
    email_key = (email or "").strip().lower()
    if email_key in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        email_key = ""
    if email_key:
        cust = base_q.filter(func.lower(models.Custodian.email) == email_key).first()
        if cust:
            return cust
    name_key = (name or "").strip().lower()
    if name_key:
        cust = base_q.filter(func.lower(models.Custodian.name) == name_key).first()
        if cust:
            return cust
    return None


def _next_consent_status_after_proof_removal(
    db: Session,
    case_id: int,
    *,
    custodian: Optional[models.Custodian],
    email: Optional[str],
    name: Optional[str],
    hold_custodian_id: Optional[int] = None,
) -> str:
    """Return the remaining consent state for one named-hold membership."""
    email_key = (email or "").strip().lower()
    name_key = (name or "").strip().lower()

    proof_q = db.query(models.CaseRequestConsentProof.id).filter(models.CaseRequestConsentProof.case_id == case_id)
    if hold_custodian_id is not None:
        proof_q = proof_q.filter(models.CaseRequestConsentProof.hold_custodian_id == hold_custodian_id)
    elif email_key:
        proof_q = proof_q.filter(func.lower(models.CaseRequestConsentProof.custodian_email) == email_key)
    elif name_key:
        proof_q = proof_q.filter(func.lower(models.CaseRequestConsentProof.custodian_name) == name_key)
    else:
        proof_q = None
    if proof_q is not None and proof_q.first():
        return "received"

    consent_q = db.query(models.CaseConsent).filter(models.CaseConsent.case_id == case_id)
    if hold_custodian_id is not None:
        consent_q = consent_q.filter(models.CaseConsent.hold_custodian_id == hold_custodian_id)
    elif custodian and custodian.id:
        consent_q = consent_q.filter(models.CaseConsent.custodian_id == custodian.id)
    elif email_key:
        consent_q = consent_q.filter(func.lower(models.CaseConsent.custodian_email) == email_key)
    elif name_key:
        consent_q = consent_q.filter(func.lower(models.CaseConsent.custodian_name) == name_key)
    else:
        consent_q = None

    if consent_q is not None:
        completed = consent_q.filter(models.CaseConsent.status.in_(["completed", "received"])).first()
        if completed:
            return "received"
    return "not sent"

def _serialize_case_consent_proof(
    proof: models.CaseRequestConsentProof,
    custodian_lookup: Optional[Dict[str, models.Custodian]] = None,
) -> Dict[str, Any]:
    case_id = proof.case_id
    email_key = (proof.custodian_email or "").strip().lower()
    custodian = custodian_lookup.get(email_key) if custodian_lookup else None
    display_name = custodian.name if (custodian and custodian.name) else proof.custodian_name
    uploader = proof.uploaded_by or getattr(proof.case_request, "requestor", None)
    original_filename = proof.original_filename or ""
    source = (
        "docusign"
        if original_filename.lower().startswith("docusign-")
        else ("case_request" if proof.case_request_id else "manual")
    )
    return {
        "id": proof.id,
        "case_request_id": proof.case_request_id,
        "hold_custodian_id": getattr(proof, "hold_custodian_id", None),
        "hold_id": getattr(getattr(proof, "hold_custodian", None), "hold_id", None),
        "hold_name": getattr(getattr(getattr(proof, "hold_custodian", None), "hold", None), "name", None),
        "custodian_name": display_name,
        "custodian_email": proof.custodian_email,
        "original_filename": original_filename,
        "size": proof.size,
        "url": f"/api/case_requests/cases/{case_id}/consent_proofs/{proof.id}" if case_id else None,
        "uploaded_at": proof.created_at.isoformat() if proof.created_at else None,
        "uploaded_by": {
            "id": uploader.id,
            "username": getattr(uploader, "username", None),
            "email": getattr(uploader, "email", None),
        } if uploader else None,
        "source": source,
    }


def _apply_consents(db: Session, case_id: Optional[int], consents: Optional[List[Dict[str, Any]]]) -> None:
    if not case_id or not consents:
        return
    case = db.get(models.Case, int(case_id))
    if case is None:
        return
    from .case_holds import ensure_default_hold
    from .hold_workflows import set_membership_consent_status

    hold = ensure_default_hold(db, case, assign_existing=True)
    db.flush()
    for item in consents or []:
        custodian = _find_custodian_for_case(
            db,
            int(case_id),
            email=(item.get("email") or "").strip() or None,
            name=(item.get("name") or "").strip() or None,
        )
        if custodian is None:
            continue
        membership = (
            db.query(models.HoldCustodian)
            .filter(
                models.HoldCustodian.hold_id == hold.id,
                models.HoldCustodian.custodian_id == custodian.id,
            )
            .first()
        )
        if membership is not None:
            set_membership_consent_status(db, membership, "received")

def _custodian_model(case_id: int, data: Dict[str, Any], ntp_sent: bool, *, use_ai_review: bool = True) -> models.Custodian:
    holds = data.get("holds") or {}
    def _hold_flags(key: str) -> tuple[bool, bool]:
        """
        Normalize hold inputs that may be booleans or status strings (pending/completed).
        Returns (hold_active, hold_pending).
        """
        raw = holds.get(key)
        pending_raw = holds.get(f"{key}_pending")
        status_raw = holds.get(f"{key}_status")

        def _state(val: Any) -> Optional[str]:
            if isinstance(val, dict):
                return _state(val.get("status"))
            if isinstance(val, bool):
                return "pending" if val else "off"
            if isinstance(val, str):
                s = val.strip().lower()
                if not s:
                    return None
                if s in {"pending", "requested", "in progress"}:
                    return "pending"
                if s in {"complete", "completed", "done", "resolved", "placed"}:
                    return "on"
                if s in {"false", "0", "off", "none", "no"}:
                    return "off"
                # Default non-empty strings to pending to avoid missing requested holds.
                return "pending"
            return None

        state = _state(status_raw) or _state(raw)
        if state is None:
            pending_state = _state(pending_raw)
            if pending_state:
                state = "pending" if pending_state != "off" else "off"

        if state == "pending":
            return (True, True)
        if state == "on":
            return (True, False)
        return (False, False)

    end_date_raw = data.get("employment_end_date") or data.get("employee_end_date")
    email_hold, email_hold_pending = _hold_flags("email")
    onedrive_hold, onedrive_hold_pending = _hold_flags("onedrive")
    gdrive_hold, gdrive_hold_pending = _hold_flags("gdrive")
    box_hold, box_hold_pending = _hold_flags("box")
    slack_hold, slack_hold_pending = _hold_flags("slack")
    rubrik_hold, rubrik_hold_pending = _hold_flags("rubrik_restore")
    custom_preservation = _extract_custom_preservation_payload({"custom_preservation": data.get("custom_preservation") or []})
    known_hold_keys = {"email", "onedrive", "gdrive", "box", "slack", "rubrik_restore"}
    custom_seen = {item["source_key"] for item in custom_preservation}
    for raw_key in list(holds.keys()):
        key_text = str(raw_key or "").strip()
        base_key = re.sub(r"_(pending|status)$", "", key_text)
        source_label = base_key.replace("custom:", "", 1)
        source_key = _custom_preservation_key(source_label)
        if not source_key or source_key in known_hold_keys or source_key in custom_seen:
            continue
        active, pending = _hold_flags(key_text)
        if not (active or pending):
            continue
        custom_seen.add(source_key)
        custom_preservation.append(
            {
                "source_key": source_key,
                "source_label": source_label.replace("_", " ").title(),
                "active": active,
                "pending": pending,
                "failed": False,
                "released": False,
            }
        )

    def _derive_employment_status(value: Any) -> tuple[Optional[str], bool, bool]:
        """
        Returns (status, rubrik_flag, over_year_flag)
        status: current | separated | separated_90 | separated_365
        rubrik_flag: True when separated 90+ days; automation requires the Rubrik auto-restore setting.
        over_year_flag: True when separated 365+ days
        """
        if value in (None, "", 0):
            return ("current", False, False)
        text = str(value).strip()
        try:
            ts = datetime.fromisoformat(text).date()
        except Exception:
            try:
                ts = datetime.strptime(text[:10], "%Y-%m-%d").date()
            except Exception:
                return (None, False, False)
        today = datetime.now(timezone.utc).date()
        if ts > today:
            return ("current", False, False)
        days = (today - ts).days
        rubrik_flag = days >= 90
        over_year = days >= 365
        if over_year:
            return ("separated_365", rubrik_flag, over_year)
        if rubrik_flag:
            return ("separated_90", rubrik_flag, over_year)
        return ("separated", rubrik_flag, over_year)

    employment_status, rubrik_flag, _ = _derive_employment_status(end_date_raw)
    auto_rubrik_enabled = case_request_auto_rubrik_restore_for_separated_email_holds()
    if auto_rubrik_enabled and rubrik_flag and email_hold:
        rubrik_hold = True
        rubrik_hold_pending = True

    raw_email = (data.get("email") or "").strip()
    raw_email_norm = raw_email.lower()
    if raw_email and raw_email_norm not in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        email_val = raw_email
    else:
        # Preserve custodians even when requestors don't have a usable email address.
        email_val = UNMATCHED_EMAIL_PLACEHOLDER
    is_org_email = is_organization_email(email_val)
    lookup_overridden = bool(data.get("person_lookup_overridden") or data.get("lookup_override"))
    if email_val == UNMATCHED_EMAIL_PLACEHOLDER:
        lookup_overridden = True
    c = models.Custodian(
        case_id=case_id,
        added_at=datetime.now(timezone.utc),
        name=data.get("name"),
        email=email_val,
        notes=data.get("notes"),
        person_lookup_overridden=lookup_overridden,
        holds_email=email_hold,
        holds_onedrive=onedrive_hold,
        holds_gdrive=gdrive_hold,
        holds_box=box_hold,
        holds_slack=slack_hold,
        holds_rubrik_restore=rubrik_hold,
        holds_email_pending=email_hold_pending,
        holds_onedrive_pending=onedrive_hold_pending,
        holds_gdrive_pending=gdrive_hold_pending,
        holds_box_pending=box_hold_pending,
        holds_slack_pending=slack_hold_pending,
        holds_rubrik_restore_pending=rubrik_hold_pending,
        employment_end_date=end_date_raw,
        employment_status=employment_status,
    )
    setattr(c, "_custom_preservation_payload", custom_preservation)
    lookup_match_payload = {
        "external_id": data.get("external_id") or data.get("employee_id"),
        "display_name": data.get("display_name"),
        "first_name": data.get("first_name"),
        "middle_name": data.get("middle_name"),
        "last_name": data.get("last_name"),
        "email": data.get("email"),
        "department_id": data.get("department_id"),
        "department": data.get("department") or data.get("department_name"),
        "title": data.get("title") or data.get("job_title_official"),
        "separation_date": data.get("separation_date") or end_date_raw,
        "employee_end_date": end_date_raw,
        "current_employee": data.get("current_employee"),
    }
    has_lookup_payload = any(
        val not in (None, "")
        for key, val in lookup_match_payload.items()
        if key not in {"current_employee", "email"}
    ) or (lookup_match_payload.get("current_employee") is not None)
    if has_lookup_payload:
        _apply_person_lookup_match_to_custodian(
            c,
            lookup_match_payload,
            overwrite_name=True,
            clear_override=not lookup_overridden,
            use_ai_review=False,
        )
        employment_status = getattr(c, "employment_status", employment_status)
    apply_custodian_name_email_review(c, use_ai=use_ai_review)

    if ntp_sent:
        c.ntp_status = "sent"
    ntp_status = (data.get("ntp_status") or "").lower()
    if ntp_status in {"sent", "acknowledged", "na"}:
        c.ntp_status = ntp_status
    if data.get("consent_received"):
        c.consent_status = "received"
    if not is_org_email:
        c.ntp_status = "na"
        c.consent_status = "na"
    if (employment_status or "").lower().startswith("separated"):
        c.ntp_status = "na"
        c.consent_status = "na"
    # Attach a transient marker so the caller knows whether to auto-create Rubrik ticket.
    c._auto_rubrik_flag = bool(auto_rubrik_enabled and rubrik_flag and email_hold)  # type: ignore[attr-defined]
    return c


def _search_model(case_id: int, data: Dict[str, Any]) -> models.Search:
    raw_ids = data.get("custodian_ids")
    custodian_ids: list[int] = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            try:
                cid = int(item)
            except Exception:
                continue
            if cid > 0:
                custodian_ids.append(cid)
    return models.Search(
        case_id=case_id,
        name=data.get("name") or f"Search {datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
        keywords=data.get("keywords"),
        senders=data.get("senders"),
        recipients=data.get("recipients"),
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        additional=data.get("additional"),
        custodian_ids=json.dumps(sorted(set(custodian_ids))),
    )


def _search_has_details(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    for v in value.values():
        if v is None:
            continue
        if isinstance(v, str):
            if v.strip():
                return True
            continue
        if isinstance(v, (list, dict)):
            if v:
                return True
            continue
        if bool(v):
            return True
    return False


def _extract_search_payloads(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    searches = payload.get("searches")
    if isinstance(searches, list):
        out: list[Dict[str, Any]] = []
        for item in searches:
            if isinstance(item, dict) and _search_has_details(item):
                out.append(item)
        return out
    search = payload.get("search")
    if isinstance(search, dict) and _search_has_details(search):
        return [search]
    return []


def _extract_versa_search_requirements(payload: Dict[str, Any]) -> str:
    for key in ("versa_search_requirements", "search_requirements"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _compose_versa_additional_text(suggestion: Dict[str, Any]) -> str | None:
    additional = (suggestion.get("additional") or "").strip() if isinstance(suggestion, dict) else ""
    kql = (suggestion.get("kql") or "").strip() if isinstance(suggestion, dict) else ""
    parts = [p for p in [additional, (f"Purview KQL:\n{kql}" if kql else "")] if p]
    return "\n\n".join(parts) if parts else None


def _auto_create_versa_searches_for_new_case(
    *,
    db: Session,
    case: models.Case,
    actor: models.User,
    request: Request | None,
    requirements: str,
    custodians: list[models.Custodian],
) -> dict[str, Any]:
    req = (requirements or "").strip()
    if not req:
        return {"status": "skipped", "reason": "no_requirements", "created": 0}

    try:
        from .searches import _build_ai_search_suggestions  # local import to avoid heavy module coupling at import time
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_requests.py:versa_import", exc)
        return {"status": "error", "reason": "import_failed", "created": 0, "error": str(exc)}

    selected = [c for c in (custodians or []) if getattr(c, "id", None) is not None]
    if not selected:
        return {"status": "skipped", "reason": "no_custodians", "created": 0}

    existing_names = [
        n for (n,) in db.query(models.Search.name).filter(models.Search.case_id == case.id).all()
        if isinstance(n, str) and n.strip()
    ]

    max_suggestions = search_builder_max_suggestions()

    draft = {
        "custodian_ids": [int(getattr(c, "id", 0) or 0) for c in selected if int(getattr(c, "id", 0) or 0) > 0],
    }

    result = _build_ai_search_suggestions(
        case=case,
        draft=draft,
        objective=req,
        selected_custodians=selected,
        all_custodians=selected,
        existing_search_names=existing_names,
        max_suggestions=max_suggestions,
    )

    status = (result.get("status") or "").strip().lower()
    if status != "ok":
        return {
            "status": "error",
            "reason": "ai_error",
            "created": 0,
            "error": result.get("error"),
            "model": result.get("model"),
        }

    suggestions = [s for s in (result.get("suggestions") or []) if isinstance(s, dict)]
    if not suggestions:
        return {
            "status": "ok",
            "reason": "no_suggestions",
            "created": 0,
            "model": result.get("model"),
            "suggestions_count": 0,
        }

    next_idx = db.query(models.Search).filter(models.Search.case_id == case.id).count() + 1
    created = 0
    for suggestion in suggestions:
        data = dict(suggestion)
        data["name"] = f"{getattr(case, 'name', 'Case')}-Search {next_idx}"
        next_idx += 1
        data["additional"] = _compose_versa_additional_text(suggestion)
        db.add(_search_model(case.id, data))
        created += 1

    return {
        "status": "ok",
        "reason": "created",
        "created": created,
        "model": result.get("model"),
        "suggestions_count": len(suggestions),
    }


def _cleanup_file(path_value: Optional[str], allowed_dir: Path) -> None:
    return _case_request_module("case_request_storage")._cleanup_file(path_value, allowed_dir)


def _cleanup_consent_proof_file(stored_filename: Optional[str]) -> None:
    return _case_request_module("case_request_storage")._cleanup_consent_proof_file(stored_filename)


def _remove_attachment(record: models.CaseRequest, remove_consent_proofs: bool = True) -> None:
    return _case_request_module("case_request_storage")._remove_attachment(record, remove_consent_proofs=remove_consent_proofs)


def _custodian_lookup_identity_key(custodian: models.Custodian) -> Optional[tuple[str, str]]:
    return _lookup_refresh.custodian_lookup_identity_key(custodian)


def _custodian_lookup_snapshot(custodian: models.Custodian) -> tuple:
    return _lookup_refresh.custodian_lookup_snapshot(custodian)


def _persist_custodian_lookup_settings(summary: Dict[str, Any], *, mark_bootstrap_complete: bool = False) -> None:
    return _lookup_refresh.persist_custodian_lookup_settings(summary, mark_bootstrap_complete=mark_bootstrap_complete)


def run_full_custodian_lookup_update(
    db: Session,
    *,
    actor_id: Optional[int] = None,
    source: str = "manual",
    mark_bootstrap_complete: bool = False,
    request: Request = None,
) -> Dict[str, Any]:
    return _lookup_refresh.run_full_custodian_lookup_update(
        db,
        actor_id=actor_id,
        source=source,
        mark_bootstrap_complete=mark_bootstrap_complete,
        request=request,
        lookup_matches_for_identity_func=_lookup_matches_for_identity,
        pick_lookup_match=_pick_lookup_match,
        apply_match_to_custodian=_apply_person_lookup_match_to_custodian,
        apply_consent_defaults=_apply_consent_not_required_defaults,
    )


def _run_custodian_lookup_bootstrap_once() -> None:
    return _lookup_refresh.run_custodian_lookup_bootstrap_once(run_full_custodian_lookup_update)


def start_custodian_lookup_bootstrap() -> None:
    return _lookup_refresh.start_custodian_lookup_bootstrap(run_full_custodian_lookup_update)

def sync_case_request_attachment_bytes(limit: int = 200) -> None:
    return _case_request_module("case_request_storage").sync_case_request_attachment_bytes(limit=limit)


def _case_request_module(module_name: str):
    import importlib
    import importlib.util
    import sys

    full_name = f"{__package__}.{module_name}"
    try:
        return importlib.import_module(full_name)
    except ModuleNotFoundError:
        module_path = Path(__file__).with_name(f"{module_name}.py")
        spec = importlib.util.spec_from_file_location(full_name, module_path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = module
        spec.loader.exec_module(module)
        return module


def custodian_lookup(*args, **kwargs):
    return _case_request_module("case_request_lookup").custodian_lookup(*args, **kwargs)


def request_stats(*args, **kwargs):
    return _case_request_module("case_request_read").request_stats(*args, **kwargs)


def list_requests(*args, **kwargs):
    return _case_request_module("case_request_read").list_requests(*args, **kwargs)


def list_mine(*args, **kwargs):
    return _case_request_module("case_request_read").list_mine(*args, **kwargs)


def _normalize_request_type(*args, **kwargs):
    return _case_request_module("case_request_create")._normalize_request_type(*args, **kwargs)


async def create_case_request(*args, **kwargs):
    return await _case_request_module("case_request_create").create_case_request(*args, **kwargs)


def approve_case_request(*args, **kwargs):
    return _case_request_module("case_request_approval").approve_case_request(*args, **kwargs)


def get_case_request_progress(*args, **kwargs):
    return _case_request_module("case_request_review").get_case_request_progress(*args, **kwargs)


def decline_case_request(*args, **kwargs):
    return _case_request_module("case_request_review").decline_case_request(*args, **kwargs)

def _ensure_pending(record: models.CaseRequest) -> None:
    if record.status != "pending":
        raise HTTPException(status_code=400, detail="Request already processed")

def _parse_audit_details(value: Any) -> Any:
    if isinstance(value, (dict, list)) or value is None:
        return value
    text_val = str(value).strip()
    if (text_val.startswith("{") and text_val.endswith("}")) or (text_val.startswith("[") and text_val.endswith("]")):
        try:
            return json.loads(text_val)
        except Exception:
            return text_val
    return text_val


def _cleanup_old_pending_requests() -> None:
    return _case_request_module("case_request_cleanup").cleanup_old_pending_requests(
        pending_cleanup_days=case_request_pending_cleanup_days(),
        session_factory=SessionLocal,
        models=models,
        remove_attachment=_remove_attachment,
        log_event=log_event,
        debug_suppressed=_debug_suppressed,
    )


def start_case_request_cleanup() -> None:
    return _case_request_module("case_request_cleanup").start_case_request_cleanup(
        pending_cleanup_days=case_request_pending_cleanup_days(),
        pending_cleanup_interval_hours=case_request_pending_cleanup_interval_hours(),
        cleanup_func=_cleanup_old_pending_requests,
    )