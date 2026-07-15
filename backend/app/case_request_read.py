from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .auth import current_user as get_current_user
from .database import get_db
from . import case_requests as case_request_core

router = APIRouter(prefix="/api/case_requests", tags=["case_requests"])

@router.get("/stats")
def request_stats(db: Session = Depends(get_db), actor: models.User = Depends(get_current_user)):
    if not actor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    case_request_core.ensure_case_request_access(actor)
    role = case_request_core.get_role(actor)
    mine = (
        db.query(func.count(models.CaseRequest.id))
        .filter(models.CaseRequest.status == "pending")
        .filter(models.CaseRequest.requestor_id == actor.id)
        .scalar()
        or 0
    )
    if role == "requestor" and not case_request_core.case_request_stats_requestor_show_global():
        return {
            "pending": mine,
            "mine_pending": mine,
        }
    total = db.query(func.count(models.CaseRequest.id)).filter(models.CaseRequest.status == "pending").scalar() or 0
    return {
        "pending": total,
        "mine_pending": mine,
    }


@router.get("")
def list_requests(
    status: Optional[str] = None,
    paged: bool = False,
    page: int = 1,
    per_page: int = 200,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    if not actor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    case_request_core.ensure_case_request_reviewer(actor)

    role = case_request_core.get_role(actor)
    include_payload = role != "requestor"
    query = db.query(models.CaseRequest)
    if role == "requestor":
        query = query.filter(models.CaseRequest.requestor_id == actor.id)
    if status:
        query = query.filter(models.CaseRequest.status == status)
    query = case_request_core._request_query_with_related(query)
    query = query.order_by(models.CaseRequest.created_at.desc())

    if not paged:
        records = query.all()
        return [case_request_core._serialize_request(r, include_payload=include_payload) for r in records]

    safe_page = max(1, int(page or 1))
    safe_per_page = max(1, min(int(per_page or 200), 1000))
    total = int(query.order_by(None).count() or 0)
    offset = (safe_page - 1) * safe_per_page
    records = query.offset(offset).limit(safe_per_page).all()
    items = [case_request_core._serialize_request(r, include_payload=include_payload) for r in records]
    return {
        "items": items,
        "total": total,
        "page": safe_page,
        "per_page": safe_per_page,
    }


@router.get("/mine")
def list_mine(
    paged: bool = False,
    page: int = 1,
    per_page: int = 200,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    if not actor:
        raise HTTPException(status_code=401, detail="Not authenticated")
    case_request_core.ensure_case_request_access(actor)

    query = (
        db.query(models.CaseRequest)
        .filter(models.CaseRequest.requestor_id == actor.id)
    )
    query = case_request_core._request_query_with_related(query)
    query = query.order_by(models.CaseRequest.created_at.desc())

    if not paged:
        return [case_request_core._serialize_request(r, include_payload=True) for r in query.all()]

    safe_page = max(1, int(page or 1))
    safe_per_page = max(1, min(int(per_page or 200), 1000))
    total = int(query.order_by(None).count() or 0)
    offset = (safe_page - 1) * safe_per_page
    rows = query.offset(offset).limit(safe_per_page).all()
    return {
        "items": [case_request_core._serialize_request(r, include_payload=True) for r in rows],
        "total": total,
        "page": safe_page,
        "per_page": safe_per_page,
    }
