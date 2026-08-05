from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, selectinload

from . import cases as case_core
from . import models, schemas


def update_case_record(
    *,
    case_id: int,
    payload: schemas.CaseUpdate,
    db: Session,
    request: Optional[Request],
    user: models.User,
) -> schemas.CaseRead:
    case = (
        db.query(models.Case)
        .options(selectinload(models.Case.requestors))
        .filter(models.Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case_core.ensure_case_visible(case, user, db)
    if case_core.get_role(user) == "tech":
        allowed_categories = case_core.tech_allowed_ticket_categories(user)
        if not allowed_categories:
            raise HTTPException(status_code=403, detail="Tech accounts must belong to a ticket group")
        payload_fields = set(payload.dict(exclude_unset=True).keys())
        if payload_fields and payload_fields != {"request_ticket_entries"}:
            raise HTTPException(status_code=403, detail="Tech accounts can only update ticket entries")
        entries_payload = getattr(payload, "request_ticket_entries", None)
        if entries_payload is None:
            raise HTTPException(status_code=400, detail="Ticket entries are required")
        normalized_entries = case_core._normalize_request_ticket_entries(entries_payload, case) or []
        for entry in normalized_entries:
            category = (entry.get("category") or "").strip().lower()
            if category not in allowed_categories:
                raise HTTPException(status_code=403, detail="Tech accounts can only manage assigned ticket types")
        existing_entries = getattr(case, "request_ticket_entries", []) or []
        preserved_entries = []
        for entry in existing_entries:
            if not isinstance(entry, dict):
                continue
            category = (entry.get("category") or "").strip().lower()
            if category not in allowed_categories:
                preserved_entries.append(entry)
        before_entries = existing_entries
        merged_entries = preserved_entries + normalized_entries
        case.request_ticket_entries = merged_entries
        case_core._sync_legacy_request_tickets(case, merged_entries)
        case_core._apply_request_holds(case, merged_entries)
        try:
            db.add(case)
            db.commit()
            db.refresh(case)
        except Exception:
            db.rollback()
            raise
        after_entries = getattr(case, "request_ticket_entries", []) or []
        if before_entries != after_entries:
            try:
                case_core.log_event(
                    db,
                    action="case_update",
                    target_type="case",
                    target_id=case.id,
                    actor_id=user.id,
                    details={
                        "case_id": case.id,
                        "case_name": getattr(case, "name", None),
                        "changes": {
                            "request_ticket_entries": {
                                "old": before_entries,
                                "new": after_entries,
                            }
                        },
                    },
                    request=request,
                )
            except Exception as exc:
                case_core._debug_suppressed("suppressed exception in cases.py:1667", exc)
        return case_core._case_read(case, status=case_core._compute_case_status(db, case.id), user=user)

    case_core.ensure_case_editable(user)
    payload_fields = set(getattr(payload, "model_fields_set", set()) or set())

    tracked_fields = ("name","legal_case_name","is_ler_hr","servicenow_inc_number","claimant","ler_representative","internal_counsel","outside_counsel","matter_number","requestor","closed","closed_at","is_private","color","description","analyst_id","start_date","rubrik_restore_ticket","box_hold_ticket","is_active_case","closure_nag_days","custom_fields")
    _before = {k: getattr(case, k, None) for k in tracked_fields}
    _before["request_ticket_entries"] = getattr(case, "request_ticket_entries", []) or []
    was_closed = bool(case.closed)
    closing_case = "closed" in payload_fields and bool(payload.closed) and not was_closed
    if closing_case:
        from .case_closure_readiness import case_closure_readiness

        readiness = case_closure_readiness(db, case_id)
        if not readiness["ready"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "case_closure_blocked",
                    "message": "This case cannot be closed until every active Hold is closed and every preservation item is released.",
                    **readiness,
                },
            )
    old_claimant = getattr(case, "claimant", None)
    # handle analyst change safely
    if payload.analyst_id is not None:
        analyst_user = db.get(models.User, payload.analyst_id)
        if analyst_user is None:
            raise HTTPException(status_code=422, detail="Selected analyst not found")
        if analyst_user.username.lower() == case_core.ADMIN_USERNAME:
            raise HTTPException(status_code=422, detail="Admin cannot be assigned as analyst")
        case.analyst_id = analyst_user.id

    # sanitize & parse start_date ("" -> None, str -> date)
    if getattr(payload, "start_date", None) is not None:
        sd = payload.start_date
        if isinstance(sd, str):
            sd = sd.strip() or None
            if sd:
                try:
                        sd = datetime.strptime(sd, "%Y-%m-%d").date()
                except ValueError:
                        raise HTTPException(status_code=422, detail="start_date must be YYYY-MM-DD")
        case.start_date = sd


    was_closed = bool(case.closed)

    # requestors (primary + secondary)
    requestors_payload = getattr(payload, "requestors", None)
    if requestors_payload is not None:
        entries = case_core._normalize_requestor_entries(
            db,
            requestors_payload,
            payload.requestor if getattr(payload, "requestor", None) is not None else case.requestor,
        )
        case_core._apply_case_requestors(case, entries)
    elif getattr(payload, "requestor", None) is not None:
        new_primary = case_core._normalize_requestor_email(payload.requestor)
        current: List[dict] = []
        for row in getattr(case, "requestors", []) or []:
            current.append(
                {
                    "email": new_primary if getattr(row, "is_primary", False) else getattr(row, "email", None),
                    "user_id": getattr(row, "user_id", None),
                    "requestor_group": getattr(row, "requestor_group", None),
                    "is_primary": bool(getattr(row, "is_primary", False)),
                }
            )
        if not current and new_primary:
            current.append({"email": new_primary, "user_id": None, "requestor_group": None, "is_primary": True})
        if current:
            case_core._apply_case_requestors(case, current)
        else:
            case.requestor = new_primary

    for field in ("name", "legal_case_name", "claimant", "closed", "is_private", "color", "description", "rubrik_restore_ticket", "box_hold_ticket", "is_active_case", "closure_nag_days"):
        value = getattr(payload, field, None)
        if value is not None:
            setattr(case, field, value)

    for field in ("internal_counsel", "outside_counsel", "matter_number"):
        if field in payload_fields:
            value = getattr(payload, field, None)
            setattr(case, field, value.strip() if isinstance(value, str) and value.strip() else None)

    if "closed" in payload_fields:
        case.closed_at = datetime.now(timezone.utc) if bool(case.closed) and not was_closed else (None if not case.closed else case.closed_at)

    case.is_ler_hr = False
    case.servicenow_inc_number = None
    case.ler_representative = None

    # If claimant is set or changed, apply the configured Silent/Implied policy defaults.
    try:
        new_claimant = getattr(case, "claimant", None)
        if getattr(payload, "claimant", None) is not None and (new_claimant or "") != (old_claimant or ""):
            custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
            for cust in custodians or []:
                if not case_core._custodian_matches_claimant(
                    claimant=new_claimant,
                    name=getattr(cust, "name", None),
                    email=getattr(cust, "email", None),
                ):
                    continue
                ntp_status = (getattr(cust, "ntp_status", "") or "").strip().lower()
                if ntp_status != "acknowledged":
                    cust.ntp_status = "silent"
                cust.consent_status = "implied"
                case_core._apply_consent_not_required_defaults(case, cust)
                db.add(cust)
                db.flush()
                from .hold_workflows import sync_custodian_not_required_policy_to_memberships

                sync_custodian_not_required_policy_to_memberships(db, cust)
    except Exception as exc:
        case_core._debug_suppressed("suppressed exception in cases.py:1753", exc)
    if "custom_fields" in payload_fields:
        from .case_templates import normalize_existing_case_custom_fields

        case.custom_fields = normalize_existing_case_custom_fields(case.custom_fields, payload.custom_fields)

    entries_payload = getattr(payload, "request_ticket_entries", None)
    if entries_payload is not None:
        normalized_entries = case_core._normalize_request_ticket_entries(entries_payload, case) or []
        case.request_ticket_entries = normalized_entries
        case_core._sync_legacy_request_tickets(case, normalized_entries)
        case_core._apply_request_holds(case, normalized_entries)

    # compute changes for audit
    _after = {k: getattr(case, k, None) for k in tracked_fields}
    _after["request_ticket_entries"] = getattr(case, "request_ticket_entries", []) or []
    _changes = {k: {"old": _before[k], "new": _after[k]} for k in _before if _before.get(k) != _after.get(k)}
    if _changes:
        try:
            case_core.log_event(
                db,
                action="case_update",
                target_type="case",
                target_id=case.id,
                actor_id=user.id,
                details={
                    "case_id": case.id,
                    "case_name": getattr(case, "name", None),
                    "changes": _changes,

                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:1781", exc)

    # case_close detection
    try:
        new_closed = bool(getattr(case, "closed", False))
        case_name = getattr(case, "name", None)
        if (not was_closed) and new_closed:
            case_core.log_event(
                db,
                action="case_close",
                target_type="case",
                target_id=case.id,
                actor_id=user.id,
                details={
                    "case_id": case.id,
                    "case_name": case_name,
                    "closed_hold_ids": [],
                },
                request=request,
            )
            try:
                case_core.notify_case_requestor_case_event(case, event="closed", request=request)
            except Exception as exc:
                case_core._debug_suppressed("suppressed exception in cases.py:1800", exc)
            try:
                case_core._maybe_create_box_hold_release_ticket(
                    db,
                    case=case,
                    actor=user,
                    request=request,
                    source="case_close",
                )
            except Exception as exc:
                case_core._debug_suppressed("suppressed exception in cases.py:1810", exc)
        if was_closed and (not new_closed):
            case_core.log_event(
                db,
                action="case_reopen",
                target_type="case",
                target_id=case.id,
                actor_id=user.id,
                details={"case_id": case.id, "case_name": case_name},
                request=request,
            )
    except Exception as exc:
        case_core._debug_suppressed("suppressed exception in cases.py:1822", exc)

    db.add(case)
    db.commit()
    db.refresh(case)
    return case_core._case_read(case, status=case_core._compute_case_status(db, case.id), user=user)

