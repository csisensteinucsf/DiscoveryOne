from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Sequence


class MailProviderAdapterError(Exception):
    """Raised when a mail provider adapter cannot deliver a message."""


class MailProviderAdapter(Protocol):
    name: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def send_email(
        self,
        *,
        recipients: Sequence[str],
        subject: str,
        body: str,
        html: Optional[str] = None,
        from_override: Optional[str] = None,
        reply_to: Optional[Sequence[str]] = None,
        cc: Optional[Sequence[str]] = None,
        bcc: Optional[Sequence[str]] = None,
        importance: Optional[str] = None,
        provider_context: Any = None,
        audit_log: bool = True,
    ) -> None:
        ...


MailProviderFactory = Callable[[], MailProviderAdapter]


@dataclass(frozen=True)
class MailProviderDefinition:
    name: str
    display_name: str
    factory: MailProviderFactory


_PROVIDERS: dict[str, MailProviderDefinition] = {}


def normalize_mail_provider_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def register_mail_provider(
    name: str,
    factory: MailProviderFactory,
    *,
    display_name: str | None = None,
    replace: bool = False,
) -> None:
    normalized = normalize_mail_provider_name(name)
    if not normalized or normalized == "none":
        raise ValueError("Mail providers require a unique provider name.")
    if normalized in _PROVIDERS and not replace:
        raise ValueError(f"Mail provider '{normalized}' is already registered.")
    _PROVIDERS[normalized] = MailProviderDefinition(
        name=normalized,
        display_name=str(display_name or normalized).strip() or normalized,
        factory=factory,
    )


def unregister_mail_provider(name: str) -> None:
    _PROVIDERS.pop(normalize_mail_provider_name(name), None)


def get_mail_provider_adapter(name: str | None) -> MailProviderAdapter | None:
    definition = _PROVIDERS.get(normalize_mail_provider_name(name))
    if definition is None:
        return None
    return definition.factory()


def mail_provider_names(*, include_none: bool = False) -> set[str]:
    names = set(_PROVIDERS)
    if include_none:
        names.add("none")
    return names


def mail_provider_display_name(name: str | None) -> str | None:
    definition = _PROVIDERS.get(normalize_mail_provider_name(name))
    return definition.display_name if definition else None


def available_mail_provider_adapters() -> list[MailProviderAdapter]:
    available: list[MailProviderAdapter] = []
    for definition in _PROVIDERS.values():
        try:
            adapter = definition.factory()
            if adapter.is_available():
                available.append(adapter)
        except Exception:
            continue
    return available


def _smtp_factory() -> MailProviderAdapter:
    from .smtp_mail_provider import SMTPMailProviderAdapter

    return SMTPMailProviderAdapter()


register_mail_provider(
    "smtp",
    _smtp_factory,
    display_name="SMTP",
)
