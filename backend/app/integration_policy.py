from __future__ import annotations

from typing import Any, Mapping

from .esignature_provider_adapters import esignature_provider_names
from .integration_settings import merge_integration_config
from .mail_provider_registry import mail_provider_names
from .person_lookup import person_lookup_provider_names
from .preservation_provider_registry import preservation_provider_names
from .search_export_provider_registry import search_export_provider_names
from .ticket_provider_adapters import ticket_provider_names


ENABLED_INTEGRATION_KEYS = frozenset(
    {
        "servicenow",
        "docusign",
        "slack",
        "purview",
        "box",
        "google_workspace",
        "dropbox_business",
        "zoom",
        "intune",
        "jamf",
        "defender",
        "crowdstrike",
        "person_lookup",
        "smtp",
        "ai",
        "log_shipping",
    }
)

INTEGRATION_CONFIG_KEYS = frozenset(
    {
        "oidc",
        "person_lookup",
        "servicenow",
        "box",
        "google_workspace",
        "dropbox_business",
        "zoom",
        "intune",
        "jamf",
        "defender",
        "crowdstrike",
        "purview",
        "docusign",
        "slack",
        "ai",
        "log_shipping",
    }
)


def provider_options() -> dict[str, set[str]]:
    """Return currently installed provider choices by settings field."""
    return {
        "person_lookup_provider": person_lookup_provider_names(include_none=True),
        "sso_provider": {"local", "oidc"},
        "ticket_provider": ticket_provider_names(include_none=True),
        "mail_provider": mail_provider_names(include_none=True),
        "esign_provider": esignature_provider_names(include_none=True),
        "preservation_provider": preservation_provider_names(include_none=True),
        "search_export_provider": search_export_provider_names(include_none=True),

    }


def merge_enabled_integrations(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        normalized = str(key or "").strip().lower()
        if normalized in ENABLED_INTEGRATION_KEYS:
            merged[normalized] = bool(value)
    return merged


def merge_provider_settings(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
    *,
    reject_unsupported: bool,
) -> dict[str, Any]:
    merged = dict(existing or {})
    allowed_by_field = provider_options()
    for key, value in (incoming or {}).items():
        normalized_key = str(key or "").strip().lower()
        if normalized_key not in allowed_by_field:
            continue
        normalized_value = str(value or "").strip().lower()
        if not normalized_value:
            continue
        if normalized_value not in allowed_by_field[normalized_key]:
            if reject_unsupported:
                raise ValueError(
                    f"Unsupported provider for {normalized_key}: {normalized_value}"
                )
            continue
        merged[normalized_key] = normalized_value
    return merged


def reconcile_provider_enablement(
    enabled: Mapping[str, Any] | None,
    providers: Mapping[str, Any] | None,
    *,
    changed_provider_fields: set[str] | None = None,
) -> dict[str, Any]:
    """Keep built-in enablement flags aligned with explicit provider changes."""
    merged = dict(enabled or {})
    values = {
        str(key or "").strip().lower(): str(value or "").strip().lower()
        for key, value in (providers or {}).items()
    }
    changed = {
        str(key or "").strip().lower()
        for key in (changed_provider_fields or set())
    }
    if "person_lookup_provider" in changed:
        merged["person_lookup"] = values.get("person_lookup_provider") not in {"", "none"}
    if "ticket_provider" in changed:
        merged["servicenow"] = values.get("ticket_provider") == "servicenow"
    if "mail_provider" in changed:
        merged["smtp"] = values.get("mail_provider") == "smtp"
    if "esign_provider" in changed:
        merged["docusign"] = values.get("esign_provider") == "docusign"
    return merged


def merge_integration_configs(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, values in (incoming or {}).items():
        normalized = str(key or "").strip().lower()
        if normalized not in INTEGRATION_CONFIG_KEYS:
            continue
        current = merged.get(normalized)
        current_values = current if isinstance(current, dict) else {}
        incoming_values = values if isinstance(values, dict) else {}
        merged[normalized] = merge_integration_config(
            normalized,
            current_values,
            incoming_values,
        )
    return merged
