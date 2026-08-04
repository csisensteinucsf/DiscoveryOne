from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import models
from .preservation_catalog import configured_hold_catalog, source_key


def _ids(values: Iterable[int] | None) -> list[int]:
    normalized: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            normalized.add(number)
    return sorted(normalized)


def case_hold_or_404(db: Session, case_id: int, hold_id: int) -> models.CaseHold:
    hold = (
        db.query(models.CaseHold)
        .filter(models.CaseHold.case_id == case_id, models.CaseHold.id == hold_id)
        .first()
    )
    if hold is None:
        raise HTTPException(status_code=404, detail="Hold not found for this case")
    return hold


def resolve_hold_memberships(
    db: Session,
    *,
    case_id: int,
    custodian_ids: Sequence[int],
    case_hold_id: int | None,
    create_default: bool = True,
) -> tuple[models.CaseHold, dict[int, models.HoldCustodian]]:
    normalized_ids = _ids(custodian_ids)
    if not normalized_ids:
        raise HTTPException(status_code=400, detail="At least one custodian is required")

    case = db.get(models.Case, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    if case_hold_id is None:
        from .case_holds import ensure_default_hold

        hold = ensure_default_hold(db, case, assign_existing=create_default)
        db.flush()
    else:
        hold = case_hold_or_404(db, case_id, int(case_hold_id))

    custodians = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id, models.Custodian.id.in_(normalized_ids))
        .all()
    )
    found_custodian_ids = {int(item.id) for item in custodians}
    missing_custodians = sorted(set(normalized_ids) - found_custodian_ids)
    if missing_custodians:
        raise HTTPException(
            status_code=422,
            detail={"message": "Custodian does not belong to this case", "custodian_ids": missing_custodians},
        )

    memberships = (
        db.query(models.HoldCustodian)
        .filter(
            models.HoldCustodian.hold_id == hold.id,
            models.HoldCustodian.custodian_id.in_(normalized_ids),
        )
        .all()
    )
    by_custodian = {int(item.custodian_id): item for item in memberships}
    missing_memberships = sorted(set(normalized_ids) - set(by_custodian))
    if missing_memberships and case_hold_id is None and create_default:
        from .case_holds import assign_custodians_to_hold

        assign_custodians_to_hold(
            db,
            case_id=case_id,
            hold_id=int(hold.id),
            custodian_ids=missing_memberships,
        )
        db.flush()
        memberships = (
            db.query(models.HoldCustodian)
            .filter(
                models.HoldCustodian.hold_id == hold.id,
                models.HoldCustodian.custodian_id.in_(normalized_ids),
            )
            .all()
        )
        by_custodian = {int(item.custodian_id): item for item in memberships}
        missing_memberships = sorted(set(normalized_ids) - set(by_custodian))

    if missing_memberships:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Custodian is not assigned to the selected hold",
                "hold_id": int(hold.id),
                "custodian_ids": missing_memberships,
            },
        )
    return hold, by_custodian


def membership_or_404(
    db: Session,
    *,
    case_id: int,
    hold_id: int,
    custodian_id: int,
) -> models.HoldCustodian:
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
    if membership is None:
        raise HTTPException(status_code=404, detail="Custodian is not assigned to this hold")
    return membership


def hold_id_for_membership(membership: models.HoldCustodian | None) -> int | None:
    if membership is None:
        return None
    try:
        return int(membership.hold_id)
    except (TypeError, ValueError):
        return None


def _refresh_legacy_ntp(db: Session, custodian_id: int) -> None:
    custodian = db.get(models.Custodian, custodian_id)
    if custodian is None:
        return
    memberships = db.query(models.HoldCustodian).filter(models.HoldCustodian.custodian_id == custodian_id).all()
    statuses = {str(item.ntp_status or "not sent").strip().lower() for item in memberships}
    if "acknowledged" in statuses:
        custodian.ntp_status = "acknowledged"
    elif "sent" in statuses:
        custodian.ntp_status = "sent"
    elif "not sent" in statuses or not statuses:
        custodian.ntp_status = "not sent"
    else:
        custodian.ntp_status = "na"
    sent_values = [item.ntp_sent_at for item in memberships if item.ntp_sent_at is not None]
    acknowledged_values = [item.ntp_acknowledged_at for item in memberships if item.ntp_acknowledged_at is not None]
    custodian.ntp_sent_at = max(sent_values) if sent_values else None
    custodian.ntp_acknowledged_at = max(acknowledged_values) if acknowledged_values else None
    db.add(custodian)


def set_membership_ntp_status(
    db: Session,
    membership: models.HoldCustodian,
    status: str,
    *,
    template_name: str | None = None,
    not_required_reason: str | None = None,
    at: datetime | None = None,
) -> None:
    normalized = str(status or "").strip().lower()
    if normalized not in {"not sent", "sent", "acknowledged", "na"}:
        raise HTTPException(status_code=422, detail="Invalid hold NTP status")
    timestamp = at or datetime.now(timezone.utc)
    membership.ntp_status = normalized
    if template_name is not None:
        membership.ntp_template_name = str(template_name).strip() or None
    if not_required_reason is not None:
        membership.ntp_not_required_reason = str(not_required_reason).strip() or None
    if normalized == "sent":
        membership.ntp_sent_at = timestamp
        membership.ntp_acknowledged_at = None
    elif normalized == "acknowledged":
        membership.ntp_sent_at = membership.ntp_sent_at or timestamp
        membership.ntp_acknowledged_at = timestamp
    elif normalized in {"not sent", "na"}:
        membership.ntp_sent_at = None
        membership.ntp_acknowledged_at = None
    db.add(membership)
    db.flush()
    _refresh_legacy_ntp(db, int(membership.custodian_id))


def _refresh_legacy_consent(db: Session, custodian_id: int) -> None:
    custodian = db.get(models.Custodian, custodian_id)
    if custodian is None:
        return
    memberships = db.query(models.HoldCustodian).filter(models.HoldCustodian.custodian_id == custodian_id).all()
    statuses = {str(item.consent_status or "not sent").strip().lower() for item in memberships}
    if "received" in statuses:
        custodian.consent_status = "received"
    elif "sent" in statuses:
        custodian.consent_status = "sent"
    elif "not sent" in statuses or not statuses:
        custodian.consent_status = "not sent"
    else:
        custodian.consent_status = "na"
    db.add(custodian)


def set_membership_consent_status(
    db: Session,
    membership: models.HoldCustodian,
    status: str,
    *,
    not_required_reason: str | None = None,
) -> None:
    normalized = str(status or "").strip().lower()
    if normalized not in {"not sent", "sent", "received", "na"}:
        raise HTTPException(status_code=422, detail="Invalid hold consent status")
    membership.consent_status = normalized
    if not_required_reason is not None:
        membership.consent_not_required_reason = str(not_required_reason).strip() or None
    db.add(membership)
    db.flush()
    _refresh_legacy_consent(db, int(membership.custodian_id))


def sync_membership_consent_from_requests(
    db: Session,
    membership: models.HoldCustodian,
) -> str:
    statuses = {
        str(row.status or "").strip().lower()
        for row in db.query(models.CaseConsent)
        .filter(models.CaseConsent.hold_custodian_id == membership.id)
        .all()
    }
    if "completed" in statuses or "received" in statuses:
        status = "received"
    elif statuses - {"voided", "declined", "deleted", "timedout"}:
        status = "sent"
    else:
        status = "not sent"
    set_membership_consent_status(db, membership, status)
    return status


def _source_definition(key: str) -> tuple[str | None, str]:
    normalized = source_key(key)
    for configured_key, field, label in configured_hold_catalog(enabled_only=False):
        if source_key(configured_key) == normalized:
            return field, label or normalized.replace("_", " ").title()
    return None, normalized.replace("_", " ").title()


def preservation_record(
    db: Session,
    membership: models.HoldCustodian,
    source: str,
    *,
    create: bool = True,
) -> models.HoldPreservationSource | None:
    key = source_key(source)
    row = (
        db.query(models.HoldPreservationSource)
        .filter(
            models.HoldPreservationSource.hold_custodian_id == membership.id,
            models.HoldPreservationSource.source_key == key,
        )
        .first()
    )
    if row is None and create:
        _field, label = _source_definition(key)
        row = models.HoldPreservationSource(
            hold_custodian_id=membership.id,
            source_key=key,
            source_label=label,
            status="not_started",
        )
        db.add(row)
        db.flush()
    return row


def _refresh_legacy_preservation(db: Session, custodian_id: int, source: str) -> None:
    custodian = db.get(models.Custodian, custodian_id)
    if custodian is None:
        return
    key = source_key(source)
    rows = (
        db.query(models.HoldPreservationSource)
        .join(models.HoldCustodian, models.HoldCustodian.id == models.HoldPreservationSource.hold_custodian_id)
        .filter(
            models.HoldCustodian.custodian_id == custodian_id,
            models.HoldPreservationSource.source_key == key,
        )
        .all()
    )
    statuses = {str(item.status or "not_started").strip().lower() for item in rows}
    field, label = _source_definition(key)
    if field:
        setattr(custodian, field, "active" in statuses)
        setattr(custodian, field + "_pending", "pending" in statuses)
        setattr(custodian, field + "_failed", "failed" in statuses)
        setattr(custodian, field + "_released", bool(statuses) and statuses <= {"released", "not_started"} and "released" in statuses)
    else:
        row = (
            db.query(models.CustodianPreservation)
            .filter(
                models.CustodianPreservation.custodian_id == custodian_id,
                models.CustodianPreservation.source_key == key,
            )
            .first()
        )
        if row is None:
            row = models.CustodianPreservation(custodian_id=custodian_id, source_key=key, source_label=label)
        row.active = "active" in statuses
        row.pending = "pending" in statuses
        row.failed = "failed" in statuses
        row.released = bool(statuses) and statuses <= {"released", "not_started"} and "released" in statuses
        db.add(row)
    db.add(custodian)


def set_membership_preservation_status(
    db: Session,
    membership: models.HoldCustodian,
    source: str,
    status: str,
    *,
    provider_reference: str | None = None,
    last_error: str | None = None,
) -> models.HoldPreservationSource:
    normalized = str(status or "").strip().lower()
    if normalized not in {"not_started", "pending", "active", "failed", "released"}:
        raise HTTPException(status_code=422, detail="Invalid hold preservation status")
    row = preservation_record(db, membership, source, create=True)
    assert row is not None
    row.status = normalized
    if provider_reference is not None:
        row.provider_reference = str(provider_reference).strip() or None
    if last_error is not None:
        row.last_error = str(last_error).strip() or None
    if normalized != "failed" and last_error is None:
        row.last_error = None
    db.add(row)
    db.flush()
    _refresh_legacy_preservation(db, int(membership.custodian_id), source)
    return row


def _legacy_source_status(custodian: models.Custodian, field: str | None, source: str) -> str:
    if field:
        if bool(getattr(custodian, field + "_failed", False)):
            return "failed"
        if bool(getattr(custodian, field + "_pending", False)):
            return "pending"
        if bool(getattr(custodian, field, False)):
            return "active"
        if bool(getattr(custodian, field + "_released", False)):
            return "released"
        return "not_started"
    key = source_key(source)
    custom = next(
        (item for item in (getattr(custodian, "custom_preservation", None) or []) if source_key(item.source_key) == key),
        None,
    )
    if custom is None:
        return "not_started"
    if bool(getattr(custom, "failed", False)):
        return "failed"
    if bool(getattr(custom, "pending", False)):
        return "pending"
    if bool(getattr(custom, "active", False)):
        return "active"
    if bool(getattr(custom, "released", False)):
        return "released"
    return "not_started"


def sync_legacy_custodian_to_default_hold(
    db: Session,
    custodian: models.Custodian,
    *,
    changed_fields: Iterable[str] | None = None,
) -> models.HoldCustodian | None:
    """Bridge older custodian writes into the case's default named hold."""
    case = db.get(models.Case, int(custodian.case_id))
    if case is None:
        return None
    from .case_holds import ensure_default_hold

    hold = ensure_default_hold(db, case, assign_existing=True)
    db.flush()
    membership = (
        db.query(models.HoldCustodian)
        .filter(
            models.HoldCustodian.hold_id == hold.id,
            models.HoldCustodian.custodian_id == custodian.id,
        )
        .first()
    )
    if membership is None:
        return None
    changed = set(changed_fields or [])
    sync_all = not changed
    if sync_all or changed.intersection({"ntp_status", "ntp_not_required_reason"}):
        set_membership_ntp_status(
            db,
            membership,
            getattr(custodian, "ntp_status", None) or "not sent",
            template_name=getattr(custodian, "ntp_template_name", None),
            not_required_reason=getattr(custodian, "ntp_not_required_reason", None),
            at=getattr(custodian, "ntp_acknowledged_at", None) or getattr(custodian, "ntp_sent_at", None),
        )
    if sync_all or changed.intersection({"consent_status", "consent_not_required_reason"}):
        set_membership_consent_status(
            db,
            membership,
            getattr(custodian, "consent_status", None) or "not sent",
            not_required_reason=getattr(custodian, "consent_not_required_reason", None),
        )
    for key, field, _label in configured_hold_catalog(enabled_only=False):
        related_fields = {"custom_preservation"} if not field else {
            field,
            field + "_pending",
            field + "_failed",
            field + "_released",
        }
        if sync_all or changed.intersection(related_fields):
            set_membership_preservation_status(
                db,
                membership,
                key,
                _legacy_source_status(custodian, field, key),
            )
    return membership


def sync_custodian_not_required_policy_to_memberships(db: Session, custodian: models.Custodian) -> None:
    """Apply global eligibility rules without erasing acknowledged NTP history."""
    memberships = db.query(models.HoldCustodian).filter(models.HoldCustodian.custodian_id == custodian.id).all()
    ntp_status = str(getattr(custodian, "ntp_status", None) or "").strip().lower()
    consent_status = str(getattr(custodian, "consent_status", None) or "").strip().lower()
    for membership in memberships:
        if ntp_status == "na" and str(membership.ntp_status or "").strip().lower() != "acknowledged":
            set_membership_ntp_status(
                db,
                membership,
                "na",
                not_required_reason=getattr(custodian, "ntp_not_required_reason", None),
            )
        if consent_status == "na":
            set_membership_consent_status(
                db,
                membership,
                "na",
                not_required_reason=getattr(custodian, "consent_not_required_reason", None),
            )

def set_search_holds(
    db: Session,
    *,
    search: models.Search,
    hold_ids: Sequence[int] | None,
) -> list[int]:
    requested = _ids(hold_ids)
    if not requested:
        case = db.get(models.Case, int(search.case_id))
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        from .case_holds import ensure_default_hold

        requested = [int(ensure_default_hold(db, case, assign_existing=True).id)]
        db.flush()
    holds = (
        db.query(models.CaseHold)
        .filter(models.CaseHold.case_id == search.case_id, models.CaseHold.id.in_(requested))
        .all()
    )
    found = {int(item.id) for item in holds}
    missing = sorted(set(requested) - found)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Hold does not belong to this case", "hold_ids": missing})
    existing = {int(item.hold_id): item for item in search.hold_memberships or []}
    for hold_id, membership in list(existing.items()):
        if hold_id not in found:
            db.delete(membership)
    for hold_id in found:
        membership = existing.get(hold_id)
        if membership is None:
            membership = models.HoldSearch(hold_id=hold_id, search_id=search.id)
        membership.status_search = search.status_search or "not performed"
        membership.status_export = search.status_export or "not performed"
        membership.status_delivery = search.status_delivery or "not performed"
        db.add(membership)
    db.flush()
    return sorted(found)


def sync_search_hold_statuses(db: Session, search: models.Search) -> None:
    rows = db.query(models.HoldSearch).filter(models.HoldSearch.search_id == search.id).all()
    for row in rows:
        row.status_search = search.status_search or "not performed"
        row.status_export = search.status_export or "not performed"
        row.status_delivery = search.status_delivery or "not performed"
        db.add(row)


def active_hold_summary(db: Session, case_id: int) -> list[dict[str, object]]:
    rows = (
        db.query(models.CaseHold)
        .filter(models.CaseHold.case_id == case_id, models.CaseHold.status == "active")
        .order_by(models.CaseHold.sort_order.asc(), models.CaseHold.id.asc())
        .all()
    )
    return [{"id": int(row.id), "name": row.name, "custodian_count": len(row.custodian_memberships or [])} for row in rows]


def close_active_holds(db: Session, case_id: int) -> list[int]:
    now = datetime.now(timezone.utc)
    rows = db.query(models.CaseHold).filter(models.CaseHold.case_id == case_id, models.CaseHold.status == "active").all()
    for row in rows:
        row.status = "closed"
        row.closed_at = now
        db.add(row)
    return [int(row.id) for row in rows]