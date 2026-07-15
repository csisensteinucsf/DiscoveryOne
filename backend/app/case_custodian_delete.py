from __future__ import annotations

import json
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .case_slack_holds import (
    sync_slack_hold_or_raise as _sync_slack_hold_or_raise,
)
from .permissions import ensure_case_editable, ensure_case_visible
from .preservation_provider import (
    remove_custodian as remove_custodian_from_preservation_provider,
)
from .safe_log import debug_suppressed as _debug_suppressed


def delete_custodian_for_case(
    case_id: int,
    custodian_id: int,
    release_holds: bool = False,
    release_ntp: bool = False,
    close_searches: bool = False,
    approval_note: Optional[str] = None,
    db: Session = None,
    request: Request = None,
    _user: models.User = None,
):
    custodian = (
        db.query(models.Custodian)
        .filter_by(id=custodian_id, case_id=case_id)
        .first()
    )
    if not custodian:
        raise HTTPException(status_code=404, detail="Custodian not found")
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    ensure_case_editable(_user)

    if bool(getattr(custodian, "holds_slack", False)):
        _sync_slack_hold_or_raise(
            case,
            custodian,
            enable=False,
            email_override=getattr(custodian, "email", None),
            db=db,
            actor_id=_user.id,
            request=request,
            source="custodian_delete",
        )

    custodian_name = getattr(custodian, "name", None)
    custodian_email = getattr(custodian, "email", None)
    case_name = getattr(case, "name", None)
    searches_updated = 0

    if close_searches:
        searches = (
            db.query(models.Search)
            .filter(models.Search.case_id == case_id)
            .all()
        )
        for search in searches:
            try:
                custodian_ids = json.loads(
                    getattr(search, "custodian_ids", "[]") or "[]"
                )
            except Exception:
                custodian_ids = []
            if not isinstance(custodian_ids, list):
                custodian_ids = []
            existing_ids = {
                int(value)
                for value in custodian_ids
                if isinstance(value, (int, float))
                or str(value).isdigit()
            }
            if custodian_id in existing_ids:
                search.custodian_ids = json.dumps(
                    [
                        value
                        for value in custodian_ids
                        if int(value) != int(custodian_id)
                    ]
                )
                searches_updated += 1
                db.add(search)

    preservation_release = None
    compatibility_fields: dict = {}
    if release_holds:
        preservation_release = remove_custodian_from_preservation_provider(
            case_id=case_id,
            custodian_id=custodian_id,
            custodian_name=custodian_name,
            custodian_email=custodian_email,
            db=db,
            request=request,
            user=_user,
        )
        if isinstance(preservation_release, dict):
            fields = preservation_release.get("compatibility_fields")
            if isinstance(fields, dict):
                compatibility_fields = fields

    details = {
        "case_id": case_id,
        "case_name": case_name,
        "custodian_id": custodian_id,
        "custodian_name": custodian_name,
        "custodian_email": custodian_email,
        "actions": {
            "release_holds": bool(release_holds),
            "release_ntp": bool(release_ntp),
            "close_searches": bool(close_searches),
            "searches_updated": searches_updated,
            "approval_note": (approval_note or "").strip() or None,
        },
        "preservation_release": preservation_release,
    }
    details.update(compatibility_fields)
    try:
        log_event(
            db,
            action="custodian_remove",
            target_type="custodian",
            target_id=custodian_id,
            actor_id=_user.id,
            details=details,
            request=request,
        )
    except Exception as exc:
        _debug_suppressed(
            "suppressed exception in case_custodian_delete.py:audit",
            exc,
        )

    db.delete(custodian)
    db.commit()

    response = {
        "ok": True,
        "preservation_release": preservation_release,
    }
    response.update(compatibility_fields)
    return response