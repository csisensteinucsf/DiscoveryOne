from __future__ import annotations

from typing import Any

from .hold_source_provider_registry import (
    HoldSourceOperationContext,
    get_hold_source_provider_adapter,
    hold_source_provider_display_name,
    normalize_hold_source_key,
)


def hold_source_label(source_key: str | None) -> str:
    normalized = normalize_hold_source_key(source_key)
    return (
        hold_source_provider_display_name(normalized)
        or normalized.replace("_", " ").title()
        or "Preservation source"
    )


def hold_source_automation_ready(source_key: str | None) -> bool:
    adapter = get_hold_source_provider_adapter(source_key)
    if adapter is None:
        return False
    try:
        return bool(adapter.is_available())
    except Exception:
        return False


def sync_custodian_hold(
    *,
    source_key: str,
    case: Any,
    custodian: Any,
    custodian_email: str,
    enable: bool,
    db: Any = None,
    request: Any = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    normalized = normalize_hold_source_key(source_key)
    adapter = get_hold_source_provider_adapter(normalized)
    if adapter is None:
        return {
            "source_key": normalized,
            "provider": "none",
            "status": "skipped",
            "reason": "automation_not_installed",
        }
    try:
        available = bool(adapter.is_available())
    except Exception:
        available = False
    if not available:
        return {
            "source_key": normalized,
            "provider": getattr(adapter, "source_key", normalized),
            "status": "skipped",
            "reason": "automation_not_configured",
        }
    result = adapter.sync_custodian_hold(
        case=case,
        custodian=custodian,
        custodian_email=custodian_email,
        enable=bool(enable),
        context=HoldSourceOperationContext(
            db=db,
            request=request,
            actor_id=actor_id,
        ),
    )
    if isinstance(result, dict):
        return result
    return {
        "source_key": normalized,
        "provider": getattr(adapter, "source_key", normalized),
        "status": "enabled" if enable else "released",
        "result": result,
    }
