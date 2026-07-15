from __future__ import annotations

from typing import Optional, Sequence

from fastapi import HTTPException

from .integration_settings import provider_value
from .mail_provider_registry import (
    MailProviderAdapter,
    MailProviderAdapterError,
    get_mail_provider_adapter,
)
from .smtp_mail_provider import SMTPSettings, load_smtp_settings, smtp_enabled

def current_mail_provider() -> str:
    return provider_value("mail_provider", default="none")


def _active_mail_adapter(
    *,
    required: bool,
    preferred: str | None = None,
) -> MailProviderAdapter | None:
    provider = str(preferred or current_mail_provider() or "none").strip().lower()
    if provider not in {"", "none"}:
        adapter = get_mail_provider_adapter(provider)
        if adapter is None:
            if required:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Mail provider '{provider}' is not installed. "
                        "Select an available provider in System > Integrations."
                    ),
                )
            return None
        return adapter

    if required:
        raise HTTPException(
            status_code=500,
            detail=(
                "No mail provider is configured. "
                "Enable one in System > Integrations."
            ),
        )
    return None


def mail_provider_ready() -> bool:
    adapter = _active_mail_adapter(required=False)
    if adapter is None:
        return False
    try:
        return bool(adapter.is_available())
    except Exception:
        return False


def send_email(
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
    # Explicit SMTP settings remain a compatibility path for tests and legacy
    # extensions. Application workflows should omit them and use the selected
    # provider from System > Integrations.
    adapter = _active_mail_adapter(
        required=True,
        preferred="smtp" if settings is not None else None,
    )
    try:
        adapter.send_email(
            recipients=recipients,
            subject=subject,
            body=body,
            html=html,
            from_override=from_override,
            reply_to=reply_to,
            cc=cc,
            bcc=bcc,
            importance=importance,
            provider_context=settings,
            audit_log=audit_log,
        )
    except HTTPException:
        raise
    except MailProviderAdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to send email: {exc}",
        ) from exc
