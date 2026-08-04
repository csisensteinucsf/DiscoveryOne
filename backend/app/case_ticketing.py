import logging
from uuid import uuid4
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, selectinload

from . import models, schemas, ticket_provider
from .audit import log_event
from .auth import current_user as get_current_user
from .cases import (
    request_ticket_category_label,
    servicenow_matched_email_required_categories,
    _apply_request_holds,
    _custodian_has_unmatched_ticket_email,
    _is_missing_or_unmatched_email,
    _normalize_request_ticket_entries,
    _recover_request_ticket_entries_from_audit,
    _require_employee_id,
    _sync_legacy_request_tickets,
)
from .database import get_db
from .emailer import send_email
from .notifications import _app_base_url, _send_teams_notification, notify_case_requestor_hold_status
from .permissions import (
    ensure_case_editable,
    ensure_case_visible,
    filter_ticket_entries_for_user,
    is_requestor,
    is_tester,
    is_tech,
    tech_allowed_ticket_categories,
)
from .safe_log import debug_suppressed as _debug_suppressed
from .ticket_provider_labels import external_ticket_label

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])


def _provider_managed_ticket_numbers(entries) -> list[str]:
    tickets: list[str] = []
    for entry in entries or []:
        if not isinstance(entry, dict) or entry.get("provider_managed") is not True:
            continue
        ticket = str(entry.get("ticket") or "").strip()
        if ticket:
            tickets.append(ticket)
    return tickets

@router.post("/{case_id}/tickets/self_heal", response_model=schemas.TicketSelfHealResponse)
def ticket_self_heal(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    """
    Manual recovery tool: rebuild missing external ticket entries from audit history.
    Intended to repair cases where provider tickets exist but disappeared from the UI.
    """
    ensure_case_editable(_user)
    case = (
        db.query(models.Case)
        .options(selectinload(models.Case.custodians))
        .filter(models.Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)

    prior = getattr(case, "request_ticket_entries", []) or []
    prior_count = len(prior)
    updated = False
    try:
        updated = bool(_recover_request_ticket_entries_from_audit(db, case=case, request=request, actor=_user, force=True))
    except Exception:
        updated = False
    after = getattr(case, "request_ticket_entries", []) or []
    after_count = len(after)
    added_count = max(0, after_count - prior_count) if updated else 0
    return schemas.TicketSelfHealResponse(
        ok=True,
        updated=updated,
        prior_count=prior_count,
        after_count=after_count,
        added_count=added_count,
    )

@router.post("/{case_id}/external_ticket", response_model=schemas.ExternalTicketResponse)
@router.post("/{case_id}/servicenow_ticket", response_model=schemas.ExternalTicketResponse)
def create_external_ticket(
    case_id: int,
    payload: schemas.ExternalTicketRequest,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    if is_tech(_user):
        allowed = tech_allowed_ticket_categories(_user)
        if payload.category not in allowed:
            raise HTTPException(status_code=403, detail="Tech accounts can only manage assigned ticket types")
    else:
        ensure_case_editable(_user)

    selected_hold = None
    if payload.case_hold_id is not None:
        selected_hold = (
            db.query(models.CaseHold)
            .filter(
                models.CaseHold.case_id == case_id,
                models.CaseHold.id == int(payload.case_hold_id),
                models.CaseHold.status == "active",
            )
            .first()
        )
        if selected_hold is None:
            raise HTTPException(status_code=422, detail="Selected hold must be an active hold for this case")

    selected_custodian_ids: set[int] = set()
    if payload.custodian_id is not None:
        selected_custodian_ids.add(int(payload.custodian_id))
    for item in payload.bulk_custodians or []:
        item_id = getattr(item, "id", None)
        if item_id is not None:
            selected_custodian_ids.add(int(item_id))

    if selected_hold is not None and selected_custodian_ids:
        assigned_ids = {
            int(row.custodian_id)
            for row in db.query(models.HoldCustodian.custodian_id)
            .filter(
                models.HoldCustodian.hold_id == selected_hold.id,
                models.HoldCustodian.custodian_id.in_(selected_custodian_ids),
            )
            .all()
        }
        missing_ids = sorted(selected_custodian_ids - assigned_ids)
        if missing_ids:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Every selected custodian must be assigned to the selected hold",
                    "hold_id": int(selected_hold.id),
                    "custodian_ids": missing_ids,
                },
            )

    if payload.category in servicenow_matched_email_required_categories():
        invalid_labels: list[str] = []
        ids_to_check = set(selected_custodian_ids)
        for item in payload.bulk_custodians or []:
            item_id = getattr(item, "id", None)
            if item_id is None and _is_missing_or_unmatched_email(getattr(item, "email", None)):
                invalid_labels.append((getattr(item, "name", None) or getattr(item, "email", None) or "Unknown custodian").strip())

        custodians_by_id: dict[int, models.Custodian] = {}
        if ids_to_check:
            rows = (
                db.query(models.Custodian)
                .filter(models.Custodian.case_id == case_id, models.Custodian.id.in_(ids_to_check))
                .all()
            )
            custodians_by_id = {int(row.id): row for row in rows}
            missing_ids = ids_to_check - set(custodians_by_id.keys())
            for missing_id in sorted(missing_ids):
                invalid_labels.append(f"Custodian {missing_id}")
            for cust in rows:
                if _custodian_has_unmatched_ticket_email(cust):
                    invalid_labels.append((getattr(cust, "name", None) or getattr(cust, "email", None) or f"Custodian {cust.id}").strip())
        if not ids_to_check and _is_missing_or_unmatched_email(payload.custodian_email):
            invalid_labels.append((payload.custodian_name or payload.custodian_email or "Selected custodian").strip())
        if invalid_labels:
            names = ", ".join(sorted({label for label in invalid_labels if label}))
            raise HTTPException(
                status_code=400,
                detail=f"{request_ticket_category_label(payload.category) or 'This configured ticket workflow'} tickets require matched custodian email addresses. Resolve person lookup for: {names}",
            )
    # Use the logged-in user's Employee ID as the external ticket customer/requestor.
    customer_id_override = _require_employee_id(_user)
    case_link = None
    try:
        base = _app_base_url(request)
        case_link = f"{base}/cases/{case_id}"
    except Exception:
        case_link = None
    try:
        result = ticket_provider.create_ticket(
            category=payload.category,
            case_name=getattr(case, "name", None),
            case_link=case_link,
            custodian_name=(payload.custodian_name or "").strip() or None,
            custodian_email=(payload.custodian_email or "").strip() or None,
            customer_id=customer_id_override,
            extra_context={
                "case_hold_id": int(selected_hold.id) if selected_hold is not None else None,
                "case_hold_name": selected_hold.name if selected_hold is not None else None,
                "access_log_employee_id": ((payload.access_log_employee_id or "").strip() or None),
                "access_log_request_notes": ((payload.access_log_request_notes or "").strip() or None),
                "access_log_time_windows": [
                    {
                        "date": (getattr(window, "date", None) or "").strip() or None,
                        "start_time": (getattr(window, "start_time", None) or "").strip() or None,
                        "end_time": (getattr(window, "end_time", None) or "").strip() or None,
                    }
                    for window in (payload.access_log_time_windows or [])
                ],
            },
        )
    except ticket_provider.TicketProviderError as exc:
        logger.error("External ticket creation failed for case %s (category=%s): %s", case_id, payload.category, exc)
        raise HTTPException(status_code=502, detail=str(exc))
    ticket_number = (result.get("ticket_number") or result.get("ticket") or result.get("number") or "").strip()
    sys_id = result.get("sys_id") or None
    entry_id = payload.entry_id or str(uuid4())
    if not ticket_number:
        raise HTTPException(status_code=502, detail=f"{external_ticket_label()} provider did not return a ticket number.")

    # Persist the ticket number on the case immediately to avoid UI refresh loss.
    try:
        entries = getattr(case, "request_ticket_entries", []) or []
        match = None
        cust_email_norm = (payload.custodian_email or "").strip().lower()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if payload.entry_id and str(entry.get("id") or "") == str(payload.entry_id):
                match = entry
                break
            if entry.get("category") != payload.category:
                continue
            entry_hold_id = entry.get("case_hold_id")
            if payload.case_hold_id is not None and int(entry_hold_id or 0) != int(payload.case_hold_id):
                continue
            if payload.custodian_id is not None and entry.get("custodian_id") == payload.custodian_id:
                match = entry
                break
            existing_email = (entry.get("custodian_email") or "").strip().lower()
            if cust_email_norm and existing_email and cust_email_norm == existing_email:
                match = entry
                break
        if match is None:
            match = {"id": entry_id, "category": payload.category}
            entries.append(match)
        else:
            entry_id = str(match.get("id") or entry_id)

        match["ticket"] = ticket_number
        match["provider_managed"] = True
        if payload.case_hold_id is not None:
            match["case_hold_id"] = int(payload.case_hold_id)
        if sys_id:
            match["sys_id"] = sys_id
        if payload.custodian_id is not None:
            match["custodian_id"] = payload.custodian_id
        if payload.custodian_name:
            match["custodian_name"] = (payload.custodian_name or "").strip()
        if payload.custodian_email:
            match["custodian_email"] = (payload.custodian_email or "").strip()
        if payload.bulk_custodians:
            bulk: list[dict] = []
            for bc in payload.bulk_custodians:
                data = bc
                if hasattr(bc, "model_dump"):
                    data = bc.model_dump()
                elif hasattr(bc, "dict"):
                    data = bc.dict()
                if not isinstance(data, dict):
                    continue
                bulk.append(
                    {
                        "id": data.get("id"),
                        "name": (data.get("name") or "").strip() or None,
                        "email": (data.get("email") or "").strip() or None,
                    }
                )
            if bulk:
                match["bulk_custodians"] = bulk

        normalized_entries = _normalize_request_ticket_entries(entries, case, trusted_provider=True) or []
        case.request_ticket_entries = normalized_entries
        _sync_legacy_request_tickets(case, normalized_entries)
        _apply_request_holds(case, normalized_entries)
        db.add(case)
        db.commit()
        db.refresh(case)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to persist external ticket entry for case %s: %s", case_id, exc)
        try:
            db.rollback()
        except Exception as exc:
            _debug_suppressed("suppressed exception in case_ticketing.py:2035", exc)

    custodian_name_val = (payload.custodian_name or "").strip() or None
    custodian_email_val = (payload.custodian_email or "").strip() or None
    bulk_for_log: list[dict] = []
    if payload.bulk_custodians:
        for bc in payload.bulk_custodians:
            data = bc
            if hasattr(bc, "model_dump"):
                data = bc.model_dump()
            elif hasattr(bc, "dict"):
                data = bc.dict()
            if not isinstance(data, dict):
                continue
            bulk_for_log.append(
                {
                    "id": data.get("id"),
                    "name": (data.get("name") or "").strip() or None,
                    "email": (data.get("email") or "").strip() or None,
                }
            )
    try:
        log_event(
            db,
            action="case_request_ticket",
            target_type="case",
            target_id=case_id,
            actor_id=_user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "category": payload.category,
                "case_hold_id": int(selected_hold.id) if selected_hold is not None else None,
                "case_hold_name": selected_hold.name if selected_hold is not None else None,
                "ticket": ticket_number,
                "sys_id": sys_id,
                "entry_id": entry_id,
                "custodian_id": payload.custodian_id,
                "custodian_name": custodian_name_val,
                "custodian_email": custodian_email_val,
                "bulk_custodians": bulk_for_log or None,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_ticketing.py:2078", exc)

    return schemas.ExternalTicketResponse(ticket_number=ticket_number, sys_id=sys_id, entry_id=entry_id)


@router.get("/{case_id}/external_ticket_statuses", response_model=list[schemas.ExternalTicketStatus])
@router.get("/{case_id}/servicenow_ticket_statuses", response_model=list[schemas.ExternalTicketStatus])
def get_external_ticket_statuses(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)

    # IMPORTANT: tech users can only *view* statuses for their assigned categories, but we must never
    # persist a filtered list back to the case (that would delete other ticket categories like Rubrik).
    all_entries = getattr(case, "request_ticket_entries", []) or []
    entries = all_entries
    if is_tech(_user):
        entries = filter_ticket_entries_for_user(all_entries, _user)
    tickets = _provider_managed_ticket_numbers(entries)

    status_lookup: dict[str, dict] = {}
    if tickets:
        try:
            status_lookup = ticket_provider.get_ticket_statuses(tickets)
        except ticket_provider.TicketProviderError as exc:
            logger.error("External ticket status lookup failed for case %s: %s", case_id, exc)
            raise HTTPException(status_code=502, detail=str(exc))

    case_label = (getattr(case, "name", None) or "").strip() or f"Case #{case_id}"
    legal_case_name = (getattr(case, "legal_case_name", None) or "").strip()
    case_link = ""
    try:
        base = _app_base_url(request)
        case_link = f"{base}/cases/{case_id}"
    except Exception:
        case_link = ""

    def _assignee_id(email, sys_id, display) -> str:
        for val in (sys_id, email, display):
            if val is None:
                continue
            text = str(val).strip()
            if text:
                return text.lower()
        return ""

    def _custodian_summary(entry: dict) -> tuple[str, int]:
        parts: list[str] = []
        bulk = entry.get("bulk_custodians")
        if isinstance(bulk, list) and bulk:
            for item in bulk:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or "").strip()
                email = (item.get("email") or "").strip()
                if name and email:
                    parts.append(f"{name} <{email}>")
                elif email:
                    parts.append(email)
                elif name:
                    parts.append(name)
        else:
            name = (entry.get("custodian_name") or "").strip()
            email = (entry.get("custodian_email") or "").strip()
            if name and email:
                parts.append(f"{name} <{email}>")
            elif email:
                parts.append(email)
            elif name:
                parts.append(name)
        seen = set()
        unique: list[str] = []
        for p in parts:
            key = p.lower()
            if key in seen:
                continue
            unique.append(p)
            seen.add(key)
        return ", ".join(unique), len(unique)

    updated = False
    teams_queue: list[tuple[str, dict]] = []

    response: list[schemas.ExternalTicketStatus] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ticket = (entry.get("ticket") or "").strip()
        if not ticket:
            continue

        old_assignee_email = (entry.get("assigned_to_email") or "").strip()
        old_assignee_display = (entry.get("assigned_to_display") or "").strip()
        old_assignee_sys_id = (entry.get("assigned_to_sys_id") or "").strip()
        old_assignee_key = _assignee_id(old_assignee_email, old_assignee_sys_id, old_assignee_display)

        old_is_closed: Optional[bool] = None
        if "is_closed" in entry:
            raw_closed = entry.get("is_closed")
            if isinstance(raw_closed, bool):
                old_is_closed = raw_closed
            elif isinstance(raw_closed, (int, float)):
                old_is_closed = bool(raw_closed)

        info = status_lookup.get(ticket) or {}
        new_sys_id = info.get("sys_id") or entry.get("sys_id")
        new_status = info.get("status") if info.get("status") is not None else entry.get("status")
        new_link = info.get("link") or entry.get("link") or entry.get("url")
        new_assignee_email = info.get("assigned_to_email") or entry.get("assigned_to_email")
        new_assignee_display = info.get("assigned_to_display") or entry.get("assigned_to_display")
        new_assignee_sys_id = info.get("assigned_to_sys_id") or entry.get("assigned_to_sys_id")

        new_closed: Optional[bool] = None
        if "is_closed" in info:
            new_closed = bool(info.get("is_closed"))
        elif new_status is not None:
            try:
                new_closed = bool(ticket_provider.is_closed_status(new_status))
            except Exception:
                new_closed = None
        if new_closed is None and isinstance(old_is_closed, bool):
            new_closed = old_is_closed

        new_assignee_key = _assignee_id(new_assignee_email, new_assignee_sys_id, new_assignee_display)
        assignee_changed = bool(new_assignee_key) and new_assignee_key != old_assignee_key
        became_closed = old_is_closed is False and new_closed is True

        if assignee_changed or became_closed:
            custodian_list, custodian_count = _custodian_summary(entry)
            ticket_category_code = (entry.get("category") or "").strip()
            ticket_category = request_ticket_category_label(ticket_category_code) or ticket_category_code or ""
            assigned_to = (new_assignee_display or new_assignee_email or new_assignee_sys_id or "").strip()
            status_text = str(new_status).strip() if new_status is not None else ""
            ctx = {
                "case_id": case_id,
                "case_label": case_label,
                "case_name": case_label,
                "legal_case_name": legal_case_name,
                "case_link": case_link,
                "entry_id": str(entry.get("id") or ""),
                "ticket": ticket,
                "ticket_link": (new_link or "").strip(),
                "ticket_category": ticket_category,
                "ticket_category_code": ticket_category_code,
                "status": status_text,
                "assigned_to": assigned_to,
                "assigned_to_display": (new_assignee_display or "").strip(),
                "assigned_to_email": (new_assignee_email or "").strip(),
                "custodians": custodian_list,
                "custodian_count": custodian_count,
            }
            if assignee_changed:
                teams_queue.append(("ticket_assigned", ctx))
            if became_closed:
                teams_queue.append(("ticket_completed", ctx))

        # Update entry if changed
        if (
            entry.get("sys_id") != new_sys_id
            or entry.get("status") != new_status
            or entry.get("assigned_to_email") != new_assignee_email
            or entry.get("assigned_to_display") != new_assignee_display
            or entry.get("assigned_to_sys_id") != new_assignee_sys_id
            or (new_closed is not None and entry.get("is_closed") != new_closed)
        ):
            entry["sys_id"] = new_sys_id
            entry["status"] = new_status
            entry["assigned_to_email"] = new_assignee_email
            entry["assigned_to_display"] = new_assignee_display
            entry["assigned_to_sys_id"] = new_assignee_sys_id
            if new_closed is not None:
                entry["is_closed"] = bool(new_closed)
            updated = True
        if new_link and entry.get("link") != new_link:
            entry["link"] = new_link
            updated = True

        response.append(
            schemas.ExternalTicketStatus(
                entry_id=str(entry.get("id") or ""),
                category=entry.get("category") or "",
                ticket=ticket,
                sys_id=new_sys_id,
                status=new_status,
                is_closed=bool(new_closed),
                link=new_link,
                assigned_to_sys_id=new_assignee_sys_id,
                assigned_to_display=new_assignee_display,
                assigned_to_email=new_assignee_email,
            )
        )

    if updated:
        committed = False
        try:
            case.request_ticket_entries = all_entries
            _apply_request_holds(case, all_entries)
            db.add(case)
            db.commit()
            committed = True
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to persist updated external ticket entries for case %s: %s", case_id, exc)
        if committed and teams_queue:
            for event, ctx in teams_queue:
                try:
                    _send_teams_notification(event, ctx)
                except Exception as exc:
                    _debug_suppressed("suppressed exception in case_ticketing.py:2317", exc)

    return response

def send_external_ticket_email(*args, **kwargs):
    from .case_ticketing_emails import send_external_ticket_email as impl
    return impl(*args, **kwargs)


def send_servicenow_ticket_email(*args, **kwargs):
    return send_external_ticket_email(*args, **kwargs)


def send_requestor_hold_status_email(*args, **kwargs):
    from .case_ticketing_emails import send_requestor_hold_status_email as impl
    return impl(*args, **kwargs)

