from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .auth import current_user as get_current_user
from .database import get_db, SessionLocal
from . import case_requests as case_request_core
from .case_request_approval_mutation import apply_approval_request_mutation
from .case_request_approval_preservation import run_approval_preservation_holds
from .case_request_approval_tickets import create_approval_tickets

router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])

@router.post("/{request_id}/approve")
def approve_case_request(
    request_id: int,
    payload_body: dict = Body(None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
):
    case_request_core.ensure_case_request_reviewer(actor)
    record = db.get(models.CaseRequest, request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    case_request_core._ensure_pending(record)

    payload = case_request_core._payload_dict(record)
    ticket_errors: list[str] = []
    def _log_progress(step: str, message: str, extra: Optional[dict] = None) -> None:
        details = {
            "request_id": record.id,
            "request_type": record.request_type,
            "case_id": record.case_id,
            "case_name": record.case_name,
            "step": step,
            "message": message,
        }
        if extra:
            details.update(extra)
        try:
            case_request_core.log_event(
                db,
                action="case_request_approve_progress",
                actor_id=actor.id,
                target_type="case_request",
                target_id=record.id,
                details=details,
                request=request,
            )
        except Exception as exc:
            case_request_core._debug_suppressed("suppressed exception in case_requests.py:3005", exc)

    analyst_id = None
    try:
        if isinstance(payload_body, dict):
            analyst_id = payload_body.get("analyst_id")
    except Exception:
        analyst_id = None

    if record.request_type == "new_case":
        _log_progress("create_case", "Creating case in DiscoveryOne...")
    elif record.request_type == "custodian":
        _log_progress("update_case", "Adding custodians to case...")
    elif record.request_type == "search":
        _log_progress("update_case", "Adding search details to case...")
    elif record.request_type == "close_case":
        _log_progress("update_case", "Closing case...")

    mutation = apply_approval_request_mutation(
        db=db,
        record=record,
        payload=payload,
        analyst_id=analyst_id,
        actor=actor,
        request=request,
    )
    rubrik_targets = mutation.rubrik_targets
    box_targets = mutation.box_targets
    case_for_tickets = mutation.case_for_tickets
    case_analyst_user = mutation.case_analyst_user
    preservation_hold_groups = mutation.preservation_hold_groups
    hold_notification_ids = mutation.hold_notification_ids
    hold_notification_should_send = mutation.hold_notification_should_send
    custodian_create_audit_payloads = mutation.custodian_create_audit_payloads
    ticket_target_debug_rows = mutation.ticket_target_debug_rows
    try:
        if record.request_type == "new_case" and record.case_id:
            submitted_custodians = case_request_core._collect_custodians(record)
            actual_custodians = (
                db.query(models.Custodian)
                .filter(models.Custodian.case_id == int(record.case_id))
                .order_by(models.Custodian.id.asc())
                .all()
            )
            requested_count = len(submitted_custodians or [])
            created_count = len(actual_custodians or [])
            if requested_count != created_count:
                case_request_core.notify_case_request_custodian_count_mismatch(
                    db,
                    record,
                    requested_count=requested_count,
                    created_count=created_count,
                    submitted_custodians=submitted_custodians,
                    actual_custodians=actual_custodians,
                    request=request,
                )
                try:
                    case_request_core.log_event(
                        db,
                        action="case_request_custodian_count_mismatch",
                        actor_id=actor.id,
                        target_type="case_request",
                        target_id=record.id,
                        details={
                            "case_id": record.case_id,
                            "case_name": record.case_name,
                            "requestor_email": record.requestor_email,
                            "submitted_count": requested_count,
                            "created_count": created_count,
                        },
                        request=request,
                    )
                except Exception as exc:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:custodian_count_mismatch_audit", exc)
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:custodian_count_mismatch_notify", exc)

    for item in custodian_create_audit_payloads:
        try:
            case_request_core.log_event(
                db,
                action="custodian_create",
                actor_id=actor.id,
                target_type="custodian",
                target_id=item.get("custodian_id"),
                details={
                    "case_id": item.get("case_id"),
                    "case_name": item.get("case_name"),
                    "custodian_id": item.get("custodian_id"),
                    "custodian_name": item.get("custodian_name"),
                    "custodian_email": item.get("custodian_email"),
                    "source": "case_request_approve",
                    "request_id": record.id,
                    "request_type": record.request_type,
                },
                request=request,
            )
        except Exception as exc:
            case_request_core._debug_suppressed("suppressed exception in case_requests.py:custodian_create_audit", exc)

    if record.request_type in {"new_case", "search"}:
        versa_requirements = case_request_core._extract_versa_search_requirements(payload)
        if versa_requirements and record.case_id:
            try:
                case_for_versa = db.get(models.Case, int(record.case_id))
                versa_custodians = (
                    db.query(models.Custodian)
                    .filter(models.Custodian.case_id == int(record.case_id))
                    .order_by(models.Custodian.id.asc())
                    .all()
                )
                versa_result = case_request_core._auto_create_versa_searches_for_new_case(
                    db=db,
                    case=case_for_versa,
                    actor=actor,
                    request=request,
                    requirements=versa_requirements,
                    custodians=versa_custodians,
                ) if case_for_versa else {"status": "error", "reason": "case_not_found", "created": 0}
                db.commit()
                try:
                    case_request_core.log_event(
                        db,
                        action="case_request_versa_search_builder",
                        actor_id=getattr(actor, "id", None),
                        target_type="case",
                        target_id=getattr(record, "case_id", None),
                        details={
                            "request_id": record.id,
                            "case_id": getattr(record, "case_id", None),
                            "case_name": getattr(record, "case_name", None),
                            "status": versa_result.get("status"),
                            "reason": versa_result.get("reason"),
                            "created": versa_result.get("created"),
                            "suggestions_count": versa_result.get("suggestions_count"),
                            "model": versa_result.get("model"),
                            "error": versa_result.get("error"),
                        },
                        request=request,
                    )
                except Exception as exc:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:versa_log", exc)
            except Exception as exc:
                try:
                    db.rollback()
                except Exception as rb_exc:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:versa_rollback", rb_exc)
                case_request_core._debug_suppressed("suppressed exception in case_requests.py:versa_build", exc)
                try:
                    case_request_core.log_event(
                        db,
                        action="case_request_versa_search_builder",
                        actor_id=getattr(actor, "id", None),
                        target_type="case",
                        target_id=getattr(record, "case_id", None),
                        details={
                            "request_id": record.id,
                            "case_id": getattr(record, "case_id", None),
                            "case_name": getattr(record, "case_name", None),
                            "status": "error",
                            "reason": "unexpected_exception",
                            "created": 0,
                            "error": str(exc),
                        },
                        request=request,
                    )
                except Exception as exc2:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:versa_log_error", exc2)

    rubrik_targets = run_approval_preservation_holds(
        db=db,
        record=record,
        actor=actor,
        request=request,
        preservation_hold_groups=preservation_hold_groups,
        hold_notification_ids=hold_notification_ids,
        rubrik_targets=rubrik_targets,
        log_progress=_log_progress,
    )
    create_approval_tickets(
        db=db,
        record=record,
        actor=actor,
        request=request,
        case_for_tickets=case_for_tickets,
        case_analyst_user=case_analyst_user,
        rubrik_targets=rubrik_targets,
        box_targets=box_targets,
        ticket_target_debug_rows=ticket_target_debug_rows,
        ticket_errors=ticket_errors,
        log_progress=_log_progress,
        session_factory=SessionLocal,
    )
    try:
        if hold_notification_should_send and hold_notification_ids:
            base_url = None
            try:
                base_url = case_request_core._app_base_url(request)
            except Exception:
                base_url = None
            case_request_core._schedule_case_request_hold_status_email(
                record.id,
                hold_notification_ids,
                base_url=base_url,
            )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3759", exc)

    try:
        case_request_core.log_event(
            db,
            action="case_request_approve",
            actor_id=actor.id,
            target_type="case_request",
            target_id=record.id,
            details={
                "type": record.request_type,
                "case_id": record.case_id,
                "case_name": record.case_name,
                "requestor_email": record.requestor_email,
            },
            request=request,
        )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3777", exc)
    try:
        case_request_core.notify_case_request_outcome(db, record, approved=True, request=request)
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3781", exc)
    return case_request_core._serialize_request(record, include_payload=True)



