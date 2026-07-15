from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, selectinload

from . import models
from .auth import current_user as get_current_user
from .database import get_db
from . import ntp as ntp_core

router = APIRouter(prefix="/api", tags=["ntp"])

@router.get("/ntp/templates")
def list_ntp_templates(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    templates = ntp_core._templates_for_user(db, user)
    default_reminder_id: Optional[int] = None
    try:
        reminder_candidates = [
            int(getattr(t, "id", 0) or 0)
            for t in templates
            if isinstance(getattr(t, "name", None), str) and ("reminder" in t.name.lower())
        ]
        reminder_candidates = [cid for cid in reminder_candidates if cid > 0]
        default_reminder_id = min(reminder_candidates) if reminder_candidates else None
    except Exception:
        default_reminder_id = None
    return [ntp_core._template_response(t, user=user, default_reminder_id=default_reminder_id) for t in templates]

@router.post("/ntp/templates", status_code=201)
def create_ntp_template(
    payload: ntp_core.TemplatePayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    manager_group = None
    if ntp_core.is_requestor(user):
        manager_group = ntp_core._user_group(user)
        if not manager_group:
            raise HTTPException(status_code=403, detail="Requestor accounts must belong to a group to manage templates.")
    else:
        ntp_core.ensure_case_editable(user)
    exists = db.query(models.NTPTemplate).filter(models.NTPTemplate.name.ilike(payload.name.strip())).first()
    if exists:
        raise HTTPException(status_code=409, detail="Template name already exists")
    try:
        clean_body = ntp_core._sanitize_template_html(payload.body)
    except Exception as exc:
        logger.exception("Failed to sanitize NTP template body (create)")
        raise HTTPException(status_code=400, detail="Template body contains unsupported HTML/style") from exc
    row = models.NTPTemplate(
        name=payload.name.strip(),
        subject=payload.subject.strip(),
        body=clean_body,
        description=(payload.description or "").strip() or None,
        cc=(payload.cc or "").strip() or None,
        bcc=None,
        high_importance=bool(payload.high_importance),
        created_by=user.id,
    )
    groups = payload.groups
    if manager_group:
        groups = [manager_group]
    ntp_core._apply_template_groups(row, groups)
    db.add(row)
    db.flush()
    if payload.is_default:
        user.ntp_default_template_id = row.id
    db.commit()
    db.refresh(row)
    try:
        ntp_core.log_event(
            db,
            action="ntp_template_create",
            target_type="ntp_template",
            target_id=row.id,
            actor_id=user.id,
            details={"template_id": row.id, "name": row.name},
        )
    except Exception as exc:
        ntp_core._debug_suppressed("suppressed exception in ntp.py:661", exc)
    return {"ok": True}


@router.put("/ntp/templates/{template_id}")
def update_ntp_template(
    template_id: int,
    payload: ntp_core.TemplatePayload,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    row = (
        db.query(models.NTPTemplate)
        .options(selectinload(models.NTPTemplate.groups))
        .filter(models.NTPTemplate.id == template_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    manager_group = None
    if ntp_core.is_requestor(user):
        manager_group = ntp_core._user_group(user)
        if not manager_group:
            raise HTTPException(status_code=403, detail="Requestor accounts must belong to a group to manage templates.")
        if manager_group not in ntp_core._template_group_names(row):
            raise HTTPException(status_code=403, detail="Template is not assigned to your group.")
    else:
        ntp_core.ensure_case_editable(user)
    conflict = (
        db.query(models.NTPTemplate)
        .filter(models.NTPTemplate.id != template_id, models.NTPTemplate.name.ilike(payload.name.strip()))
        .first()
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Template name already exists")
    row.name = payload.name.strip()
    row.subject = payload.subject.strip()
    try:
        row.body = ntp_core._sanitize_template_html(payload.body)
    except Exception as exc:
        logger.exception("Failed to sanitize NTP template body (update)")
        raise HTTPException(status_code=400, detail="Template body contains unsupported HTML/style") from exc
    row.description = (payload.description or "").strip() or None
    row.cc = (payload.cc or "").strip() or None
    row.bcc = None
    row.high_importance = bool(payload.high_importance)
    if payload.is_default:
        user.ntp_default_template_id = row.id
    elif getattr(user, "ntp_default_template_id", None) == row.id:
        user.ntp_default_template_id = None
    groups = payload.groups
    if manager_group:
        groups = ntp_core._template_group_names(row) or [manager_group]
    ntp_core._apply_template_groups(row, groups)
    db.commit()
    db.refresh(row)
    try:
        ntp_core.log_event(
            db,
            action="ntp_template_update",
            target_type="ntp_template",
            target_id=row.id,
            actor_id=user.id,
            details={"template_id": row.id, "name": row.name},
            request=request,
        )
    except Exception as exc:
        ntp_core._debug_suppressed("suppressed exception in ntp.py:728", exc)
    return ntp_core._template_response(row, user=user)


@router.delete("/ntp/templates/{template_id}", status_code=204)
def delete_ntp_template(
    template_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    row = (
        db.query(models.NTPTemplate)
        .options(selectinload(models.NTPTemplate.groups))
        .filter(models.NTPTemplate.id == template_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    if ntp_core.is_requestor(user):
        manager_group = ntp_core._user_group(user)
        if not manager_group:
            raise HTTPException(status_code=403, detail="Requestor accounts must belong to a group to manage templates.")
        template_groups = ntp_core._template_group_names(row)
        if template_groups != [manager_group]:
            raise HTTPException(status_code=403, detail="Only templates dedicated to your group can be deleted.")
    else:
        ntp_core.ensure_case_editable(user)
    db.delete(row)
    db.commit()
    try:
        ntp_core.log_event(
            db,
            action="ntp_template_delete",
            target_type="ntp_template",
            target_id=template_id,
            actor_id=user.id,
            details={"template_id": template_id, "name": row.name},
        )
    except Exception as exc:
        ntp_core._debug_suppressed("suppressed exception in ntp.py:767", exc)


@router.get("/ntp/groups")
def list_ntp_groups(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if ntp_core.is_requestor(user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    groups = set()
    rows = (
        db.query(models.User.requestor_group)
        .filter(models.User.requestor_group.isnot(None))
        .all()
    )
    for (value,) in rows:
        norm = ntp_core._normalize_group_name(value)
        if norm:
            groups.add(norm)
    template_rows = (
        db.query(models.NTPTemplateGroup.group_name)
        .distinct()
        .all()
    )
    for (value,) in template_rows:
        norm = ntp_core._normalize_group_name(value)
        if norm:
            groups.add(norm)
    return {"groups": sorted(groups)}
