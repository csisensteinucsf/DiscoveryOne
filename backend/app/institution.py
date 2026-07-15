from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Dict, Iterable

from .system_settings import load_system_settings


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, Iterable):
        raw_items = list(value)
    else:
        raw_items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip().lower()
        if not text:
            continue
        if text.startswith("@"):
            text = text[1:]
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _split_emails(value: Any) -> list[str]:
    return [item for item in _split_csv(value) if "@" in item]


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name)
    return _split_csv(raw) if raw is not None else []


def _env_email_list(name: str) -> list[str]:
    raw = os.getenv(name)
    return _split_emails(raw) if raw is not None else []


def _setup_completed(settings: Dict[str, Any]) -> bool:
    return bool(settings.get("initial_setup_completed"))


def _settings_or_env(settings_ready: bool, stored: Any, env_name: str, default: str = "") -> str:
    stored_text = str(stored or "").strip()
    if settings_ready:
        return stored_text or default
    return (os.getenv(env_name) or stored_text or default).strip()


def _list_settings_or_env(settings_ready: bool, stored: Any, env_name: str, *, emails: bool = False) -> list[str]:
    parser = _split_emails if emails else _split_csv
    stored_values = parser(stored)
    if settings_ready:
        return stored_values
    raw = os.getenv(env_name)
    env_values = parser(raw) if raw is not None else []
    return env_values or stored_values


def load_institution_settings() -> Dict[str, Any]:
    all_settings = load_system_settings()
    settings = deepcopy((all_settings.get("institution") or {}))
    settings_ready = _setup_completed(all_settings)

    institution = {
        "org_name": _settings_or_env(settings_ready, settings.get("org_name"), "ORG_NAME"),
        "org_short_name": _settings_or_env(settings_ready, settings.get("org_short_name"), "ORG_SHORT_NAME"),
        "allowed_requestor_email_domains": _list_settings_or_env(settings_ready, settings.get("allowed_requestor_email_domains"), "ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS"),
        "requestor_email_exceptions": _list_settings_or_env(settings_ready, settings.get("requestor_email_exceptions"), "ORG_REQUESTOR_EMAIL_EXCEPTIONS", emails=True),
        "employee_id_label": "Employee ID",
        "sso_display_name": _settings_or_env(settings_ready, settings.get("sso_display_name"), "SSO_DISPLAY_NAME", "Single sign-on"),
        "support_email": _settings_or_env(settings_ready, settings.get("support_email"), "SUPPORT_EMAIL"),
    }
    if not institution["org_short_name"] and institution["org_name"]:
        institution["org_short_name"] = institution["org_name"]
    return institution


def load_integration_settings() -> Dict[str, Any]:
    settings = load_system_settings()
    settings_ready = _setup_completed(settings)
    configured = deepcopy(settings.get("integrations") or {})
    enabled = deepcopy(settings.get("enabled_integrations") or {})

    def provider(key: str, env_name: str, default: str) -> str:
        configured_value = str(configured.get(key) or "").strip().lower()
        if settings_ready:
            return configured_value or default
        return (os.getenv(env_name) or configured_value or default).strip().lower()

    providers = {
        "person_lookup_provider": provider("person_lookup_provider", "PERSON_LOOKUP_PROVIDER", "none"),
        "sso_provider": provider("sso_provider", "SSO_PROVIDER", "oidc" if _truthy(os.getenv("OIDC_ENABLED")) else "local"),
        "ticket_provider": provider("ticket_provider", "TICKET_PROVIDER", "none"),
        "mail_provider": provider("mail_provider", "MAIL_PROVIDER", "smtp"),
        "esign_provider": provider("esign_provider", "ESIGN_PROVIDER", "none"),
        "preservation_provider": provider("preservation_provider", "PRESERVATION_PROVIDER", "none"),
        "search_export_provider": provider("search_export_provider", "SEARCH_EXPORT_PROVIDER", "none"),
    }

    def flag(key: str, env_name: str, default: bool = False) -> bool:
        if settings_ready:
            return bool(enabled.get(key, default))
        raw = os.getenv(env_name)
        if raw is not None:
            return _truthy(raw)
        return bool(enabled.get(key, default))

    providers["enabled_integrations"] = {
        "servicenow": flag("servicenow", "SERVICENOW_ENABLED"),
        "docusign": flag("docusign", "DOCUSIGN_ENABLED"),
        "slack": flag("slack", "SLACK_ENABLED"),
        "purview": flag("purview", "PURVIEW_ENABLED"),
        "box": flag("box", "BOX_ENABLED"),
        "google_workspace": flag("google_workspace", "GOOGLE_WORKSPACE_ENABLED"),
        "dropbox_business": flag("dropbox_business", "DROPBOX_BUSINESS_ENABLED"),
        "zoom": flag("zoom", "ZOOM_ENABLED"),
        "intune": flag("intune", "INTUNE_ENABLED"),
        "jamf": flag("jamf", "JAMF_ENABLED"),
        "defender": flag("defender", "DEFENDER_ENABLED"),
        "crowdstrike": flag("crowdstrike", "CROWDSTRIKE_ENABLED"),
        "person_lookup": flag("person_lookup", "PERSON_LOOKUP_ENABLED"),
        "smtp": flag("smtp", "SMTP_ENABLED"),
    }
    return providers


def organization_domains() -> list[str]:
    return load_institution_settings()["allowed_requestor_email_domains"]


def organization_domain_label() -> str:
    domains = organization_domains()
    if not domains:
        return "configured organization email domain"
    if len(domains) == 1:
        return f"@{domains[0]}"
    return ", ".join(f"@{domain}" for domain in domains)


def sso_display_name() -> str:
    return load_institution_settings().get("sso_display_name") or "Single sign-on"


def email_domain(value: str | None) -> str:
    text = (value or "").strip().lower()
    if "@" not in text:
        return ""
    return text.rsplit("@", 1)[-1]


def is_organization_email(value: str | None) -> bool:
    domains = organization_domains()
    if not domains:
        return True
    return email_domain(value) in domains


def is_requestor_email_exception(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    return normalized in set(load_institution_settings()["requestor_email_exceptions"])
