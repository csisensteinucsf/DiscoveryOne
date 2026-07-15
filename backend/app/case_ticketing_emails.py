"""Ticket-related outbound email routes."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import case_ticketing as ticket_core, models, schemas, ticket_provider
from .database import get_db
from .notifications import render_email_template
from .ticket_provider_labels import generic_external_ticket_label

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("/{case_id}/external_ticket_email", response_model=schemas.OkResponse)
@router.post("/{case_id}/servicenow_ticket_email", response_model=schemas.OkResponse)
def send_external_ticket_email(
    case_id: int,
    payload: schemas.ExternalTicketEmailRequest,
    db: Session = Depends(get_db),
    _user: models.User = Depends(ticket_core.get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ticket_core.ensure_case_visible(case, _user, db)
    entries = getattr(case, "request_ticket_entries", []) or []
    entry = next((e for e in entries if isinstance(e, dict) and str(e.get("id")) == payload.entry_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Ticket entry not found")
    ticket = (entry.get("ticket") or "").strip()
    if not ticket:
        raise HTTPException(status_code=400, detail="Ticket number missing")
    category = (entry.get("category") or "").strip()
    if ticket_core.is_tech(_user):
        allowed = ticket_core.tech_allowed_ticket_categories(_user)
        if category.strip().lower() not in allowed:
            raise HTTPException(status_code=403, detail="Tech accounts can only manage assigned ticket types")
    assigned_email = (entry.get("assigned_to_email") or "").strip()
    assigned_display = (entry.get("assigned_to_display") or "").strip()
    link = (entry.get("link") or entry.get("url") or "").strip()
    custodian_name = (entry.get("custodian_name") or "").strip()
    custodian_email = (entry.get("custodian_email") or "").strip()
    bulk_custodians = []
    if isinstance(entry.get("bulk_custodians"), list):
        for item in entry["bulk_custodians"]:
            if not isinstance(item, dict):
                continue
            bulk_custodians.append({
                "name": (item.get("name") or "").strip() or None,
                "email": (item.get("email") or "").strip() or None,
            })
    if not bulk_custodians and (custodian_email or custodian_name):
        bulk_custodians.append({
            "name": custodian_name or None,
            "email": custodian_email or None,
        })
    if not assigned_email:
        raise HTTPException(status_code=400, detail="Assigned user email is missing")
    need_label = ticket_core.request_ticket_category_label(category) or category or "this request"
    ticket_link = link or "N/A"
    if ticket_link in {"", "N/A"}:
        sys_id = (entry.get("sys_id") or "").strip()
        if sys_id:
            ticket_link = ticket_provider.ticket_link(sys_id=sys_id, fallback=ticket_link or "N/A")
    case_label = getattr(case, "name", "") or ""
    custodian_lines = []
    if bulk_custodians:
        for cust in bulk_custodians:
            name = cust.get("name") or "Unknown"
            email = cust.get("email") or "Unknown"
            custodian_lines.append(f"  - {name} | Email: {email}")
    custodian_list = "\n".join(custodian_lines) or "  - No custodians listed"
    ticket_label = generic_external_ticket_label()
    default_subject = "[{app_name}] Custodian details for ticket {ticket}"
    default_body = (
        f"{ticket_label.capitalize()}: {{ticket}} - {{ticket_link}}\n\n"
        "Case: {case_label}\n\n"
        "The following custodians require {need_label}:\n{custodian_list}\n\n"
        f"Please keep these details out of the {ticket_label}.\n\n"
        "If you have any questions, please reach out to the ticket customer."
    )
    subject, body = render_email_template(
        "external_ticket_assignee_details",
        default_subject=default_subject,
        default_body=default_body,
        context={
            "ticket": ticket,
            "ticket_link": ticket_link,
            "case_label": case_label,
            "case_name": case_label,
            "need_label": need_label,
            "ticket_category": need_label,
            "ticket_category_code": category,
            "custodian_list": custodian_list,
            "assigned_to": assigned_display or assigned_email,
            "assigned_to_email": assigned_email,
        },
    )
    if subject is None or body is None:
        raise HTTPException(status_code=400, detail="Ticket assignee detail emails are disabled")
    try:
        ticket_core.send_email(
            recipients=[assigned_email],
            subject=subject,
            body=body,
        )
        # Mark as sent so the UI can persist the state
        try:
            entry["assignment_email_sent"] = True
            case.request_ticket_entries = entries
            db.add(case)
            db.commit()
        except Exception:
            db.rollback()
    except HTTPException as exc:
        raise exc
    except Exception as exc:
        ticket_core.logger.warning("Failed to send assignment email for ticket %s: %s", ticket, exc)
        raise HTTPException(status_code=502, detail=f"Failed to send email: {exc}")
    return schemas.OkResponse()


def send_servicenow_ticket_email(*args, **kwargs):
    return send_external_ticket_email(*args, **kwargs)


@router.post("/{case_id}/requestor_hold_status_email", response_model=schemas.OkResponse)
def send_requestor_hold_status_email(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(ticket_core.get_current_user),
):
    """
    Send the requestor a snapshot of the current hold status for the case.

    Intended for tech workflows (e.g., Box team confirms hold placement) to notify the requestor.
    """
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ticket_core.ensure_case_visible(case, _user, db)
    if ticket_core.is_requestor(_user):
        raise HTTPException(status_code=403, detail="Requestors cannot trigger notifications")

    try:
        base_url = ticket_core._app_base_url(request)
    except Exception:
        base_url = None

    try:
        ticket_core.notify_case_requestor_hold_status(db, case, request=request, base_url=base_url, reason="box_hold_confirmed")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to send email: {exc}")

    try:
        ticket_core.log_event(
            db,
            action="requestor_hold_status_email",
            actor_id=getattr(_user, "id", None),
            target_type="case",
            target_id=case.id,
            details={
                "case_id": case.id,
                "case_name": getattr(case, "name", None),
                "reason": "box_hold_confirmed",
                "requestor": getattr(case, "requestor", None),
            },
            request=request,
        )
    except Exception as exc:
        ticket_core._debug_suppressed("suppressed exception in case_ticketing.py:2467", exc)

    return schemas.OkResponse()
