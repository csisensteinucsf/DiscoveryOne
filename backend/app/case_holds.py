from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload

from . import models, preservation_provider, schemas
from .audit import log_event
from .auth import current_user as get_current_user
from .case_source_holds import sync_hold_or_raise
from .database import get_db
from .hold_source_provider import hold_source_automation_ready
from .hold_workflows import (
    set_membership_consent_status,
    set_membership_ntp_status,
    set_membership_preservation_status,
)
from .permissions import ensure_case_editable, ensure_case_visible
from .preservation_catalog import configured_hold_catalog, source_key


router = APIRouter(prefix="/api/cases/{case_id}/holds", tags=["case-holds"])

HoldStatus = Literal["active", "released", "closed"]
PreservationStatus = Literal["not_started", "pending", "active", "failed", "released"]


class CaseHoldCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    ntp_template_name: Optional[str] = Field(default=None, max_length=255)
    preservation_template_name: Optional[str] = Field(default=None, max_length=255)


class CaseHoldUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    status: Optional[HoldStatus] = None
    ntp_template_name: Optional[str] = Field(default=None, max_length=255)
    preservation_template_name: Optional[str] = Field(default=None, max_length=255)


class HoldCustodianAssignment(BaseModel):
    custodian_ids: list[int] = Field(default_factory=list)


class HoldSearchAssignment(BaseModel):
    search_ids: list[int] = Field(default_factory=list)


class HoldPreservationUpdate(BaseModel):
    status: PreservationStatus
    provider_reference: Optional[str] = Field(default=None, max_length=512)
    last_error: Optional[str] = Field(default=None, max_length=4000)


class HoldPreservationAutomation(BaseModel):
    enabled: bool = True


class HoldMemberWorkflowUpdate(BaseModel):
    ntp_status: Optional[str] = Field(default=None, max_length=32)
    ntp_template_name: Optional[str] = Field(default=None, max_length=255)
    ntp_not_required_reason: Optional[str] = Field(default=None, max_length=4000)
    consent_status: Optional[str] = Field(default=None, max_length=32)
    consent_not_required_reason: Optional[str] = Field(default=None, max_length=4000)


def _case_for_user(db: Session, case_id: int, user: models.User, *, editable: bool = False) -> models.Case:
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, user, db)
    if editable:
        ensure_case_editable(user)
    return case


def _hold_for_case(db: Session, case_id: int, hold_id: int) -> models.CaseHold:
    hold = (
        db.query(models.CaseHold)
        .options(
            selectinload(models.CaseHold.custodian_memberships)
            .selectinload(models.HoldCustodian.custodian),
            selectinload(models.CaseHold.custodian_memberships)
            .selectinload(models.HoldCustodian.preservation_sources),
            selectinload(models.CaseHold.search_memberships)
            .selectinload(models.HoldSearch.search),
        )
        .filter(models.CaseHold.id == hold_id, models.CaseHold.case_id == case_id)
        .first()
    )
    if not hold:
        raise HTTPException(status_code=404, detail="Hold not found")
    return hold


def _next_hold_name(existing_names: list[str]) -> str:
    used = {str(name or "").strip().lower() for name in existing_names}
    index = 0
    while True:
        if index < 26:
            suffix = chr(ord("A") + index)
        else:
            suffix = str(index + 1)
        candidate = "Hold " + suffix
        if candidate.lower() not in used:
            return candidate
        index += 1


def _primary_provider_source(key: str) -> str | None:
    return {"email": "mailbox", "onedrive": "site"}.get(source_key(key))


def _source_automation_ready(key: str) -> bool:
    normalized = source_key(key)
    if _primary_provider_source(normalized) and preservation_provider.preservation_automation_ready():
        return True
    return hold_source_automation_ready(normalized)


def _legacy_source_status(custodian: models.Custodian, field: Optional[str]) -> str:
    if not field:
        return "not_started"
    if bool(getattr(custodian, field + "_failed", False)):
        return "failed"
    if bool(getattr(custodian, field + "_pending", False)):
        return "pending"
    if bool(getattr(custodian, field, False)):
        return "active"
    if bool(getattr(custodian, field + "_released", False)):
        return "released"
    return "not_started"


def _source_rows_for_custodian(custodian: models.Custodian) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    custom_by_key = {
        source_key(getattr(item, "source_key", "")): item
        for item in (getattr(custodian, "custom_preservation", None) or [])
    }
    for key, field, label in configured_hold_catalog(enabled_only=True):
        normalized = source_key(key)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if field:
            status = _legacy_source_status(custodian, field)
        else:
            custom = custom_by_key.get(normalized)
            if custom is None:
                status = "not_started"
            elif bool(getattr(custom, "failed", False)):
                status = "failed"
            elif bool(getattr(custom, "pending", False)):
                status = "pending"
            elif bool(getattr(custom, "active", False)):
                status = "active"
            elif bool(getattr(custom, "released", False)):
                status = "released"
            else:
                status = "not_started"
        rows.append((normalized, label or normalized, status))
    return rows


def _create_membership(
    db: Session,
    hold: models.CaseHold,
    custodian: models.Custodian,
) -> models.HoldCustodian:
    existing = (
        db.query(models.HoldCustodian)
        .filter(
            models.HoldCustodian.hold_id == hold.id,
            models.HoldCustodian.custodian_id == custodian.id,
        )
        .first()
    )
    if existing:
        return existing

    membership = models.HoldCustodian(
        hold_id=hold.id,
        custodian_id=custodian.id,
        ntp_status=getattr(custodian, "ntp_status", None) or "not sent",
        ntp_sent_at=getattr(custodian, "ntp_sent_at", None),
        ntp_acknowledged_at=getattr(custodian, "ntp_acknowledged_at", None),
        ntp_template_name=getattr(custodian, "ntp_template_name", None),
        ntp_not_required_reason=getattr(custodian, "ntp_not_required_reason", None),
        consent_status=getattr(custodian, "consent_status", None) or "not sent",
        consent_not_required_reason=getattr(custodian, "consent_not_required_reason", None),
    )
    db.add(membership)
    db.flush()

    for key, label, status in _source_rows_for_custodian(custodian):
        db.add(
            models.HoldPreservationSource(
                hold_custodian_id=membership.id,
                source_key=key,
                source_label=label,
                status=status,
            )
        )
    return membership


def ensure_default_hold(
    db: Session,
    case: models.Case,
    *,
    assign_existing: bool = True,
) -> models.CaseHold:
    """Return the first existing hold without creating holds or memberships."""
    hold = (
        db.query(models.CaseHold)
        .filter(models.CaseHold.case_id == case.id)
        .order_by(models.CaseHold.sort_order.asc(), models.CaseHold.id.asc())
        .first()
    )
    if hold is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "hold_required",
                "message": "Create a Hold and assign the applicable custodians before starting this workflow.",
            },
        )
    return hold


def assign_custodians_to_hold(
    db: Session,
    *,
    case_id: int,
    hold_id: int,
    custodian_ids: list[int],
) -> int:
    hold = _hold_for_case(db, case_id, hold_id)
    normalized_ids = sorted({int(value) for value in custodian_ids if int(value) > 0})
    if not normalized_ids:
        return 0
    custodians = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id, models.Custodian.id.in_(normalized_ids))
        .all()
    )
    found_ids = {custodian.id for custodian in custodians}
    missing = sorted(set(normalized_ids) - found_ids)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Custodian does not belong to this case", "custodian_ids": missing})
    created = 0
    for custodian in custodians:
        before = (
            db.query(models.HoldCustodian.id)
            .filter(
                models.HoldCustodian.hold_id == hold.id,
                models.HoldCustodian.custodian_id == custodian.id,
            )
            .first()
        )
        _create_membership(db, hold, custodian)
        if before is None:
            created += 1
    return created


def _serialize_hold(hold: models.CaseHold) -> dict:
    members = []
    source_totals: dict[str, dict[str, int | str]] = {}
    ntp_counts: dict[str, int] = {}
    consent_counts: dict[str, int] = {}

    for membership in hold.custodian_memberships or []:
        custodian = membership.custodian
        sources = []
        for source in membership.preservation_sources or []:
            item = {
                "id": source.id,
                "source_key": source.source_key,
                "source_label": source.source_label,
                "status": source.status,
                "automation_ready": _source_automation_ready(source.source_key),
                "provider_reference": source.provider_reference,
                "last_error": source.last_error,
                "updated_at": source.updated_at,
            }
            sources.append(item)
            aggregate = source_totals.setdefault(
                source.source_key,
                {"source_key": source.source_key, "source_label": source.source_label},
            )
            aggregate[source.status] = int(aggregate.get(source.status, 0)) + 1

        ntp_status = membership.ntp_status or "not sent"
        consent_status = membership.consent_status or "not sent"
        ntp_counts[ntp_status] = ntp_counts.get(ntp_status, 0) + 1
        consent_counts[consent_status] = consent_counts.get(consent_status, 0) + 1
        members.append(
            {
                "membership_id": membership.id,
                "custodian_id": membership.custodian_id,
                "name": getattr(custodian, "name", None),
                "email": getattr(custodian, "email", None),
                "employee_id": getattr(custodian, "employee_id", None),
                "department": getattr(custodian, "person_department", None),
                "title": getattr(custodian, "person_title", None),
                "ntp_status": ntp_status,
                "ntp_sent_at": membership.ntp_sent_at,
                "ntp_acknowledged_at": membership.ntp_acknowledged_at,
                "ntp_template_name": membership.ntp_template_name,
                "ntp_not_required_reason": membership.ntp_not_required_reason,
                "consent_status": consent_status,
                "consent_not_required_reason": membership.consent_not_required_reason,
                "preservation_sources": sorted(sources, key=lambda item: item["source_label"].lower()),
            }
        )

    search_counts: dict[str, dict[str, int]] = {
        "search": {},
        "export": {},
        "delivery": {},
    }
    search_rows = []
    for membership in hold.search_memberships or []:
        search = membership.search
        if search is None:
            continue
        stage_values = {
            "search": membership.status_search or "not performed",
            "export": membership.status_export or "not performed",
            "delivery": membership.status_delivery or "not performed",
        }
        for stage, status in stage_values.items():
            search_counts[stage][status] = search_counts[stage].get(status, 0) + 1
        search_rows.append(
            {
                "membership_id": membership.id,
                "search_id": membership.search_id,
                "name": search.name,
                "status_search": stage_values["search"],
                "status_export": stage_values["export"],
                "status_delivery": stage_values["delivery"],
                "export_without_consent": bool(getattr(search, "export_without_consent", False)),
                "custodian_ids": getattr(search, "custodian_ids", "[]"),
            }
        )

    return {
        "id": hold.id,
        "case_id": hold.case_id,
        "name": hold.name,
        "description": hold.description,
        "status": hold.status,
        "sort_order": hold.sort_order,
        "ntp_template_name": hold.ntp_template_name,
        "preservation_template_name": hold.preservation_template_name,
        "created_at": hold.created_at,
        "updated_at": hold.updated_at,
        "closed_at": hold.closed_at,
        "custodian_count": len(members),
        "search_count": len(search_rows),
        "ntp_counts": ntp_counts,
        "consent_counts": consent_counts,
        "source_totals": sorted(source_totals.values(), key=lambda item: str(item["source_label"]).lower()),
        "search_counts": search_counts,
        "custodians": sorted(members, key=lambda item: ((item.get("name") or "").lower(), (item.get("email") or "").lower())),
        "searches": sorted(search_rows, key=lambda item: ((item.get("name") or "").lower(), item["search_id"])),
        "search_ids": sorted(item["search_id"] for item in search_rows),
    }


@router.get("")
def list_case_holds(
    case_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user)
    holds = (
        db.query(models.CaseHold)
        .options(
            selectinload(models.CaseHold.custodian_memberships)
            .selectinload(models.HoldCustodian.custodian),
            selectinload(models.CaseHold.custodian_memberships)
            .selectinload(models.HoldCustodian.preservation_sources),
            selectinload(models.CaseHold.search_memberships)
            .selectinload(models.HoldSearch.search),
        )
        .filter(models.CaseHold.case_id == case_id)
        .order_by(models.CaseHold.sort_order.asc(), models.CaseHold.created_at.asc(), models.CaseHold.id.asc())
        .all()
    )
    return {
        "holds": [_serialize_hold(hold) for hold in holds],
        "totals": {
            "holds": len(holds),
            "active": sum(1 for hold in holds if hold.status == "active"),
            "custodian_memberships": sum(len(hold.custodian_memberships or []) for hold in holds),
        },
    }


@router.post("", status_code=201)
def create_case_hold(
    case_id: int,
    payload: CaseHoldCreate,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    existing = db.query(models.CaseHold.name).filter(models.CaseHold.case_id == case_id).all()
    name = (payload.name or "").strip() or _next_hold_name([row[0] for row in existing])
    duplicate = (
        db.query(models.CaseHold)
        .filter(models.CaseHold.case_id == case_id, models.CaseHold.name.ilike(name))
        .first()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="A hold with this name already exists")

    next_order = max(
        [int(row[0] or 0) for row in db.query(models.CaseHold.sort_order).filter(models.CaseHold.case_id == case_id).all()]
        or [-1]
    ) + 1
    hold = models.CaseHold(
        case_id=case_id,
        name=name,
        description=(payload.description or "").strip() or None,
        status="active",
        sort_order=next_order,
        ntp_template_name=(payload.ntp_template_name or "").strip() or None,
        preservation_template_name=(payload.preservation_template_name or "").strip() or None,
    )
    db.add(hold)
    db.commit()
    db.refresh(hold)
    log_event(
        db,
        action="case_hold_create",
        target_type="case_hold",
        target_id=hold.id,
        actor_id=user.id,
        details={"case_id": case_id, "hold_id": hold.id, "hold_name": hold.name},
        request=request,
    )
    return _serialize_hold(_hold_for_case(db, case_id, hold.id))


@router.put("/{hold_id}")
def update_case_hold(
    case_id: int,
    hold_id: int,
    payload: CaseHoldUpdate,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    hold = _hold_for_case(db, case_id, hold_id)
    fields = payload.model_fields_set

    if "name" in fields:
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Hold name is required")
        duplicate = (
            db.query(models.CaseHold)
            .filter(
                models.CaseHold.case_id == case_id,
                models.CaseHold.id != hold_id,
                models.CaseHold.name.ilike(name),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="A hold with this name already exists")
        hold.name = name
    for field in ("description", "ntp_template_name", "preservation_template_name"):
        if field in fields:
            value = getattr(payload, field)
            setattr(hold, field, value.strip() if isinstance(value, str) and value.strip() else None)
    if "status" in fields and payload.status:
        hold.status = payload.status
        hold.closed_at = datetime.now(timezone.utc) if payload.status in {"released", "closed"} else None

    db.add(hold)
    db.commit()
    log_event(
        db,
        action="case_hold_update",
        target_type="case_hold",
        target_id=hold.id,
        actor_id=user.id,
        details={"case_id": case_id, "hold_id": hold.id, "hold_name": hold.name, "status": hold.status},
        request=request,
    )
    return _serialize_hold(_hold_for_case(db, case_id, hold.id))


@router.delete("/{hold_id}")
def delete_case_hold(
    case_id: int,
    hold_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    hold = _hold_for_case(db, case_id, hold_id)
    if hold.custodian_memberships or hold.search_memberships:
        raise HTTPException(status_code=409, detail="Remove custodians and searches before deleting this hold")
    remaining = db.query(models.CaseHold).filter(models.CaseHold.case_id == case_id).count()
    if remaining <= 1:
        raise HTTPException(status_code=409, detail="A case must retain at least one hold")
    hold_name = hold.name
    db.delete(hold)
    db.commit()
    log_event(
        db,
        action="case_hold_delete",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={"case_id": case_id, "hold_id": hold_id, "hold_name": hold_name},
        request=request,
    )
    return {"ok": True}


@router.post("/{hold_id}/custodians")
def add_hold_custodians(
    case_id: int,
    hold_id: int,
    payload: HoldCustodianAssignment,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    created = assign_custodians_to_hold(
        db,
        case_id=case_id,
        hold_id=hold_id,
        custodian_ids=payload.custodian_ids,
    )
    db.commit()
    log_event(
        db,
        action="case_hold_custodians_add",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={"case_id": case_id, "hold_id": hold_id, "custodian_ids": payload.custodian_ids, "created": created},
        request=request,
    )
    return _serialize_hold(_hold_for_case(db, case_id, hold_id))


@router.delete("/{hold_id}/custodians/{custodian_id}")
def remove_hold_custodian(
    case_id: int,
    hold_id: int,
    custodian_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    membership = (
        db.query(models.HoldCustodian)
        .join(models.CaseHold, models.CaseHold.id == models.HoldCustodian.hold_id)
        .filter(
            models.CaseHold.case_id == case_id,
            models.HoldCustodian.hold_id == hold_id,
            models.HoldCustodian.custodian_id == custodian_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Custodian is not assigned to this hold")
    db.delete(membership)
    db.commit()
    log_event(
        db,
        action="case_hold_custodian_remove",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={
            "case_id": case_id,
            "hold_id": hold_id,
            "hold_name": membership.hold.name if membership.hold else None,
            "custodian_id": custodian_id,
            "changes": changes,
        },
        request=request,
    )
    return {"ok": True}


@router.put("/{hold_id}/custodians/{custodian_id}/workflow")
def update_hold_custodian_workflow(
    case_id: int,
    hold_id: int,
    custodian_id: int,
    payload: HoldMemberWorkflowUpdate,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    membership = (
        db.query(models.HoldCustodian)
        .join(models.CaseHold, models.CaseHold.id == models.HoldCustodian.hold_id)
        .filter(
            models.CaseHold.case_id == case_id,
            models.HoldCustodian.hold_id == hold_id,
            models.HoldCustodian.custodian_id == custodian_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Custodian is not assigned to this hold")
    audited_fields = (
        "ntp_status",
        "ntp_template_name",
        "ntp_not_required_reason",
        "consent_status",
        "consent_not_required_reason",
    )
    before = {field: getattr(membership, field, None) for field in audited_fields}
    for field in (
        "ntp_template_name",
        "ntp_not_required_reason",
        "consent_not_required_reason",
    ):
        if field in payload.model_fields_set:
            value = getattr(payload, field)
            setattr(membership, field, value.strip() if isinstance(value, str) and value.strip() else None)
    if "ntp_status" in payload.model_fields_set:
        if payload.ntp_status is None:
            raise HTTPException(status_code=422, detail="NTP status cannot be empty")
        set_membership_ntp_status(
            db,
            membership,
            payload.ntp_status,
            template_name=payload.ntp_template_name if "ntp_template_name" in payload.model_fields_set else None,
            not_required_reason=payload.ntp_not_required_reason if "ntp_not_required_reason" in payload.model_fields_set else None,
        )
    if "consent_status" in payload.model_fields_set:
        if payload.consent_status is None:
            raise HTTPException(status_code=422, detail="Consent status cannot be empty")
        set_membership_consent_status(
            db,
            membership,
            payload.consent_status,
            not_required_reason=(
                payload.consent_not_required_reason
                if "consent_not_required_reason" in payload.model_fields_set
                else None
            ),
        )
    db.add(membership)
    db.commit()
    after = {field: getattr(membership, field, None) for field in audited_fields}
    changes = {
        field: {"old": before[field], "new": after[field]}
        for field in audited_fields
        if before[field] != after[field]
    }
    log_event(
        db,
        action="case_hold_custodian_workflow_update",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={
            "case_id": case_id,
            "hold_id": hold_id,
            "hold_name": membership.hold.name if membership.hold else None,
            "custodian_id": custodian_id,
            "changes": changes,
        },
        request=request,
    )
    return _serialize_hold(_hold_for_case(db, case_id, hold_id))


@router.put("/{hold_id}/custodians/{custodian_id}/preservation/{source}")
def update_hold_preservation(
    case_id: int,
    hold_id: int,
    custodian_id: int,
    source: str,
    payload: HoldPreservationUpdate,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    membership = (
        db.query(models.HoldCustodian)
        .join(models.CaseHold, models.CaseHold.id == models.HoldCustodian.hold_id)
        .filter(
            models.CaseHold.case_id == case_id,
            models.HoldCustodian.hold_id == hold_id,
            models.HoldCustodian.custodian_id == custodian_id,
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=404, detail="Custodian is not assigned to this hold")
    key = source_key(source)
    existing = next((item for item in membership.preservation_sources if item.source_key == key), None)
    before = {
        "status": existing.status if existing is not None else "not_started",
        "provider_reference": existing.provider_reference if existing is not None else None,
        "last_error": existing.last_error if existing is not None else None,
    }
    record = set_membership_preservation_status(
        db,
        membership,
        key,
        payload.status,
        provider_reference=payload.provider_reference,
        last_error=payload.last_error,
    )
    db.commit()
    after = {
        "status": record.status,
        "provider_reference": record.provider_reference,
        "last_error": record.last_error,
    }
    log_event(
        db,
        action="case_hold_preservation_update",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={
            "case_id": case_id,
            "hold_id": hold_id,
            "hold_name": membership.hold.name if membership.hold else None,
            "custodian_id": custodian_id,
            "source": key,
            "source_label": record.source_label,
            "status": record.status,
            "changes": {
                field: {"old": before[field], "new": after[field]}
                for field in before
                if before[field] != after[field]
            },
        },
        request=request,
    )
    return _serialize_hold(_hold_for_case(db, case_id, hold_id))


@router.post("/{hold_id}/custodians/{custodian_id}/preservation/{source}/automation")
def automate_hold_preservation(
    case_id: int,
    hold_id: int,
    custodian_id: int,
    source: str,
    payload: HoldPreservationAutomation,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    case = _case_for_user(db, case_id, user, editable=True)
    hold = _hold_for_case(db, case_id, hold_id)
    membership = next(
        (
            row
            for row in hold.custodian_memberships or []
            if int(row.custodian_id) == int(custodian_id)
        ),
        None,
    )
    if membership is None or membership.custodian is None:
        raise HTTPException(status_code=404, detail="Custodian is not assigned to this hold")

    key = source_key(source)
    target_status = "pending" if payload.enabled else "released"
    set_membership_preservation_status(db, membership, key, target_status)
    db.commit()

    if not _source_automation_ready(key):
        return {
            "ok": True,
            "mode": "manual",
            "automation_ready": False,
            "status": target_status,
            "hold": _serialize_hold(_hold_for_case(db, case_id, hold_id)),
        }

    try:
        provider_source = _primary_provider_source(key)
        if provider_source:
            provider_payload = schemas.PreservationHoldRequest(
                case_hold_id=hold_id,
                custodian_ids=[custodian_id],
                included_sources=[provider_source],
            )
            operation = (
                preservation_provider.apply_holds
                if payload.enabled
                else preservation_provider.release_holds
            )
            provider_result = operation(
                case_id=case_id,
                payload=provider_payload,
                db=db,
                request=request,
                user=user,
            )
        else:
            provider_result = sync_hold_or_raise(
                case,
                membership.custodian,
                source_key=key,
                enable=payload.enabled,
                db=db,
                actor_id=getattr(user, "id", None),
                request=request,
                source="named_hold",
            )
        final_status = "active" if payload.enabled else "released"
        set_membership_preservation_status(db, membership, key, final_status)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        membership = (
            db.query(models.HoldCustodian)
            .filter(models.HoldCustodian.id == membership.id)
            .first()
        )
        if membership is not None:
            set_membership_preservation_status(
                db,
                membership,
                key,
                "failed",
                last_error=str(exc.detail),
            )
            db.commit()
        raise

    log_event(
        db,
        action="case_hold_preservation_automation",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={
            "case_id": case_id,
            "hold_id": hold_id,
            "custodian_id": custodian_id,
            "source": key,
            "enabled": payload.enabled,
            "provider_result": provider_result,
        },
        request=request,
    )
    return {
        "ok": True,
        "mode": "automated",
        "automation_ready": True,
        "status": final_status,
        "provider_result": provider_result,
        "hold": _serialize_hold(_hold_for_case(db, case_id, hold_id)),
    }


@router.put("/{hold_id}/searches")
def set_hold_searches(
    case_id: int,
    hold_id: int,
    payload: HoldSearchAssignment,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    _case_for_user(db, case_id, user, editable=True)
    hold = _hold_for_case(db, case_id, hold_id)
    normalized_ids = sorted({int(value) for value in payload.search_ids if int(value) > 0})
    searches = (
        db.query(models.Search)
        .filter(models.Search.case_id == case_id, models.Search.id.in_(normalized_ids))
        .all()
        if normalized_ids
        else []
    )
    found = {search.id for search in searches}
    missing = sorted(set(normalized_ids) - found)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Search does not belong to this case", "search_ids": missing})

    db.query(models.HoldSearch).filter(models.HoldSearch.hold_id == hold.id).delete(synchronize_session=False)
    for search_id in normalized_ids:
        db.add(models.HoldSearch(hold_id=hold.id, search_id=search_id))
    db.commit()
    log_event(
        db,
        action="case_hold_searches_update",
        target_type="case_hold",
        target_id=hold_id,
        actor_id=user.id,
        details={"case_id": case_id, "hold_id": hold_id, "search_ids": normalized_ids},
        request=request,
    )
    return _serialize_hold(_hold_for_case(db, case_id, hold_id))
