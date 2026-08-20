from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4
from .safe_log import debug_suppressed as _debug_suppressed
from .catalog_defaults import default_preservation_sources, default_ticket_workflows

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = APP_DIR / "data"
DATA_ROOT = Path(os.getenv("APP_DATA_DIR") or os.getenv("SYSTEM_DATA_DIR") or DEFAULT_DATA_ROOT)
DATA_DIR = DATA_ROOT
LOGO_DIR = DATA_ROOT / "logos"
TLS_DIR = DATA_ROOT / "tls"
SETTINGS_PATH = DATA_DIR / "system_settings.json"
_SETTINGS_LOCK = threading.RLock()

for path in (DATA_DIR, LOGO_DIR, TLS_DIR):
    path.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "active_theme": "light",
    "user_theme": "light",
    "logos": [],
    "active_logo": None,
    "branding": {
        "app_name": "DiscoveryOne",
        "app_tagline": "eDiscovery Case Manager",
    },
    "initial_setup_completed": False,
    "initial_setup_completed_at": None,
    "initial_setup_version": 1,
    "deployment": {
        "app_base_url": "",
        "allowed_hosts": [],
        "tls": {
            "mode": "self_signed",
            "common_name": "",
            "certificate_filename": "",
            "private_key_filename": "",
        },
    },
    "custodian_lookup_bootstrap_completed": False,
    "custodian_lookup_last_run_at": None,
    "institution": {
        "org_name": "",
        "org_short_name": "",
        "allowed_requestor_email_domains": [],
        "requestor_email_exceptions": [],
        "internal_counsel_label": "Internal Counsel",
        "sso_display_name": "Single sign-on",
        "support_email": "",
    },
    "enabled_integrations": {
        "servicenow": False,
        "docusign": False,
        "slack": False,
        "purview": False,
        "box": False,
        "google_workspace": False,
        "dropbox_business": False,
        "zoom": False,
        "intune": False,
        "jamf": False,
        "defender": False,
        "crowdstrike": False,
        "log_shipping": False,
        "person_lookup": False,
        "ntp_ack_bridge": False,
        "smtp": False,
        "ai": False,
        "email_intake": False,
    },
    "integrations": {
        "person_lookup_provider": "none",
        "sso_provider": "local",
        "ticket_provider": "none",
        "mail_provider": "smtp",
        "esign_provider": "none",
        "preservation_provider": "none",
        "search_export_provider": "none",
    },
    "integration_configs": {
        "oidc": {},
        "person_lookup": {},
        "ntp_ack_bridge": {
            "bridge_url": "",
            "display_url": "",
            "shared_secret": "",
        },
        "servicenow": {},
        "box": {},
        "google_workspace": {},
        "dropbox_business": {},
        "zoom": {},
        "intune": {},
        "jamf": {},
        "defender": {},
        "crowdstrike": {},
        "log_shipping": {
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "sharepoint_site_id": "",
            "sharepoint_drive_id": "",
            "sharepoint_drive_name": "",
            "sharepoint_folder": "DiscoveryOneLogs",
            "interval_hours": 24,
            "run_on_startup": True,
            "graph_base": "https://graph.microsoft.com/v1.0",
            "scope": "https://graph.microsoft.com/.default",
            "max_file_mb": 250,
            "max_archive_mb": 250,
            "max_files": 5000,
            "timeout_seconds": 120,
            "retry_count": 3,
        },
        "purview": {},
        "docusign": {},
        "slack": {},
        "ai": {},
        "email_intake": {
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "mailbox": "",
            "folder_id": "inbox",
            "poll_interval_seconds": 60,
            "max_messages_per_poll": 50,
            "sender_policy": "any",
            "allowed_senders": "",
            "allowed_sender_domains": "",
            "graph_base": "https://graph.microsoft.com/v1.0",
            "scope": "https://graph.microsoft.com/.default",
            "requestor_from_sender": True,
            "process_existing_on_first_run": False,
            "startup_delay_seconds": 15,
            "timeout_seconds": 30,
            "retry_count": 3
        },
    },
    "preservation_sources": default_preservation_sources(),
    "ticket_workflows": default_ticket_workflows(),
    "matter_types": [
        "Public Record Request",
        "General Litigation",
        "Internal Investigation",
        "Subpoena Request",
    ],
    "case_naming": {
        "mode": "legal_case_name",
    },
    "case_closure": {
        "default_nag_days": 180,
        "loop_seconds": 3600,
        "batch_size": 25,
    },
    "case_status": {
        "ntp_ack_days": 7,
        "consent_received_days": 7,
    },
    "case_requests": {
        "requestor_stats_show_global": False,
        "hold_automation_allow_override": False,
        "auto_rubrik_restore_for_separated_email_holds": False,
        "pending_cleanup_days": 30,
        "pending_cleanup_interval_hours": 12,
        "hold_status_email_delay_seconds": 300,
        "preservation_auto_apply_max_attempts": 3,
        "preservation_auto_apply_delay_seconds": 2.0,
        "preservation_status_max_seconds": 90,
        "preservation_status_interval_seconds": 5.0,
    },
    "smtp": {
        "host": "",
        "port": 587,
        "username": "",
        "from_address": "",
        "use_tls": True,
        "use_ssl": False,
        "timeout_seconds": 15,
        "password": None,
    },
    "notifications": {
        "teams": {
            "webhook_url": "",
            "events": {
                "case_request_submitted": {
                    "enabled": True,
                    "template": "New {request_type} request from {requestor} for {case_label}. Review: {link}",
                },
                "admin_help": {
                    "enabled": True,
                    "template": "Login assistance requested by {identifier} (IP: {ip}). Note: {note}",
                },
                "registration_request": {
                    "enabled": True,
                    "template": "New account registration request from {name} <{email}>. Review in System > Account Requests.",
                },
                "backup_key_missing": {
                    "enabled": True,
                    "template": "Backup encryption key missing; container deployments generate and persist one automatically.",
                },
                "backup_restore": {
                    "enabled": True,
                    "template": "Backup restore {status} by {actor}. File: {filename}. Detail: {detail}",
                },
                "malware_upload_detected": {
                    "enabled": True,
                    "template": "Upload blocked: {filename} (user: {user}, ip: {ip})",
                },
                "consent_completed": {
                    "enabled": True,
                    "template": "Consent completed for {case_label}. Custodian: {custodian_name} <{custodian_email}>. Case: {case_link}",
                },
                "ticket_assigned": {
                    "enabled": True,
                    "template": "Ticket assigned: {ticket} ({ticket_category}) -> {assigned_to}. Case: {case_label}. Ticket: {ticket_link}",
                },
                "ticket_completed": {
                    "enabled": True,
                    "template": "Ticket completed: {ticket} ({ticket_category}). Case: {case_label}. Ticket: {ticket_link}",
                },
            },
        },
        "search_delivery_reminders": {
            "enabled": True,
            "interval_days": 7,
            "loop_seconds": 3600,
            "batch_size": 25,
        },
        "consent_notifications": {
            "completed_email_enabled": True,
            "weekly_pending_enabled": True,
            "weekly_weekday": 4,
            "weekly_hour": 8,
            "weekly_minute": 0,
            "weekly_timezone": "UTC",
        },
        "email": {
            "events": {
                "admin_help": {
                    "enabled": True,
                    "subject": "[{app_name}] Login assistance requested",
                    "body": "A user requested assistance signing in to {app_name}.\n\nIdentifier: {identifier}\nIP address: {ip}\nNote: {note}",
                },
                "registration_request_admins": {
                    "enabled": True,
                    "subject": "[{app_name}] New account registration request",
                    "body": "A new account registration request was submitted.\n\nName: {name}\nEmail: {email}\n\nReview this request in {app_name} > System > Account Requests.",
                },
                "registration_invite": {
                    "enabled": True,
                    "subject": "[{app_name}] Complete your account registration",
                    "body": "Hello {name},\n\nYour {app_name} account request has been approved. Use the link below to {action_text}. This link expires in {expires_hours} hours.\n\n{link}\n\nIf you did not expect this email, ignore it.",
                },
                "registration_ready": {
                    "enabled": True,
                    "subject": "[{app_name}] Your account is ready",
                    "body": "Hello {name},\n\nYour {app_name} account request has been approved and your account is ready. Sign in using your {sso_display_name} credentials.\n\nSign in: {login_link}\n\nIf you did not expect this email, ignore it.",
                },
                "registration_decline": {
                    "enabled": True,
                    "subject": "[{app_name}] Account request update",
                    "body": "Hello {name},\n\nYour {app_name} account request was declined.\n\nReason: {reason}\nPlease contact the eDiscovery administrators if you have questions.",
                },
                "registration_existing_account": {
                    "enabled": True,
                    "subject": "[{app_name}] Account already exists",
                    "body": "You tried to register a {app_name} account, but an account already exists with this email address.\n\nUsername: {username}\n\n{access_guidance}\n\nIf you did not attempt to register, you can ignore this email.",
                },
                "external_ticket_assignee_details": {
                    "enabled": True,
                    "subject": "[{app_name}] Custodian details for ticket {ticket}",
                    "body": "External ticket: {ticket} - {ticket_link}\n\nCase: {case_label}\n\nThe following custodians require {need_label}:\n{custodian_list}\n\nPlease keep these details out of the external ticket.\n\nIf you have any questions, please reach out to the ticket customer.",
                },
            },
        },
    },
    "ntp": {
        "archive_bcc_address": "",
        "archive_copy_required": False,
        "reserved_archive_bcc_addresses": "",
        "ack_automate_url": "",
        "ack_display_url": "",
        "ack_automate_secret": "",
        "reminder_interval_days": 14,
        "reminder_duration_days": 90,
        "reminder_loop_seconds": 900,
    },
    "account_review": {
        "enabled": True,
        "interval_days": 120,
        "check_interval_hours": 12,
        "last_sent_at": None,
    },
    "backups": {
        "automatic_enabled": True,
        "interval_hours": 6,
        "retention_hours": 48,
    },
}


def _merge_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(DEFAULT_SETTINGS)
    result.update({k: v for k, v in settings.items() if v is not None})
    smtp = deepcopy(DEFAULT_SETTINGS["smtp"])
    smtp.update(settings.get("smtp") or {})
    result["smtp"] = smtp
    result["logos"] = settings.get("logos") or []

    branding = deepcopy(DEFAULT_SETTINGS["branding"])
    incoming_branding = settings.get("branding") if isinstance(settings.get("branding"), dict) else {}
    branding.update({k: v for k, v in (incoming_branding or {}).items() if v is not None})
    branding["app_name"] = str(branding.get("app_name") or "DiscoveryOne").strip() or "DiscoveryOne"
    branding["app_tagline"] = str(branding.get("app_tagline") or "").strip()
    result["branding"] = branding

    deployment = deepcopy(DEFAULT_SETTINGS["deployment"])
    incoming_deployment = settings.get("deployment") if isinstance(settings.get("deployment"), dict) else {}
    deployment.update(incoming_deployment or {})
    deployment["allowed_hosts"] = incoming_deployment.get("allowed_hosts") or []
    incoming_tls = incoming_deployment.get("tls") if isinstance(incoming_deployment.get("tls"), dict) else {}
    tls = deepcopy(DEFAULT_SETTINGS["deployment"]["tls"])
    tls.update(incoming_tls or {})
    deployment["tls"] = tls
    result["deployment"] = deployment

    institution = deepcopy(DEFAULT_SETTINGS["institution"])
    incoming_institution = settings.get("institution") if isinstance(settings.get("institution"), dict) else {}
    institution.update(incoming_institution or {})
    institution["allowed_requestor_email_domains"] = incoming_institution.get("allowed_requestor_email_domains") or []
    institution["requestor_email_exceptions"] = incoming_institution.get("requestor_email_exceptions") or []
    result["institution"] = institution

    enabled_integrations = deepcopy(DEFAULT_SETTINGS["enabled_integrations"])
    enabled_integrations.update(settings.get("enabled_integrations") or {})
    result["enabled_integrations"] = enabled_integrations

    integrations = deepcopy(DEFAULT_SETTINGS["integrations"])
    integrations.update(settings.get("integrations") or {})
    result["integrations"] = integrations

    integration_configs = deepcopy(DEFAULT_SETTINGS["integration_configs"])
    incoming_configs = settings.get("integration_configs") if isinstance(settings.get("integration_configs"), dict) else {}
    for key, value in (incoming_configs or {}).items():
        if isinstance(value, dict):
            integration_configs[key] = value
    result["integration_configs"] = integration_configs

    incoming_sources = settings.get("preservation_sources")
    result["preservation_sources"] = incoming_sources if isinstance(incoming_sources, list) else deepcopy(DEFAULT_SETTINGS["preservation_sources"])

    incoming_ticket_workflows = settings.get("ticket_workflows")
    result["ticket_workflows"] = incoming_ticket_workflows if isinstance(incoming_ticket_workflows, list) else deepcopy(DEFAULT_SETTINGS["ticket_workflows"])

    case_naming = deepcopy(DEFAULT_SETTINGS["case_naming"])
    incoming_case_naming = settings.get("case_naming") if isinstance(settings.get("case_naming"), dict) else {}
    mode = str(incoming_case_naming.get("mode") or case_naming["mode"]).strip().lower()
    if mode not in {"legal_case_name", "created_date", "color"}:
        mode = case_naming["mode"]
    case_naming["mode"] = mode
    result["case_naming"] = case_naming

    case_closure = deepcopy(DEFAULT_SETTINGS["case_closure"])
    incoming_case_closure = settings.get("case_closure") if isinstance(settings.get("case_closure"), dict) else {}
    case_closure.update(incoming_case_closure or {})
    result["case_closure"] = case_closure

    case_status = deepcopy(DEFAULT_SETTINGS["case_status"])
    incoming_case_status = settings.get("case_status") if isinstance(settings.get("case_status"), dict) else {}
    case_status.update(incoming_case_status or {})
    result["case_status"] = case_status

    case_requests = deepcopy(DEFAULT_SETTINGS["case_requests"])
    incoming_case_requests = settings.get("case_requests") if isinstance(settings.get("case_requests"), dict) else {}
    case_requests.update(incoming_case_requests or {})
    result["case_requests"] = case_requests

    notifications = deepcopy(DEFAULT_SETTINGS["notifications"])
    incoming = settings.get("notifications") if isinstance(settings.get("notifications"), dict) else {}

    def _merge_notification_channel(channel_name: str, fields: tuple[str, ...]) -> None:
        channel = deepcopy(notifications.get(channel_name, {}))
        incoming_channel = incoming.get(channel_name) if isinstance(incoming.get(channel_name), dict) else {}
        channel.update({k: v for k, v in (incoming_channel or {}).items() if k != "events"})
        default_events = (notifications.get(channel_name) or {}).get("events") or {}
        incoming_events = (incoming_channel or {}).get("events") or {}
        merged_events = {}
        for key, meta in default_events.items():
            merged = deepcopy(meta)
            incoming_meta = incoming_events.get(key) if isinstance(incoming_events.get(key), dict) else {}
            for field in fields:
                if field in incoming_meta:
                    merged[field] = incoming_meta[field]
            merged_events[key] = merged
        for key, meta in incoming_events.items():
            if key in merged_events or not isinstance(meta, dict):
                continue
            merged_events[key] = deepcopy(meta)
        channel["events"] = merged_events
        notifications[channel_name] = channel

    _merge_notification_channel("teams", ("enabled", "template"))
    _merge_notification_channel("email", ("enabled", "subject", "body"))

    reminder_defaults = deepcopy(DEFAULT_SETTINGS["notifications"].get("search_delivery_reminders") or {})
    incoming_reminders = incoming.get("search_delivery_reminders") if isinstance(incoming.get("search_delivery_reminders"), dict) else {}
    reminder_defaults.update(incoming_reminders or {})
    notifications["search_delivery_reminders"] = reminder_defaults

    consent_defaults = deepcopy(DEFAULT_SETTINGS["notifications"].get("consent_notifications") or {})
    incoming_consent = incoming.get("consent_notifications") if isinstance(incoming.get("consent_notifications"), dict) else {}
    consent_defaults.update(incoming_consent or {})
    notifications["consent_notifications"] = consent_defaults
    result["notifications"] = notifications
    ntp = deepcopy(DEFAULT_SETTINGS["ntp"])
    ntp.update(settings.get("ntp") or {})
    result["ntp"] = ntp

    account_review = deepcopy(DEFAULT_SETTINGS["account_review"])
    account_review.update(settings.get("account_review") or {})
    result["account_review"] = account_review

    backups = deepcopy(DEFAULT_SETTINGS["backups"])
    incoming_backups = settings.get("backups") if isinstance(settings.get("backups"), dict) else {}
    backups.update(incoming_backups or {})
    result["backups"] = backups
    return result


def load_stored_system_settings() -> Dict[str, Any]:
    """Return persisted settings without applying defaults."""
    with _SETTINGS_LOCK:
        if not SETTINGS_PATH.exists():
            return {}
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"System settings file is unreadable or invalid: {SETTINGS_PATH}"
            ) from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"System settings file must contain a JSON object: {SETTINGS_PATH}")
    return data


def load_system_settings() -> Dict[str, Any]:
    return _merge_defaults(load_stored_system_settings())


def save_system_settings(data: Dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _merge_defaults(data)
    serialized = json.dumps(sanitized, indent=2)
    temporary_path = SETTINGS_PATH.with_name(
        f".{SETTINGS_PATH.name}.{uuid4().hex}.tmp"
    )
    with _SETTINGS_LOCK:
        try:
            with temporary_path.open("w", encoding="utf-8", newline="") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                temporary_path.chmod(0o600)
            except Exception as exc:
                _debug_suppressed("unable to restrict temporary system settings permissions", exc)
            os.replace(temporary_path, SETTINGS_PATH)
            try:
                SETTINGS_PATH.chmod(0o600)
            except Exception as exc:
                _debug_suppressed("unable to restrict system settings permissions", exc)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except Exception as exc:
                _debug_suppressed("unable to remove temporary system settings file", exc)
