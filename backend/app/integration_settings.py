from __future__ import annotations

import base64
import hashlib
import os
from typing import Any, Iterable
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from .system_settings import load_system_settings

MASKED_SECRET_VALUE = "__configured__"

SECRET_FIELDS = {
    "oidc": {"client_secret"},
    "person_lookup": {"http_auth_value"},
    "ntp_ack_bridge": {"shared_secret"},
    "servicenow": {"password", "oauth_client_secret"},
    "box": {"client_secret", "jwt_private_key", "jwt_passphrase"},
    "google_workspace": {"service_account_private_key"},
    "dropbox_business": {"client_secret", "refresh_token", "access_token"},
    "zoom": {"client_secret"},
    "intune": {"client_secret"},
    "jamf": {"client_secret", "password"},
    "defender": {"client_secret"},
    "crowdstrike": {"client_secret"},
    "log_shipping": {"client_secret"},
    "purview": {"client_secret"},
    "docusign": {"private_key", "connect_key", "connect_keys"},
    "slack": {"legal_holds_token", "client_secret", "shared_secret", "oauth_state_secret"},
    "ai": {"api_key"},
    "email_intake": {"client_secret"},
}

_SECRET_FIELD_SUFFIXES = (
    "_secret",
    "_password",
    "_token",
    "_private_key",
    "_passphrase",
    "_api_key",
    "_auth_value",
    "_connect_key",
    "_connect_keys",
)
_SECRET_FIELD_NAMES = {
    "secret",
    "password",
    "token",
    "private_key",
    "passphrase",
    "api_key",
}


def is_secret_field(name: str, key: str) -> bool:
    normalized_name = str(name or "").strip().lower()
    normalized_key = str(key or "").strip().lower()
    return (
        normalized_key in SECRET_FIELDS.get(normalized_name, set())
        or normalized_key in _SECRET_FIELD_NAMES
        or normalized_key.endswith(_SECRET_FIELD_SUFFIXES)
    )


def _has_config_value(values: dict[str, Any], key: str) -> bool:
    text = str((values or {}).get(key) or "").strip()
    return bool(text and text != MASKED_SECRET_VALUE)


def _enabled(enabled_integrations: dict[str, Any] | None, key: str) -> bool:
    return bool((enabled_integrations or {}).get(key))


def _validate_https_url(errors: list[str], label: str, value: Any) -> None:
    text = str(value or "").strip()
    if not text:
        return
    try:
        parsed = urlparse(text)
    except Exception:
        parsed = None
    if not parsed or parsed.scheme.lower() != "https" or not parsed.netloc:
        errors.append(f"{label} must be a valid HTTPS URL")


def _validate_number(
    errors: list[str],
    label: str,
    value: Any,
    *,
    minimum: float,
    maximum: float,
    integer_only: bool = False,
) -> None:
    if value is None or str(value).strip() == "":
        return
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric")
        return
    if parsed < minimum or parsed > maximum or (integer_only and not parsed.is_integer()):
        errors.append(f"{label} must be between {minimum:g} and {maximum:g}")


INTEGRATION_ENV_FLAGS = {
    "servicenow": "SERVICENOW_ENABLED",
    "docusign": "DOCUSIGN_ENABLED",
    "slack": "SLACK_ENABLED",
    "purview": "PURVIEW_ENABLED",
    "box": "BOX_ENABLED",
    "google_workspace": "GOOGLE_WORKSPACE_ENABLED",
    "dropbox_business": "DROPBOX_BUSINESS_ENABLED",
    "zoom": "ZOOM_ENABLED",
    "intune": "INTUNE_ENABLED",
    "jamf": "JAMF_ENABLED",
    "defender": "DEFENDER_ENABLED",
    "crowdstrike": "CROWDSTRIKE_ENABLED",
    "log_shipping": "LOG_SHIP_ENABLED",
    "person_lookup": "PERSON_LOOKUP_ENABLED",
    "smtp": "SMTP_ENABLED",
    "ai": "AI_ENABLED",
}


PROVIDER_ENV_NAMES = {
    "person_lookup_provider": "PERSON_LOOKUP_PROVIDER",
    "sso_provider": "SSO_PROVIDER",
    "ticket_provider": "TICKET_PROVIDER",
    "mail_provider": "MAIL_PROVIDER",
    "esign_provider": "ESIGN_PROVIDER",
    "preservation_provider": "PRESERVATION_PROVIDER",
    "search_export_provider": "SEARCH_EXPORT_PROVIDER",
}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _setup_completed(settings: dict[str, Any]) -> bool:
    return bool(settings.get("initial_setup_completed"))


def settings_are_authoritative(settings: dict[str, Any] | None = None) -> bool:
    """Return whether app-managed settings must override legacy environment values."""
    if settings is None:
        try:
            settings = load_system_settings()
        except Exception:
            settings = {}
    return _setup_completed(settings or {})


def integration_enabled(name: str, *, default: bool = False) -> bool:
    key = str(name or "").strip().lower()
    if not key:
        return False
    try:
        settings = load_system_settings()
    except Exception:
        settings = {}
    enabled = settings.get("enabled_integrations") or {}
    if _setup_completed(settings):
        if isinstance(enabled, dict) and key in enabled:
            return bool(enabled.get(key))
        return bool(default)
    env_name = INTEGRATION_ENV_FLAGS.get(key)
    if env_name:
        raw = os.getenv(env_name)
        if raw is not None:
            return _truthy(raw)
    if isinstance(enabled, dict) and key in enabled:
        return bool(enabled.get(key))
    return bool(default)


def provider_value(name: str, *, default: str = "none") -> str:
    key = str(name or "").strip().lower()
    try:
        settings = load_system_settings()
    except Exception:
        settings = {}
    integrations = settings.get("integrations") or {}
    if _setup_completed(settings):
        if isinstance(integrations, dict):
            value = integrations.get(key)
            if value is not None:
                return str(value or "").strip().lower() or default
        return default
    env_name = PROVIDER_ENV_NAMES.get(key)
    if env_name:
        raw = os.getenv(env_name)
        if raw is not None:
            return str(raw or "").strip().lower() or default
    if isinstance(integrations, dict):
        value = integrations.get(key)
        if value is not None:
            return str(value or "").strip().lower() or default
    return default


def integration_active(
    name: str,
    *,
    provider_key: str | None = None,
    provider: str | None = None,
    default: bool = False,
) -> bool:
    if integration_enabled(name, default=default):
        return True
    if provider_key and provider:
        return provider_value(provider_key) == str(provider).strip().lower()
    return False


def validate_integration_settings(
    *,
    enabled_integrations: dict[str, Any] | None,
    providers: dict[str, Any] | None,
    configs: dict[str, dict[str, Any]] | None,
    smtp: dict[str, Any] | None = None,
) -> None:
    """
    Validate that enabled providers have enough stored configuration to work.

    Values may be plaintext, encrypted, or masked placeholders after a public
    settings round trip. This only checks presence and provider-specific shape;
    provider clients still perform live connection validation when used.
    """
    errors: list[str] = []
    enabled = enabled_integrations or {}
    provider_values = providers or {}
    config_values = configs or {}

    if _enabled(enabled, "smtp"):
        smtp_values = smtp or {}
        missing = []
        if not _has_config_value(smtp_values, "host"):
            missing.append("host")
        if not _has_config_value(smtp_values, "from_address"):
            missing.append("from address")
        if missing:
            errors.append(f"SMTP is enabled but missing {', '.join(missing)}")
        _validate_number(errors, "SMTP timeout seconds", smtp_values.get("timeout_seconds"), minimum=1, maximum=300)

    if _enabled(enabled, "ntp_ack_bridge"):
        bridge = config_values.get("ntp_ack_bridge") or {}
        missing = [
            label
            for key, label in (
                ("bridge_url", "external acknowledgement bridge URL"),
                ("display_url", "acknowledgement display URL"),
                ("shared_secret", "shared secret"),
            )
            if not _has_config_value(bridge, key)
        ]
        if missing:
            errors.append(
                f"DMZ NTP Acknowledgment Server is enabled but missing {', '.join(missing)}"
            )
        _validate_https_url(
            errors,
            "DMZ NTP external acknowledgement bridge URL",
            bridge.get("bridge_url"),
        )
        _validate_https_url(
            errors,
            "DMZ NTP acknowledgement display URL",
            bridge.get("display_url"),
        )
        bridge_url = str(bridge.get("bridge_url") or "").strip()
        if bridge_url and "{token}" not in bridge_url:
            errors.append(
                "DMZ NTP external acknowledgement bridge URL must include {token}"
            )

    if _enabled(enabled, "ai"):
        ai = config_values.get("ai") or {}
        missing = [label for key, label in (("url", "URL"), ("model", "model")) if not _has_config_value(ai, key)]
        if missing:
            errors.append(f"AI is enabled but missing {', '.join(missing)}")
        _validate_https_url(errors, "AI endpoint URL", ai.get("url"))

    if str(provider_values.get("sso_provider") or "local").strip().lower() == "oidc":
        oidc = config_values.get("oidc") or {}
        missing = [label for key, label in (
            ("issuer", "issuer URL"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
        ) if not _has_config_value(oidc, key)]
        if missing:
            errors.append(f"OIDC single sign-on is selected but missing {', '.join(missing)}")
        _validate_https_url(errors, "OIDC issuer URL", oidc.get("issuer"))
        _validate_https_url(errors, "OIDC redirect URI", oidc.get("redirect_uri"))
        _validate_https_url(errors, "OIDC logout redirect URI", oidc.get("logout_redirect_uri"))

    person_provider = str(provider_values.get("person_lookup_provider") or "none").strip().lower()
    if _enabled(enabled, "person_lookup"):
        person = config_values.get("person_lookup") or {}
        if person_provider in {"", "none"}:
            errors.append("Person lookup is enabled but no provider is selected")
        elif person_provider == "csv":
            if not _has_config_value(person, "csv_path"):
                errors.append("CSV person lookup is enabled but missing CSV file path")
        elif person_provider in {"http", "api", "idp", "hr"}:
            if not _has_config_value(person, "http_url"):
                errors.append("API person lookup is enabled but missing lookup API URL")
            _validate_https_url(errors, "Person lookup API URL", person.get("http_url"))
            _validate_number(errors, "Person lookup timeout seconds", person.get("http_timeout_seconds"), minimum=1, maximum=120)
        else:
            from .person_lookup import person_lookup_provider_names

            if person_provider not in person_lookup_provider_names():
                errors.append(
                    f"Person lookup provider '{person_provider}' is not supported"
                )
        _validate_number(errors, "Person lookup maximum custodians", person.get("max_custodians"), minimum=1, maximum=1000, integer_only=True)

    ticket_provider = str(provider_values.get("ticket_provider") or "none").strip().lower()
    if _enabled(enabled, "servicenow") or ticket_provider == "servicenow":
        servicenow = config_values.get("servicenow") or {}
        missing = []
        if not _has_config_value(servicenow, "base_url"):
            missing.append("base URL")
        auth_type = str(servicenow.get("auth_type") or "basic").strip().lower()
        if auth_type not in {"basic", "oauth"}:
            errors.append("ServiceNow auth type must be basic or oauth")
        elif auth_type == "oauth":
            for key, label in (
                ("oauth_client_id", "OAuth client ID"),
                ("oauth_client_secret", "OAuth client secret"),
            ):
                if not _has_config_value(servicenow, key):
                    missing.append(label)
        else:
            for key, label in (("username", "username"), ("password", "password")):
                if not _has_config_value(servicenow, key):
                    missing.append(label)
        if missing:
            errors.append(f"ServiceNow is enabled but missing {', '.join(missing)}")
        _validate_https_url(errors, "ServiceNow base URL", servicenow.get("base_url"))
        _validate_https_url(errors, "ServiceNow OAuth token URL", servicenow.get("oauth_token_url"))
    if _enabled(enabled, "box"):
        box = config_values.get("box") or {}
        missing = [label for key, label in (
            ("enterprise_id", "enterprise ID"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
            ("jwt_key_id", "JWT public key ID"),
            ("jwt_private_key", "JWT private key"),
            ("jwt_passphrase", "JWT passphrase"),
        ) if not _has_config_value(box, key)]
        if missing:
            errors.append(f"Box is enabled but missing {', '.join(missing)}")

    google_selected = str(provider_values.get("preservation_provider") or "none").strip().lower() == "google_workspace"
    if _enabled(enabled, "google_workspace") or google_selected:
        google = config_values.get("google_workspace") or {}
        missing = [label for key, label in (
            ("customer_id", "customer ID"),
            ("delegated_admin_email", "delegated admin email"),
            ("service_account_client_email", "service account client email"),
            ("service_account_private_key", "service account private key"),
        ) if not _has_config_value(google, key)]
        scopes = str(google.get("vault_scopes") or "").strip()
        if "https://www.googleapis.com/auth/ediscovery" not in scopes.split():
            missing.append("Google Vault eDiscovery scope")
        if missing:
            errors.append(f"Google Workspace is enabled but missing {', '.join(missing)}")

    if _enabled(enabled, "dropbox_business"):
        dropbox = config_values.get("dropbox_business") or {}
        missing = [label for key, label in (
            ("team_id", "team ID"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
        ) if not _has_config_value(dropbox, key)]
        if missing:
            errors.append(f"Dropbox Business is enabled but missing {', '.join(missing)}")

    if _enabled(enabled, "zoom"):
        zoom = config_values.get("zoom") or {}
        missing = [label for key, label in (
            ("account_id", "account ID"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
        ) if not _has_config_value(zoom, key)]
        if missing:
            errors.append(f"Zoom is enabled but missing {', '.join(missing)}")

    for key, label in (
        ("intune", "Microsoft Intune"),
        ("defender", "Microsoft Defender"),
    ):
        if _enabled(enabled, key):
            cfg = config_values.get(key) or {}
            missing = [field_label for field_key, field_label in (
                ("tenant_id", "tenant ID"),
                ("client_id", "client ID"),
                ("client_secret", "client secret"),
            ) if not _has_config_value(cfg, field_key)]
            if missing:
                errors.append(f"{label} is enabled but missing {', '.join(missing)}")

    if _enabled(enabled, "jamf"):
        jamf = config_values.get("jamf") or {}
        missing = []
        if not _has_config_value(jamf, "base_url"):
            missing.append("base URL")
        auth_type = str(jamf.get("auth_type") or "oauth").strip().lower()
        if auth_type not in {"oauth", "basic"}:
            errors.append("Jamf auth type must be oauth or basic")
        elif auth_type == "basic":
            for key, label in (("username", "username"), ("password", "password")):
                if not _has_config_value(jamf, key):
                    missing.append(label)
        else:
            for key, label in (("client_id", "client ID"), ("client_secret", "client secret")):
                if not _has_config_value(jamf, key):
                    missing.append(label)
        if missing:
            errors.append(f"Jamf is enabled but missing {', '.join(missing)}")

    if _enabled(enabled, "crowdstrike"):
        crowdstrike = config_values.get("crowdstrike") or {}
        missing = [label for key, label in (
            ("base_url", "base URL"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
        ) if not _has_config_value(crowdstrike, key)]
        if missing:
            errors.append(f"CrowdStrike is enabled but missing {', '.join(missing)}")

    if _enabled(enabled, "log_shipping"):
        log_shipping = config_values.get("log_shipping") or {}
        missing = [label for key, label in (
            ("tenant_id", "tenant ID"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
            ("sharepoint_site_id", "SharePoint site ID"),
        ) if not _has_config_value(log_shipping, key)]
        if not (
            _has_config_value(log_shipping, "sharepoint_drive_id")
            or _has_config_value(log_shipping, "sharepoint_drive_name")
        ):
            missing.append("SharePoint drive ID or drive name")
        if missing:
            errors.append(f"Log shipping is enabled but missing {', '.join(missing)}")

        graph_base = str(log_shipping.get("graph_base") or "").strip()
        if graph_base and not graph_base.lower().startswith("https://"):
            errors.append("Log shipping Graph base must use HTTPS")
        scope = str(log_shipping.get("scope") or "").strip()
        if "scope" in log_shipping and not scope:
            errors.append("Log shipping scope cannot be empty")

        numeric_limits = (
            ("interval_hours", "interval hours", 1.0, 720.0, False),
            ("max_file_mb", "maximum file size", 1.0, 250.0, False),
            ("max_archive_mb", "maximum archive size", 1.0, 250.0, False),
            ("max_files", "maximum file count", 1.0, 5000.0, True),
            ("timeout_seconds", "timeout seconds", 5.0, 300.0, False),
            ("retry_count", "retry count", 0.0, 10.0, True),
        )
        for field, label, minimum, maximum, integer_only in numeric_limits:
            raw = log_shipping.get(field)
            if raw is None or str(raw).strip() == "":
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                errors.append(f"Log shipping {label} must be numeric")
                continue
            if value < minimum or value > maximum or (integer_only and not value.is_integer()):
                errors.append(
                    f"Log shipping {label} must be between {minimum:g} and {maximum:g}"
                )

    if _enabled(enabled, "email_intake"):
        email_intake = config_values.get("email_intake") or {}
        missing = [label for key, label in (
            ("tenant_id", "tenant ID"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
            ("mailbox", "mailbox address"),
            ("folder_id", "mail folder ID or well-known name"),
        ) if not _has_config_value(email_intake, key)]
        if missing:
            errors.append(f"Email Intake is enabled but missing {', '.join(missing)}")
        _validate_https_url(errors, "Email Intake Graph base", email_intake.get("graph_base"))
        _validate_number(
            errors,
            "Email Intake polling interval seconds",
            email_intake.get("poll_interval_seconds"),
            minimum=15,
            maximum=86400,
            integer_only=True,
        )
        _validate_number(
            errors,
            "Email Intake maximum messages per poll",
            email_intake.get("max_messages_per_poll"),
            minimum=1,
            maximum=500,
            integer_only=True,
        )
        policy = str(email_intake.get("sender_policy") or "any").strip().lower()
        if policy not in {"any", "organization", "allowlist"}:
            errors.append("Email Intake sender policy must be any, organization, or allowlist")
        if policy == "allowlist" and not (
            _has_config_value(email_intake, "allowed_senders")
            or _has_config_value(email_intake, "allowed_sender_domains")
        ):
            errors.append("Email Intake allowlist policy requires allowed senders or sender domains")

    if _enabled(enabled, "docusign") or str(provider_values.get("esign_provider") or "none").strip().lower() == "docusign":
        docusign = config_values.get("docusign") or {}
        missing = [label for key, label in (
            ("base_url", "base URL"),
            ("account_id", "account ID"),
            ("template_id", "template ID"),
            ("integration_key", "integration key"),
            ("user_id", "user ID"),
            ("private_key", "private key"),
        ) if not _has_config_value(docusign, key)]
        if missing:
            errors.append(f"DocuSign is enabled but missing {', '.join(missing)}")
        _validate_https_url(errors, "DocuSign base URL", docusign.get("base_url"))

    if _enabled(enabled, "purview") or str(provider_values.get("preservation_provider") or "none").strip().lower() == "purview":
        purview = config_values.get("purview") or {}
        missing = [label for key, label in (
            ("tenant_id", "tenant ID"),
            ("client_id", "client ID"),
            ("client_secret", "client secret"),
        ) if not _has_config_value(purview, key)]
        if missing:
            errors.append(f"Microsoft Purview is enabled but missing {', '.join(missing)}")
        for key, label in (
            ("graph_base", "Purview Graph beta base"),
            ("graph_base_v1", "Purview Graph v1 base"),
            ("security_base", "Purview security base"),
        ):
            _validate_https_url(errors, label, purview.get(key))
        _validate_number(errors, "Purview HTTP timeout seconds", purview.get("http_timeout_seconds"), minimum=5, maximum=300)
        _validate_number(errors, "Purview HTTP retry count", purview.get("http_retry_count"), minimum=0, maximum=10, integer_only=True)

    if _enabled(enabled, "slack"):
        slack = config_values.get("slack") or {}
        if not _has_config_value(slack, "legal_holds_token"):
            errors.append("Slack is enabled but missing Legal Holds token")
        for key, label in (
            ("api_base", "Slack API base"),
            ("oauth_redirect_uri", "Slack OAuth redirect URI"),
            ("oauth_authorize_url", "Slack OAuth authorize URL"),
            ("oauth_access_url", "Slack OAuth token URL"),
        ):
            _validate_https_url(errors, label, slack.get(key))
        _validate_number(errors, "Slack OAuth state lifetime seconds", slack.get("oauth_state_ttl_seconds"), minimum=60, maximum=3600, integer_only=True)

    if errors:
        raise ValueError("; ".join(errors))


def _key_material() -> bytes:
    raw = (os.getenv("SETTINGS_ENCRYPTION_KEY") or "").strip()
    if raw:
        return raw.encode("utf-8")
    secret = (os.getenv("SECRET_KEY") or "").encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(secret).digest())


def _fernet() -> Fernet:
    return Fernet(_key_material())


def encrypt_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("enc:v1:"):
        return text
    return "enc:v1:" + _fernet().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt_secret(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("enc:v1:"):
        return text
    try:
        return _fernet().decrypt(text.removeprefix("enc:v1:").encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def sanitize_integration_config(name: str, values: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in values.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        if is_secret_field(name, clean_key):
            encrypted = encrypt_secret(value)
            if encrypted:
                out[clean_key] = encrypted
        else:
            out[clean_key] = value
    return out


def merge_integration_config(name: str, existing: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(existing or {})
    if not isinstance(incoming, dict):
        return base
    for key, value in incoming.items():
        clean_key = str(key or "").strip()
        if not clean_key:
            continue
        if is_secret_field(name, clean_key):
            text = str(value or "").strip()
            if not text or text == MASKED_SECRET_VALUE:
                continue
            base[clean_key] = encrypt_secret(text)
            continue
        if value is None:
            base.pop(clean_key, None)
        else:
            base[clean_key] = value
    return base


def get_integration_config(name: str, *, reveal_secrets: bool = True) -> dict[str, Any]:
    configs = load_system_settings().get("integration_configs") or {}
    raw = configs.get(name) if isinstance(configs, dict) else {}
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    if reveal_secrets:
        for key in list(out):
            if is_secret_field(name, key):
                out[key] = decrypt_secret(out.get(key))
    return out


def public_integration_config(name: str) -> dict[str, Any]:
    raw = get_integration_config(name, reveal_secrets=False)
    out = dict(raw)
    for key in list(out):
        if is_secret_field(name, key) and out.get(key):
            out[key] = MASKED_SECRET_VALUE
    return out


def stored_value(name: str, key: str, *, settings: dict[str, Any] | None = None) -> str:
    if settings is None:
        try:
            settings = load_system_settings()
        except Exception:
            settings = {}
    configs = (settings or {}).get("integration_configs") or {}
    config = configs.get(name) if isinstance(configs, dict) else {}
    value = config.get(key) if isinstance(config, dict) else None
    if is_secret_field(name, key):
        value = decrypt_secret(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value or "").strip()


def config_value(name: str, key: str, env_names: str | Iterable[str], default: str = "") -> str:
    try:
        settings = load_system_settings()
    except Exception:
        settings = {}
    stored = stored_value(name, key, settings=settings)
    if stored:
        return stored
    if settings_are_authoritative(settings):
        return default
    names = [env_names] if isinstance(env_names, str) else list(env_names)
    for env_name in names:
        value = (os.getenv(env_name) or "").strip()
        if value:
            return value
    return default
