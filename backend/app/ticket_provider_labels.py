from __future__ import annotations

from .integration_settings import provider_value
from .ticket_provider_adapters import ticket_provider_display_name

TICKET_PROVIDER_LABELS = {
    "none": "No external ticket provider",
    "manual": "Manual tracking",
    "servicenow": "ServiceNow",
}


def normalize_ticket_provider(provider: str | None = None) -> str:
    value = (provider or "").strip().lower()
    if not value:
        value = provider_value("ticket_provider", default="none")
    if value in TICKET_PROVIDER_LABELS or ticket_provider_display_name(value):
        return value
    return "manual"


def ticket_provider_label(provider: str | None = None) -> str:
    normalized = normalize_ticket_provider(provider)
    return TICKET_PROVIDER_LABELS.get(normalized) or ticket_provider_display_name(normalized) or TICKET_PROVIDER_LABELS["manual"]


def external_ticket_label(provider: str | None = None) -> str:
    normalized = normalize_ticket_provider(provider)
    if normalized in {"none", "manual"}:
        return "external ticket"
    return f"{ticket_provider_label(normalized)} ticket"


def generic_external_ticket_label() -> str:
    return "external ticket"
