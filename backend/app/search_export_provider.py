from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from .integration_settings import provider_value
from .search_export_provider_registry import (
    SearchExportOperationContext,
    get_search_export_provider_adapter,
    search_export_provider_display_name,
)


def current_search_export_provider() -> str:
    return provider_value("search_export_provider", default="none")


def search_export_provider_label() -> str:
    provider = current_search_export_provider()
    return (
        search_export_provider_display_name(provider)
        or str(provider or "Search export").replace("_", " ").title()
    )


def normalize_search_query(raw: Any) -> str:
    adapter = get_search_export_provider_adapter(
        current_search_export_provider()
    )
    normalizer = getattr(adapter, "normalize_query", None)
    if callable(normalizer):
        return str(normalizer(raw) or "").strip()
    return " ".join(str(raw or "").strip().split())


def push_search(
    *,
    case: Any,
    search: Any,
    payload: dict[str, Any] | None,
    db: Any,
    request: Any = None,
    user: Any = None,
) -> dict[str, Any]:
    provider = current_search_export_provider()
    if provider in {"", "none"}:
        raise HTTPException(
            status_code=503,
            detail=(
                "No automated search export provider is configured. "
                "Select one in System > Integrations."
            ),
        )
    adapter = get_search_export_provider_adapter(provider)
    if adapter is None:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Search export provider '{provider}' is not installed. "
                "Select an available provider in System > Integrations."
            ),
        )
    try:
        available = bool(adapter.is_available())
    except Exception:
        available = False
    if not available:
        raise HTTPException(
            status_code=503,
            detail=(
                f"{getattr(adapter, 'display_name', provider)} is not configured."
            ),
        )
    return adapter.push_search(
        case=case,
        search=search,
        payload=payload if isinstance(payload, dict) else {},
        context=SearchExportOperationContext(
            db=db,
            request=request,
            user=user,
        ),
    )