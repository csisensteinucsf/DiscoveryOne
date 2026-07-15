"""Requestor group management routes for users."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from . import users as users_core
from .database import get_db

router = APIRouter(prefix="/api/users", tags=["users"])


def _normalize_group(value: str | None) -> str:
    return (value or "").strip().lower()


def _group_label(value: str | None) -> str:
    normalized = _normalize_group(value)
    if not normalized:
        return ""
    return " ".join(part.upper() if len(part) <= 3 else part[:1].upper() + part[1:] for part in normalized.split())


def _clean_group_label(value: str | None) -> str:
    return (value or "").strip()


def _group_label_map(db: Session) -> dict[str, str]:
    labels: dict[str, str] = {}
    definition_rows = db.query(models.RequestorGroup).order_by(models.RequestorGroup.id.asc()).all()
    for row in definition_rows:
        group = _normalize_group(getattr(row, "name", None))
        label = _clean_group_label(getattr(row, "label", None))
        if group and label:
            labels[group] = label

    raw_sources = [
        db.query(models.User.requestor_group).filter(models.User.requestor_group.isnot(None)).all(),
        db.query(models.CaseRequestor.requestor_group).filter(models.CaseRequestor.requestor_group.isnot(None)).all(),
        db.query(models.AccountRegistrationRequest.requestor_group).filter(models.AccountRegistrationRequest.requestor_group.isnot(None)).all(),
        db.query(models.NTPTemplateGroup.group_name).filter(models.NTPTemplateGroup.group_name.isnot(None)).all(),
        db.query(models.RequestorGroupAccess.source_group).all(),
        db.query(models.RequestorGroupAccess.target_group).all(),
    ]
    for rows in raw_sources:
        for (value,) in rows:
            group = _normalize_group(value)
            label = _clean_group_label(value)
            if group and label and group not in labels:
                labels[group] = label
    return labels


def _all_requestor_groups(db: Session) -> list[str]:
    groups: set[str] = set()
    sources = [
        db.query(models.RequestorGroup.name).filter(models.RequestorGroup.name.isnot(None)).all(),
        db.query(models.User.requestor_group).filter(models.User.requestor_group.isnot(None)).all(),
        db.query(models.CaseRequestor.requestor_group).filter(models.CaseRequestor.requestor_group.isnot(None)).all(),
        db.query(models.AccountRegistrationRequest.requestor_group).filter(models.AccountRegistrationRequest.requestor_group.isnot(None)).all(),
        db.query(models.NTPTemplateGroup.group_name).filter(models.NTPTemplateGroup.group_name.isnot(None)).all(),
        db.query(models.RequestorGroupAccess.source_group).all(),
        db.query(models.RequestorGroupAccess.target_group).all(),
    ]
    for rows in sources:
        for (value,) in rows:
            group = _normalize_group(value)
            if group:
                groups.add(group)
    return sorted(groups)



@router.get("/groups")
def list_groups(
    db: Session = Depends(get_db),
    actor: models.User = Depends(users_core.get_current_admin),
):
    groups = _all_requestor_groups(db)
    label_map = _group_label_map(db)
    user_rows = db.query(models.User).filter(models.User.requestor_group.isnot(None)).all()
    users_by_group: dict[str, list[dict]] = {group: [] for group in groups}
    for row in user_rows:
        group = _normalize_group(getattr(row, "requestor_group", None))
        if not group:
            continue
        users_by_group.setdefault(group, []).append(users_core._serialize_user(row))
    access_rows = db.query(models.RequestorGroupAccess).all()
    access_map: dict[str, list[str]] = {group: [] for group in groups}
    for row in access_rows:
        source = _normalize_group(getattr(row, "source_group", None))
        target = _normalize_group(getattr(row, "target_group", None))
        if source and target:
            access_map.setdefault(source, []).append(target)
    items = [
        {
            "name": group,
            "label": label_map.get(group) or _group_label(group),
            "user_count": len(users_by_group.get(group, [])),
            "users": sorted(users_by_group.get(group, []), key=lambda item: ((item.get("last_name") or ""), (item.get("first_name") or ""), (item.get("email") or ""))),
            "can_see_groups": sorted(set(access_map.get(group, []))),
        }
        for group in groups
    ]
    return sorted(items, key=lambda item: ((item.get("label") or item.get("name") or "").lower(), item.get("name") or ""))


@router.post("/groups", status_code=status.HTTP_201_CREATED)
def create_group(
    payload: dict,
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(users_core.get_current_admin),
):
    data = payload or {}
    raw_name = _clean_group_label(data.get("name"))
    group = _normalize_group(raw_name)
    if not group:
        raise HTTPException(status_code=400, detail="Group name is required")
    label = raw_name or _group_label(group)
    if group in set(_all_requestor_groups(db)):
        raise HTTPException(status_code=400, detail="A group with that name already exists")
    raw_targets = data.get("can_see_groups") or []
    if not isinstance(raw_targets, list):
        raise HTTPException(status_code=400, detail="can_see_groups must be a list")
    targets = sorted({
        _normalize_group(value)
        for value in raw_targets
        if _normalize_group(value) and _normalize_group(value) != group
    })

    row = models.RequestorGroup(name=group, label=label)
    db.add(row)
    valid_groups = set(_all_requestor_groups(db))
    valid_groups.add(group)
    for target in targets:
        if target not in valid_groups:
            raise HTTPException(status_code=400, detail=f"Unknown group: {target}")
        db.add(models.RequestorGroupAccess(source_group=group, target_group=target))
    db.commit()
    db.refresh(row)
    try:
        users_core.log_event(
            db,
            action="user_create",
            actor_id=actor.id,
            target_type="requestor_group",
            target_id=row.id,
            details={"group": group, "label": label, "can_see_groups": targets},
            request=request,
        )
    except Exception as exc:
        users_core._debug_suppressed("suppressed exception in users.py:group_create_audit", exc)
    return {"ok": True, "name": group, "label": label}


@router.patch("/groups/{group_name}")
def update_group(
    group_name: str,
    payload: dict,
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(users_core.get_current_admin),
):
    old_group = _normalize_group(group_name)
    if not old_group:
        raise HTTPException(status_code=400, detail="Group is required")
    data = payload or {}
    raw_name = _clean_group_label(data.get("name") or old_group)
    new_group = _normalize_group(raw_name or old_group)
    if not new_group:
        raise HTTPException(status_code=400, detail="Group name is required")
    new_label = raw_name or _group_label(new_group)
    all_groups = set(_all_requestor_groups(db))
    if old_group not in all_groups:
        raise HTTPException(status_code=404, detail="Group not found")
    if new_group != old_group and new_group in all_groups:
        raise HTTPException(status_code=400, detail="A group with that name already exists")

    raw_targets = data.get("can_see_groups") or []
    if not isinstance(raw_targets, list):
        raise HTTPException(status_code=400, detail="can_see_groups must be a list")
    targets = sorted({
        _normalize_group(value)
        for value in raw_targets
        if _normalize_group(value) and _normalize_group(value) not in {old_group, new_group}
    })

    try:
        definition = (
            db.query(models.RequestorGroup)
            .filter(func.lower(models.RequestorGroup.name) == old_group)
            .first()
        )
        if new_group != old_group:
            db.query(models.User).filter(func.lower(models.User.requestor_group) == old_group).update(
                {models.User.requestor_group: new_group},
                synchronize_session=False,
            )
            db.query(models.CaseRequestor).filter(func.lower(models.CaseRequestor.requestor_group) == old_group).update(
                {models.CaseRequestor.requestor_group: new_group},
                synchronize_session=False,
            )
            db.query(models.AccountRegistrationRequest).filter(func.lower(models.AccountRegistrationRequest.requestor_group) == old_group).update(
                {models.AccountRegistrationRequest.requestor_group: new_group},
                synchronize_session=False,
            )
            db.query(models.NTPTemplateGroup).filter(func.lower(models.NTPTemplateGroup.group_name) == old_group).update(
                {models.NTPTemplateGroup.group_name: new_group},
                synchronize_session=False,
            )
            db.query(models.RequestorGroupAccess).filter(func.lower(models.RequestorGroupAccess.source_group) == old_group).update(
                {models.RequestorGroupAccess.source_group: new_group},
                synchronize_session=False,
            )
            db.query(models.RequestorGroupAccess).filter(func.lower(models.RequestorGroupAccess.target_group) == old_group).update(
                {models.RequestorGroupAccess.target_group: new_group},
                synchronize_session=False,
            )
            if definition is not None:
                definition.name = new_group
        if definition is None:
            definition = models.RequestorGroup(name=new_group, label=new_label)
            db.add(definition)
        else:
            definition.label = new_label

        db.query(models.RequestorGroupAccess).filter(func.lower(models.RequestorGroupAccess.source_group) == new_group).delete(synchronize_session=False)
        valid_groups = set(_all_requestor_groups(db))
        valid_groups.add(new_group)
        for target in targets:
            if target not in valid_groups:
                raise HTTPException(status_code=400, detail=f"Unknown group: {target}")
            db.add(models.RequestorGroupAccess(source_group=new_group, target_group=target))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unable to update group") from exc

    try:
        users_core.log_event(
            db,
            action="user_update",
            actor_id=actor.id,
            target_type="requestor_group",
            details={"group": old_group, "new_group": new_group, "label": new_label, "can_see_groups": targets},
            request=request,
        )
    except Exception as exc:
        users_core._debug_suppressed("suppressed exception in users.py:group_update_audit", exc)
    return {"ok": True, "name": new_group, "label": new_label}


