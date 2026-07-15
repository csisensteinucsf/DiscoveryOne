from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


@dataclass(frozen=True)
class HoldSourceOperationContext:
    db: Any = None
    request: Any = None
    actor_id: int | None = None


class HoldSourceProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


class HoldSourceConfigurationError(HoldSourceProviderError):
    pass


class HoldSourceSubjectNotFound(HoldSourceProviderError):
    pass


class HoldSourceOperationError(HoldSourceProviderError):
    pass


class HoldSourceProviderAdapter(Protocol):
    source_key: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def sync_custodian_hold(
        self,
        *,
        case: Any,
        custodian: Any,
        custodian_email: str,
        enable: bool,
        context: HoldSourceOperationContext,
    ) -> dict[str, Any]:
        ...


HoldSourceProviderFactory = Callable[[], HoldSourceProviderAdapter]

_FACTORIES: dict[str, HoldSourceProviderFactory] = {}
_DISPLAY_NAMES: dict[str, str] = {}


def normalize_hold_source_key(source_key: str | None) -> str:
    return str(source_key or "").strip().lower()


def register_hold_source_provider(
    source_key: str,
    factory: HoldSourceProviderFactory,
    *,
    display_name: str | None = None,
    replace: bool = False,
) -> None:
    normalized = normalize_hold_source_key(source_key)
    if not normalized:
        raise ValueError("Hold source providers require a source key.")
    if normalized in _FACTORIES and not replace:
        raise ValueError(
            f"Hold source provider '{normalized}' is already registered."
        )
    _FACTORIES[normalized] = factory
    _DISPLAY_NAMES[normalized] = (
        str(display_name or normalized).strip() or normalized
    )


def unregister_hold_source_provider(source_key: str) -> None:
    normalized = normalize_hold_source_key(source_key)
    _FACTORIES.pop(normalized, None)
    _DISPLAY_NAMES.pop(normalized, None)


def get_hold_source_provider_adapter(
    source_key: str | None,
) -> HoldSourceProviderAdapter | None:
    factory = _FACTORIES.get(normalize_hold_source_key(source_key))
    return factory() if factory else None


def hold_source_provider_names() -> set[str]:
    return set(_FACTORIES)


def hold_source_provider_display_name(source_key: str | None) -> str | None:
    return _DISPLAY_NAMES.get(normalize_hold_source_key(source_key))


def _slack_factory() -> HoldSourceProviderAdapter:
    from .hold_source_provider_adapters import SlackHoldSourceProviderAdapter

    return SlackHoldSourceProviderAdapter()


register_hold_source_provider(
    "slack",
    _slack_factory,
    display_name="Slack",
)
