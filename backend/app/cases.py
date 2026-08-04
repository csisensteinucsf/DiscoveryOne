import json
import logging
import os
import re
import threading
import time
from urllib.parse import urlparse
from datetime import date, datetime, timezone
from typing import Any, List, Optional, Tuple

import pyotp
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import case as sql_case, desc, func, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import (
    case_box_release,
    models,
    preservation_provider,
    schemas,
    ticket_provider,
)
from .audit import log_event
from .auth import current_user as get_current_user
from .case_closure import case_closure_default_nag_days
from .case_request_settings import hold_status_email_delay_seconds
from .database import get_db, SessionLocal
from .emailer import send_email
from .notifications import _app_base_url, _send_teams_notification, notify_case_requestor_case_event, notify_case_requestor_hold_status
from .permissions import (
    ensure_case_editable,
    ensure_case_visible,
    case_has_ticket_category,
    filter_ticket_entries_for_user,
    get_requestor_allowed_emails,
    get_requestor_visible_groups,
    get_visible_case_ids,
    requestor_case_visibility_filter,
    get_role,
    is_requestor,
    is_sys_admin,
    is_tech,
    tech_allowed_ticket_categories,
)
from .institution import is_organization_email, load_institution_settings
from .safe_log import debug_suppressed as _debug_suppressed
from .ticket_provider_labels import generic_external_ticket_label
from .ticket_workflow_catalog import (
    category_hold_fields,
    category_label,
    category_legacy_fields,
    matched_email_required_categories,
    workflow_lookup,
)
from .identity_review import apply_custodian_name_email_review
from .case_naming import _case_name_from_payload, _case_naming_mode, _extract_year_and_color_from_name
from .case_status_summary import _compute_case_status, _compute_case_status_map
from .case_requestors import (
    apply_case_requestors as _apply_case_requestors,
    derive_name_from_email as _derive_name_from_email,
    ensure_registration_invite as _ensure_registration_invite,
    normalize_requestor_email as _normalize_requestor_email,
    normalize_requestor_entries as _normalize_requestor_entries,
    user_display_name as _user_display_name,
)
from .case_request_tickets import (
    MAX_TICKET_LENGTH,
    MAX_TICKET_METADATA_LENGTH,
    _apply_request_holds,
    _clean_str,
    _first_ticket,
    _normalize_request_ticket_entries,
    _recover_request_ticket_entries_from_audit,
    _sync_legacy_request_tickets,
)

from .custodian_policy import (
    CONSENT_NOT_REQUIRED_REASON_CLAIMANT,
    CONSENT_NOT_REQUIRED_REASON_DEFAULT,
    CONSENT_NOT_REQUIRED_REASON_SEPARATED,
    NTP_NOT_REQUIRED_REASON_CLAIMANT,
    NTP_NOT_REQUIRED_REASON_DEFAULT,
    NTP_NOT_REQUIRED_REASON_NON_ORG,
    NTP_NOT_REQUIRED_REASON_SEPARATED,
    _apply_consent_not_required_defaults,
    _apply_ntp_not_required_defaults,
    _consent_not_required_auto_reason,
    _custodian_matches_claimant,
    _normalize_optional_text,
    _normalize_person_label,
    _ntp_not_required_auto_reason,
)



ADMIN_USERNAME = "admin"

# Legacy ticket fields still exist in the database, but workflow behavior comes
# from System > Ticket Workflows so universal deployments can define their own categories.
def _ticket_workflow_lookup(include_disabled: bool = True) -> dict[str, dict[str, Any]]:
    return workflow_lookup(include_disabled=include_disabled)


def servicenow_matched_email_required_categories() -> set[str]:
    return matched_email_required_categories()


def _ticket_category_hold_fields() -> dict[str, str]:
    return category_hold_fields()


def _ticket_category_legacy_fields() -> dict[str, str]:
    return category_legacy_fields()


def request_ticket_category_label(category: Optional[str]) -> str:
    return category_label(category)
NO_EMAIL_PLACEHOLDER = "NoEmail"
UNMATCHED_EMAIL_PLACEHOLDER = "UNMATCHED"


router = APIRouter(prefix="/api/cases", tags=["cases"])
logger = logging.getLogger(__name__)

FALLBACK_CUSTOMER_ID = ""

_preservation_poll_lock = threading.Lock()
# Keyed by (case_id, named_hold_id, delay_seconds_int) so polls for separate holds never cancel each other.
_preservation_poll_timers: dict[tuple[int, int, int], threading.Timer] = {}
_case_hold_email_lock = threading.Lock()
_case_hold_email_timers: dict[int, threading.Timer] = {}


def _schedule_preservation_status_poll(
    case_id: int,
    reason: str,
    delay_seconds: Optional[float] = None,
    case_hold_id: Optional[int] = None,
) -> None:
    if not preservation_provider.preservation_automation_ready():
        return
    delay = preservation_provider.status_poll_delay_seconds() if delay_seconds is None else delay_seconds
    if delay <= 0:
        return
    delay_key = int(delay)
    key = (case_id, int(case_hold_id or 0), delay_key)
    def _run() -> None:
        with _preservation_poll_lock:
            _preservation_poll_timers.pop(key, None)
        db = SessionLocal()
        try:
            logger.info("preservation_status_poll_start case_id=%s case_hold_id=%s reason=%s delay=%.1f", case_id, case_hold_id, reason, delay)
            preservation_provider.get_status(case_id=case_id, db=db, request=None, user=None, case_hold_id=case_hold_id)
            logger.info("preservation_status_poll_complete case_id=%s case_hold_id=%s reason=%s", case_id, case_hold_id, reason)
        except Exception as exc:
            logger.warning("preservation_status_poll_failed case_id=%s case_hold_id=%s reason=%s error=%s", case_id, case_hold_id, reason, exc)
        finally:
            try:
                db.close()
            except Exception as exc:
                _debug_suppressed("suppressed exception in cases.py:223", exc)
    with _preservation_poll_lock:
        existing = _preservation_poll_timers.get(key)
        if existing:
            try:
                existing.cancel()
            except Exception as exc:
                _debug_suppressed("suppressed exception in cases.py:230", exc)
        timer = threading.Timer(delay, _run)
        timer.daemon = True
        _preservation_poll_timers[key] = timer
        timer.start()


def _schedule_purview_status_poll(
    case_id: int,
    reason: str,
    delay_seconds: Optional[float] = None,
) -> None:
    """Compatibility alias for older provider-specific callers."""
    _schedule_preservation_status_poll(case_id, reason, delay_seconds)


def _schedule_case_requestor_hold_status_email(
    case_id: int,
    custodian_ids: list[int],
    *,
    reason: str,
    request: Optional[Request],
) -> None:
    delay = hold_status_email_delay_seconds()
    if delay <= 0:
        return
    if not custodian_ids:
        return

    def _run() -> None:
        with _case_hold_email_lock:
            _case_hold_email_timers.pop(case_id, None)
        db = SessionLocal()
        try:
            case = db.get(models.Case, case_id)
            if not case:
                return
            base_url = None
            try:
                base_url = _app_base_url(request)
            except Exception:
                base_url = None
            notify_case_requestor_hold_status(
                db,
                case,
                request=request,
                base_url=base_url,
                custodian_ids=custodian_ids,
                reason=reason,
            )
        except Exception as exc:
            logger.warning("case_requestor_hold_status_email_failed case_id=%s reason=%s error=%s", case_id, reason, exc)
        finally:
            try:
                db.close()
            except Exception as exc:
                _debug_suppressed("suppressed exception in cases.py:277", exc)

    with _case_hold_email_lock:
        existing = _case_hold_email_timers.get(case_id)
        if existing:
            try:
                existing.cancel()
            except Exception as exc:
                _debug_suppressed("suppressed exception in cases.py:285", exc)
        timer = threading.Timer(delay, _run)
        timer.daemon = True
        _case_hold_email_timers[case_id] = timer
        timer.start()


def _is_missing_or_unmatched_email(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    return not normalized or normalized in {
        NO_EMAIL_PLACEHOLDER.lower(),
        UNMATCHED_EMAIL_PLACEHOLDER.lower(),
    }


def _custodian_has_unmatched_ticket_email(custodian: models.Custodian | None) -> bool:
    if not custodian:
        return True
    return bool(getattr(custodian, "person_lookup_overridden", False)) or _is_missing_or_unmatched_email(
        getattr(custodian, "email", None)
    )


def _normalize_employee_id_digits(value: str | None) -> str:
    digits = "".join(ch for ch in (value or "").strip() if ch.isdigit())
    return digits.strip()


def _normalize_employee_id(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return re.sub(r"[\s-]+", "", text)


def _configured_ticket_default_customer_id() -> str:
    return (ticket_provider.default_customer_id() or FALLBACK_CUSTOMER_ID).strip()


def _ticket_customer_id_fallback(user: models.User | None = None) -> str:
    fallback = _configured_ticket_default_customer_id()
    if fallback:
        return fallback
    label = load_institution_settings().get("employee_id_label") or "Employee ID"
    ticket_label = generic_external_ticket_label()
    user_id = getattr(user, "id", None)
    logger.warning("Missing %s for user=%s and no %s default customer ID is configured", label, user_id, ticket_label)
    raise HTTPException(
        status_code=422,
        detail=f"{label} is required for {ticket_label} creation, or configure a default ticket customer ID in System > Integrations.",
    )


def _require_employee_id(user: models.User) -> str | None:
    if not user:
        return _ticket_customer_id_fallback(user)
    username = (getattr(user, "username", "") or "").strip().lower()
    role = get_role(user)
    if role in ("analyst", "sys_admin") and username != ADMIN_USERNAME:
        value = _normalize_employee_id(getattr(user, "employee_id", None))
        if not value:
            return _ticket_customer_id_fallback(user)
        return value
    value = _normalize_employee_id(getattr(user, "employee_id", None))
    if value:
        return value
    return _ticket_customer_id_fallback(user)



def _case_link(request: Request | None, case_id: int) -> Optional[str]:
    try:
        base = _app_base_url(request)
        return f"{base}/cases/{case_id}"
    except Exception:
        return None


def _custodian_needs_box_hold_release(cust: models.Custodian) -> bool:
    return case_box_release.custodian_needs_box_hold_release(cust)


def _case_has_box_hold_request(case: models.Case, entries: list[dict]) -> bool:
    return case_box_release.case_has_box_hold_request(case, entries)


def _has_box_hold_release_ticket(entries: list[dict]) -> bool:
    return case_box_release.has_box_hold_release_ticket(entries)


def _maybe_create_box_hold_release_ticket(
    db: Session,
    *,
    case: models.Case,
    actor: models.User,
    request: Request | None,
    source: str,
) -> Optional[dict]:
    return case_box_release.maybe_create_box_hold_release_ticket(
        db,
        case=case,
        actor=actor,
        request=request,
        source=source,
        require_customer_id=_require_employee_id,
        case_link=_case_link,
        normalize_request_ticket_entries=_normalize_request_ticket_entries,
        sync_legacy_request_tickets=_sync_legacy_request_tickets,
        apply_request_holds=_apply_request_holds,
        debug_suppressed=_debug_suppressed,
    )


def _case_read(
    case: models.Case,
    status: schemas.CaseStatus | None = None,
    user: models.User | None = None,
) -> schemas.CaseRead:
    """
    Build the API response for a case with derived fields (status, analyst name).
    """
    reqs: List[schemas.CaseRequestorEntry] = []
    try:
        requestor_rows = getattr(case, "requestors", []) or []
        requestor_rows = sorted(
            requestor_rows,
            key=lambda r: (
                0 if getattr(r, "is_primary", False) else 1,
                getattr(r, "created_at", None) or datetime.min,
                getattr(r, "id", 0),
            ),
        )
        for row in requestor_rows:
            reqs.append(
                schemas.CaseRequestorEntry(
                    id=getattr(row, "id", None),
                    user_id=getattr(row, "user_id", None),
                    email=getattr(row, "email", None),
                    requestor_group=getattr(row, "requestor_group", None),
                    is_primary=bool(getattr(row, "is_primary", False)),
                )
            )
    except Exception:
        reqs = []
    inc_number = (getattr(case, "servicenow_inc_number", None) or "").strip() or None
    inc_link = None
    if inc_number:
        inc_link = ticket_provider.ticket_link(
            ticket_number=inc_number,
            fallback="",
        ) or None
    result = schemas.CaseRead.from_orm(case).copy(
        update={
            "status": status,
            "analyst_name": _user_display_name(getattr(case, "analyst", None)),
            "is_ler_hr": bool(getattr(case, "is_ler_hr", False)),
            "servicenow_inc_number": inc_number,
            "servicenow_inc_link": inc_link,
            "is_private": bool(getattr(case, "is_private", False)),
            "closure_nag_days": getattr(case, "closure_nag_days", None),
            "requestors": reqs,
            "notes_internal_count": int(getattr(case, "notes_internal_count", 0) or 0),
            "notes_requestor_count": int(getattr(case, "notes_requestor_count", 0) or 0),
            "notes_ticket_count": int(getattr(case, "notes_ticket_count", 0) or 0),
            "consent_envelope_count": int(getattr(case, "consent_envelope_count", 0) or 0),
            "consent_proof_count": int(getattr(case, "consent_proof_count", 0) or 0),
            "is_active_case": bool(getattr(case, "is_active_case", False)),
        }
    )
    if user and is_tech(user):
        allowed = tech_allowed_ticket_categories(user)
        filtered_entries = filter_ticket_entries_for_user(getattr(case, "request_ticket_entries", []) or [], user)
        updates = {
            "request_ticket_entries": filtered_entries,
        }
        for category, field in _ticket_category_legacy_fields().items():
            if category not in allowed:
                updates[field] = None
        result = result.copy(update=updates)
    return result


def _active_note_preview(text: Any, limit: int = 180) -> Optional[str]:
    raw = str(text or "").strip()
    if not raw:
        return None
    compact = re.sub(r"<[^>]+>", " ", raw)
    compact = re.sub(r"\s+", " ", compact).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "..."


def _sync_case_documentation_counters(db: Session, case_id: int) -> None:
    try:
        case = db.get(models.Case, case_id)
        if case is None:
            return
        consent_count = (
            db.query(func.count(models.CaseConsent.id))
            .filter(models.CaseConsent.case_id == case_id)
            .scalar()
            or 0
        )
        proof_count = (
            db.query(func.count(models.CaseRequestConsentProof.id))
            .filter(models.CaseRequestConsentProof.case_id == case_id)
            .scalar()
            or 0
        )
        case.consent_envelope_count = int(consent_count or 0)
        case.consent_proof_count = int(proof_count or 0)
        db.add(case)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception as rollback_exc:
            _debug_suppressed("suppressed exception in cases.py:rollback_documentation_counter_sync", rollback_exc)
        _debug_suppressed("suppressed exception in cases.py:sync_case_documentation_counters", exc)


def _requestor_case_visibility_filter(user: models.User, db: Session):
    return requestor_case_visibility_filter(user, db)


def _repair_case_note_counters_if_empty(db: Session, case: models.Case) -> None:
    try:
        case_id = int(getattr(case, "id", 0) or 0)
        if case_id <= 0:
            return
        rows = (
            db.query(
                func.coalesce(models.CaseNote.audience, "internal").label("audience"),
                func.count(models.CaseNote.id).label("count"),
            )
            .filter(models.CaseNote.case_id == case_id)
            .group_by(func.coalesce(models.CaseNote.audience, "internal"))
            .all()
        )
        recalculated = {"internal": 0, "requestor": 0, "ticket": 0}
        for audience, count in rows:
            key = str(audience or "internal").strip().lower() or "internal"
            if key not in recalculated:
                continue
            try:
                recalculated[key] = int(count or 0)
            except Exception:
                recalculated[key] = 0
        current_internal = int(getattr(case, "notes_internal_count", 0) or 0)
        current_requestor = int(getattr(case, "notes_requestor_count", 0) or 0)
        current_ticket = int(getattr(case, "notes_ticket_count", 0) or 0)
        if (
            current_internal == recalculated["internal"]
            and current_requestor == recalculated["requestor"]
            and current_ticket == recalculated["ticket"]
        ):
            return
        case.notes_internal_count = recalculated["internal"]
        case.notes_requestor_count = recalculated["requestor"]
        case.notes_ticket_count = recalculated["ticket"]
        db.add(case)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception as rollback_exc:
            _debug_suppressed("suppressed exception in cases.py:rollback_repair_case_note_counters_if_empty", rollback_exc)
        _debug_suppressed("suppressed exception in cases.py:repair_case_note_counters_if_empty", exc)
# === Duplicate Email Guard (case-insensitive) ===
def _normalize_email(val: str) -> str:
    return (val or "").strip().lower()

def _is_organization_email(val: Optional[str]) -> bool:
    try:
        return bool(val) and is_organization_email(val)
    except Exception:
        return False


def _derive_employment_status_from_end_date(value: Optional[str]) -> Optional[str]:
    """
    Returns: current | separated | separated_90 | separated_365
    """
    if value in (None, "", 0):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        ts = datetime.fromisoformat(text).date()
    except Exception:
        try:
            ts = datetime.strptime(text[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    today = datetime.now(timezone.utc).date()
    if ts > today:
        return "current"
    days = (today - ts).days
    if days >= 365:
        return "separated_365"
    if days >= 90:
        return "separated_90"
    return "separated"

def _email_in_use(db: Session, case_id: int, email_norm: str, exclude_id: int = None) -> bool:
    if not email_norm:
        return False
    if email_norm == NO_EMAIL_PLACEHOLDER.lower():
        return False
    if email_norm == UNMATCHED_EMAIL_PLACEHOLDER.lower():
        return False
    q = db.query(models.Custodian).filter(
        models.Custodian.case_id == case_id,
        func.lower(models.Custodian.email) == email_norm,
    )
    if exclude_id:
        q = q.filter(models.Custodian.id != exclude_id)
    return db.query(q.exists()).scalar()
# === End Duplicate Email Guard ===


def _tech_allowed_hold_fields(user) -> set[str]:
    allowed = tech_allowed_ticket_categories(user)
    fields: set[str] = set()
    for category in allowed:
        hold_field = _ticket_category_hold_fields().get(category)
        if hold_field:
            fields.add(hold_field)
            fields.add(f"{hold_field}_pending")
            fields.add(f"{hold_field}_failed")
            fields.add(f"{hold_field}_released")
    return fields


def _normalize_hold_payload(data: dict, hold_fields: List[str]) -> None:
    for hold_key in hold_fields:
        pending_key = f"{hold_key}_pending"
        failed_key = f"{hold_key}_failed"
        released_key = f"{hold_key}_released"
        if data.get(released_key) is True:
            data[hold_key] = False
            data[pending_key] = False
            data[failed_key] = False
            continue
        if data.get(failed_key) is True:
            data[hold_key] = False
            data[pending_key] = False
            data[released_key] = False
            continue
        if data.get(pending_key) is True:
            data[hold_key] = True
            data[failed_key] = False
            data[released_key] = False
            continue
        if hold_key in data:
            if data.get(hold_key):
                data[failed_key] = False
                data[released_key] = False
            else:
                data[pending_key] = False
                data[failed_key] = False
                data[released_key] = False


@router.get("", response_model=List[schemas.CaseRead])
def list_cases(
    closed: Optional[bool] = None,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    q = db.query(models.Case).options(selectinload(models.Case.requestors))
    if closed is not None:
        q = q.filter(models.Case.closed == closed)
    visible_case_ids = get_visible_case_ids(_user, db)
    if visible_case_ids is not None:
        if not visible_case_ids:
            return []
        q = q.filter(models.Case.id.in_(visible_case_ids))
    items = q.order_by(desc(models.Case.created_at)).all()
    case_ids = []
    for case in items:
        try:
            cid = int(getattr(case, "id", 0) or 0)
        except Exception:
            cid = 0
        if cid > 0:
            case_ids.append(cid)
    status_map = _compute_case_status_map(db, case_ids)

    out: List[schemas.CaseRead] = []
    for case in items:
        try:
            cid = int(getattr(case, "id", 0) or 0)
        except Exception:
            cid = 0
        status = status_map.get(cid) or schemas.CaseStatus()
        out.append(_case_read(case, status=status, user=_user))
    return out


def _visible_case_ids_for_user(db: Session, user: models.User, candidate_ids: list[int]) -> list[int]:
    normalized_ids: list[int] = []
    for raw in candidate_ids or []:
        try:
            value = int(raw)
        except Exception:
            continue
        if value > 0:
            normalized_ids.append(value)
    if not normalized_ids:
        return []
    unique_ids = sorted(set(normalized_ids))

    scoped_ids = get_visible_case_ids(user, db)
    if scoped_ids is None:
        return unique_ids
    return sorted(set(unique_ids).intersection(scoped_ids))


@router.post("/stats")
def case_stats(
    payload: dict = Body(...),
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    raw_ids = payload.get("case_ids") if isinstance(payload, dict) else []
    case_ids = raw_ids if isinstance(raw_ids, list) else []
    visible_ids = _visible_case_ids_for_user(db, _user, case_ids)
    if not visible_ids:
        return {}

    cust_rows = (
        db.query(models.Custodian.case_id, func.count(models.Custodian.id))
        .filter(models.Custodian.case_id.in_(visible_ids))
        .group_by(models.Custodian.case_id)
        .all()
    )
    workflow_rows = (
        db.query(
            models.CaseHold.case_id,
            func.sum(sql_case((func.lower(func.coalesce(models.HoldCustodian.ntp_status, "")) == "sent", 1), else_=0)),
            func.sum(sql_case((func.lower(func.coalesce(models.HoldCustodian.ntp_status, "")) == "acknowledged", 1), else_=0)),
            func.sum(sql_case((func.lower(func.coalesce(models.HoldCustodian.consent_status, "")) == "sent", 1), else_=0)),
            func.sum(sql_case((func.lower(func.coalesce(models.HoldCustodian.consent_status, "")).in_(("received", "implied", "awoc")), 1), else_=0)),
        )
        .join(models.HoldCustodian, models.HoldCustodian.hold_id == models.CaseHold.id)
        .filter(models.CaseHold.case_id.in_(visible_ids), models.CaseHold.status == "active")
        .group_by(models.CaseHold.case_id)
        .all()
    )
    preservation_rows = (
        db.query(
            models.CaseHold.case_id,
            func.count(func.distinct(models.HoldCustodian.id)),
        )
        .join(models.HoldCustodian, models.HoldCustodian.hold_id == models.CaseHold.id)
        .join(
            models.HoldPreservationSource,
            models.HoldPreservationSource.hold_custodian_id == models.HoldCustodian.id,
        )
        .filter(
            models.CaseHold.case_id.in_(visible_ids),
            models.CaseHold.status == "active",
            models.HoldPreservationSource.status == "active",
        )
        .group_by(models.CaseHold.case_id)
        .all()
    )

    named_hold_rows = (
        db.query(
            models.CaseHold.case_id,
            func.count(models.CaseHold.id),
            func.sum(sql_case((models.CaseHold.status == "active", 1), else_=0)),
        )
        .filter(models.CaseHold.case_id.in_(visible_ids))
        .group_by(models.CaseHold.case_id)
        .all()
    )
    search_rows = (
        db.query(
            models.CaseHold.case_id,
            func.count(models.HoldSearch.id),
            func.sum(sql_case((models.HoldSearch.status_search == "performed", 1), else_=0)),
            func.sum(sql_case((models.HoldSearch.status_export == "performed", 1), else_=0)),
            func.sum(sql_case((models.HoldSearch.status_delivery == "performed", 1), else_=0)),
        )
        .join(models.HoldSearch, models.HoldSearch.hold_id == models.CaseHold.id)
        .filter(models.CaseHold.case_id.in_(visible_ids), models.CaseHold.status == "active")
        .group_by(models.CaseHold.case_id)
        .all()
    )
    out: dict[str, dict[str, int]] = {}
    for cid in visible_ids:
        out[str(cid)] = {
            "total": 0,
            "hold": 0,
            "namedHoldCount": 0,
            "namedHoldActiveCount": 0,
            "ntpSent": 0,
            "ntpAck": 0,
            "consentSent": 0,
            "consentReceived": 0,
            "searchTotal": 0,
            "search": 0,
            "export": 0,
            "delivered": 0,
        }

    for row in cust_rows:
        try:
            cid = int(row[0])
        except Exception:
            continue
        key = str(cid)
        if key in out:
            out[key]["total"] = int(row[1] or 0)

    for row in workflow_rows:
        try:
            cid = int(row[0])
        except Exception:
            continue
        key = str(cid)
        if key not in out:
            continue
        out[key]["ntpSent"] = int(row[1] or 0)
        out[key]["ntpAck"] = int(row[2] or 0)
        out[key]["consentSent"] = int(row[3] or 0)
        out[key]["consentReceived"] = int(row[4] or 0)

    for row in preservation_rows:
        try:
            cid = int(row[0])
        except Exception:
            continue
        key = str(cid)
        if key in out:
            out[key]["hold"] = int(row[1] or 0)
    for row in named_hold_rows:
        try:
            cid = int(row[0])
        except Exception:
            continue
        key = str(cid)
        if key in out:
            out[key]["namedHoldCount"] = int(row[1] or 0)
            out[key]["namedHoldActiveCount"] = int(row[2] or 0)
    for row in search_rows:
        try:
            cid = int(row[0])
        except Exception:
            continue
        key = str(cid)
        if key not in out:
            continue
        out[key]["searchTotal"] = int(row[1] or 0)
        out[key]["search"] = int(row[2] or 0)
        out[key]["export"] = int(row[3] or 0)
        out[key]["delivered"] = int(row[4] or 0)

    return out

@router.get("/{case_id}", response_model=schemas.CaseRead)
def get_case(
    case_id: int,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    obj = (
        db.query(models.Case)
        .options(selectinload(models.Case.requestors))
        .filter(models.Case.id == case_id)
        .first()
    )
    if obj is None:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(obj, _user, db)
    if any(getattr(obj, key, None) is None for key in ("notes_internal_count", "notes_requestor_count", "notes_ticket_count")):
        _repair_case_note_counters_if_empty(db, obj)
    status = _compute_case_status(db, case_id)
    return _case_read(obj, status=status, user=_user)


@router.get("/{case_id}/closure-readiness")
def get_case_closure_readiness(
    case_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    from .case_closure_readiness import case_closure_readiness

    return case_closure_readiness(db, case_id)


@router.post("", response_model=schemas.CaseRead, status_code=201)
def create_case(payload: schemas.CaseCreate, db: Session = Depends(get_db), request: Request = None, _user: models.User = Depends(get_current_user)):
    ensure_case_editable(_user)
    from .case_templates import apply_case_template

    payload, case_template = apply_case_template(db, payload)
    analyst_user = None
    if payload.analyst_id is not None:
        analyst_user = db.get(models.User, payload.analyst_id)
        if analyst_user is None:
            raise HTTPException(status_code=422, detail="Selected analyst not found")
        if analyst_user.username.lower() == ADMIN_USERNAME:
            raise HTTPException(status_code=422, detail="Admin cannot be assigned as analyst")

    # sanitize & parse start_date: "" -> None, "YYYY-MM-DD" -> date
    sd = payload.start_date
    if isinstance(sd, str):
        sd = sd.strip() or None
        if sd:
            try:
                    sd = datetime.strptime(sd, "%Y-%m-%d").date()
            except ValueError:
                    raise HTTPException(status_code=422, detail="start_date must be YYYY-MM-DD")

    case_name, case_color = _case_name_from_payload(db, payload)

    try:
        is_ler_hr = False
        servicenow_inc_number = None
        ler_representative = None
        requestor_entries = _normalize_requestor_entries(db, getattr(payload, "requestors", None), payload.requestor)
        requestor_email = requestor_entries[0]["email"] if requestor_entries else _normalize_requestor_email(payload.requestor)
        case = models.Case(
            name=case_name,
            legal_case_name=payload.legal_case_name,
            is_ler_hr=is_ler_hr,
            servicenow_inc_number=servicenow_inc_number,
            claimant=payload.claimant,
            ler_representative=ler_representative,
            internal_counsel=payload.internal_counsel,
            outside_counsel=payload.outside_counsel,
            matter_number=payload.matter_number,
            requestor=requestor_email,
            analyst_id=analyst_user.id if analyst_user else None,
            closed=bool(payload.closed) if payload.closed is not None else False,
            closed_at=datetime.now(timezone.utc) if bool(payload.closed) else None,
            is_private=bool(getattr(payload, "is_private", False)),
            color=case_color,
            description=payload.description,
            rubrik_restore_ticket=getattr(payload, "rubrik_restore_ticket", None),
            box_hold_ticket=getattr(payload, "box_hold_ticket", None),
            is_active_case=bool(getattr(payload, "is_active_case", False)),
            closure_nag_days=payload.closure_nag_days or case_closure_default_nag_days(),
            start_date=sd,
            case_template_id=case_template.id if case_template else None,
        )
        entries_payload = getattr(payload, "request_ticket_entries", None)
        if entries_payload is not None:
            normalized_entries = _normalize_request_ticket_entries(entries_payload, case) or []
            case.request_ticket_entries = normalized_entries
            _sync_legacy_request_tickets(case, normalized_entries)
            _apply_request_holds(case, normalized_entries)
        if not case_color and case_name and "-" in case_name and _case_naming_mode() == "color":
            _, parsed_color = _extract_year_and_color_from_name(case_name)
            if parsed_color:
                case.color = parsed_color

        if requestor_entries:
            _apply_case_requestors(case, requestor_entries)

        db.add(case)
        db.flush()
        db.commit()
        db.refresh(case)
        try:
            log_event(
                db,
                action="case_create",
                target_type="case",
                target_id=case.id,
                actor_id=_user.id,
                details={
                    "case_id": case.id,
                    "case_name": getattr(case, "name", None),
                    "requestor": case.requestor,
                    "analyst_id": case.analyst_id,
                    "case_template_id": case.case_template_id,
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in cases.py:1579", exc)
        return _case_read(case, status=_compute_case_status(db, case.id), user=_user)

    except IntegrityError:
        db.rollback()
        # in case a race slipped past the pre-check
        raise HTTPException(status_code=409, detail="Case name already exists")
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        msg = getattr(getattr(e, "orig", None), "pgerror", None) or str(e)
        raise HTTPException(status_code=400, detail=f"Unable to create case: {msg}")


@router.put("/{case_id}", response_model=schemas.CaseRead)
def update_case(
    case_id: int,
    payload: schemas.CaseUpdate,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    from .case_update import update_case_record

    return update_case_record(
        case_id=case_id,
        payload=payload,
        db=db,
        request=request,
        user=_user,
    )

def _case_purview_impl():
    import importlib

    return importlib.import_module(f"{__package__}.case_purview")


def create_case_in_purview(*args, **kwargs):
    return _case_purview_impl().create_case_in_purview(*args, **kwargs)


def _purview_email_norm(*args, **kwargs):
    return _case_purview_impl()._purview_email_norm(*args, **kwargs)


def _purview_name_norm(*args, **kwargs):
    return _case_purview_impl()._purview_name_norm(*args, **kwargs)


def _extract_email_candidates(*args, **kwargs):
    return _case_purview_impl()._extract_email_candidates(*args, **kwargs)


def _purview_hold_display_name(*args, **kwargs):
    return _case_purview_impl()._purview_hold_display_name(*args, **kwargs)


def _purview_hold_name_match(*args, **kwargs):
    return _case_purview_impl()._purview_hold_name_match(*args, **kwargs)


def _purview_sources_set(*args, **kwargs):
    return _case_purview_impl()._purview_sources_set(*args, **kwargs)


def _purview_sources_flags(*args, **kwargs):
    return _case_purview_impl()._purview_sources_flags(*args, **kwargs)


def _purview_sync_case_datasources(*args, **kwargs):
    return _case_purview_impl()._purview_sync_case_datasources(*args, **kwargs)


def _normalize_site_url(*args, **kwargs):
    return _case_purview_impl()._normalize_site_url(*args, **kwargs)


def _looks_like_url(*args, **kwargs):
    return _case_purview_impl()._looks_like_url(*args, **kwargs)


def _normalize_personal_key(*args, **kwargs):
    return _case_purview_impl()._normalize_personal_key(*args, **kwargs)


def _onedrive_personal_key(*args, **kwargs):
    return _case_purview_impl()._onedrive_personal_key(*args, **kwargs)


def _personal_key_from_url(*args, **kwargs):
    return _case_purview_impl()._personal_key_from_url(*args, **kwargs)


def _canonical_site_key(*args, **kwargs):
    return _case_purview_impl()._canonical_site_key(*args, **kwargs)


def _candidate_site_keys(*args, **kwargs):
    return _case_purview_impl()._candidate_site_keys(*args, **kwargs)


def _purview_site_key(*args, **kwargs):
    return _case_purview_impl()._purview_site_key(*args, **kwargs)


def get_purview_status(*args, **kwargs):
    return _case_purview_impl().get_purview_status(*args, **kwargs)


def apply_purview_holds(*args, **kwargs):
    return _case_purview_impl().apply_purview_holds(*args, **kwargs)


def release_purview_holds(*args, **kwargs):
    return _case_purview_impl().release_purview_holds(*args, **kwargs)


def _log_purview_failure(*args, **kwargs):
    return _case_purview_impl()._log_purview_failure(*args, **kwargs)

def _case_history_counts(db: Session, case_id: int) -> dict[str, int]:
    counts = {
        "custodians": db.query(models.Custodian).filter(models.Custodian.case_id == case_id).count(),
        "searches": db.query(models.Search).filter(models.Search.case_id == case_id).count(),
        "notes": db.query(models.CaseNote).filter(models.CaseNote.case_id == case_id).count(),
        "consents": db.query(models.CaseConsent).filter(models.CaseConsent.case_id == case_id).count(),
        "requests": db.query(models.CaseRequest).filter(models.CaseRequest.case_id == case_id).count(),
    }
    return {key: int(value or 0) for key, value in counts.items()}


@router.delete("/{case_id}")
def delete_case(
    case_id: int,
    override: bool = Query(default=False),
    override_reason: Optional[str] = Query(default=None, max_length=1000),
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    if not is_sys_admin(_user):
        raise HTTPException(status_code=403, detail="Only system administrators can permanently delete cases")

    history = _case_history_counts(db, case_id)
    has_significant_history = any(history.values())
    override_enabled = override if isinstance(override, bool) else False
    reason = override_reason.strip() if isinstance(override_reason, str) else ""
    if has_significant_history and not override_enabled:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "case_has_history",
                "message": "Close this case to retain its record. Permanent deletion requires an override reason.",
                "history": history,
            },
        )
    if has_significant_history and len(reason) < 10:
        raise HTTPException(
            status_code=422,
            detail="An override reason of at least 10 characters is required to delete a case with history",
        )

    case_name = getattr(case, "name", None)
    (
        db.query(models.CaseRequest)
        .filter(
            or_(
                models.CaseRequest.case_id == case_id,
                models.CaseRequest.case_name == case_name,
            )
        )
        .update({models.CaseRequest.case_deleted: True}, synchronize_session=False)
    )
    try:
        notify_case_requestor_case_event(case, event="deleted", request=request)
    except Exception as exc:
        _debug_suppressed("suppressed exception in cases.py:delete_notification", exc)
    db.delete(case)
    db.commit()
    log_event(
        db,
        action="case_delete",
        target_type="case",
        target_id=case_id,
        actor_id=_user.id,
        details={
            "case_id": case_id,
            "case_name": case_name,
            "history": history,
            "override": bool(has_significant_history),
            "override_reason": reason or None,
        },
        request=request,
    )
    return {"ok": True}

def _case_custodians_impl():
    import importlib

    _impl = importlib.import_module(f"{__package__}.case_custodians")
    for _name in (
        "ensure_case_visible",
        "ensure_case_editable",
        "log_event",
        "apply_custodian_name_email_review",
    ):
        if _name in globals():
            setattr(_impl, _name, globals()[_name])
    return _impl


def _extract_custom_preservation_payload(*args, **kwargs):
    return _case_custodians_impl()._extract_custom_preservation_payload(*args, **kwargs)


def _custom_preservation_key(*args, **kwargs):
    return _case_custodians_impl()._custom_preservation_key(*args, **kwargs)


def _sync_custom_preservation(*args, **kwargs):
    return _case_custodians_impl()._sync_custom_preservation(*args, **kwargs)


def _custom_preservation_for_custodian(*args, **kwargs):
    return _case_custodians_impl()._custom_preservation_for_custodian(*args, **kwargs)
def add_custodian(*args, **kwargs):
    return _case_custodians_impl().add_custodian(*args, **kwargs)


def bulk_import_custodians(*args, **kwargs):
    return _case_custodians_impl().bulk_import_custodians(*args, **kwargs)


def list_custodians(*args, **kwargs):
    return _case_custodians_impl().list_custodians(*args, **kwargs)


def update_custodian(*args, **kwargs):
    return _case_custodians_impl().update_custodian(*args, **kwargs)


def bulk_update_custodians(*args, **kwargs):
    return _case_custodians_impl().bulk_update_custodians(*args, **kwargs)


def delete_custodian(*args, **kwargs):
    return _case_custodians_impl().delete_custodian(*args, **kwargs)

def list_case_consents(*args, **kwargs):
    from .case_consents import list_case_consents as _impl
    return _impl(*args, **kwargs)




