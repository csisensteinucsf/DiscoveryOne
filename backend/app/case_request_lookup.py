from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import case_requests as case_request_core
from . import models
from .auth import current_user as get_current_user
from .database import get_db
from .person_lookup import person_lookup_max_custodians

router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])


@router.post("/custodian_lookup")
def custodian_lookup(
    payload: dict = Body(...),
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not actor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    case_request_core.ensure_case_request_access(actor)
    if not case_request_core.person_lookup_enabled():
        return {"results": []}

    custodians = payload.get("custodians") or []
    if not isinstance(custodians, list):
        custodians = []
    results: List[Dict[str, Any]] = []
    if not custodians:
        return {"results": results}
    max_custodians = person_lookup_max_custodians()
    if len(custodians) > max_custodians:
        raise HTTPException(
            status_code=413,
            detail=f"Lookup is limited to {max_custodians} custodians per request.",
        )

    for item in custodians:
        name = ""
        item_id = None
        email = None
        query = ""
        try:
            name = (item.get("name") or "").strip()
            item_id = item.get("id")
            email = (item.get("email") or "").strip() or None
            query = name or (email or "").strip()
        except AttributeError:
            name = ""
            item_id = None
            query = ""

        matches, err = case_request_core._lookup_matches_for_query(query, email=email)
        results.append({
            "id": item_id,
            "name": name,
            "email": email,
            "matches": matches,
            "error": err,
        })

    try:
        case_request_core.log_event(
            db,
            action="custodian_lookup",
            actor_id=actor.id,
            target_type="system",
            details={
                "requested_count": len(custodians),
                "result_count": sum(len(item.get("matches") or []) for item in results),
                "role": case_request_core.get_role(actor),
                "errors": sum(1 for item in results if item.get("error")),
            },
            request=request,
        )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_request_lookup.py:custodian_lookup_audit", exc)
    return {"results": results}