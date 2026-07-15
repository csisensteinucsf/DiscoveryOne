from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models
from .auth import current_user as get_current_user
from .database import get_db
from . import case_requests as case_request_core

router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])

@router.get("/{request_id}/progress")
def get_case_request_progress(
    request_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    case_request_core.ensure_case_request_reviewer(actor)
    record = db.get(models.CaseRequest, request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    row = db.execute(
        text(
            """
            SELECT ev.created_at, ev.details
              FROM audit_events ev
             WHERE ev.action = :action
               AND ev.target_type = :target_type
               AND ev.target_id = :target_id
             ORDER BY ev.created_at DESC, ev.id DESC
             LIMIT 1
            """
        ),
        {
            "action": "case_request_approve_progress",
            "target_type": "case_request",
            "target_id": request_id,
        },
    ).mappings().first()
    details = case_request_core._parse_audit_details(row.get("details")) if row else None
    message = details.get("message") if isinstance(details, dict) else None
    step = details.get("step") if isinstance(details, dict) else None
    return {
        "request_id": request_id,
        "case_id": record.case_id,
        "status": record.status,
        "step": step,
        "message": message,
        "timestamp": row.get("created_at") if row else None,
    }


@router.post("/{request_id}/decline")
def decline_case_request(
    request_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
):
    case_request_core.ensure_case_request_reviewer(actor)
    record = db.get(models.CaseRequest, request_id)
    if not record:
        raise HTTPException(status_code=404, detail="Request not found")
    case_request_core._ensure_pending(record)
    reason = (payload or {}).get("reason")
    if not reason:
        raise HTTPException(status_code=400, detail="Decline reason required")
    record.status = "declined"
    record.decline_reason = reason
    record.reviewed_at = datetime.now(timezone.utc)
    record.reviewed_by_id = actor.id
    case_request_core._remove_attachment(record)
    db.commit()
    try:
        case_request_core.log_event(
            db,
            action="case_request_decline",
            actor_id=actor.id,
            target_type="case_request",
            target_id=record.id,
            details={
                "type": record.request_type,
                "case_id": record.case_id,
                "case_name": record.case_name,
                "reason": reason,
                "requestor_email": record.requestor_email,
            },
            request=request,
        )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3865", exc)
    try:
        case_request_core.notify_case_request_outcome(db, record, approved=False, request=request)
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3869", exc)
    return case_request_core._serialize_request(record, include_payload=True)
