from __future__ import annotations

from typing import Any, Optional, Protocol
from urllib.parse import quote

from . import servicenow
from .integration_settings import config_value


class TicketProviderAdapterError(Exception):
    """Raised when a ticket adapter cannot complete an operation."""


class TicketProviderAdapter(Protocol):
    """Provider-neutral contract used by case ticket workflows."""

    name: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def create_ticket(
        self,
        *,
        category: str,
        case_name: Optional[str] = None,
        case_link: Optional[str] = None,
        custodian_name: Optional[str] = None,
        custodian_email: Optional[str] = None,
        customer_id: Optional[str] = None,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Optional[str]]:
        ...

    def get_ticket_statuses(
        self,
        ticket_numbers: list[str],
    ) -> dict[str, dict[str, Optional[str]]]:
        ...

    def is_closed_status(self, status: Optional[str]) -> bool:
        ...

    def default_customer_id(self) -> str:
        ...

    def ticket_link(
        self,
        *,
        sys_id: str | None = None,
        ticket_number: str | None = None,
        fallback: str = "N/A",
    ) -> str:
        ...


class ServiceNowTicketProviderAdapter:
    name = "servicenow"
    display_name = "ServiceNow"

    def is_available(self) -> bool:
        return servicenow.servicenow_enabled()

    def create_ticket(
        self,
        *,
        category: str,
        case_name: Optional[str] = None,
        case_link: Optional[str] = None,
        custodian_name: Optional[str] = None,
        custodian_email: Optional[str] = None,
        customer_id: Optional[str] = None,
        extra_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Optional[str]]:
        try:
            return servicenow.create_ticket(
                category=category,
                case_name=case_name,
                case_link=case_link,
                custodian_name=custodian_name,
                custodian_email=custodian_email,
                customer_id=customer_id,
                extra_context=extra_context,
            )
        except servicenow.ServiceNowError as exc:
            raise TicketProviderAdapterError(str(exc)) from exc

    def get_ticket_statuses(
        self,
        ticket_numbers: list[str],
    ) -> dict[str, dict[str, Optional[str]]]:
        try:
            return servicenow.get_ticket_statuses(ticket_numbers)
        except servicenow.ServiceNowError as exc:
            raise TicketProviderAdapterError(str(exc)) from exc

    def is_closed_status(self, status: Optional[str]) -> bool:
        return servicenow._is_closed_state(status)

    def default_customer_id(self) -> str:
        return (
            config_value(
                "servicenow",
                "default_customer_id",
                "SNOW_DEFAULT_CUSTOMER_ID",
            )
            or config_value(
                "servicenow",
                "customer_id",
                "SNOW_CUSTOMER_ID",
            )
        ).strip()

    def ticket_link(
        self,
        *,
        sys_id: str | None = None,
        ticket_number: str | None = None,
        fallback: str = "N/A",
    ) -> str:
        if not sys_id and not ticket_number:
            return fallback
        try:
            config = servicenow.load_config()
        except Exception:
            return fallback
        table = getattr(config, "status_table", None) or getattr(config, "table", None) or "incident"
        if sys_id:
            return f"{config.base_url}/nav_to.do?uri={table}.do?sys_id={sys_id}"
        inner_uri = f"{table}_list.do?sysparm_query=number={ticket_number}"
        return f"{config.base_url}/nav_to.do?uri={quote(inner_uri, safe='')}"


_ADAPTERS: dict[str, TicketProviderAdapter] = {}


def normalize_ticket_provider_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def register_ticket_provider(
    adapter: TicketProviderAdapter,
    *,
    replace: bool = False,
) -> None:
    name = normalize_ticket_provider_name(getattr(adapter, "name", ""))
    if not name or name in {"none", "manual"}:
        raise ValueError("Ticket provider adapters require a unique provider name.")
    if name in _ADAPTERS and not replace:
        raise ValueError(f"Ticket provider '{name}' is already registered.")
    _ADAPTERS[name] = adapter


def unregister_ticket_provider(name: str) -> None:
    _ADAPTERS.pop(normalize_ticket_provider_name(name), None)


def get_ticket_provider_adapter(name: str | None) -> TicketProviderAdapter | None:
    return _ADAPTERS.get(normalize_ticket_provider_name(name))


def ticket_provider_names(*, include_none: bool = False) -> set[str]:
    names = set(_ADAPTERS)
    if include_none:
        names.add("none")
    return names


def ticket_provider_display_name(name: str | None) -> str | None:
    adapter = get_ticket_provider_adapter(name)
    if adapter is None:
        return None
    return str(getattr(adapter, "display_name", "") or adapter.name).strip()


def available_ticket_provider_adapters() -> list[TicketProviderAdapter]:
    available: list[TicketProviderAdapter] = []
    for adapter in _ADAPTERS.values():
        try:
            if adapter.is_available():
                available.append(adapter)
        except Exception:
            continue
    return available


register_ticket_provider(ServiceNowTicketProviderAdapter())
