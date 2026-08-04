# backend/app/searches.py
#
# Drop-in replacement that fixes audit logging for `search_delete`.
# - Records `actor_id` (current user) so the UI "User" column is populated.
# - Emits structured `details` with `search_name`, `case_id`, and `case_name` so "Details" is meaningful.
# - Leaves other endpoints unchanged and fully compatible with existing schemas/models.
#
# Minimal comments: we document "why", not "what".

from fastapi import Request, APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import Any, List
from urllib.parse import urlparse
import json
import re
import os


import httpx
from .database import get_db
from . import models, schemas, search_export_provider
from .audit import log_event
from .auth import current_user  # why: to capture actor_id on mutations
from .permissions import ensure_case_visible, ensure_case_editable
from .safe_log import debug_suppressed as _debug_suppressed
from .search_naming import next_search_number, suggest_search_name
from .hold_workflows import set_search_holds, sync_search_hold_statuses
router = APIRouter(prefix="/api/cases", tags=["searches"])


def _ensure_case(db: Session, case_id: int, user: models.User | None = None) -> models.Case:
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user is not None:
        ensure_case_visible(case, user, db)
    return case


def _none_if_blank(x):
    if isinstance(x, str) and x.strip() == "":
        return None
    return x



def _serialize_search(obj: models.Search) -> dict:
    # why: some DBs store JSON as text; UI expects a list
    try:
        if isinstance(obj.custodian_ids, (str, bytes)):
            custodian_ids = json.loads(obj.custodian_ids or "[]")
        else:
            custodian_ids = obj.custodian_ids or []
    except Exception:
        custodian_ids = []
    hold_memberships = list(getattr(obj, "hold_memberships", None) or [])
    return {
        "id": obj.id,
        "case_id": obj.case_id,
        "name": obj.name,
        "keywords": obj.keywords,
        "senders": obj.senders,
        "recipients": obj.recipients,
        "date_from": obj.date_from,
        "date_to": obj.date_to,
        "additional": obj.additional,
        "status_search": obj.status_search,
        "status_export": obj.status_export,
        "export_without_consent": bool(getattr(obj, "export_without_consent", False)),
        "status_delivery": obj.status_delivery,
        "custodian_ids": custodian_ids,
        "hold_ids": sorted(int(item.hold_id) for item in hold_memberships),
        "hold_statuses": [
            {
                "hold_id": int(item.hold_id),
                "status_search": item.status_search,
                "status_export": item.status_export,
                "status_delivery": item.status_delivery,
            }
            for item in sorted(hold_memberships, key=lambda value: int(value.hold_id))
        ],
    }

def _escape_re(text: str) -> str:
    try:
        return re.escape(text or "")
    except Exception:
        return ""


def _next_search_number(case_name: str, existing_names: List[str]) -> int:
    return next_search_number(case_name, existing_names)


def _suggest_search_name(case_name: str, existing_names: List[str]) -> str:
    return suggest_search_name(case_name, existing_names)


def _looks_like_case_numbered_search(case_name: str, name: str) -> bool:
    base = (case_name or "").strip()
    value = (name or "").strip()
    if not base or not value:
        return False
    escaped = _escape_re(base)
    patterns = [
        re.compile(rf"^{escaped}-Search\s+\d+$", re.IGNORECASE),
        re.compile(rf"^{escaped}\s+Search\s+\d+$", re.IGNORECASE),
        re.compile(rf"^{escaped}-Search\s*\d+$", re.IGNORECASE),
    ]
    return any(p.match(value) for p in patterns)



def _build_ai_search_suggestions(*args, **kwargs):
    from .search_ai import _build_ai_search_suggestions as impl
    return impl(*args, **kwargs)


@router.get("/{case_id}/searches", response_model=List[schemas.SearchRead])
def list_searches(case_id: int, db: Session = Depends(get_db), request: Request = None, user: models.User = Depends(current_user)):
    _ensure_case(db, case_id, user)
    items = (
        db.query(models.Search)
        .filter(models.Search.case_id == case_id)
        .order_by(models.Search.id.desc())
        .all()
    )
    return [_serialize_search(x) for x in items]


@router.post("/{case_id}/searches", response_model=schemas.SearchRead, status_code=201)
def create_search(
    case_id: int,
    payload: schemas.SearchCreate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(current_user),
):
    case = _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    existing = [n for (n,) in db.query(models.Search.name).filter(models.Search.case_id == case_id).all()]
    incoming_name = (getattr(payload, "name", None) or "").strip()
    if not incoming_name:
        incoming_name = _suggest_search_name(getattr(case, "name", "") or "", existing)
    else:
        # If client supplied a default-style name that already exists, bump to the next number.
        if _looks_like_case_numbered_search(getattr(case, "name", "") or "", incoming_name):
            for n in existing:
                if (n or "").strip().lower() == incoming_name.lower():
                    incoming_name = _suggest_search_name(getattr(case, "name", "") or "", existing)
                    break
    obj = models.Search(
        case_id=case_id,
        name=incoming_name,
        keywords=_none_if_blank(payload.keywords),
        senders=_none_if_blank(payload.senders),
        recipients=_none_if_blank(payload.recipients),
        date_from=_none_if_blank(payload.date_from),
        date_to=_none_if_blank(payload.date_to),
        additional=_none_if_blank(payload.additional),
        status_search="not performed",
        status_export="not performed",
        export_without_consent=False,
        status_delivery="not performed",
        custodian_ids=json.dumps(payload.custodian_ids or []),
    )
    db.add(obj)
    db.flush()
    set_search_holds(db, search=obj, hold_ids=payload.hold_ids)
    db.commit()
    db.refresh(obj)
    try:
        log_event(db,
            action="search_create",
            target_type="search",
            target_id=obj.id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "search_id": obj.id,
                "search_name": obj.name,
            },  request=request)
    except Exception as exc:
        # why: do not block primary flow on audit failure
        _debug_suppressed("suppressed exception in searches.py:189", exc)
    return _serialize_search(obj)


@router.put("/{case_id}/searches/{search_id}", response_model=schemas.SearchRead)
def update_search(
    case_id: int,
    search_id: int,
    payload: schemas.SearchUpdate,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(current_user),
):
    case = _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    obj = (
        db.query(models.Search)
        .filter(models.Search.id == search_id, models.Search.case_id == case_id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Search not found")

    before = _serialize_search(obj)
    data = payload.dict(exclude_unset=True)
    hold_ids = data.pop("hold_ids", None)
    for field, value in data.items():
        if isinstance(value, str) and value.strip() == "":
            value = None
        if field == "custodian_ids":
            setattr(obj, field, json.dumps(value or []))
            continue
        if field == "export_without_consent":
            # This flag is controlled by automated export sync, not direct UI edits.
            continue
        if field == "status_export":
            # Any explicit export status change from the UI clears the automatic warning flag.
            obj.export_without_consent = False
        setattr(obj, field, value)

    db.add(obj)
    db.flush()
    if hold_ids is not None:
        set_search_holds(db, search=obj, hold_ids=hold_ids)
    else:
        sync_search_hold_statuses(db, obj)
    db.commit()
    db.refresh(obj)
    try:
        after = _serialize_search(obj)
        changes = {}
        for key in (
            "name",
            "keywords",
            "senders",
            "recipients",
            "date_from",
            "date_to",
            "additional",
            "status_search",
            "status_export",
            "export_without_consent",
            "status_delivery",
            "custodian_ids",
            "hold_ids",
        ):
            if before.get(key) != after.get(key):
                changes[key] = {"old": before.get(key), "new": after.get(key)}
        if changes:
            log_event(db,
                action="search_update",
                target_type="search",
                target_id=obj.id,
                actor_id=user.id,
                details={
                    "case_id": case_id,
                    "case_name": getattr(case, "name", None) if case else None,
                    "search_id": obj.id,
                    "search_name": obj.name,
                    "changes": changes,
                },  request=request)
    except Exception as exc:
        _debug_suppressed("suppressed exception in searches.py:264", exc)
    return _serialize_search(obj)


@router.delete("/{case_id}/searches/{search_id}", status_code=204)
def delete_search(
    case_id: int,
    search_id: int,
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(current_user),  # why: to populate actor_id
):
    case = _ensure_case(db, case_id, user)  # why: capture case.name
    ensure_case_editable(user)
    obj = (
        db.query(models.Search)
        .filter(models.Search.id == search_id, models.Search.case_id == case_id)
        .first()
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Search not found")

    db.delete(obj)
    db.commit()

    # Emit rich audit row. This fixes the "User" and "Details" columns.
    try:
        log_event(db,
            action="search_delete",
            target_type="search",
            target_id=obj.id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None) if case else None,
                "search_id": obj.id,
                "search_name": obj.name,
            },  request=request)
    except Exception as exc:
        _debug_suppressed("suppressed exception in searches.py:302", exc)

    return









@router.post(
    "/{case_id}/searches/{search_id}/push_to_purview",
    include_in_schema=False,
)
@router.post("/{case_id}/searches/{search_id}/push_to_provider")
def push_search_to_provider(
    case_id: int,
    search_id: int,
    payload: dict[str, Any] | None = Body(default=None),
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(current_user),
):
    case = _ensure_case(db, case_id, user)
    ensure_case_editable(user)
    search = (
        db.query(models.Search)
        .filter(
            models.Search.id == search_id,
            models.Search.case_id == case_id,
        )
        .first()
    )
    if not search:
        raise HTTPException(status_code=404, detail="Search not found")

    return search_export_provider.push_search(
        case=case,
        search=search,
        payload=payload,
        db=db,
        request=request,
        user=user,
    )




