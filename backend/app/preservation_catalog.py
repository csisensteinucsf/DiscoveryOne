from __future__ import annotations

from typing import Any

from .system_admin_config import normalize_preservation_sources, preservation_source_key
from .system_settings import load_system_settings


BUILTIN_HOLD_FIELDS: dict[str, str] = {
    "email": "holds_email",
    "onedrive": "holds_onedrive",
    "gdrive": "holds_gdrive",
    "box": "holds_box",
    "slack": "holds_slack",
    "rubrik_restore": "holds_rubrik_restore",
}

SOURCE_ALIASES: dict[str, str] = {
    "mailbox": "email",
    "mail": "email",
    "o365": "email",
    "m365": "email",
    "site": "onedrive",
    "one_drive": "onedrive",
    "google_drive": "gdrive",
    "drive": "gdrive",
    "google": "gdrive",
    "rubrik": "rubrik_restore",
}


def source_key(value: Any) -> str:
    key = preservation_source_key(value)
    return SOURCE_ALIASES.get(key, key)


def preservation_sources_raw() -> list[dict[str, Any]]:
    try:
        raw = load_system_settings().get("preservation_sources") or []
    except Exception:
        return []
    return raw if isinstance(raw, list) else []


def preservation_sources(*, enabled_only: bool = False) -> list[dict[str, Any]]:
    sources = normalize_preservation_sources(preservation_sources_raw())
    if enabled_only:
        sources = [item for item in sources if item.get("enabled") is not False]
    return sources


def configured_custom_hold_sources(*, enabled_only: bool = True) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in preservation_sources(enabled_only=enabled_only):
        key = source_key(item.get("key") or item.get("label"))
        if not key or key in BUILTIN_HOLD_FIELDS or key in seen:
            continue
        seen.add(key)
        label = str(item.get("label") or key).strip() or key
        sources.append((key, label))
    return sources


def configured_hold_catalog(
    *,
    enabled_only: bool = True,
) -> list[tuple[str, str | None, str]]:
    catalog = [
        (key, field, label)
        for key, field, label in configured_builtin_hold_fields(
            enabled_only=enabled_only
        )
    ]
    catalog.extend(
        (key, None, label)
        for key, label in configured_custom_hold_sources(
            enabled_only=enabled_only
        )
    )
    return catalog

def configured_builtin_hold_fields(*, enabled_only: bool = True) -> list[tuple[str, str, str]]:
    fields: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in preservation_sources(enabled_only=enabled_only):
        key = source_key(item.get("key") or item.get("label"))
        field = BUILTIN_HOLD_FIELDS.get(key)
        if not field or key in seen:
            continue
        seen.add(key)
        label = str(item.get("label") or key).strip() or key
        fields.append((key, field, label))
    return fields


def hold_field_for_source(value: Any) -> str:
    return BUILTIN_HOLD_FIELDS.get(source_key(value), "")


def hold_source_for_field(field_name: Any) -> str:
    field = str(field_name or "").strip()
    for key, candidate in BUILTIN_HOLD_FIELDS.items():
        if candidate == field:
            return key
    return ""


def configured_hold_keys(*, enabled_only: bool = True) -> list[str]:
    return [key for key, _field, _label in configured_builtin_hold_fields(enabled_only=enabled_only)]


def configured_hold_field_names(*, enabled_only: bool = True) -> list[str]:
    return [field for _key, field, _label in configured_builtin_hold_fields(enabled_only=enabled_only)]


def custodian_configured_hold_flags(custodian: Any, *, enabled_only: bool = True) -> dict[str, bool]:
    flags = {
        key: bool(getattr(custodian, field, False))
        for key, field, _label in configured_builtin_hold_fields(
            enabled_only=enabled_only
        )
    }
    configured_custom = {
        key for key, _label in configured_custom_hold_sources(
            enabled_only=enabled_only
        )
    }
    custom_records = getattr(custodian, "custom_preservation", None) or []
    records_by_key = {
        source_key(getattr(record, "source_key", None)): record
        for record in custom_records
    }
    for key in configured_custom:
        record = records_by_key.get(key)
        flags[key] = bool(getattr(record, "active", False)) if record else False
    return flags


def custodian_has_configured_hold(custodian: Any, *, enabled_only: bool = True) -> bool:
    return any(custodian_configured_hold_flags(custodian, enabled_only=enabled_only).values())
