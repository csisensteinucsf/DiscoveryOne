from __future__ import annotations

from sqlalchemy.orm import Session

from . import models
from .hold_workflows import _legacy_source_status
from .preservation_catalog import configured_hold_catalog


BLOCKING_PRESERVATION_STATUSES = {"pending", "active", "failed"}


def case_closure_readiness(db: Session, case_id: int) -> dict:
    active_holds = (
        db.query(models.CaseHold)
        .filter(models.CaseHold.case_id == case_id, models.CaseHold.status == "active")
        .order_by(models.CaseHold.sort_order, models.CaseHold.id)
        .all()
    )
    active_hold_rows = [
        {
            "hold_id": int(hold.id),
            "hold_name": hold.name,
            "custodian_count": int(
                db.query(models.HoldCustodian.id)
                .filter(models.HoldCustodian.hold_id == hold.id)
                .count()
            ),
        }
        for hold in active_holds
    ]

    source_rows = (
        db.query(
            models.HoldPreservationSource,
            models.HoldCustodian,
            models.CaseHold,
            models.Custodian,
        )
        .join(models.HoldCustodian, models.HoldCustodian.id == models.HoldPreservationSource.hold_custodian_id)
        .join(models.CaseHold, models.CaseHold.id == models.HoldCustodian.hold_id)
        .join(models.Custodian, models.Custodian.id == models.HoldCustodian.custodian_id)
        .filter(
            models.CaseHold.case_id == case_id,
            models.HoldPreservationSource.status.in_(sorted(BLOCKING_PRESERVATION_STATUSES)),
        )
        .all()
    )
    preservation_blockers = [
        {
            "scope": "hold",
            "hold_id": int(hold.id),
            "hold_name": hold.name,
            "custodian_id": int(custodian.id),
            "custodian_name": custodian.name,
            "source_key": source.source_key,
            "source_label": source.source_label,
            "status": source.status,
        }
        for source, _membership, hold, custodian in source_rows
    ]

    assigned_custodian_ids = {
        int(row[0])
        for row in (
            db.query(models.HoldCustodian.custodian_id)
            .join(models.CaseHold, models.CaseHold.id == models.HoldCustodian.hold_id)
            .filter(models.CaseHold.case_id == case_id)
            .distinct()
            .all()
        )
    }
    unassigned = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
    for custodian in unassigned:
        if int(custodian.id) in assigned_custodian_ids:
            continue
        for source_key, field, source_label in configured_hold_catalog(enabled_only=False):
            status = _legacy_source_status(custodian, field, source_key)
            if status not in BLOCKING_PRESERVATION_STATUSES:
                continue
            preservation_blockers.append(
                {
                    "scope": "matter",
                    "hold_id": None,
                    "hold_name": None,
                    "custodian_id": int(custodian.id),
                    "custodian_name": custodian.name,
                    "source_key": source_key,
                    "source_label": source_label,
                    "status": status,
                }
            )

    preservation_blockers.sort(
        key=lambda item: (
            str(item.get("hold_name") or ""),
            str(item.get("custodian_name") or ""),
            str(item.get("source_label") or ""),
        )
    )
    return {
        "ready": not active_hold_rows and not preservation_blockers,
        "active_holds": active_hold_rows,
        "preservation_blockers": preservation_blockers,
        "blocking_count": len(active_hold_rows) + len(preservation_blockers),
    }
