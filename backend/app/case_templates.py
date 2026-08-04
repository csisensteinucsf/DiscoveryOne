from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .audit import log_event
from .auth import current_user, require_admin
from .database import get_db


router = APIRouter(prefix="/api/case-templates", tags=["case templates"])

TEMPLATE_FIELDS = {
    "legal_case_name",
    "claimant",
    "internal_counsel",
    "outside_counsel",
    "matter_number",
    "requestor",
    "requestors",
    "analyst_id",
    "is_private",
    "description",
    "start_date",
    "closure_nag_days",
}
BOOLEAN_FIELDS = {"is_private"}
LIST_FIELDS = {"requestors"}
INTEGER_FIELDS = {"analyst_id", "closure_nag_days"}


def _template_response(row: models.CaseTemplate) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "enabled": bool(row.enabled),
        "is_default": bool(row.is_default),
        "sort_order": int(row.sort_order or 0),
        "defaults": row.defaults,
        "field_rules": row.field_rules,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _normalize_defaults(values: dict[str, Any] | None) -> dict[str, Any]:
    raw = values or {}
    unknown = sorted(set(raw) - TEMPLATE_FIELDS - {"start_date_mode"})
    if unknown:
        raise HTTPException(status_code=422, detail={"message": "Unsupported case template defaults", "fields": unknown})
    normalized: dict[str, Any] = {}
    for field, value in raw.items():
        if field == "start_date_mode":
            mode = str(value or "blank").strip().lower()
            if mode not in {"blank", "today"}:
                raise HTTPException(status_code=422, detail="start_date_mode must be blank or today")
            normalized[field] = mode
            continue
        if field in BOOLEAN_FIELDS:
            normalized[field] = bool(value)
        elif field in LIST_FIELDS:
            if not isinstance(value, list):
                raise HTTPException(status_code=422, detail=f"{field} must be a list")
            normalized[field] = value
        elif field in INTEGER_FIELDS:
            if value in (None, ""):
                normalized[field] = None
            else:
                try:
                    number = int(value)
                except (TypeError, ValueError) as exc:
                    raise HTTPException(status_code=422, detail=f"{field} must be an integer") from exc
                if field == "closure_nag_days" and not 1 <= number <= 3650:
                    raise HTTPException(status_code=422, detail="closure_nag_days must be between 1 and 3650")
                normalized[field] = number
        elif value is None:
            normalized[field] = None
        else:
            normalized[field] = str(value).strip()
    return normalized


def _normalize_rules(values: dict[str, Any] | None) -> dict[str, dict[str, bool]]:
    raw = values or {}
    unknown = sorted(set(raw) - TEMPLATE_FIELDS)
    if unknown:
        raise HTTPException(status_code=422, detail={"message": "Unsupported case template field rules", "fields": unknown})
    normalized: dict[str, dict[str, bool]] = {}
    for field, value in raw.items():
        if isinstance(value, schemas.CaseTemplateFieldRule):
            value = value.model_dump()
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail=f"Rule for {field} must be an object")
        visible = bool(value.get("visible", True))
        required = bool(value.get("required", False))
        if required and not visible:
            raise HTTPException(status_code=422, detail=f"{field} cannot be required while hidden")
        normalized[field] = {"visible": visible, "required": required}
    return normalized


def _set_default(db: Session, row: models.CaseTemplate, enabled: bool) -> None:
    if enabled:
        db.query(models.CaseTemplate).filter(models.CaseTemplate.id != row.id).update(
            {models.CaseTemplate.is_default: False},
            synchronize_session=False,
        )
    row.is_default = enabled


def apply_case_template(db: Session, payload: schemas.CaseCreate) -> tuple[schemas.CaseCreate, models.CaseTemplate | None]:
    template_id = getattr(payload, "case_template_id", None)
    if template_id is None:
        return payload, None
    template = db.get(models.CaseTemplate, int(template_id))
    if template is None or not template.enabled:
        raise HTTPException(status_code=422, detail="Selected case template is unavailable")

    defaults = _normalize_defaults(template.defaults)
    rules = _normalize_rules(template.field_rules)
    fields_set = set(getattr(payload, "model_fields_set", set()))
    updates: dict[str, Any] = {}

    if defaults.get("start_date_mode") == "today" and "start_date" not in fields_set:
        updates["start_date"] = date.today().isoformat()

    for field in TEMPLATE_FIELDS:
        rule = rules.get(field, {"visible": True, "required": False})
        if not rule["visible"]:
            if field in defaults:
                updates[field] = defaults[field]
            elif field in BOOLEAN_FIELDS:
                updates[field] = False
            elif field in LIST_FIELDS:
                updates[field] = []
            else:
                updates[field] = None
        elif field not in fields_set and field in defaults:
            updates[field] = defaults[field]

    applied = payload.model_copy(update=updates)
    missing: list[str] = []
    for field, rule in rules.items():
        if not rule.get("required"):
            continue
        value = getattr(applied, field, None)
        if value is None or value == "" or value == []:
            missing.append(field)
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Required case template fields are missing", "fields": sorted(missing)},
        )
    return applied, template


@router.get("")
def list_case_templates(
    include_disabled: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    query = db.query(models.CaseTemplate)
    if include_disabled:
        if not bool(getattr(user, "is_admin", False)):
            raise HTTPException(status_code=403, detail="Admin required")
    else:
        query = query.filter(models.CaseTemplate.enabled.is_(True))
    rows = query.order_by(models.CaseTemplate.sort_order, models.CaseTemplate.name).all()
    return [_template_response(row) for row in rows]


@router.post("", status_code=201)
def create_case_template(
    payload: schemas.CaseTemplateCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    row = models.CaseTemplate(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        enabled=payload.enabled,
        sort_order=payload.sort_order,
        created_by_id=user.id,
        updated_by_id=user.id,
    )
    row.defaults = _normalize_defaults(payload.defaults)
    row.field_rules = _normalize_rules(payload.field_rules)
    db.add(row)
    try:
        db.flush()
        _set_default(db, row, bool(payload.is_default))
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Case template name already exists") from exc
    log_event(
        db,
        action="case_template_create",
        target_type="case_template",
        target_id=row.id,
        actor_id=user.id,
        details={"name": row.name},
        request=request,
    )
    return _template_response(row)


@router.put("/{template_id}")
def update_case_template(
    template_id: int,
    payload: schemas.CaseTemplateUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    row = db.get(models.CaseTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case template not found")
    changed = payload.model_fields_set
    if "name" in changed and payload.name is not None:
        row.name = payload.name.strip()
    if "description" in changed:
        row.description = (payload.description or "").strip() or None
    if "enabled" in changed and payload.enabled is not None:
        row.enabled = payload.enabled
        if not row.enabled:
            row.is_default = False
    if "sort_order" in changed and payload.sort_order is not None:
        row.sort_order = payload.sort_order
    if "defaults" in changed:
        row.defaults = _normalize_defaults(payload.defaults)
    if "field_rules" in changed:
        row.field_rules = _normalize_rules(payload.field_rules)
    if "is_default" in changed and payload.is_default is not None:
        if payload.is_default and not row.enabled:
            raise HTTPException(status_code=422, detail="A disabled template cannot be the default")
        _set_default(db, row, payload.is_default)
    row.updated_by_id = user.id
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Case template name already exists") from exc
    log_event(
        db,
        action="case_template_update",
        target_type="case_template",
        target_id=row.id,
        actor_id=user.id,
        details={"name": row.name},
        request=request,
    )
    return _template_response(row)


@router.delete("/{template_id}", status_code=204)
def delete_case_template(
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_admin),
):
    row = db.get(models.CaseTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Case template not found")
    if db.query(models.Case.id).filter(models.Case.case_template_id == row.id).first():
        raise HTTPException(status_code=409, detail="Disable templates that have already been used instead of deleting them")
    name = row.name
    db.delete(row)
    db.commit()
    log_event(
        db,
        action="case_template_delete",
        target_type="case_template",
        target_id=template_id,
        actor_id=user.id,
        details={"name": name},
        request=request,
    )
