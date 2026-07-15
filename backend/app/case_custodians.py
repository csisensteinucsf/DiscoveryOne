import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .audit import log_event
from .auth import current_user as get_current_user
from .database import get_db
from .permissions import ensure_case_editable, ensure_case_visible, is_requestor, is_tech
from .safe_log import debug_suppressed as _debug_suppressed
from .identity_review import apply_custodian_name_email_review
from .case_custodian_delete import delete_custodian_for_case
from . import cases as case_core
from .case_slack_holds import (
    sync_slack_hold_or_raise as _sync_slack_hold_or_raise,
    sync_slack_hold_transition as _sync_slack_hold_transition,
)
from .cases import (
    NO_EMAIL_PLACEHOLDER,
    UNMATCHED_EMAIL_PLACEHOLDER,
    _apply_consent_not_required_defaults,
    _apply_ntp_not_required_defaults,
    _custodian_matches_claimant,
    _derive_employment_status_from_end_date,
    _email_in_use,
    _is_organization_email,
    _normalize_email,
    _normalize_hold_payload,
    _purview_email_norm,
    _purview_name_norm,

    _tech_allowed_hold_fields,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])

def _load_case_for_custodian_write(case_id: int, db: Session, _user: models.User):
    case_query = (
        db.query(models.Case)
        .enable_eagerloads(False)
        .filter(models.Case.id == case_id)
    )
    try:
        case = case_query.with_for_update(of=models.Case).first()
    except Exception as lock_exc:
        _debug_suppressed("suppressed exception in cases.py:add_custodian_row_lock", lock_exc)
        try:
            db.rollback()
        except Exception as rollback_exc:
            _debug_suppressed("suppressed exception in cases.py:add_custodian_row_lock_rollback", rollback_exc)
        case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    ensure_case_editable(_user)
    return case


def _log_custodian_create_failure(
    db: Session,
    *,
    case_id: int,
    case: models.Case | None,
    actor_id: int | None,
    request: Request | None,
    custodian_name: str | None,
    custodian_email: str | None,
    error: str,
    status_code: int,
) -> None:
    try:
        log_event(
            db,
            action="custodian_create_failed",
            target_type="case",
            target_id=case_id,
            actor_id=actor_id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "custodian_name": custodian_name,
                "custodian_email": custodian_email,
                "error": error,
                "status_code": status_code,
            },
            request=request,
        )
    except Exception as log_exc:
        _debug_suppressed("suppressed exception in cases.py:custodian_create_failure_log", log_exc)


def _log_custodian_create_success(
    db: Session,
    *,
    case_id: int,
    case: models.Case | None,
    custodian: models.Custodian,
    actor_id: int | None,
    request: Request | None,
    name_email_review: Any,
) -> None:
    try:
        log_event(
            db,
            action="custodian_create",
            target_type="custodian",
            target_id=custodian.id,
            actor_id=actor_id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "custodian_id": custodian.id,
                "custodian_name": custodian.name,
                "custodian_email": custodian.email,
                "name_email_review_required": bool(getattr(custodian, "name_email_review_required", False)),
                "name_email_review_reason": getattr(custodian, "name_email_review_reason", None),
                "name_email_review_source": getattr(name_email_review, "source", None),
                "name_email_review_confidence": getattr(name_email_review, "confidence", None),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in cases.py:custodian_create_success_log", exc)


def _prepare_custodian_for_create(
    *,
    case_id: int,
    case: models.Case,
    data: dict[str, Any],
    use_ai_review: bool,
) -> tuple[models.Custodian, Optional[str], str, Any]:
    data = _normalize_person_lookup_aliases(dict(data or {}))
    _extract_custom_preservation_payload(data)
    email_raw = data.get("email")
    email_norm = _normalize_email(email_raw)
    trimmed_email = (email_raw or None)
    trimmed_email = trimmed_email.strip() if trimmed_email else None
    if not trimmed_email:
        trimmed_email = UNMATCHED_EMAIL_PLACEHOLDER
    custodian = models.Custodian(case_id=case_id, added_at=datetime.now(timezone.utc), **{**data, "email": trimmed_email})
    if not _is_organization_email(trimmed_email):
        custodian.ntp_status = "na"
        custodian.consent_status = "na"
    derived = _derive_employment_status_from_end_date(getattr(custodian, "employment_end_date", None))
    custodian.employment_status = derived
    emp_status = (getattr(custodian, "employment_status", None) or "").strip().lower()
    if emp_status.startswith("separated"):
        custodian.ntp_status = "na"
        custodian.consent_status = "na"
    if _custodian_matches_claimant(
        claimant=getattr(case, "claimant", None),
        name=getattr(custodian, "name", None),
        email=getattr(custodian, "email", None),
    ):
        custodian.ntp_status = "na"
        custodian.consent_status = "na"
    _apply_ntp_not_required_defaults(case, custodian)
    _apply_consent_not_required_defaults(case, custodian)
    try:
        name_email_review = apply_custodian_name_email_review(custodian, use_ai=use_ai_review)
    except Exception as exc:
        name_email_review = None
        _debug_suppressed("suppressed exception in cases.py:add_custodian_name_email_review", exc)
    return custodian, email_norm, trimmed_email, name_email_review


def _case_custodian_email_set(db: Session, case_id: int) -> set[str]:
    seen: set[str] = set()
    for row in db.query(models.Custodian.email).filter_by(case_id=case_id).all():
        raw = None
        try:
            raw = row[0]
        except Exception:
            raw = getattr(row, "email", None)
        email_norm = _normalize_email(raw)
        if email_norm:
            seen.add(email_norm)
    return seen


def _custom_preservation_key(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = re.sub(r"[^a-z0-9]+", "_", text_value)
    text_value = re.sub(r"_+", "_", text_value).strip("_")
    return text_value[:80]


def _extract_custom_preservation_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.pop("custom_preservation", None)
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = _custom_preservation_key(item.get("source_key") or item.get("key") or item.get("source_label") or item.get("label"))
        if not key or key in seen:
            continue
        seen.add(key)
        label = str(item.get("source_label") or item.get("label") or key.replace("_", " ").title()).strip()[:255]
        normalized.append(
            {
                "source_key": key,
                "source_label": label or key,
                "active": bool(item.get("active")),
                "pending": bool(item.get("pending")),
                "failed": bool(item.get("failed")),
                "released": bool(item.get("released")),
            }
        )
    return normalized


def _sync_custom_preservation(db: Session, custodian: models.Custodian, entries: list[dict[str, Any]]) -> None:
    if not entries:
        return
    existing = {
        row.source_key: row
        for row in db.query(models.CustodianPreservation)
        .filter(models.CustodianPreservation.custodian_id == custodian.id)
        .all()
    }
    for item in entries:
        key = item["source_key"]
        row = existing.get(key)
        if row is None:
            row = models.CustodianPreservation(custodian_id=custodian.id, source_key=key)
            db.add(row)
        row.source_label = item["source_label"]
        row.active = bool(item.get("active"))
        row.pending = bool(item.get("pending"))
        row.failed = bool(item.get("failed"))
        row.released = bool(item.get("released"))
        try:
            row.updated_at = datetime.now(timezone.utc)
        except Exception:
            pass


def _custom_preservation_for_custodian(db: Session, custodian_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(models.CustodianPreservation)
        .filter(models.CustodianPreservation.custodian_id == custodian_id)
        .order_by(models.CustodianPreservation.source_label.asc(), models.CustodianPreservation.source_key.asc())
        .all()
    )
    return [
        {
            "source_key": row.source_key,
            "source_label": row.source_label,
            "active": bool(row.active),
            "pending": bool(row.pending),
            "failed": bool(row.failed),
            "released": bool(row.released),
        }
        for row in rows
    ]


_PERSON_LOOKUP_ALIAS_TO_STORAGE = {
    "external_id": "employee_id",
    "employee_id": "employee_id",
    "person_id": "employee_id",
    "first_name": "person_first_name",
    "last_name": "person_last_name",
    "department_id": "person_department_id",
    "department": "person_department",
    "title": "person_title",
    "current_employee": "person_current_employee",
    "person_lookup_last_at": "person_lookup_last_at",
    "last_lookup_at": "person_lookup_last_at",
}
_PERSON_LOOKUP_NON_STORAGE_FIELDS = {"display_name", "middle_name", "source"}


def _has_person_lookup_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _normalize_person_lookup_aliases(data: dict[str, Any]) -> dict[str, Any]:
    for source, target in _PERSON_LOOKUP_ALIAS_TO_STORAGE.items():
        if source not in data:
            continue
        value = data.pop(source)
        if _has_person_lookup_value(value) and not _has_person_lookup_value(data.get(target)):
            data[target] = value
    for key in _PERSON_LOOKUP_NON_STORAGE_FIELDS:
        data.pop(key, None)
    return data


def _add_person_lookup_aliases(data: dict[str, Any], custodian: models.Custodian) -> dict[str, Any]:
    employee_id = getattr(custodian, "employee_id", None)
    data.update(
        {
            "external_id": employee_id,
            "employee_id": employee_id,
            "first_name": getattr(custodian, "person_first_name", None),
            "last_name": getattr(custodian, "person_last_name", None),
            "department_id": getattr(custodian, "person_department_id", None),
            "department": getattr(custodian, "person_department", None),
            "title": getattr(custodian, "person_title", None),
            "current_employee": getattr(custodian, "person_current_employee", None),
            "person_lookup_last_at": getattr(custodian, "person_lookup_last_at", None),
        }
    )
    return data


def _custodian_read(db: Session, custodian: models.Custodian) -> schemas.CustodianRead:
    data = schemas.CustodianRead.model_validate(custodian).model_dump()
    _add_person_lookup_aliases(data, custodian)
    data["custom_preservation"] = _custom_preservation_for_custodian(db, int(custodian.id))
    return schemas.CustodianRead(**data)


def _custodian_read_many(db: Session, custodians: list[models.Custodian]) -> list[schemas.CustodianRead]:
    return [_custodian_read(db, custodian) for custodian in custodians]


def _bulk_import_log_summary(
    db: Session,
    *,
    case_id: int,
    case: models.Case | None,
    actor_id: int | None,
    request: Request | None,
    requested_count: int,
    created_count: int,
    duplicate_count: int,
    failed_count: int,
    used_ai_review: bool,
) -> None:
    try:
        log_event(
            db,
            action="custodian_bulk_import",
            target_type="case",
            target_id=case_id,
            actor_id=actor_id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "requested_count": requested_count,
                "created_count": created_count,
                "duplicate_count": duplicate_count,
                "failed_count": failed_count,
                "used_ai_review": used_ai_review,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in cases.py:custodian_bulk_import_log", exc)


@router.post("/{case_id}/custodians", response_model=schemas.CustodianRead, status_code=201)
def add_custodian(
    case_id: int,
    payload: schemas.CustodianCreate,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = _load_case_for_custodian_write(case_id, db, _user)
    data = payload.dict()
    custom_preservation = _extract_custom_preservation_payload(data)
    email_raw = data.get("email")
    email_norm = _normalize_email(email_raw)
    trimmed_email = (email_raw or "").strip() or None
    if email_norm and _email_in_use(db, case_id, email_norm):
        _log_custodian_create_failure(
            db,
            case_id=case_id,
            case=case,
            actor_id=getattr(_user, "id", None),
            request=request,
            custodian_name=data.get("name"),
            custodian_email=trimmed_email,
            error="duplicate_email",
            status_code=409,
        )
        raise HTTPException(status_code=409, detail="duplicate_email")
    c, email_norm, trimmed_email_for_log, name_email_review = _prepare_custodian_for_create(
        case_id=case_id,
        case=case,
        data=data,
        use_ai_review=True,
    )
    try:
        db.add(c)
        db.flush()
        _sync_custom_preservation(db, c, custom_preservation)
        if bool(getattr(c, "holds_slack", False)):
            _sync_slack_hold_transition(
                case,
                c,
                before_holds_slack=False,
                before_email=None,
                db=db,
                actor_id=_user.id,
                request=request,
                source="custodian_create",
            )
        db.commit()
        db.refresh(c)
    except IntegrityError as exc:
        db.rollback()
        if email_norm and _email_in_use(db, case_id, email_norm):
            _log_custodian_create_failure(
                db,
                case_id=case_id,
                case=case,
                actor_id=getattr(_user, "id", None),
                request=request,
                custodian_name=data.get("name"),
                custodian_email=trimmed_email_for_log,
                error="duplicate_email",
                status_code=409,
            )
            raise HTTPException(status_code=409, detail="duplicate_email")
        _log_custodian_create_failure(
            db,
            case_id=case_id,
            case=case,
            actor_id=getattr(_user, "id", None),
            request=request,
            custodian_name=data.get("name"),
            custodian_email=trimmed_email_for_log,
            error="integrity_error",
            status_code=500,
        )
        logger.error("Failed to add custodian to case %s: %s", case_id, exc)
        raise HTTPException(status_code=500, detail="Unable to add custodian")
    except Exception as exc:
        db.rollback()
        status_code = int(getattr(exc, "status_code", 500) or 500)
        detail_value = getattr(exc, "detail", None)
        if isinstance(detail_value, (dict, list)):
            detail_text = json.dumps(detail_value)
        elif detail_value is not None:
            detail_text = str(detail_value)
        else:
            detail_text = str(exc)
        _log_custodian_create_failure(
            db,
            case_id=case_id,
            case=case,
            actor_id=getattr(_user, "id", None),
            request=request,
            custodian_name=data.get("name"),
            custodian_email=trimmed_email_for_log,
            error=detail_text,
            status_code=status_code,
        )
        logger.error("Failed to add custodian to case %s: %s", case_id, exc)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail="Unable to add custodian")
    _log_custodian_create_success(
        db,
        case_id=case_id,
        case=case,
        custodian=c,
        actor_id=getattr(_user, "id", None),
        request=request,
        name_email_review=name_email_review,
    )
    if getattr(c, "added_at", None) is None:
        setattr(c, "added_at", getattr(c, "created_at", None))
    return _custodian_read(db, c)


@router.post("/{case_id}/custodians/import", response_model=schemas.CustodianBulkCreateResponse)
def bulk_import_custodians(
    case_id: int,
    payload: schemas.CustodianBulkCreateRequest,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    from .case_custodian_bulk_import import bulk_import_custodians_for_case

    return bulk_import_custodians_for_case(
        case_id=case_id,
        payload=payload,
        db=db,
        request=request,
        user=_user,
    )

@router.get("/{case_id}/custodians", response_model=List[schemas.CustodianRead])
def list_custodians(
    case_id: int,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    custodians = db.query(models.Custodian).filter_by(case_id=case_id).all()
    return _custodian_read_many(db, custodians)

CUSTODIAN_REQUESTOR_UPDATE_FIELDS = {"ntp_status", "ntp_not_required_reason", "consent_status", "consent_not_required_reason"}
CUSTODIAN_IDENTITY_REVIEW_TRIGGER_FIELDS = {"name", "email", "first_name", "last_name", "person_first_name", "person_last_name"}
CUSTODIAN_AUDIT_FIELDS = [
    "name",
    "email",
    "notes",
    "holds_email",
    "holds_onedrive",
    "holds_gdrive",
    "holds_box",
    "holds_slack",
    "holds_rubrik_restore",
    "holds_email_pending",
    "holds_onedrive_pending",
    "holds_gdrive_pending",
    "holds_box_pending",
    "holds_slack_pending",
    "holds_rubrik_restore_pending",
    "holds_email_failed",
    "holds_onedrive_failed",
    "holds_gdrive_failed",
    "holds_box_failed",
    "holds_slack_failed",
    "holds_rubrik_restore_failed",
    "holds_email_released",
    "holds_onedrive_released",
    "holds_gdrive_released",
    "holds_box_released",
    "holds_slack_released",
    "holds_rubrik_restore_released",
    "ntp_status",
    "ntp_not_required_reason",
    "consent_status",
    "consent_not_required_reason",
    "search_done",
    "export_done",
    "delivered_done",
    "employment_end_date",
    "employee_id",
    "person_first_name",
    "person_last_name",
    "person_department_id",
    "person_department",
    "person_title",
    "person_current_employee",
    "person_lookup_last_at",
    "name_email_review_required",
    "name_email_review_reason",
    "name_email_review_last_checked_at",
]


def _custodian_update_error_detail(exc: Exception) -> str:
    detail_value = getattr(exc, "detail", None)
    if isinstance(detail_value, (dict, list)):
        return json.dumps(detail_value)
    if detail_value is not None:
        return str(detail_value)
    return str(exc)



def _should_run_name_email_review_for_update(custodian: models.Custodian, data: dict[str, Any]) -> bool:
    for field in CUSTODIAN_IDENTITY_REVIEW_TRIGGER_FIELDS:
        if field not in data:
            continue
        before = getattr(custodian, field, None)
        after = data.get(field)
        if field == "email":
            before = _normalize_email(before)
            after = _normalize_email(after)
        if before != after:
            return True
    return False



def _apply_custodian_update_payload(
    *,
    db: Session,
    case_id: int,
    case: models.Case,
    custodian: models.Custodian,
    data: dict[str, Any],
    actor_id: int | None,
    request: Request | None,
    source: str,
    use_ai_review: bool,
) -> Any:
    hold_fields = (
        "holds_email",
        "holds_onedrive",
        "holds_gdrive",
        "holds_box",
        "holds_slack",
        "holds_rubrik_restore",
    )
    payload = _normalize_person_lookup_aliases(dict(data or {}))
    custom_preservation = _extract_custom_preservation_payload(payload)
    _before_holds_slack = bool(getattr(custodian, "holds_slack", False))
    _before_email = (getattr(custodian, "email", None) or "").strip()
    _normalize_hold_payload(payload, list(hold_fields))
    if "email" in payload:
        email_norm = _normalize_email(payload.get("email"))
        if email_norm and _email_in_use(db, case_id, email_norm, exclude_id=getattr(custodian, "id", None)):
            raise HTTPException(status_code=409, detail="duplicate_email")
        trimmed_email = (payload.get("email") or None)
        trimmed_email = trimmed_email.strip() if trimmed_email else None
        if not trimmed_email:
            trimmed_email = UNMATCHED_EMAIL_PLACEHOLDER
        payload["email"] = trimmed_email
    run_name_email_review = _should_run_name_email_review_for_update(custodian, payload)
    for key, value in payload.items():
        setattr(custodian, key, value)
    _sync_custom_preservation(db, custodian, custom_preservation)
    _sync_slack_hold_transition(
        case,
        custodian,
        before_holds_slack=_before_holds_slack,
        before_email=_before_email,
        db=db,
        actor_id=actor_id,
        request=request,
        source=source,
    )
    if "employment_end_date" in payload:
        custodian.employment_status = _derive_employment_status_from_end_date(getattr(custodian, "employment_end_date", None))
    email_norm_after = _normalize_email(getattr(custodian, "email", None))
    if not email_norm_after or email_norm_after in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        custodian.email = UNMATCHED_EMAIL_PLACEHOLDER
    if not _is_organization_email(getattr(custodian, "email", None)):
        custodian.ntp_status = "na"
        custodian.consent_status = "na"
    emp_status = (getattr(custodian, "employment_status", None) or "").strip().lower()
    if emp_status.startswith("separated"):
        custodian.ntp_status = "na"
        custodian.consent_status = "na"
    _apply_ntp_not_required_defaults(case, custodian)
    _apply_consent_not_required_defaults(case, custodian)
    review_result = None
    if run_name_email_review:
        review_result = apply_custodian_name_email_review(custodian, use_ai=use_ai_review)
    db.add(custodian)
    db.add(case)
    return review_result



def _log_custodian_update_event(
    db: Session,
    *,
    case_id: int,
    case: models.Case | None,
    custodian: models.Custodian,
    actor_id: int | None,
    request: Request | None,
    changes: dict[str, Any],
    review_result: Any,
) -> None:
    if not changes:
        return
    details = {
        "case_id": case_id,
        "case_name": getattr(case, "name", None) if case else None,
        "custodian_id": getattr(custodian, "id", None),
        "custodian_name": getattr(custodian, "name", None),
        "custodian_email": getattr(custodian, "email", None),
        "changes": changes,
    }
    if review_result is not None:
        details["name_email_review"] = {
            "required": bool(getattr(custodian, "name_email_review_required", False)),
            "reason": getattr(custodian, "name_email_review_reason", None),
            "source": getattr(review_result, "source", None),
            "confidence": getattr(review_result, "confidence", None),
        }
    try:
        log_event(
            db,
            action="custodian_update",
            target_type="custodian",
            target_id=getattr(custodian, "id", None),
            actor_id=actor_id,
            details=details,
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in cases.py:custodian_update_log", exc)



def _bulk_custodian_update_entries(payload: schemas.CustodianBulkUpdateRequest) -> list[tuple[int, dict[str, Any]]]:
    entries: list[tuple[int, dict[str, Any]]] = []
    if payload.updates:
        for item in payload.updates:
            patch = item.patch.dict(exclude_unset=True)
            if patch:
                entries.append((int(item.id), patch))
    elif payload.ids and payload.patch is not None:
        patch = payload.patch.dict(exclude_unset=True)
        if patch:
            for raw_id in payload.ids:
                entries.append((int(raw_id), dict(patch)))
    return entries


@router.put("/{case_id}/custodians/{custodian_id}", response_model=schemas.CustodianRead)
def update_custodian(
    case_id: int,
    custodian_id: int,
    payload: schemas.CustodianUpdate,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    c = db.query(models.Custodian).filter_by(id=custodian_id, case_id=case_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Custodian not found")
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    data = payload.dict(exclude_unset=True)
    if is_tech(_user):
        allowed_fields = _tech_allowed_hold_fields(_user)
        if not allowed_fields:
            raise HTTPException(status_code=403, detail="Tech accounts must belong to a ticket group")
        if not data:
            raise HTTPException(status_code=400, detail="Hold updates are required")
        invalid = [key for key in data.keys() if key not in allowed_fields]
        if invalid:
            raise HTTPException(status_code=403, detail="Tech accounts can only update assigned hold types")
        audited_fields = sorted(allowed_fields)
        use_ai_review = False
    elif is_requestor(_user):
        if not data:
            raise HTTPException(status_code=400, detail="NTP or consent updates are required")
        invalid = [key for key in data.keys() if key not in CUSTODIAN_REQUESTOR_UPDATE_FIELDS]
        if invalid:
            raise HTTPException(status_code=403, detail="Requestor accounts can only update NTP and consent statuses")
        audited_fields = list(CUSTODIAN_AUDIT_FIELDS)
        use_ai_review = False
    else:
        ensure_case_editable(_user)
        audited_fields = list(CUSTODIAN_AUDIT_FIELDS)
        use_ai_review = True
    before = {field: getattr(c, field, None) for field in audited_fields}
    review_result = _apply_custodian_update_payload(
        db=db,
        case_id=case_id,
        case=case,
        custodian=c,
        data=data,
        actor_id=getattr(_user, "id", None),
        request=request,
        source="custodian_update",
        use_ai_review=use_ai_review,
    )
    after = {field: getattr(c, field, None) for field in audited_fields}
    changes = {
        field: {"old": before.get(field), "new": after.get(field)}
        for field in audited_fields
        if before.get(field) != after.get(field)
    }
    _log_custodian_update_event(
        db,
        case_id=case_id,
        case=case,
        custodian=c,
        actor_id=getattr(_user, "id", None),
        request=request,
        changes=changes,
        review_result=review_result,
    )
    db.commit()
    db.refresh(c)
    return _custodian_read(db, c)


@router.put("/{case_id}/custodians", response_model=schemas.CustodianBulkUpdateResponse)
def bulk_update_custodians(
    case_id: int,
    payload: schemas.CustodianBulkUpdateRequest,
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    entries = _bulk_custodian_update_entries(payload)
    if not entries:
        raise HTTPException(status_code=400, detail="Bulk custodian updates are required")
    ids = [cid for cid, _patch in entries]
    unique_ids = []
    seen_ids = set()
    for cid in ids:
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        unique_ids.append(cid)
    rows = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id, models.Custodian.id.in_(unique_ids))
        .all()
    )
    by_id = {int(getattr(row, "id", 0)): row for row in rows}
    missing = [cid for cid in unique_ids if cid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Custodian not found: {missing[0]}")
    if is_tech(_user):
        allowed_fields = _tech_allowed_hold_fields(_user)
        if not allowed_fields:
            raise HTTPException(status_code=403, detail="Tech accounts must belong to a ticket group")
        use_ai_review = False
    elif is_requestor(_user):
        use_ai_review = False
    else:
        ensure_case_editable(_user)
        allowed_fields = None
        use_ai_review = True
    changed_rows: list[tuple[models.Custodian, dict[str, Any], Any]] = []
    try:
        for cid, data in entries:
            custodian = by_id[cid]
            if is_tech(_user):
                invalid = [key for key in data.keys() if key not in allowed_fields]
                if invalid:
                    raise HTTPException(status_code=403, detail="Tech accounts can only update assigned hold types")
                audited_fields = sorted(allowed_fields)
            elif is_requestor(_user):
                invalid = [key for key in data.keys() if key not in CUSTODIAN_REQUESTOR_UPDATE_FIELDS]
                if invalid:
                    raise HTTPException(status_code=403, detail="Requestor accounts can only update NTP and consent statuses")
                audited_fields = list(CUSTODIAN_AUDIT_FIELDS)
            else:
                audited_fields = list(CUSTODIAN_AUDIT_FIELDS)
            before = {field: getattr(custodian, field, None) for field in audited_fields}
            review_result = _apply_custodian_update_payload(
                db=db,
                case_id=case_id,
                case=case,
                custodian=custodian,
                data=data,
                actor_id=getattr(_user, "id", None),
                request=request,
                source="custodian_bulk_update",
                use_ai_review=use_ai_review,
            )
            after = {field: getattr(custodian, field, None) for field in audited_fields}
            changes = {
                field: {"old": before.get(field), "new": after.get(field)}
                for field in audited_fields
                if before.get(field) != after.get(field)
            }
            changed_rows.append((custodian, changes, review_result))
        for custodian, changes, review_result in changed_rows:
            _log_custodian_update_event(
                db,
                case_id=case_id,
                case=case,
                custodian=custodian,
                actor_id=getattr(_user, "id", None),
                request=request,
                changes=changes,
                review_result=review_result,
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    updated: list[models.Custodian] = []
    for cid in unique_ids:
        custodian = by_id[cid]
        db.refresh(custodian)
        updated.append(custodian)
    return schemas.CustodianBulkUpdateResponse(
        updated=_custodian_read_many(db, updated),
        updated_count=len(updated),
        errors=[],
    )


@router.delete("/{case_id}/custodians/{custodian_id}")
def delete_custodian(
    case_id: int,
    custodian_id: int,
    release_holds: bool = Query(False),
    release_ntp: bool = Query(False),
    close_searches: bool = Query(False),
    approval_note: Optional[str] = Query(None),
    db: Session = Depends(get_db), request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    return delete_custodian_for_case(
        case_id=case_id,
        custodian_id=custodian_id,
        release_holds=release_holds,
        release_ntp=release_ntp,
        close_searches=close_searches,
        approval_note=approval_note,
        db=db,
        request=request,
        _user=_user,
    )