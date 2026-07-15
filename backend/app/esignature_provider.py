from __future__ import annotations

from typing import Optional

from .esignature_provider_adapters import (
    ESignatureProviderAdapter,
    ESignatureProviderAdapterError,
    get_esignature_provider_adapter,
)
from .integration_settings import provider_value


class ESignatureProviderError(Exception):
    """Raised when the configured e-signature provider cannot complete a request."""


def _provider() -> str:
    return provider_value("esign_provider", default="none")


def current_esignature_provider() -> str:
    return _provider()


def _active_adapter(
    *,
    provider: str | None = None,
    required: bool = True,
) -> ESignatureProviderAdapter | None:
    provider = provider or current_esignature_provider()
    if provider not in {"", "none"}:
        adapter = get_esignature_provider_adapter(provider)
        if adapter is None:
            if required:
                raise ESignatureProviderError(
                    f"E-signature provider '{provider}' is not installed. "
                    "Select an available provider in System > Integrations."
                )
            return None
        return adapter

    if required:
        raise ESignatureProviderError(
            "No e-signature provider is configured. "
            "Enable one in System > Integrations."
        )
    return None


def send_consent_request(
    *,
    custodian_name: str,
    custodian_email: str,
    case_name: Optional[str] = None,
    subject: Optional[str] = None,
    message: Optional[str] = None,
    fields: Optional[dict[str, str]] = None,
    provider: str | None = None,
) -> str:
    adapter = _active_adapter(provider=provider)
    try:
        return adapter.send_consent_request(
            custodian_name=custodian_name,
            custodian_email=custodian_email,
            case_name=case_name,
            subject=subject,
            message=message,
            fields=fields,
        )
    except ESignatureProviderAdapterError as exc:
        raise ESignatureProviderError(str(exc)) from exc


def resend_request(request_id: str, *, provider: str | None = None) -> str:
    adapter = _active_adapter(provider=provider)
    try:
        return adapter.resend_request(request_id)
    except ESignatureProviderAdapterError as exc:
        raise ESignatureProviderError(str(exc)) from exc


def void_request(request_id: str, reason: str, *, provider: str | None = None) -> None:
    adapter = _active_adapter(provider=provider)
    try:
        adapter.void_request(request_id, reason)
    except ESignatureProviderAdapterError as exc:
        raise ESignatureProviderError(str(exc)) from exc


def download_completed_document(
    request_id: str,
    *,
    provider: str | None = None,
) -> tuple[bytes, str]:
    adapter = _active_adapter(provider=provider)
    try:
        return adapter.download_completed_document(request_id)
    except ESignatureProviderAdapterError as exc:
        raise ESignatureProviderError(str(exc)) from exc
