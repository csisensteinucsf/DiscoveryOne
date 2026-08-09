from __future__ import annotations

from datetime import date
import math
import re
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
    "is_test_case",
    "description",
    "start_date",
    "closure_nag_days",
}
BOOLEAN_FIELDS = {"is_private", "is_test_case"}
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
        "custom_fields": row.custom_fields,
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


CUSTOM_FIELD_TYPES = {"text", "textarea", "number", "date", "checkbox", "select"}
CUSTOM_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _normalize_custom_value(definition: dict[str, Any], value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    field_type = definition["field_type"]
    if value is None or value == "":
        return None
    if field_type in {"text", "textarea"}:
        return str(value).strip()
    if field_type == "number":
        if isinstance(value, bool):
            raise HTTPException(status_code=422, detail=f'{definition["label"]} must be a number')
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f'{definition["label"]} must be a number') from exc
        if not math.isfinite(number):
            raise HTTPException(status_code=422, detail=f'{definition["label"]} must be a finite number')
        return int(number) if number.is_integer() else number
    if field_type == "date":
        try:
            return date.fromisoformat(str(value).strip()).isoformat()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f'{definition["label"]} must be a valid date') from exc
    if field_type == "checkbox":
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise HTTPException(status_code=422, detail=f'{definition["label"]} must be true or false')
    if field_type == "select":
        normalized = str(value).strip()
        if normalized not in definition["options"]:
            raise HTTPException(status_code=422, detail=f'Unsupported value for {definition["label"]}')
        return normalized
    raise HTTPException(status_code=422, detail=f"Unsupported custom field type: {field_type}")


def _normalize_custom_fields(values: list[Any] | None) -> list[dict[str, Any]]:
    raw_fields = values or []
    if not isinstance(raw_fields, list):
        raise HTTPException(status_code=422, detail="custom_fields must be a list")
    if len(raw_fields) > 25:
        raise HTTPException(status_code=422, detail="A case template can define at most 25 custom fields")

    normalized: list[dict[str, Any]] = []
    keys: set[str] = set()
    labels: set[str] = set()
    for value in raw_fields:
        if isinstance(value, schemas.CaseTemplateCustomField):
            value = value.model_dump()
        if not isinstance(value, dict):
            raise HTTPException(status_code=422, detail="Each custom field must be an object")

        key = str(value.get("key") or "").strip().lower()
        label = str(value.get("label") or "").strip()
        field_type = str(value.get("field_type") or "text").strip().lower()
        if not CUSTOM_FIELD_KEY_RE.fullmatch(key):
            raise HTTPException(status_code=422, detail=f"Invalid custom field key: {key or '(blank)'}")
        if key in keys:
            raise HTTPException(status_code=422, detail=f"Duplicate custom field key: {key}")
        if not label:
            raise HTTPException(status_code=422, detail="Custom field labels are required")
        if label.casefold() in labels:
            raise HTTPException(status_code=422, detail=f"Duplicate custom field label: {label}")
        if field_type not in CUSTOM_FIELD_TYPES:
            raise HTTPException(status_code=422, detail=f"Unsupported custom field type: {field_type}")

        options: list[str] = []
        if field_type == "select":
            source_options = value.get("options") or []
            if not isinstance(source_options, list):
                raise HTTPException(status_code=422, detail=f"Options for {label} must be a list")
            for option in source_options:
                cleaned = str(option or "").strip()
                if cleaned and cleaned not in options:
                    options.append(cleaned)
            if not options:
                raise HTTPException(status_code=422, detail=f"Dropdown field {label} requires at least one option")

        definition = {
            "key": key,
            "label": label,
            "field_type": field_type,
            "required": bool(value.get("required", False)),
            "options": options,
            "default_value": None,
        }
        default_value = value.get("default_value")
        if default_value is not None and default_value != "":
            definition["default_value"] = _normalize_custom_value(definition, default_value)

        keys.add(key)
        labels.add(label.casefold())
        normalized.append(definition)
    return normalized


def _normalize_case_custom_fields(
    definitions: list[Any] | None,
    values: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    normalized_definitions = _normalize_custom_fields(definitions)
    raw_values = values or {}
    if not isinstance(raw_values, dict):
        raise HTTPException(status_code=422, detail="Case custom_fields must be an object")

    allowed = {definition["key"] for definition in normalized_definitions}
    unknown = sorted(set(raw_values) - allowed)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail={"message": "Unsupported custom case fields", "fields": unknown},
        )

    result: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for definition in normalized_definitions:
        key = definition["key"]
        source = raw_values[key] if key in raw_values else definition.get("default_value")
        if source is None and definition["field_type"] == "checkbox":
            source = False
        normalized_value = _normalize_custom_value(definition, source)
        if definition["required"] and (normalized_value is None or normalized_value == ""):
            missing.append(f"custom_fields.{key}")
        result[key] = {
            "label": definition["label"],
            "field_type": definition["field_type"],
            "required": definition["required"],
            "options": list(definition["options"]),
            "value": normalized_value,
        }
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Required case template fields are missing", "fields": missing},
        )
    return result


def normalize_existing_case_custom_fields(
    existing: dict[str, Any] | None,
    values: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    existing = existing or {}
    definitions: list[dict[str, Any]] = []
    merged_values: dict[str, Any] = {}
    for key, entry in existing.items():
        if not isinstance(entry, dict):
            continue
        definitions.append({
            "key": key,
            "label": entry.get("label") or key.replace("_", " ").title(),
            "field_type": entry.get("field_type") or "text",
            "required": bool(entry.get("required", False)),
            "options": entry.get("options") or [],
        })
        merged_values[key] = entry.get("value")
    if values:
        merged_values.update(values)
    return _normalize_case_custom_fields(definitions, merged_values)

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
        if getattr(payload, "custom_fields", None):
            raise HTTPException(status_code=422, detail="Custom fields require a case template")
        return payload, None
    template = db.get(models.CaseTemplate, int(template_id))
    if template is None or not template.enabled:
        raise HTTPException(status_code=422, detail="Selected case template is unavailable")

    defaults = _normalize_defaults(template.defaults)
    rules = _normalize_rules(template.field_rules)
    fields_set = set(getattr(payload, "model_fields_set", set()))
    custom_definitions = _normalize_custom_fields(template.custom_fields)
    updates: dict[str, Any] = {}

    updates["custom_fields"] = _normalize_case_custom_fields(custom_definitions, payload.custom_fields)
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
    row.custom_fields = _normalize_custom_fields(payload.custom_fields)
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
    if "custom_fields" in changed:
        row.custom_fields = _normalize_custom_fields(payload.custom_fields)
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
