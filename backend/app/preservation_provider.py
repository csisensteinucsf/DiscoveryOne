from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .integration_settings import provider_value
from .preservation_provider_registry import (
    PreservationOperationContext,
    PreservationProviderAdapter,
    get_preservation_provider_adapter,
    preservation_provider_display_name,
)


def current_preservation_provider() -> str:
    return provider_value("preservation_provider", default="none")


def preservation_provider_label() -> str:
    provider = current_preservation_provider()
    return (
        preservation_provider_display_name(provider)
        or str(provider or "Preservation provider").replace("_", " ").title()
    )


def _active_adapter(*, required: bool) -> PreservationProviderAdapter | None:
    provider = current_preservation_provider()
    if provider not in {"", "none"}:
        adapter = get_preservation_provider_adapter(provider)
        if adapter is None:
            if required:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"Preservation provider '{provider}' is not installed. "
                        "Select an available provider in System > Integrations."
                    ),
                )
            return None
        return adapter

    if required:
        raise HTTPException(
            status_code=503,
            detail=(
                "No automated preservation provider is configured. "
                "Manual hold tracking remains available."
            ),
        )
    return None


def preservation_automation_ready() -> bool:
    adapter = _active_adapter(required=False)
    if adapter is None:
        return False
    try:
        return bool(adapter.is_available())
    except Exception:
        return False


def status_poll_delay_seconds() -> float:
    adapter = _active_adapter(required=False)
    if adapter is None:
        return 0.0
    try:
        if not adapter.is_available():
            return 0.0
        poll_delay = getattr(adapter, "status_poll_delay_seconds", None)
        if not callable(poll_delay):
            return 0.0
        return max(0.0, float(poll_delay()))
    except Exception:
        return 0.0


def _context(*, db: Any, request: Any = None, user: Any = None) -> PreservationOperationContext:
    return PreservationOperationContext(db=db, request=request, user=user)


def create_case(
    *,
    case_id: int,
    db: Any,
    request: Any = None,
    user: Any = None,
) -> Any:
    adapter = _active_adapter(required=True)
    return adapter.create_case(
        case_id=case_id,
        context=_context(db=db, request=request, user=user),
    )


def get_status(
    *,
    case_id: int,
    db: Any,
    request: Any = None,
    user: Any = None,
) -> Any:
    adapter = _active_adapter(required=True)
    return adapter.get_status(
        case_id=case_id,
        context=_context(db=db, request=request, user=user),
    )


def apply_holds(
    *,
    case_id: int,
    payload: Any,
    db: Any,
    request: Any = None,
    user: Any = None,
) -> Any:
    adapter = _active_adapter(required=True)
    return adapter.apply_holds(
        case_id=case_id,
        payload=payload,
        context=_context(db=db, request=request, user=user),
    )


def release_holds(
    *,
    case_id: int,
    payload: Any,
    db: Any,
    request: Any = None,
    user: Any = None,
) -> Any:
    adapter = _active_adapter(required=True)
    return adapter.release_holds(
        case_id=case_id,
        payload=payload,
        context=_context(db=db, request=request, user=user),
    )



def remove_custodian(
    *,
    case_id: int,
    custodian_id: int,
    custodian_name: str | None,
    custodian_email: str | None,
    db: Any,
    request: Any = None,
    user: Any = None,
) -> dict[str, Any]:
    adapter = _active_adapter(required=False)
    if adapter is None:
        return {
            "provider": "none",
            "status": "skipped",
            "reason": "automation_not_configured",
            "compatibility_fields": {},
        }
    try:
        if not adapter.is_available():
            return {
                "provider": getattr(adapter, "name", "unknown"),
                "status": "skipped",
                "reason": "automation_not_configured",
                "compatibility_fields": {},
            }
    except Exception:
        return {
            "provider": getattr(adapter, "name", "unknown"),
            "status": "skipped",
            "reason": "automation_not_available",
            "compatibility_fields": {},
        }

    operation = getattr(adapter, "remove_custodian", None)
    if not callable(operation):
        return {
            "provider": getattr(adapter, "name", "unknown"),
            "status": "unsupported",
            "reason": "custodian_removal_not_supported",
            "compatibility_fields": {},
        }
    result = operation(
        case_id=case_id,
        custodian_id=custodian_id,
        custodian_name=custodian_name,
        custodian_email=custodian_email,
        context=_context(db=db, request=request, user=user),
    )
    if isinstance(result, dict):
        return result
    return {
        "provider": getattr(adapter, "name", "unknown"),
        "status": "completed",
        "result": result,
        "compatibility_fields": {},
    }
