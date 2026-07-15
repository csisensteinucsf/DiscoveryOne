from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, EmailStr

from .institution import load_institution_settings, load_integration_settings
from .system_settings import load_system_settings
from .integration_settings import (
    MASKED_SECRET_VALUE,
    integration_enabled,
    provider_value,
    public_integration_config,
)
from .catalog_defaults import default_preservation_sources, default_ticket_workflows
from .case_naming_config import normalize_case_naming

THEMES = ["light", "dark", "system"]


class EmailTestPayload(BaseModel):
    to: EmailStr
    subject: Optional[str] = None
    body: Optional[str] = None


class SMTPConfigPayload(BaseModel):
    host: str
    port: int = 587
    from_address: EmailStr
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 15


class NTPConfigPayload(BaseModel):
    archive_bcc_address: Optional[str] = None
    archive_copy_required: Optional[bool] = None
    reserved_archive_bcc_addresses: Optional[str] = None
    ack_automate_url: Optional[str] = None
    ack_display_url: Optional[str] = None
    ack_automate_secret: Optional[str] = None
    reminder_interval_days: Optional[int] = None
    reminder_duration_days: Optional[int] = None
    reminder_loop_seconds: Optional[int] = None


class NotificationsPayload(BaseModel):
    teams: Optional[Dict[str, Any]] = None
    email: Optional[Dict[str, Any]] = None
    search_delivery_reminders: Optional[Dict[str, Any]] = None
    consent_notifications: Optional[Dict[str, Any]] = None


class AccountReviewPayload(BaseModel):
    enabled: Optional[bool] = None
    interval_days: Optional[int] = None
    check_interval_hours: Optional[float] = None


class BackupSettingsPayload(BaseModel):
    automatic_enabled: Optional[bool] = None
    interval_hours: Optional[float] = None
    retention_hours: Optional[float] = None


class SystemIntegrationsPayload(BaseModel):
    enabled_integrations: Optional[Dict[str, bool]] = None
    providers: Optional[Dict[str, str]] = None
    configs: Optional[Dict[str, Dict[str, Any]]] = None


class InstitutionSettingsPayload(BaseModel):
    org_name: Optional[str] = None
    org_short_name: Optional[str] = None
    allowed_requestor_email_domains: Optional[List[str]] = None
    requestor_email_exceptions: Optional[List[EmailStr]] = None
    sso_display_name: Optional[str] = None
    support_email: Optional[EmailStr] = None


class PreservationSourcesPayload(BaseModel):
    preservation_sources: List[Dict[str, Any]] = []


class TicketWorkflowsPayload(BaseModel):
    ticket_workflows: List[Dict[str, Any]] = []


class CaseNamingPayload(BaseModel):
    mode: str


class CaseClosurePayload(BaseModel):
    default_nag_days: Optional[int] = None
    loop_seconds: Optional[int] = None
    batch_size: Optional[int] = None


class DeploymentPayload(BaseModel):
    app_base_url: Optional[str] = None
    allowed_hosts: Optional[List[str]] = None


class CaseStatusPayload(BaseModel):
    ntp_ack_days: Optional[int] = None
    consent_received_days: Optional[int] = None


class CaseRequestSettingsPayload(BaseModel):
    requestor_stats_show_global: Optional[bool] = None
    hold_automation_allow_override: Optional[bool] = None
    auto_rubrik_restore_for_separated_email_holds: Optional[bool] = None
    pending_cleanup_days: Optional[float] = None
    pending_cleanup_interval_hours: Optional[float] = None
    hold_status_email_delay_seconds: Optional[float] = None
    preservation_auto_apply_max_attempts: Optional[int] = None
    preservation_auto_apply_delay_seconds: Optional[float] = None
    preservation_status_max_seconds: Optional[float] = None
    preservation_status_interval_seconds: Optional[float] = None
    # Legacy request keys are accepted during upgrades but are not persisted.
    purview_auto_apply_max_attempts: Optional[int] = None
    purview_auto_apply_delay_seconds: Optional[float] = None
    purview_approval_status_max_seconds: Optional[float] = None
    purview_approval_status_interval_seconds: Optional[float] = None


class BrandingTextPayload(BaseModel):
    app_name: Optional[str] = None
    app_tagline: Optional[str] = None


def public_branding_config(raw: Optional[Dict[str, Any]]) -> Dict[str, str]:
    data = raw or {}
    app_name = str(data.get("app_name") or "DiscoveryOne").strip() or "DiscoveryOne"
    app_tagline = str(data.get("app_tagline") or "eDiscovery Case Manager").strip()
    return {"app_name": app_name, "app_tagline": app_tagline}


def public_smtp_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw or {}
    has_password = bool(data.get("password"))
    try:
        timeout_seconds = max(1.0, min(300.0, float(data.get("timeout_seconds") or 15)))
    except (TypeError, ValueError):
        timeout_seconds = 15.0
    return {
        "host": data.get("host") or "",
        "port": data.get("port") or 587,
        "username": data.get("username") or "",
        "from_address": data.get("from_address") or "",
        "use_tls": bool(data.get("use_tls", True)) and not bool(data.get("use_ssl", False)),
        "use_ssl": bool(data.get("use_ssl", False)),
        "timeout_seconds": timeout_seconds,
        "password": MASKED_SECRET_VALUE if has_password else "",
    }


def _clean_host(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        parsed = urlparse(text)
        text = parsed.hostname or ""
    else:
        text = text.split("/", 1)[0].split(":", 1)[0]
    if not text or "@" in text or any(ch.isspace() for ch in text):
        raise ValueError(f"Invalid hostname: {value}")
    return text[:255]


def normalize_deployment_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    base = str(data.get("app_base_url") or "").strip().rstrip("/")
    if base:
        parsed = urlparse(base)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Public app URL must use https:// and include a hostname")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Public app URL must not include credentials, query strings, or fragments")
    hosts: list[str] = []
    seen: set[str] = set()
    values = data.get("allowed_hosts") or []
    if isinstance(values, str):
        values = values.split(",")
    if not isinstance(values, list):
        values = []
    for value in values:
        host = _clean_host(value)
        if host and host not in seen:
            hosts.append(host)
            seen.add(host)
    if base:
        host = (urlparse(base).hostname or "").lower()
        if host and host not in seen:
            hosts.append(host)
    return {"app_base_url": base, "allowed_hosts": hosts}


def public_deployment_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    try:
        return normalize_deployment_config(raw)
    except ValueError:
        return {"app_base_url": "", "allowed_hosts": []}


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def public_ntp_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw or {}
    ack_secret = str(data.get("ack_automate_secret") or "").strip()
    return {
        "archive_bcc_address": (data.get("archive_bcc_address") or "").strip(),
        "archive_copy_required": bool(data.get("archive_copy_required", False)),
        "reserved_archive_bcc_addresses": (data.get("reserved_archive_bcc_addresses") or "").strip(),
        "ack_automate_url": (data.get("ack_automate_url") or "").strip(),
        "ack_display_url": (data.get("ack_display_url") or "").strip(),
        "ack_automate_secret": MASKED_SECRET_VALUE if ack_secret else "",
        "reminder_interval_days": _bounded_int(data.get("reminder_interval_days"), 14, minimum=1, maximum=365),
        "reminder_duration_days": _bounded_int(data.get("reminder_duration_days"), 90, minimum=1, maximum=3650),
        "reminder_loop_seconds": _bounded_int(data.get("reminder_loop_seconds"), 900, minimum=30, maximum=86400),
    }


def public_case_closure_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "default_nag_days": _bounded_int(data.get("default_nag_days"), 180, minimum=1, maximum=3650),
        "loop_seconds": _bounded_int(data.get("loop_seconds"), 3600, minimum=300, maximum=86400),
        "batch_size": _bounded_int(data.get("batch_size"), 25, minimum=1, maximum=500),
    }


def public_case_status_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "ntp_ack_days": _bounded_int(data.get("ntp_ack_days"), 7, minimum=1, maximum=3650),
        "consent_received_days": _bounded_int(data.get("consent_received_days"), 7, minimum=1, maximum=3650),
    }


def _bounded_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def public_account_review_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "enabled": bool(data.get("enabled", True)),
        "interval_days": _bounded_int(data.get("interval_days"), 120, minimum=1, maximum=3650),
        "check_interval_hours": _bounded_float(data.get("check_interval_hours"), 12.0, minimum=1.0, maximum=168.0),
        "last_sent_at": data.get("last_sent_at") or None,
    }


def public_backup_settings_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "automatic_enabled": bool(data.get("automatic_enabled", True)),
        "interval_hours": _bounded_float(data.get("interval_hours"), 6.0, minimum=1.0, maximum=168.0),
        "retention_hours": _bounded_float(data.get("retention_hours"), 48.0, minimum=1.0, maximum=8760.0),
    }


def public_case_request_settings_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "requestor_stats_show_global": bool(data.get("requestor_stats_show_global", False)),
        "hold_automation_allow_override": bool(data.get("hold_automation_allow_override", False)),
        "auto_rubrik_restore_for_separated_email_holds": bool(data.get("auto_rubrik_restore_for_separated_email_holds", False)),
        "pending_cleanup_days": _bounded_float(data.get("pending_cleanup_days"), 30.0, minimum=1.0, maximum=3650.0),
        "pending_cleanup_interval_hours": _bounded_float(data.get("pending_cleanup_interval_hours"), 12.0, minimum=1.0, maximum=168.0),
        "hold_status_email_delay_seconds": _bounded_float(data.get("hold_status_email_delay_seconds"), 300.0, minimum=0.0, maximum=86400.0),
        "preservation_auto_apply_max_attempts": _bounded_int(data.get("preservation_auto_apply_max_attempts", data.get("purview_auto_apply_max_attempts")), 3, minimum=1, maximum=20),
        "preservation_auto_apply_delay_seconds": _bounded_float(data.get("preservation_auto_apply_delay_seconds", data.get("purview_auto_apply_delay_seconds")), 2.0, minimum=0.0, maximum=3600.0),
        "preservation_status_max_seconds": _bounded_float(data.get("preservation_status_max_seconds", data.get("purview_approval_status_max_seconds")), 90.0, minimum=0.0, maximum=86400.0),
        "preservation_status_interval_seconds": _bounded_float(data.get("preservation_status_interval_seconds", data.get("purview_approval_status_interval_seconds")), 5.0, minimum=1.0, maximum=3600.0),
    }


def preservation_source_key(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = re.sub(r"[^a-z0-9]+", "_", text_value)
    text_value = re.sub(r"_+", "_", text_value).strip("_")
    return text_value[:80]


def normalize_preservation_sources(values: Any) -> list[dict[str, Any]]:
    defaults = default_preservation_sources()
    by_key = {item["key"]: dict(item) for item in defaults}
    if not isinstance(values, list):
        return list(by_key.values())
    for item in values:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("key") or "").strip()[:80]
        key = preservation_source_key(item.get("key") or label)
        if not key or not label:
            continue
        existing = by_key.get(key)
        by_key[key] = {
            "key": key,
            "label": existing.get("label") if existing else label,
            "enabled": bool(item.get("enabled", True)),
            "built_in": bool(existing.get("built_in")) if existing else bool(item.get("built_in", False)),
        }
    return list(by_key.values())


def normalize_ticket_workflows(values: Any) -> list[dict[str, Any]]:
    by_key = {item["key"]: dict(item) for item in default_ticket_workflows()}
    raw_values = values if isinstance(values, list) else []
    allowed_metadata_schemas = {"", "access_log_request"}
    for item in raw_values:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("key") or "").strip()[:120]
        key = preservation_source_key(item.get("key") or label)
        if not key or not label:
            continue
        existing = by_key.get(key, {})
        provider = str(item.get("provider") or existing.get("provider") or "manual").strip().lower()
        if provider not in {"manual", "servicenow"}:
            provider = "manual"
        external_ticket_enabled = bool(
            item.get(
                "external_ticket_enabled",
                item.get(
                    "service_now_enabled",
                    existing.get(
                        "external_ticket_enabled",
                        existing.get("service_now_enabled", provider == "servicenow"),
                    ),
                ),
            )
        )
        tech_group = preservation_source_key(item.get("tech_group") or existing.get("tech_group") or key)
        hold_key = str(item.get("hold_key") or existing.get("hold_key") or "").strip()
        legacy_field = str(item.get("legacy_field") or existing.get("legacy_field") or "").strip()
        auto_create_on_approval = bool(
            item.get(
                "auto_create_on_approval",
                existing.get("auto_create_on_approval", bool(hold_key or item.get("preservation_source"))),
            )
        )
        manual_status_tracking = bool(
            item.get(
                "manual_status_tracking",
                existing.get("manual_status_tracking", False),
            )
        )
        hold_operation = str(
            item.get("hold_operation")
            or item.get("operation")
            or existing.get("hold_operation")
            or "hold"
        ).strip().lower()
        if hold_operation in {"apply", "create"}:
            hold_operation = "hold"
        if hold_operation not in {"hold", "release"}:
            hold_operation = "hold"
        completion_satisfies_source = preservation_source_key(
            item.get("completion_satisfies_source")
            or existing.get("completion_satisfies_source")
        )
        completion_satisfies_hold_key = str(
            item.get("completion_satisfies_hold_key")
            or existing.get("completion_satisfies_hold_key")
            or ""
        ).strip()
        metadata_schema = str(item.get("metadata_schema") or existing.get("metadata_schema") or "").strip().lower()
        if metadata_schema not in allowed_metadata_schemas:
            metadata_schema = ""
        by_key[key] = {
            "key": key,
            "label": label,
            "enabled": bool(item.get("enabled", existing.get("enabled", True))),
            "provider": provider,
            "external_ticket_enabled": external_ticket_enabled,
            # Keep persisted legacy settings readable while callers migrate to the
            # provider-neutral field. Never allow the aliases to disagree.
            "service_now_enabled": external_ticket_enabled,
            "auto_create_on_approval": auto_create_on_approval,
            "manual_status_tracking": manual_status_tracking,
            "hold_operation": hold_operation,
            "completion_satisfies_source": completion_satisfies_source,
            "completion_satisfies_hold_key": completion_satisfies_hold_key,
            "preservation_source": preservation_source_key(item.get("preservation_source") or existing.get("preservation_source") or key),
            "hold_key": hold_key,
            "tech_group": tech_group,
            "requires_matched_email": bool(item.get("requires_matched_email", existing.get("requires_matched_email", False))),
            "metadata_schema": metadata_schema,
            "legacy_field": legacy_field,
            "built_in": bool(existing.get("built_in")) if existing else bool(item.get("built_in", False)),
            "short_description": str(item.get("short_description") or existing.get("short_description") or "").strip(),
            "assignment_group": str(item.get("assignment_group") or existing.get("assignment_group") or "").strip(),
            "symptom": str(item.get("symptom") or existing.get("symptom") or "Inquiry").strip() or "Inquiry",
            "incident_keyword": str(item.get("incident_keyword") or existing.get("incident_keyword") or "").strip(),
            "request_type": str(item.get("request_type") or existing.get("request_type") or "").strip(),
            "link_label": str(item.get("link_label") or existing.get("link_label") or "Case link").strip() or "Case link",
        }
    return list(by_key.values())


def public_ticket_workflows(raw: Any, *, enabled_only: bool = False) -> list[dict[str, Any]]:
    workflows = normalize_ticket_workflows(raw)
    if enabled_only:
        workflows = [item for item in workflows if item.get("enabled")]
    return workflows


def ticket_workflow_lookup(raw: Any, *, include_disabled: bool = True) -> Dict[str, Dict[str, Any]]:
    workflows = normalize_ticket_workflows(raw)
    if not include_disabled:
        workflows = [item for item in workflows if item.get("enabled")]
    return {item["key"]: item for item in workflows}


def tech_group_ticket_categories(raw: Any) -> Dict[str, set[str]]:
    groups: Dict[str, set[str]] = {}
    for item in normalize_ticket_workflows(raw):
        group = preservation_source_key(item.get("tech_group"))
        if not group:
            continue
        groups.setdefault(group, set()).add(item["key"])
    return groups


def ticket_legacy_fields(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in normalize_ticket_workflows(raw):
        field = str(item.get("legacy_field") or "").strip()
        if field:
            out[item["key"]] = field
    return out


def safe_logo_name(orig: str) -> str:
    base = "".join(ch for ch in orig if ch.isalnum() or ch in (".", "-", "_")).strip()
    if not base:
        base = uuid4().hex[:8] + ".png"
    return base


def public_logo_url(filename: str) -> str:
    return f"/api/system/logo/{filename}"


_TEAMS_EVENT_LABELS = {
    "case_request_submitted": "Case request submitted",
    "admin_help": "Login assistance request",
    "registration_request": "Account registration request",
    "backup_key_missing": "Backup encryption key missing",
    "backup_restore": "Backup restore",
    "malware_upload_detected": "Malware detected in upload",
    "consent_completed": "Consent completed",
    "ticket_assigned": "Ticket assigned",
    "ticket_completed": "Ticket completed",
}

_TEAMS_EVENT_CATEGORIES = {
    "case_request_submitted": "Requests",
    "registration_request": "Requests",
    "admin_help": "Accounts",
    "backup_key_missing": "System",
    "backup_restore": "System",
    "malware_upload_detected": "Security",
    "consent_completed": "Consent",
    "ticket_assigned": "Tickets",
    "ticket_completed": "Tickets",
}

_EMAIL_EVENT_LABELS = {
    "admin_help": "Login assistance request",
    "registration_request_admins": "Account registration request",
    "registration_invite": "Account registration invite",
    "registration_ready": "SSO account ready",
    "registration_decline": "Account request declined",
    "registration_existing_account": "Existing account notice",
}

_EMAIL_EVENT_CATEGORIES = {
    "admin_help": "Accounts",
    "registration_request_admins": "Accounts",
    "registration_invite": "Accounts",
    "registration_ready": "Accounts",
    "registration_decline": "Accounts",
    "registration_existing_account": "Accounts",
}


def _notification_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def public_search_delivery_reminder_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "enabled": bool(data.get("enabled", True)),
        "interval_days": _notification_int(data.get("interval_days"), 7, minimum=1, maximum=365),
        "loop_seconds": _notification_int(data.get("loop_seconds"), 3600, minimum=300, maximum=86400),
        "batch_size": _notification_int(data.get("batch_size"), 25, minimum=1, maximum=500),
    }


def public_consent_notification_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    timezone = str(data.get("weekly_timezone") or "UTC").strip()[:80] or "UTC"
    return {
        "completed_email_enabled": bool(data.get("completed_email_enabled", True)),
        "weekly_pending_enabled": bool(data.get("weekly_pending_enabled", True)),
        "weekly_weekday": _notification_int(data.get("weekly_weekday"), 4, minimum=0, maximum=6),
        "weekly_hour": _notification_int(data.get("weekly_hour"), 8, minimum=0, maximum=23),
        "weekly_minute": _notification_int(data.get("weekly_minute"), 0, minimum=0, maximum=59),
        "weekly_timezone": timezone,
    }


def public_notifications_config(raw: Optional[Dict[str, Any]], include_webhook: bool = False) -> Dict[str, Any]:
    notifications = raw or {}
    teams = notifications.get("teams") or {}
    teams_events = teams.get("events") or {}
    public_teams_events = {}
    for key, meta in teams_events.items():
        public_teams_events[key] = {
            "enabled": bool(meta.get("enabled", False)),
            "template": meta.get("template") or "",
            "label": _TEAMS_EVENT_LABELS.get(key, key.replace("_", " ").title()),
            "category": _TEAMS_EVENT_CATEGORIES.get(key, "General"),
        }
    email = notifications.get("email") or {}
    email_events = email.get("events") or {}
    public_email_events = {}
    for key, meta in email_events.items():
        public_email_events[key] = {
            "enabled": bool(meta.get("enabled", True)),
            "subject": meta.get("subject") or "",
            "body": meta.get("body") or "",
            "label": _EMAIL_EVENT_LABELS.get(key, key.replace("_", " ").title()),
            "category": _EMAIL_EVENT_CATEGORIES.get(key, "General"),
        }
    settings_ready = bool(load_system_settings().get("initial_setup_completed"))
    has_env_override = (
        not settings_ready
        and bool((os.getenv("SYSADMIN_ANALYST_TEAMS_WEBHOOK") or "").strip())
    )
    return {
        "teams": {
            "webhook_url": (
                MASKED_SECRET_VALUE
                if include_webhook and str(teams.get("webhook_url") or "").strip()
                else ("" if include_webhook else None)
            ),
            "webhook_configured": bool(str(teams.get("webhook_url") or "").strip()),
            "has_env_override": has_env_override,
            "events": public_teams_events,
        },
        "email": {
            "events": public_email_events,
        },
        "search_delivery_reminders": public_search_delivery_reminder_config(notifications.get("search_delivery_reminders")),
        "consent_notifications": public_consent_notification_config(notifications.get("consent_notifications")),
    }

def normalize_institution_config(values: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = values or {}

    domains: List[str] = []
    seen_domains: set[str] = set()
    for raw in data.get("allowed_requestor_email_domains") or []:
        domain = str(raw or "").strip().lower().lstrip("@")
        if not domain:
            continue
        if "@" in domain or "/" in domain or " " in domain or "." not in domain:
            raise ValueError(f"Invalid requestor email domain: {raw}")
        if domain not in seen_domains:
            seen_domains.add(domain)
            domains.append(domain)

    exceptions: List[str] = []
    seen_emails: set[str] = set()
    for raw in data.get("requestor_email_exceptions") or []:
        email = str(raw or "").strip().lower()
        if not email or email in seen_emails:
            continue
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise ValueError(f"Invalid requestor exception email: {raw}")
        seen_emails.add(email)
        exceptions.append(email)

    org_name = str(data.get("org_name") or "").strip()[:255]
    org_short_name = str(data.get("org_short_name") or "").strip()[:80]
    sso_display_name = str(data.get("sso_display_name") or "").strip()[:80]
    support_email = str(data.get("support_email") or "").strip().lower()[:255]
    return {
        "org_name": org_name,
        "org_short_name": org_short_name or org_name,
        "allowed_requestor_email_domains": domains,
        "requestor_email_exceptions": exceptions,
        "employee_id_label": "Employee ID",
        "sso_display_name": sso_display_name or "Single sign-on",
        "support_email": support_email,
    }


def public_institution_config(*, include_exceptions: bool = False) -> Dict[str, Any]:
    institution = normalize_institution_config(load_institution_settings())
    if not include_exceptions:
        institution.pop("requestor_email_exceptions", None)
    return institution

def public_integration_config_summary() -> Dict[str, Any]:
    integrations = load_integration_settings()
    enabled = dict(integrations.get("enabled_integrations") or {})
    enabled.setdefault("log_shipping", integration_enabled("log_shipping"))
    return {
        "providers": {
            "person_lookup_provider": integrations.get("person_lookup_provider") or "none",
            "sso_provider": integrations.get("sso_provider") or "local",
            "ticket_provider": integrations.get("ticket_provider") or "none",
            "mail_provider": integrations.get("mail_provider") or "smtp",
            "esign_provider": integrations.get("esign_provider") or "none",
            "preservation_provider": integrations.get("preservation_provider") or "none",
            "search_export_provider": (
                integrations.get("search_export_provider")
                or provider_value("search_export_provider")
                or "none"
            ),
        },
        "enabled": enabled,
    }


def public_integration_admin_config() -> Dict[str, Any]:
    payload = public_integration_config_summary()
    payload["configs"] = {
        name: public_integration_config(name)
        for name in (
            "oidc",
            "person_lookup",
            "ntp_ack_bridge",
            "servicenow",
            "box",
            "google_workspace",
            "dropbox_business",
            "zoom",
            "intune",
            "jamf",
            "defender",
            "crowdstrike",
            "log_shipping",
            "purview",
            "docusign",
            "slack",
            "ai",
        )
    }
    return payload


