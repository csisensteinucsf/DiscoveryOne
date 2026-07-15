from __future__ import annotations

import time
from typing import Optional, Dict, Any

import httpx
import jwt

from .integration_settings import config_value, integration_active


DEFAULT_TEMPLATE_TAB_LABELS = {
    "case_name": "case_name",
    "record_type": "recordtype",
    "date_from": "datefrom",
    "date_to": "dateto",
}


class DocuSignError(Exception):
    """Raised when DocuSign operations fail."""


def docusign_enabled() -> bool:
    return integration_active("docusign", provider_key="esign_provider", provider="docusign")


def _load_private_key() -> str:
    inline = config_value("docusign", "private_key", "DOCUSIGN_PRIVATE_KEY")
    if inline:
        return inline.replace("\\n", "\n").strip()
    raise DocuSignError("DocuSign private key is required. Configure DocuSign in System > Integrations.")


def _config() -> Dict[str, str]:
    if not docusign_enabled():
        raise DocuSignError("DocuSign integration is disabled. Enable DocuSign in System > Integrations before sending consent envelopes.")
    base_url = config_value("docusign", "base_url", "DOCUSIGN_BASE_URL").rstrip("/")
    account_id = config_value("docusign", "account_id", "DOCUSIGN_ACCOUNT_ID")
    template_id = config_value("docusign", "template_id", "DOCUSIGN_TEMPLATE_ID")
    signer_role = config_value("docusign", "signer_role", "DOCUSIGN_SIGNER_ROLE", "signer")
    integration_key = config_value("docusign", "integration_key", "DOCUSIGN_INTEGRATION_KEY")
    user_id = config_value("docusign", "user_id", "DOCUSIGN_USER_ID")
    auth_server = config_value("docusign", "auth_server", "DOCUSIGN_AUTH_SERVER", "account-d.docusign.com")
    private_key_raw = _load_private_key()
    if not base_url or not account_id or not template_id or not integration_key or not user_id or not private_key_raw:
        missing = [name for name, val in {
            "base URL": base_url,
            "account ID": account_id,
            "template ID": template_id,
            "integration key": integration_key,
            "user ID": user_id,
            "private key": private_key_raw,
        }.items() if not val]
        raise DocuSignError(f"Missing DocuSign configuration: {', '.join(missing)}")
    return {
        "base_url": base_url,
        "account_id": account_id,
        "template_id": template_id,
        "signer_role": signer_role or "signer",
        "case_name_tab": config_value("docusign", "case_name_tab", "DOCUSIGN_CASE_NAME_TAB", DEFAULT_TEMPLATE_TAB_LABELS["case_name"]),
        "record_type_tab": config_value("docusign", "record_type_tab", "DOCUSIGN_RECORD_TYPE_TAB", DEFAULT_TEMPLATE_TAB_LABELS["record_type"]),
        "date_from_tab": config_value("docusign", "date_from_tab", "DOCUSIGN_DATE_FROM_TAB", DEFAULT_TEMPLATE_TAB_LABELS["date_from"]),
        "date_to_tab": config_value("docusign", "date_to_tab", "DOCUSIGN_DATE_TO_TAB", DEFAULT_TEMPLATE_TAB_LABELS["date_to"]),
        "integration_key": integration_key,
        "user_id": user_id,
        "private_key": private_key_raw,
        "auth_server": auth_server,
    }


_token_cache: Optional[tuple[str, float]] = None


def _build_jwt(cfg: Dict[str, str]) -> str:
    now = int(time.time())
    claims = {
        "iss": cfg["integration_key"],
        "sub": cfg["user_id"],
        "aud": cfg["auth_server"],
        "iat": now,
        "exp": now + 600,
        "scope": "signature impersonation",
    }
    try:
        return jwt.encode(claims, cfg["private_key"], algorithm="RS256")
    except Exception as exc:
        raise DocuSignError(f"Unable to sign DocuSign JWT: {exc}") from exc


def _get_token(cfg: Dict[str, str]) -> str:
    global _token_cache
    now = time.time()
    if _token_cache and _token_cache[1] > now + 60:
        return _token_cache[0]
    assertion = _build_jwt(cfg)
    url = f"https://{cfg['auth_server']}/oauth/token"
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data=data, headers=headers)
    except Exception as exc:
        raise DocuSignError(f"Unable to reach DocuSign auth server: {exc}") from exc
    if resp.status_code < 200 or resp.status_code >= 300:
        snippet = resp.text[:400]
        try:
            parsed = resp.json()
        except Exception:
            parsed = {}
        if isinstance(parsed, dict) and str(parsed.get("error")) == "consent_required":
            # Provide a clear next-step URL for granting consent interactively.
            consent_url = (
                f"https://{cfg['auth_server']}/oauth/auth"
                f"?response_type=code&scope=signature%20impersonation"
                f"&client_id={cfg['integration_key']}"
                f"&redirect_uri=https://www.docusign.com"
            )
            raise DocuSignError(
                f"DocuSign consent is required for this integration key/user. "
                f"Have the DocuSign user sign in and grant consent via: {consent_url}"
            )
        raise DocuSignError(f"DocuSign auth failed {resp.status_code}: {snippet}")
    payload = resp.json()
    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    if not token:
        raise DocuSignError("DocuSign auth response missing access_token")
    _token_cache = (token, now + expires_in - 60)
    return token


def _tab_label(cfg: Dict[str, str], semantic_name: str, fallback: str) -> str:
    value = str(cfg.get(f"{semantic_name}_tab") or "").strip()
    return value or fallback


def _mapped_text_tabs(cfg: Dict[str, str], text_tabs: Optional[list[dict]]) -> list[dict]:
    label_map = {
        "case_name": _tab_label(cfg, "case_name", DEFAULT_TEMPLATE_TAB_LABELS["case_name"]),
        "record_type": _tab_label(cfg, "record_type", DEFAULT_TEMPLATE_TAB_LABELS["record_type"]),
        "recordtype": _tab_label(cfg, "record_type", DEFAULT_TEMPLATE_TAB_LABELS["record_type"]),
        "date_from": _tab_label(cfg, "date_from", DEFAULT_TEMPLATE_TAB_LABELS["date_from"]),
        "datefrom": _tab_label(cfg, "date_from", DEFAULT_TEMPLATE_TAB_LABELS["date_from"]),
        "date_to": _tab_label(cfg, "date_to", DEFAULT_TEMPLATE_TAB_LABELS["date_to"]),
        "dateto": _tab_label(cfg, "date_to", DEFAULT_TEMPLATE_TAB_LABELS["date_to"]),
    }
    payload: list[dict] = []
    seen: set[str] = set()
    for tab in text_tabs or []:
        if not tab:
            continue
        raw_label = tab.get("tabLabel") or tab.get("tab_label")
        if raw_label is None:
            continue
        key = str(raw_label or "").strip()
        if not key:
            continue
        mapped_label = label_map.get(key.lower(), key)
        if not mapped_label or mapped_label in seen:
            continue
        seen.add(mapped_label)
        val = tab.get("value")
        payload.append({"tabLabel": mapped_label, "value": "" if val is None else str(val)})
    return payload


def send_consent_envelope(
    *,
    custodian_name: str,
    custodian_email: str,
    case_name: Optional[str] = None,
    subject: Optional[str] = None,
    message: Optional[str] = None,
    text_tabs: Optional[list[dict]] = None,
    additional_roles: Optional[list[dict]] = None,
) -> str:
    """
    Fire-and-forget DocuSign envelope using an existing template.
    Uses JWT auth with the configured integration key and user id.
    """
    cfg = _config()
    token = _get_token(cfg)
    text_tab_payload = _mapped_text_tabs(cfg, [
        {"tabLabel": "case_name", "value": case_name or ""},
        *(text_tabs or []),
    ])
    template_roles = [
        {
            "email": custodian_email,
            "name": custodian_name,
            "roleName": cfg["signer_role"],
            "tabs": {
                "textTabs": text_tab_payload,
            },
        }
    ]
    for role in additional_roles or []:
        email = (role or {}).get("email")
        name = (role or {}).get("name")
        role_name = (role or {}).get("roleName") or (role or {}).get("role")
        if not email or not role_name:
            continue
        template_roles.append({
            "email": email,
            "name": name or email,
            "roleName": role_name,
        })
    payload: Dict[str, Any] = {
        "templateId": cfg["template_id"],
        "status": "sent",
        "templateRoles": template_roles,
    }
    if subject:
        payload["emailSubject"] = subject
    if message:
        payload["emailBlurb"] = message
    url = f"{cfg['base_url']}/v2.1/accounts/{cfg['account_id']}/envelopes"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json=payload, headers=headers)
    except Exception as exc:
        raise DocuSignError(f"Unable to reach DocuSign: {exc}") from exc
    if resp.status_code < 200 or resp.status_code >= 300:
        raise DocuSignError(f"DocuSign API error {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    envelope_id = data.get("envelopeId") or data.get("envelope_id")
    if not envelope_id:
        raise DocuSignError("DocuSign response missing envelopeId")
    return envelope_id


def _bool_value(value: str | None, default: str = "0") -> bool:
    return (value or default).strip().lower() in {"1", "true", "yes", "on"}


def resend_envelope(envelope_id: str) -> str:
    """
    Trigger a resend notification for an existing envelope.

    Resend strategy (in order):
    1) Dedicated resend endpoint.
    2) Envelope-level update with resend flag.
    3) Optional recipients PUT fallback (disabled by default because DocuSign can log it as a correction).
    """
    if not envelope_id:
        raise DocuSignError("Envelope ID is required")
    cfg = _config()
    token = _get_token(cfg)
    base = cfg["base_url"]
    account = cfg["account_id"]
    resend_url = f"{base}/v2.1/accounts/{account}/envelopes/{envelope_id}/recipients/resend"
    envelope_url = f"{base}/v2.1/accounts/{account}/envelopes/{envelope_id}"
    recipients_url = f"{base}/v2.1/accounts/{account}/envelopes/{envelope_id}/recipients"
    allow_correction_fallback = _bool_value(
        config_value(
            "docusign",
            "resend_allow_recipient_correction_fallback",
            "DOCUSIGN_RESEND_ALLOW_RECIPIENT_CORRECTION_FALLBACK",
            "0",
        ),
        "0",
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    def _snippet(resp: Optional[httpx.Response]) -> str:
        if not resp:
            return ""
        try:
            return (resp.text or "")[:500]
        except Exception:
            return ""

    try:
        with httpx.Client(timeout=15.0) as client:
            # Preferred simple resend endpoint (resends to all recipients).
            resend_resp = client.post(resend_url, json={}, headers=headers)
            if 200 <= resend_resp.status_code < 300:
                return "recipients_resend"

            # Fallback without recipient mutation: envelope update + resend flag.
            env_resp = client.put(
                envelope_url,
                params={"resend_envelope": "true"},
                json={"status": "sent"},
                headers=headers,
            )
            if 200 <= env_resp.status_code < 300:
                return "envelope_update_resend"

            # Legacy fallback: recipient PUT can be interpreted by DocuSign as a correction event.
            if allow_correction_fallback:
                rec = client.get(recipients_url, headers=headers)
                if rec.status_code < 200 or rec.status_code >= 300:
                    raise DocuSignError(
                        "DocuSign resend failed; "
                        f"resend endpoint={resend_resp.status_code}, envelope update={env_resp.status_code}, "
                        f"recipients get={rec.status_code}. "
                        f"Details: {(_snippet(env_resp) or _snippet(resend_resp) or _snippet(rec))}"
                    )
                rec_data = rec.json() if rec.content else {}
                body = {
                    k: rec_data.get(k)
                    for k in ("signers", "carbonCopies", "certifiedDeliveries", "inPersonSigners")
                    if rec_data.get(k)
                }
                if not body:
                    raise DocuSignError("DocuSign resend failed: no recipients found for envelope")
                put_resp = client.put(
                    recipients_url,
                    params={"resend_envelope": "true"},
                    json=body,
                    headers=headers,
                )
                if 200 <= put_resp.status_code < 300:
                    return "recipients_put_resend"
                raise DocuSignError(f"DocuSign resend failed {put_resp.status_code}: {put_resp.text[:500]}")

            raise DocuSignError(
                "DocuSign resend failed without recipient correction fallback; "
                f"resend endpoint={resend_resp.status_code}, envelope update={env_resp.status_code}. "
                f"Details: {(_snippet(env_resp) or _snippet(resend_resp))}"
            )
    except DocuSignError:
        raise
    except Exception as exc:
        raise DocuSignError(f"Unable to reach DocuSign: {exc}") from exc


def void_envelope(envelope_id: str, reason: Optional[str] = None) -> None:
    """
    Void an envelope with an optional reason.
    """
    if not envelope_id:
        raise DocuSignError("Envelope ID is required")
    cfg = _config()
    token = _get_token(cfg)
    url = f"{cfg['base_url']}/v2.1/accounts/{cfg['account_id']}/envelopes/{envelope_id}"
    payload = {
        "status": "voided",
        "voidedReason": (reason or "Voided by DiscoveryOne")[:500],
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.put(url, json=payload, headers=headers)
    except Exception as exc:
        raise DocuSignError(f"Unable to reach DocuSign: {exc}") from exc
    if resp.status_code < 200 or resp.status_code >= 300:
        raise DocuSignError(f"DocuSign void failed {resp.status_code}: {resp.text[:500]}")


def sender_view_url(envelope_id: str, return_url: str) -> str:
    """
    Generate a sender (embedded) view URL so users can open the envelope without a DocuSign login prompt.
    """
    if not envelope_id:
        raise DocuSignError("Envelope ID is required")
    cfg = _config()
    token = _get_token(cfg)
    url = f"{cfg['base_url']}/v2.1/accounts/{cfg['account_id']}/envelopes/{envelope_id}/views/sender"
    payload = {"returnUrl": return_url or "https://www.docusign.com"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=headers)
    except Exception as exc:
        raise DocuSignError(f"Unable to reach DocuSign: {exc}") from exc
    if resp.status_code < 200 or resp.status_code >= 300:
        raise DocuSignError(f"DocuSign sender view failed {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    view_url = data.get("url")
    if not view_url:
        raise DocuSignError("DocuSign sender view response missing url")
    return view_url


def download_envelope_combined(envelope_id: str) -> tuple[bytes, str]:
    """
    Download the combined/completed envelope as a PDF using the integration's JWT auth.
    """
    if not envelope_id:
        raise DocuSignError("Envelope ID is required")
    cfg = _config()
    token = _get_token(cfg)
    url = f"{cfg['base_url']}/v2.1/accounts/{cfg['account_id']}/envelopes/{envelope_id}/documents/combined"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/pdf",
    }
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=headers)
    except Exception as exc:
        raise DocuSignError(f"Unable to reach DocuSign: {exc}") from exc
    if resp.status_code < 200 or resp.status_code >= 300:
        raise DocuSignError(f"DocuSign download failed {resp.status_code}: {resp.text[:500]}")
    filename = "consent.pdf"
    disposition = resp.headers.get("Content-Disposition") or ""
    for part in disposition.split(";"):
        part = part.strip()
        if part.lower().startswith("filename="):
            filename = part.split("=", 1)[1].strip().strip('"')
            break
    return resp.content, filename or "consent.pdf"

