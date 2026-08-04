from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class PreservationOperationContext:
    db: Any
    request: Any = None
    user: Any = None
    options: dict[str, Any] = field(default_factory=dict)


class PreservationProviderAdapter(Protocol):
    name: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def status_poll_delay_seconds(self) -> float:
        ...

    def create_case(
        self,
        *,
        case_id: int,
        context: PreservationOperationContext,
    ) -> Any:
        ...

    def get_status(
        self,
        *,
        case_id: int,
        context: PreservationOperationContext,
    ) -> Any:
        ...

    def apply_holds(
        self,
        *,
        case_id: int,
        payload: Any,
        context: PreservationOperationContext,
    ) -> Any:
        ...

    def release_holds(
        self,
        *,
        case_id: int,
        payload: Any,
        context: PreservationOperationContext,
    ) -> Any:
        ...


    def remove_custodian(
        self,
        *,
        case_id: int,
        custodian_id: int,
        custodian_name: str | None,
        custodian_email: str | None,
        context: PreservationOperationContext,
    ) -> Any:
        ...

PreservationProviderFactory = Callable[[], PreservationProviderAdapter]

_FACTORIES: dict[str, PreservationProviderFactory] = {}
_DISPLAY_NAMES: dict[str, str] = {}


def normalize_preservation_provider_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def register_preservation_provider(
    name: str,
    factory: PreservationProviderFactory,
    *,
    display_name: str | None = None,
    replace: bool = False,
) -> None:
    normalized = normalize_preservation_provider_name(name)
    if not normalized or normalized == "none":
        raise ValueError("Preservation providers require a unique provider name.")
    if normalized in _FACTORIES and not replace:
        raise ValueError(
            f"Preservation provider '{normalized}' is already registered."
        )
    _FACTORIES[normalized] = factory
    _DISPLAY_NAMES[normalized] = (
        str(display_name or normalized).strip() or normalized
    )


def unregister_preservation_provider(name: str) -> None:
    normalized = normalize_preservation_provider_name(name)
    _FACTORIES.pop(normalized, None)
    _DISPLAY_NAMES.pop(normalized, None)


def get_preservation_provider_adapter(
    name: str | None,
) -> PreservationProviderAdapter | None:
    factory = _FACTORIES.get(normalize_preservation_provider_name(name))
    return factory() if factory else None


def preservation_provider_names(*, include_none: bool = False) -> set[str]:
    names = set(_FACTORIES)
    if include_none:
        names.add("none")
    return names


def preservation_provider_display_name(name: str | None) -> str | None:
    return _DISPLAY_NAMES.get(normalize_preservation_provider_name(name))


def available_preservation_provider_adapters() -> list[PreservationProviderAdapter]:
    available: list[PreservationProviderAdapter] = []
    for factory in _FACTORIES.values():
        try:
            adapter = factory()
            if adapter.is_available():
                available.append(adapter)
        except Exception:
            continue
    return available


def _purview_factory() -> PreservationProviderAdapter:
    from .preservation_provider_adapters import (
        PurviewPreservationProviderAdapter,
    )

    return PurviewPreservationProviderAdapter()


register_preservation_provider(
    "purview",
    _purview_factory,
    display_name="Microsoft Purview",
)
