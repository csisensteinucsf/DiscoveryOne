from __future__ import annotations

from typing import Any, Optional

from .integration_settings import provider_value
from .ticket_provider_adapters import (
    TicketProviderAdapter,
    TicketProviderAdapterError,
    get_ticket_provider_adapter,
)


class TicketProviderError(Exception):
    """Raised when the configured ticket provider cannot complete a request."""


_GENERIC_CLOSED_STATUSES = {
    "closed",
    "resolved",
    "complete",
    "completed",
    "done",
    "canceled",
    "cancelled",
    "void",
}


def current_ticket_provider() -> str:
    return provider_value("ticket_provider", default="none")


def _active_adapter(*, required: bool) -> TicketProviderAdapter | None:
    provider = current_ticket_provider()
    if provider not in {"", "none", "manual"}:
        adapter = get_ticket_provider_adapter(provider)
        if adapter is None:
            if required:
                raise TicketProviderError(
                    f"Ticket provider '{provider}' is not installed. "
                    "Select an available provider in System > Integrations."
                )
            return None
        return adapter

    if required:
        raise TicketProviderError(
            "No external ticket provider is configured. "
            "Enable one in System > Integrations."
        )
    return None


def create_ticket(
    *,
    category: str,
    case_name: Optional[str] = None,
    case_link: Optional[str] = None,
    custodian_name: Optional[str] = None,
    custodian_email: Optional[str] = None,
    customer_id: Optional[str] = None,
    extra_context: Optional[dict[str, Any]] = None,
) -> dict[str, Optional[str]]:
    adapter = _active_adapter(required=True)
    try:
        return adapter.create_ticket(
            category=category,
            case_name=case_name,
            case_link=case_link,
            custodian_name=custodian_name,
            custodian_email=custodian_email,
            customer_id=customer_id,
            extra_context=extra_context,
        )
    except TicketProviderAdapterError as exc:
        raise TicketProviderError(str(exc)) from exc


def get_ticket_statuses(ticket_numbers: list[str]) -> dict[str, dict[str, Optional[str]]]:
    adapter = _active_adapter(required=True)
    try:
        return adapter.get_ticket_statuses(ticket_numbers)
    except TicketProviderAdapterError as exc:
        raise TicketProviderError(str(exc)) from exc


def is_closed_status(status: Optional[str]) -> bool:
    adapter = _active_adapter(required=False)
    if adapter is not None:
        return adapter.is_closed_status(status)
    normalized = str(status or "").strip().lower()
    return any(marker == normalized or marker in normalized for marker in _GENERIC_CLOSED_STATUSES)


def default_customer_id() -> str:
    adapter = _active_adapter(required=False)
    if adapter is None:
        return ""
    return str(adapter.default_customer_id() or "").strip()

def ticket_link(
    *,
    sys_id: str | None = None,
    ticket_number: str | None = None,
    fallback: str = "N/A",
) -> str:
    if not sys_id and not ticket_number:
        return fallback
    adapter = _active_adapter(required=False)
    if adapter is None:
        return fallback
    return adapter.ticket_link(
        sys_id=sys_id,
        ticket_number=ticket_number,
        fallback=fallback,
    )
