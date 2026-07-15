from __future__ import annotations

from typing import Optional, Protocol

from . import docusign_client


class ESignatureProviderAdapterError(Exception):
    """Raised when an e-signature adapter cannot complete an operation."""


class ESignatureProviderAdapter(Protocol):
    """Provider-neutral contract used by consent signature workflows."""

    name: str
    display_name: str

    def is_available(self) -> bool:
        ...

    def send_consent_request(
        self,
        *,
        custodian_name: str,
        custodian_email: str,
        case_name: Optional[str] = None,
        subject: Optional[str] = None,
        message: Optional[str] = None,
        fields: Optional[dict[str, str]] = None,
    ) -> str:
        ...

    def resend_request(self, request_id: str) -> str:
        ...

    def void_request(self, request_id: str, reason: str) -> None:
        ...

    def download_completed_document(self, request_id: str) -> tuple[bytes, str]:
        ...


class DocuSignESignatureProviderAdapter:
    name = "docusign"
    display_name = "DocuSign"

    def is_available(self) -> bool:
        return docusign_client.docusign_enabled()

    def send_consent_request(
        self,
        *,
        custodian_name: str,
        custodian_email: str,
        case_name: Optional[str] = None,
        subject: Optional[str] = None,
        message: Optional[str] = None,
        fields: Optional[dict[str, str]] = None,
    ) -> str:
        try:
            text_tabs = [
                {"tabLabel": name, "value": value}
                for name, value in (fields or {}).items()
                if name != "case_name"
            ]
            return docusign_client.send_consent_envelope(
                custodian_name=custodian_name,
                custodian_email=custodian_email,
                case_name=case_name,
                subject=subject,
                message=message,
                text_tabs=text_tabs,
            )
        except docusign_client.DocuSignError as exc:
            raise ESignatureProviderAdapterError(str(exc)) from exc

    def resend_request(self, request_id: str) -> str:
        try:
            return docusign_client.resend_envelope(request_id)
        except docusign_client.DocuSignError as exc:
            raise ESignatureProviderAdapterError(str(exc)) from exc

    def void_request(self, request_id: str, reason: str) -> None:
        try:
            docusign_client.void_envelope(request_id, reason)
        except docusign_client.DocuSignError as exc:
            raise ESignatureProviderAdapterError(str(exc)) from exc

    def download_completed_document(self, request_id: str) -> tuple[bytes, str]:
        try:
            return docusign_client.download_envelope_combined(request_id)
        except docusign_client.DocuSignError as exc:
            raise ESignatureProviderAdapterError(str(exc)) from exc


_ADAPTERS: dict[str, ESignatureProviderAdapter] = {}


def normalize_esignature_provider_name(name: str | None) -> str:
    return str(name or "").strip().lower()


def register_esignature_provider(
    adapter: ESignatureProviderAdapter,
    *,
    replace: bool = False,
) -> None:
    name = normalize_esignature_provider_name(getattr(adapter, "name", ""))
    if not name or name == "none":
        raise ValueError("E-signature provider adapters require a unique provider name.")
    if name in _ADAPTERS and not replace:
        raise ValueError(f"E-signature provider '{name}' is already registered.")
    _ADAPTERS[name] = adapter


def unregister_esignature_provider(name: str) -> None:
    _ADAPTERS.pop(normalize_esignature_provider_name(name), None)


def get_esignature_provider_adapter(name: str | None) -> ESignatureProviderAdapter | None:
    return _ADAPTERS.get(normalize_esignature_provider_name(name))


def esignature_provider_names(*, include_none: bool = False) -> set[str]:
    names = set(_ADAPTERS)
    if include_none:
        names.add("none")
    return names


def available_esignature_provider_adapters() -> list[ESignatureProviderAdapter]:
    available: list[ESignatureProviderAdapter] = []
    for adapter in _ADAPTERS.values():
        try:
            if adapter.is_available():
                available.append(adapter)
        except Exception:
            continue
    return available


register_esignature_provider(DocuSignESignatureProviderAdapter())
