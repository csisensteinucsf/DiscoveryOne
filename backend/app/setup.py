from __future__ import annotations

import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .database import get_db
from .file_security import scan_payload, validate_logo_bytes
from .integration_settings import encrypt_secret, validate_integration_settings
from .integration_policy import (
    merge_enabled_integrations,
    merge_integration_configs,
    merge_provider_settings,
    reconcile_provider_enablement,
)
from .safe_log import debug_suppressed as _debug_suppressed
from .security import hash_password
from .system_settings import LOGO_DIR, TLS_DIR, load_system_settings, save_system_settings
from .case_naming_config import normalize_case_naming
from .system_admin_config import normalize_preservation_sources

router = APIRouter(prefix="/api/setup", tags=["setup"])

ALLOWED_LOGO_TYPES = {"image/png", "image/jpeg"}
ALLOWED_CERT_TYPES = {"application/x-pem-file", "application/pem-certificate-chain", "application/octet-stream", "text/plain", ""}
LOGO_MAX_BYTES = int(os.getenv("LOGO_MAX_BYTES", str(2 * 1024 * 1024)))
TLS_FILE_MAX_BYTES = int(os.getenv("TLS_FILE_MAX_BYTES", str(128 * 1024)))
SETUP_VERSION = 1
SETUP_LOCK_KEY = 0x44314F4E45
_SETUP_PROCESS_LOCK = threading.RLock()


class InitialSetupPayload(BaseModel):
    bootstrap_secret: str = ""
    app_base_url: str = ""
    allowed_hosts: list[str] = Field(default_factory=list)
    tls_mode: str = "self_signed"
    tls_common_name: str = ""
    org_name: str = ""
    org_short_name: str = ""
    allowed_requestor_email_domains: list[str] = Field(default_factory=list)
    requestor_email_exceptions: list[str] = Field(default_factory=list)
    sso_display_name: str = "Single sign-on"
    support_email: str = ""
    app_name: str = "DiscoveryOne"
    app_tagline: str = "eDiscovery Case Manager"
    admin_username: str = "admin"
    admin_password: str
    enabled_integrations: dict[str, bool] = Field(default_factory=dict)
    integrations: dict[str, str] = Field(default_factory=dict)
    integration_configs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    smtp: dict[str, Any] = Field(default_factory=dict)
    preservation_sources: list[dict[str, Any]] = Field(default_factory=list)
    case_naming: dict[str, Any] = Field(default_factory=dict)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _verify_bootstrap_secret(provided: Any) -> None:
    expected = str(os.getenv("SETUP_BOOTSTRAP_SECRET") or "").strip()
    if len(expected) < 24:
        raise HTTPException(
            status_code=503,
            detail="The one-time setup code is unavailable. Restart the backend to generate it.",
        )
    supplied = str(provided or "").strip()
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=403, detail="The one-time setup code is invalid")


def _acquire_setup_transaction_lock(db: Session) -> None:
    bind = db.get_bind()
    dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "")
    if dialect_name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:setup_lock_key)"),
            {"setup_lock_key": SETUP_LOCK_KEY},
        )

def _strong_password(value: str) -> bool:
    text = value or ""
    if len(text) < 12:
        return False
    classes = [
        bool(re.search(r"[a-z]", text)),
        bool(re.search(r"[A-Z]", text)),
        bool(re.search(r"\d", text)),
        bool(re.search(r"[^A-Za-z0-9]", text)),
    ]
    return sum(classes) >= 3


def _split_domains(values: Any) -> list[str]:
    raw_items = values
    if isinstance(values, str):
        raw_items = values.split(",")
    if not isinstance(raw_items, list):
        raw_items = []
    domains: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip().lower()
        if text.startswith("@"):
            text = text[1:]
        if not text:
            continue
        if "@" in text or "/" in text or " " in text or "." not in text:
            raise HTTPException(status_code=422, detail=f"Invalid email domain: {item}")
        if text not in seen:
            seen.add(text)
            domains.append(text)
    return domains


def _split_emails(values: Any) -> list[str]:
    raw_items = values
    if isinstance(values, str):
        raw_items = re.split(r"[\n,]+", values)
    if not isinstance(raw_items, list):
        raw_items = []

    emails: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        try:
            normalized = validate_email(text, check_deliverability=False).normalized.lower()
        except EmailNotValidError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid requestor exception email: {item}") from exc
        if normalized not in seen:
            seen.add(normalized)
            emails.append(normalized)
    return emails


def _split_hosts(values: Any) -> list[str]:
    raw_items = values
    if isinstance(values, str):
        raw_items = values.split(",")
    if not isinstance(raw_items, list):
        raw_items = []
    hosts: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item or "").strip().lower()
        if not text:
            continue
        if "://" in text:
            parsed = urlparse(text)
            text = parsed.hostname or ""
        else:
            text = text.split("/", 1)[0].split(":", 1)[0]
        if not text or "@" in text or " " in text:
            raise HTTPException(status_code=422, detail=f"Invalid hostname: {item}")
        if text not in seen:
            seen.add(text)
            hosts.append(text)
    return hosts


def _normalize_base_url(value: Any) -> str:
    text = _clean_text(value, 2048).rstrip("/")
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(status_code=422, detail="Public app URL must use https:// and include a hostname")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Public app URL must not include credentials, query strings, or fragments")
    return text


def _clean_text(value: Any, max_len: int = 255) -> str:
    return str(value or "").strip()[:max_len]


def _boolish(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_case_naming(value: Any) -> dict[str, str]:
    try:
        return normalize_case_naming(value, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _normalize_smtp_config(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    host = _clean_text(values.get("host"), 255)
    from_address = _clean_text(values.get("from_address"), 255)
    username = _clean_text(values.get("username"), 255)
    password = str(values.get("password") or "").strip()
    try:
        port = int(values.get("port") or 587)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="SMTP port must be a number")
    port = max(1, min(port, 65535))
    use_ssl = _boolish(values.get("use_ssl"), False)
    use_tls = _boolish(values.get("use_tls"), True) and not use_ssl
    try:
        timeout_seconds = max(1.0, min(300.0, float(values.get("timeout_seconds") or 15)))
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="SMTP timeout must be a number")
    normalized = {
        "host": host,
        "port": port,
        "from_address": from_address,
        "username": username,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "timeout_seconds": timeout_seconds,
        "password": encrypt_secret(password) if password else None,
    }
    return {key: value for key, value in normalized.items() if value not in ("", None)}


def _safe_logo_name(orig: str) -> str:
    base = "".join(ch for ch in (orig or "") if ch.isalnum() or ch in (".", "-", "_")).strip()
    if not base:
        base = uuid4().hex[:8] + ".png"
    return base


def _safe_tls_name(orig: str, fallback_ext: str) -> str:
    base = "".join(ch for ch in (orig or "") if ch.isalnum() or ch in (".", "-", "_")).strip()
    if not base:
        base = uuid4().hex[:8] + fallback_ext
    return base


def _public_logo_url(filename: str) -> str:
    return f"/api/system/logo/{filename}"


def _sys_admin_count(db: Session) -> int:
    return int(
        db.query(func.count(models.User.id))
        .filter((models.User.role == "sys_admin") | (models.User.is_admin.is_(True)))
        .scalar()
        or 0
    )


def _setup_completed(settings: dict[str, Any], db: Session) -> bool:
    if bool(settings.get("initial_setup_completed")):
        return True
    if _truthy(os.getenv("INITIAL_SETUP_COMPLETED")):
        return True
    return _sys_admin_count(db) > 0


def _setup_status_payload(db: Session) -> dict[str, Any]:
    settings = load_system_settings()
    completed = _setup_completed(settings, db)
    return {
        "completed": completed,
        "required": not completed,
        "version": int(settings.get("initial_setup_version") or SETUP_VERSION),
        "completed_at": settings.get("initial_setup_completed_at"),
        "has_sys_admin": _sys_admin_count(db) > 0,
    }


@router.get("/status")
def setup_status(db: Session = Depends(get_db)):
    return _setup_status_payload(db)


def _validate_payload(raw_payload: str) -> InitialSetupPayload:
    try:
        parsed = json.loads(raw_payload or "{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid setup payload") from exc
    try:
        payload = InitialSetupPayload(**parsed)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Invalid setup payload") from exc

    payload.org_name = _clean_text(payload.org_name)
    payload.org_short_name = _clean_text(payload.org_short_name)
    payload.app_base_url = _normalize_base_url(payload.app_base_url)
    payload.allowed_hosts = _split_hosts(payload.allowed_hosts)
    payload.tls_mode = _clean_text(payload.tls_mode, 40).lower() or "self_signed"
    if payload.tls_mode not in {"self_signed", "uploaded"}:
        raise HTTPException(status_code=422, detail="TLS mode must be self_signed or uploaded")
    payload.tls_common_name = _clean_text(payload.tls_common_name, 255)
    if payload.app_base_url:
        parsed_base = urlparse(payload.app_base_url)
        base_host = (parsed_base.hostname or "").lower()
        if base_host and base_host not in payload.allowed_hosts:
            payload.allowed_hosts.append(base_host)
    payload.sso_display_name = _clean_text(payload.sso_display_name, 80) or "Single sign-on"
    payload.support_email = _clean_text(payload.support_email, 255)
    payload.app_name = _clean_text(payload.app_name, 80) or "DiscoveryOne"
    payload.app_tagline = _clean_text(payload.app_tagline, 140)
    payload.admin_username = "admin"
    payload.allowed_requestor_email_domains = _split_domains(payload.allowed_requestor_email_domains)
    payload.requestor_email_exceptions = _split_emails(payload.requestor_email_exceptions)
    payload.preservation_sources = normalize_preservation_sources(payload.preservation_sources)
    payload.case_naming = _normalize_case_naming(payload.case_naming)
    payload.smtp = _normalize_smtp_config(payload.smtp)

    if not re.match(r"^[a-z0-9_.@+-]{3,255}$", payload.admin_username):
        raise HTTPException(status_code=422, detail="Admin username must be 3-255 characters and use letters, numbers, dots, dashes, underscores, plus signs, or @.")
    if payload.support_email:
        try:
            payload.support_email = validate_email(payload.support_email, check_deliverability=False).normalized.lower()
        except EmailNotValidError as exc:
            raise HTTPException(status_code=422, detail="Support email is invalid") from exc
    if not _strong_password(payload.admin_password):
        raise HTTPException(status_code=422, detail="Admin password must be at least 12 characters and include at least three character types.")
    return payload


def _merge_setup_settings(settings: dict[str, Any], payload: InitialSetupPayload) -> dict[str, Any]:
    deployment = settings.get("deployment") or {}
    tls = deployment.get("tls") if isinstance(deployment.get("tls"), dict) else {}
    tls.update(
        {
            "mode": payload.tls_mode,
            "common_name": payload.tls_common_name,
        }
    )
    deployment.update(
        {
            "app_base_url": payload.app_base_url,
            "allowed_hosts": payload.allowed_hosts,
            "tls": tls,
        }
    )
    settings["deployment"] = deployment

    institution = settings.get("institution") or {}
    institution.update(
        {
            "org_name": payload.org_name,
            "org_short_name": payload.org_short_name or payload.org_name,
            "allowed_requestor_email_domains": payload.allowed_requestor_email_domains,
            "requestor_email_exceptions": payload.requestor_email_exceptions,
            "sso_display_name": payload.sso_display_name,
            "support_email": payload.support_email,
        }
    )
    settings["institution"] = institution
    settings["branding"] = {
        "app_name": payload.app_name,
        "app_tagline": payload.app_tagline,
    }

    settings["enabled_integrations"] = merge_enabled_integrations(
        settings.get("enabled_integrations"),
        payload.enabled_integrations,
    )
    incoming_providers = dict(payload.integrations or {})
    disabled_provider_bindings = {
        "person_lookup": ("person_lookup_provider",),
        "servicenow": ("ticket_provider",),
        "smtp": ("mail_provider",),
        "docusign": ("esign_provider",),
        "purview": ("preservation_provider", "search_export_provider"),
    }
    for integration, provider_fields in disabled_provider_bindings.items():
        if integration in payload.enabled_integrations and not payload.enabled_integrations[integration]:
            for provider_field in provider_fields:
                incoming_providers[provider_field] = "none"
    try:
        settings["integrations"] = merge_provider_settings(
            settings.get("integrations"),
            incoming_providers,
            reject_unsupported=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings["enabled_integrations"] = reconcile_provider_enablement(
        settings.get("enabled_integrations"),
        settings.get("integrations"),
        changed_provider_fields=set(incoming_providers),
    )
    settings["integration_configs"] = merge_integration_configs(
        settings.get("integration_configs"),
        payload.integration_configs,
    )
    if payload.smtp:
        smtp = settings.get("smtp") if isinstance(settings.get("smtp"), dict) else {}
        smtp.update(payload.smtp)
        settings["smtp"] = smtp
    settings["preservation_sources"] = payload.preservation_sources
    settings["case_naming"] = payload.case_naming
    try:
        validate_integration_settings(
            enabled_integrations=settings.get("enabled_integrations") or {},
            providers=settings.get("integrations") or {},
            configs=settings.get("integration_configs") or {},
            smtp=settings.get("smtp") or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return settings


def _store_logo_if_present(
    *,
    settings: dict[str, Any],
    logo: Optional[UploadFile],
    request: Optional[Request],
) -> Optional[dict[str, Any]]:
    if logo is None:
        return None
    filename = logo.filename or ""
    if not filename:
        return None
    declared = (logo.content_type or "").lower()
    if declared and declared not in ALLOWED_LOGO_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported logo format")
    payload = logo.file.read()
    try:
        logo.file.close()
    except Exception as exc:
        _debug_suppressed("suppressed exception in setup.py:logo_close", exc)
    if not payload:
        return None

    validate_logo_bytes(payload, max_bytes=LOGO_MAX_BYTES)
    logo_id = uuid4().hex[:8]
    safe_name = f"{logo_id}_{_safe_logo_name(filename)}"
    scan_payload(payload, safe_name, request=request, actor=None)
    dest = LOGO_DIR / safe_name
    dest.write_bytes(payload)
    entry = {"id": logo_id, "filename": safe_name}
    logos = settings.setdefault("logos", [])
    logos.append(entry)
    settings["active_logo"] = logo_id
    return {**entry, "url": _public_logo_url(safe_name)}


def _store_tls_file(
    *,
    settings: dict[str, Any],
    file: Optional[UploadFile],
    request: Optional[Request],
    kind: str,
) -> Optional[str]:
    if file is None or not hasattr(file, "filename"):
        return None
    filename = file.filename or ""
    if not filename:
        return None
    declared = (file.content_type or "").lower()
    if declared not in ALLOWED_CERT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported TLS {kind} file type")
    suffix = Path(filename).suffix.lower()
    if kind == "certificate" and suffix not in {".crt", ".cer", ".pem"}:
        raise HTTPException(status_code=415, detail="TLS certificate must be a .crt, .cer, or .pem file")
    if kind == "private_key" and suffix not in {".key", ".pem"}:
        raise HTTPException(status_code=415, detail="TLS private key must be a .key or .pem file")

    payload = file.file.read()
    try:
        file.file.close()
    except Exception as exc:
        _debug_suppressed(f"suppressed exception in setup.py:{kind}_close", exc)
    if not payload:
        return None
    if len(payload) > TLS_FILE_MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"TLS {kind} file is too large")
    text_sample = payload[:8192].decode("utf-8", errors="ignore")
    if "-----BEGIN" not in text_sample:
        raise HTTPException(status_code=422, detail=f"TLS {kind} file must be PEM encoded")

    safe_name = f"{kind}_{uuid4().hex[:8]}_{_safe_tls_name(filename, suffix or '.pem')}"
    scan_payload(payload, safe_name, request=request, actor=None)
    dest = TLS_DIR / safe_name
    dest.write_bytes(payload)
    try:
        dest.chmod(0o600 if kind == "private_key" else 0o644)
    except Exception as exc:
        _debug_suppressed(f"suppressed exception in setup.py:{kind}_chmod", exc)

    deployment = settings.setdefault("deployment", {})
    tls = deployment.setdefault("tls", {})
    if kind == "certificate":
        tls["certificate_filename"] = safe_name
    else:
        tls["private_key_filename"] = safe_name
    return safe_name


@router.post("/complete")
def complete_setup(
    payload: str = Form(...),
    logo: Optional[UploadFile] = File(None),
    tls_certificate: Optional[UploadFile] = File(None),
    tls_private_key: Optional[UploadFile] = File(None),
    request: Request = None,
    db: Session = Depends(get_db),
):
    parsed = _validate_payload(payload)
    _verify_bootstrap_secret(parsed.bootstrap_secret)

    with _SETUP_PROCESS_LOCK:
        _acquire_setup_transaction_lock(db)
        settings = load_system_settings()
        if _setup_completed(settings, db):
            raise HTTPException(status_code=409, detail="Initial setup is already complete")

        existing_username = (
            db.query(models.User)
            .filter(func.lower(models.User.username) == parsed.admin_username.lower())
            .first()
        )
        if existing_username:
            raise HTTPException(status_code=409, detail="Admin username already exists")

        settings = _merge_setup_settings(settings, parsed)
        logo_entry = _store_logo_if_present(settings=settings, logo=logo, request=request)
        cert_name = _store_tls_file(settings=settings, file=tls_certificate, request=request, kind="certificate")
        key_name = _store_tls_file(settings=settings, file=tls_private_key, request=request, kind="private_key")
        if parsed.tls_mode == "uploaded" and not (
            (cert_name or settings.get("deployment", {}).get("tls", {}).get("certificate_filename"))
            and (key_name or settings.get("deployment", {}).get("tls", {}).get("private_key_filename"))
        ):
            raise HTTPException(status_code=422, detail="Uploaded TLS mode requires both a certificate and private key")
        now = datetime.now(timezone.utc).isoformat()
        settings["initial_setup_completed"] = True
        settings["initial_setup_completed_at"] = now
        settings["initial_setup_version"] = SETUP_VERSION

        admin = models.User(
            username=parsed.admin_username,
            email=None,
            first_name="System",
            last_name="Administrator",
            password_hash=hash_password(parsed.admin_password),
            is_admin=True,
            role="sys_admin",
            local_auth_only=True,
            is_active=True,
        )
        db.add(admin)
        try:
            db.commit()
            db.refresh(admin)
        except Exception as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail="Unable to create initial administrator") from exc

        save_system_settings(settings)
        try:
            log_event(
                db,
                action="initial_setup_complete",
                actor_id=admin.id,
                target_type="system",
                details={
                    "admin_username": admin.username,
                    "org_name": parsed.org_name,
                    "logo_uploaded": bool(logo_entry),
                    "tls_mode": parsed.tls_mode,
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in setup.py:audit", exc)

        return {
            "ok": True,
            "setup": _setup_status_payload(db),
            "admin": {"id": admin.id, "username": admin.username, "email": admin.email},
            "logo": logo_entry,
        }
