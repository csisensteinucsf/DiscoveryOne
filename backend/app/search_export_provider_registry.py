from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class SearchExportOperationContext:
    db: Any
    request: Any = None
    user: Any = None


class SearchExportProviderAdapter(Protocol):
    name: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def normalize_query(self, raw: Any) -> str:
        ...

    def push_search(
        self,
        *,
        case: Any,
        search: Any,
        payload: dict[str, Any],
        context: SearchExportOperationContext,
    ) -> dict[str, Any]:
        ...


SearchExportProviderFactory = Callable[[], SearchExportProviderAdapter]

_FACTORIES: dict[str, SearchExportProviderFactory] = {}
_DISPLAY_NAMES: dict[str, str] = {}


def normalize_search_export_provider_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def register_search_export_provider(
    name: str,
    factory: SearchExportProviderFactory,
    *,
    display_name: str | None = None,
    replace: bool = False,
) -> None:
    normalized = normalize_search_export_provider_name(name)
    if not normalized or normalized == "none":
        raise ValueError("Search export providers require a unique provider name.")
    if normalized in _FACTORIES and not replace:
        raise ValueError(
            f"Search export provider '{normalized}' is already registered."
        )
    _FACTORIES[normalized] = factory
    _DISPLAY_NAMES[normalized] = (
        str(display_name or normalized).strip() or normalized
    )


def unregister_search_export_provider(name: str) -> None:
    normalized = normalize_search_export_provider_name(name)
    _FACTORIES.pop(normalized, None)
    _DISPLAY_NAMES.pop(normalized, None)


def get_search_export_provider_adapter(
    name: str | None,
) -> SearchExportProviderAdapter | None:
    factory = _FACTORIES.get(normalize_search_export_provider_name(name))
    return factory() if factory else None


def search_export_provider_names(*, include_none: bool = False) -> set[str]:
    names = set(_FACTORIES)
    if include_none:
        names.add("none")
    return names


def search_export_provider_display_name(name: str | None) -> str | None:
    return _DISPLAY_NAMES.get(normalize_search_export_provider_name(name))


def _purview_factory() -> SearchExportProviderAdapter:
    from .search_export_provider_adapters import (
        PurviewSearchExportProviderAdapter,
    )

    return PurviewSearchExportProviderAdapter()


register_search_export_provider(
    "purview",
    _purview_factory,
    display_name="Microsoft Purview",
)