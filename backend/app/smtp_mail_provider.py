from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, Optional, Sequence

from fastapi import HTTPException

from .integration_settings import decrypt_secret, integration_active, settings_are_authoritative
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings

@dataclass(slots=True)
class SMTPSettings:
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    use_tls: bool
    use_ssl: bool
    timeout: float
    sender: str
    enabled: bool = True

    @property
    def is_configured(self) -> bool:
        return bool(self.enabled and self.host and self.sender)


def smtp_enabled() -> bool:
    return integration_active("smtp", provider_key="mail_provider", provider="smtp")


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _value_from_env(env_name: str, default: str = "") -> str:
    return (os.getenv(env_name) or default).strip()


def _stored_value(stored: dict, key: str, default: str = "") -> str:
    value = stored.get(key)
    if value is None:
        return default
    return str(value).strip()


def load_smtp_settings() -> SMTPSettings:
    all_settings = load_system_settings()
    stored = (all_settings.get("smtp") or {}).copy()
    settings_ready = settings_are_authoritative(all_settings)
    saved_endpoint = bool(_stored_value(stored, "host") or _stored_value(stored, "from_address"))
    if settings_ready or saved_endpoint:
        host = _stored_value(stored, "host")
        port_raw = _stored_value(stored, "port", "587")
        username = _stored_value(stored, "username") or None
        raw_password = stored.get("password")
        sender = _stored_value(stored, "from_address")
        use_ssl = bool(stored.get("use_ssl", False))
        use_tls = bool(stored.get("use_tls", True))
        timeout_raw = _stored_value(stored, "timeout_seconds", "15")
    else:
        host = _value_from_env("SMTP_HOST")
        port_raw = _value_from_env("SMTP_PORT", "587")
        username = _value_from_env("SMTP_USERNAME") or None
        raw_password = os.getenv("SMTP_PASSWORD")
        sender = _value_from_env("SMTP_FROM_ADDRESS")
        use_ssl = _bool_env("SMTP_USE_SSL", False)
        use_tls = _bool_env("SMTP_USE_TLS", True)
        timeout_raw = _value_from_env("SMTP_TIMEOUT_SECONDS", "15")
    try:
        port = int(port_raw or "587")
    except (TypeError, ValueError):
        port = 587
    password = decrypt_secret(raw_password) if raw_password else None
    try:
        timeout = max(1.0, min(300.0, float(timeout_raw or "15")))
    except (TypeError, ValueError):
        timeout = 15.0

    return SMTPSettings(
        host=host,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls and not use_ssl,  # SSL sockets can't also use starttls
        use_ssl=use_ssl,
        timeout=timeout,
        sender=sender,
        enabled=smtp_enabled(),
    )


def _build_message(
    *,
    sender: str,
    recipients: Sequence[str],
    subject: str,
    body: str,
    html: Optional[str] = None,
    reply_to: Optional[Sequence[str]] = None,
    cc: Optional[Sequence[str]] = None,
    bcc: Optional[Sequence[str]] = None,
    importance: Optional[str] = None,
) -> EmailMessage:
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if reply_to:
        msg["Reply-To"] = ", ".join(reply_to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or "(no subject)"
    if importance:
        imp = importance.strip().lower()
        if imp in {"high", "normal", "low"}:
            msg["Importance"] = {"high": "High", "normal": "Normal", "low": "Low"}[imp]
            if imp == "high":
                msg["X-Priority"] = "1"
                msg["X-MSMail-Priority"] = "High"
                msg["Priority"] = "urgent"
            elif imp == "low":
                msg["X-Priority"] = "5"
                msg["X-MSMail-Priority"] = "Low"
                msg["Priority"] = "non-urgent"
    msg.set_content(body or "")
    if html:
        msg.add_alternative(html, subtype="html")
    if bcc:
        # BCC is not stored in headers for privacy; track separately
        msg["X-Bcc-Count"] = str(len(bcc))
    return msg


def _send_smtp_email(
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
    settings: Optional[SMTPSettings] = None,
    audit_log: bool = True,
) -> None:
    settings = settings or load_smtp_settings()
    if not settings.is_configured:
        if not getattr(settings, "enabled", True):
            raise HTTPException(status_code=500, detail="SMTP mail provider is disabled")
        raise HTTPException(status_code=500, detail="SMTP is not configured")
    clean_to = _clean_addresses(recipients)
    clean_cc = _clean_addresses(cc)
    clean_bcc = _clean_addresses(bcc)
    clean_reply_to = _clean_addresses(reply_to)

    header_sender = (from_override or "").strip() or settings.sender
    msg = _build_message(
        sender=header_sender,
        recipients=clean_to,
        subject=subject,
        body=body,
        html=html,
        reply_to=clean_reply_to or None,
        cc=clean_cc,
        bcc=clean_bcc,
        importance=importance,
    )
    if not clean_to and not clean_cc and not clean_bcc:
        raise HTTPException(status_code=400, detail="At least one recipient is required")
    all_recipients = list(dict.fromkeys(clean_to + clean_cc + clean_bcc))

    try:
        smtp_client = _smtp_client(settings)
        with smtp_client as client:
            client.send_message(msg, from_addr=settings.sender, to_addrs=all_recipients)
        if audit_log:
            _audit_email_sent(
                settings=settings,
                to_addrs=clean_to,
                cc_addrs=clean_cc,
                bcc_addrs=clean_bcc,
                reply_to_addrs=clean_reply_to,
                subject=subject,
                from_header=header_sender,
                importance=importance,
                has_html=bool(html),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to send email: {exc}") from exc


def _audit_email_sent(
    *,
    settings: SMTPSettings,
    to_addrs: Sequence[str],
    cc_addrs: Sequence[str],
    bcc_addrs: Sequence[str],
    reply_to_addrs: Sequence[str],
    subject: str,
    from_header: str,
    importance: Optional[str],
    has_html: bool,
) -> None:
    """
    Best-effort audit log for successful email sends.

    Avoid logging body/html content; only metadata is persisted.
    """
    try:
        from .audit import log_event
        from .database import SessionLocal
    except Exception:
        return

    details = {
        "subject": subject or "(no subject)",
        "to": list(to_addrs or []),
        "cc": list(cc_addrs or []),
        "bcc_count": int(len(bcc_addrs or [])),
        "reply_to": list(reply_to_addrs or []),
        "from": (from_header or "").strip() or None,
        "smtp_sender": (getattr(settings, "sender", "") or "").strip() or None,
        "recipients_total": int(len(set([*(to_addrs or []), *(cc_addrs or []), *(bcc_addrs or [])]))),
        "importance": (importance or "").strip() or None,
        "has_html": bool(has_html),
        "smtp_host": (getattr(settings, "host", "") or "").strip() or None,
        "smtp_port": getattr(settings, "port", None),
        "smtp_use_tls": bool(getattr(settings, "use_tls", False)),
        "smtp_use_ssl": bool(getattr(settings, "use_ssl", False)),
    }

    db = None
    try:
        db = SessionLocal()
        log_event(
            db,  # type: ignore[arg-type]
            action="email_sent",
            actor_id=None,
            target_type="email",
            target_id=None,
            details=details,
            request=None,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in emailer.py:219", exc)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception as exc:
                _debug_suppressed("suppressed exception in emailer.py:225", exc)


def _clean_addresses(values: Optional[Iterable[str]]) -> list[str]:
    out: list[str] = []
    if not values:
        return out
    for value in values:
        addr = (value or "").strip()
        if addr:
            out.append(addr)
    return out


def _smtp_client(settings: SMTPSettings):
    if settings.use_ssl:
        context = ssl.create_default_context()
        client = smtplib.SMTP_SSL(
            settings.host,
            settings.port,
            timeout=settings.timeout,
            context=context,
        )
    else:
        client = smtplib.SMTP(
            settings.host,
            settings.port,
            timeout=settings.timeout,
        )
    client.ehlo()
    if settings.use_tls:
        context = ssl.create_default_context()
        client.starttls(context=context)
        client.ehlo()
    if settings.username and settings.password:
        client.login(settings.username, settings.password)
    return client

class SMTPMailProviderAdapter:
    name = "smtp"
    display_name = "SMTP"

    def is_available(self) -> bool:
        return load_smtp_settings().is_configured

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
        provider_context=None,
        audit_log: bool = True,
    ) -> None:
        settings = (
            provider_context
            if isinstance(provider_context, SMTPSettings)
            else load_smtp_settings()
        )
        _send_smtp_email(
            recipients=recipients,
            subject=subject,
            body=body,
            html=html,
            from_override=from_override,
            reply_to=reply_to,
            cc=cc,
            bcc=bcc,
            importance=importance,
            settings=settings,
            audit_log=audit_log,
        )
