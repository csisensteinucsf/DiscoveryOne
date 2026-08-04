from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .integration_settings import get_integration_config, integration_enabled

logger = logging.getLogger(__name__)


class EmailIntakeGraphError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class EmailIntakeSettings:
    enabled: bool
    tenant_id: str
    client_id: str
    client_secret: str
    mailbox: str
    folder_id: str
    poll_interval_seconds: int
    max_messages_per_poll: int
    sender_policy: str
    allowed_senders: tuple[str, ...]
    allowed_sender_domains: tuple[str, ...]
    graph_base: str
    scope: str
    requestor_from_sender: bool
    process_existing_on_first_run: bool
    startup_delay_seconds: int
    timeout_seconds: float
    retry_count: int

    @property
    def ready(self) -> bool:
        return bool(
            self.enabled
            and self.tenant_id
            and self.client_id
            and self.client_secret
            and self.mailbox
            and self.folder_id
        )


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _list_value(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = str(value or "").replace(";", "\n").replace(",", "\n").splitlines()
    return tuple(sorted({str(item).strip().lower().lstrip("@") for item in values if str(item).strip()}))


def load_email_intake_settings() -> EmailIntakeSettings:
    config = get_integration_config("email_intake", reveal_secrets=True)
    return EmailIntakeSettings(
        enabled=integration_enabled("email_intake"),
        tenant_id=str(config.get("tenant_id") or "").strip(),
        client_id=str(config.get("client_id") or "").strip(),
        client_secret=str(config.get("client_secret") or "").strip(),
        mailbox=str(config.get("mailbox") or "").strip().lower(),
        folder_id=str(config.get("folder_id") or "inbox").strip() or "inbox",
        poll_interval_seconds=_bounded_int(config.get("poll_interval_seconds"), 60, 15, 86400),
        max_messages_per_poll=_bounded_int(config.get("max_messages_per_poll"), 50, 1, 500),
        sender_policy=str(config.get("sender_policy") or "any").strip().lower(),
        allowed_senders=_list_value(config.get("allowed_senders")),
        allowed_sender_domains=_list_value(config.get("allowed_sender_domains")),
        graph_base=str(config.get("graph_base") or "https://graph.microsoft.com/v1.0").strip().rstrip("/"),
        scope=str(config.get("scope") or "https://graph.microsoft.com/.default").strip(),
        requestor_from_sender=_truthy(config.get("requestor_from_sender"), True),
        process_existing_on_first_run=_truthy(config.get("process_existing_on_first_run"), False),
        startup_delay_seconds=_bounded_int(config.get("startup_delay_seconds"), 15, 0, 3600),
        timeout_seconds=_bounded_float(config.get("timeout_seconds"), 30, 5, 300),
        retry_count=_bounded_int(config.get("retry_count"), 3, 0, 10),
    )


_token_cache: dict[str, Any] = {"key": None, "token": None, "expires_at": 0.0}


def _token(settings: EmailIntakeSettings) -> str:
    cache_key = (settings.tenant_id, settings.client_id, settings.scope)
    now = time.time()
    if _token_cache.get("key") == cache_key and _token_cache.get("token") and float(_token_cache.get("expires_at") or 0) > now:
        return str(_token_cache["token"])
    url = f"https://login.microsoftonline.com/{quote(settings.tenant_id, safe='')}/oauth2/v2.0/token"
    try:
        response = httpx.post(
            url,
            data={
                "client_id": settings.client_id,
                "client_secret": settings.client_secret,
                "scope": settings.scope,
                "grant_type": "client_credentials",
            },
            timeout=settings.timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise EmailIntakeGraphError(f"Microsoft identity token request failed: {exc}") from exc
    if response.status_code != 200:
        raise EmailIntakeGraphError(
            f"Microsoft identity token request failed ({response.status_code}): {response.text[:300]}",
            status_code=response.status_code,
        )
    payload = response.json()
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise EmailIntakeGraphError("Microsoft identity response did not include an access token")
    expires_in = _bounded_int(payload.get("expires_in"), 3600, 60, 86400)
    _token_cache.update({"key": cache_key, "token": access_token, "expires_at": now + expires_in - 30})
    return access_token


def _request(settings: EmailIntakeSettings, method: str, url: str) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {_token(settings)}",
        "Accept": "application/json",
        "Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"',
    }
    last_response: httpx.Response | None = None
    for attempt in range(settings.retry_count + 1):
        try:
            response = httpx.request(method, url, headers=headers, timeout=settings.timeout_seconds)
        except httpx.HTTPError as exc:
            if attempt >= settings.retry_count:
                raise EmailIntakeGraphError(f"Microsoft Graph request failed: {exc}") from exc
            time.sleep(min(8.0, 0.5 * (2 ** attempt)))
            continue
        last_response = response
        if response.status_code not in {429, 500, 502, 503, 504} or attempt >= settings.retry_count:
            break
        try:
            delay = float(response.headers.get("Retry-After") or 0)
        except (TypeError, ValueError):
            delay = 0
        time.sleep(max(delay, min(8.0, 0.5 * (2 ** attempt))))
    if last_response is None:
        raise EmailIntakeGraphError("Microsoft Graph request did not return a response")
    if last_response.status_code >= 400:
        raise EmailIntakeGraphError(
            f"Microsoft Graph request failed ({last_response.status_code}): {last_response.text[:400]}",
            status_code=last_response.status_code,
        )
    return last_response


def test_connection(settings: EmailIntakeSettings) -> dict[str, Any]:
    if not settings.ready:
        raise EmailIntakeGraphError("Email Intake configuration is incomplete")
    mailbox = quote(settings.mailbox, safe="")
    folder = quote(settings.folder_id, safe="")
    url = f"{settings.graph_base}/users/{mailbox}/mailFolders/{folder}?$select=id,displayName,parentFolderId"
    payload = _request(settings, "GET", url).json()
    return {
        "mailbox": settings.mailbox,
        "folder_id": payload.get("id") or settings.folder_id,
        "folder_name": payload.get("displayName") or settings.folder_id,
    }


def delta_messages(
    settings: EmailIntakeSettings,
    cursor_url: str | None,
) -> tuple[list[dict[str, Any]], str | None, bool]:
    if not settings.ready:
        raise EmailIntakeGraphError("Email Intake configuration is incomplete")
    if cursor_url:
        url = cursor_url
    else:
        mailbox = quote(settings.mailbox, safe="")
        folder = quote(settings.folder_id, safe="")
        select = "id,internetMessageId,changeKey,receivedDateTime,from,toRecipients,ccRecipients,bccRecipients,subject,body,hasAttachments"
        url = (
            f"{settings.graph_base}/users/{mailbox}/mailFolders/{folder}/messages/delta"
            f"?$select={select}&$top={settings.max_messages_per_poll}"
        )
    messages: list[dict[str, Any]] = []
    next_cursor: str | None = url
    caught_up = False
    while next_cursor and len(messages) < settings.max_messages_per_poll:
        payload = _request(settings, "GET", next_cursor).json()
        for item in payload.get("value") or []:
            if isinstance(item, dict):
                messages.append(item)
        next_link = str(payload.get("@odata.nextLink") or "").strip() or None
        delta_link = str(payload.get("@odata.deltaLink") or "").strip() or None
        next_cursor = next_link or delta_link
        if delta_link:
            caught_up = True
        if delta_link or not next_link:
            break
    return messages[: settings.max_messages_per_poll], next_cursor, caught_up


def message_attachments(settings: EmailIntakeSettings, graph_message_id: str) -> list[dict[str, Any]]:
    mailbox = quote(settings.mailbox, safe="")
    message_id = quote(graph_message_id, safe="")
    url = f"{settings.graph_base}/users/{mailbox}/messages/{message_id}/attachments?$top=100"
    results: list[dict[str, Any]] = []
    while url:
        payload = _request(settings, "GET", url).json()
        for item in payload.get("value") or []:
            if not isinstance(item, dict):
                continue
            content = item.get("contentBytes")
            decoded: bytes | None = None
            if content and str(item.get("@odata.type") or "").lower().endswith("fileattachment"):
                try:
                    decoded = base64.b64decode(str(content), validate=True)
                except (ValueError, TypeError):
                    decoded = None
            results.append({
                "id": item.get("id"),
                "name": str(item.get("name") or "attachment"),
                "content_type": str(item.get("contentType") or "application/octet-stream"),
                "size": int(item.get("size") or (len(decoded) if decoded is not None else 0)),
                "content": decoded,
                "is_inline": bool(item.get("isInline")),
                "supported": decoded is not None,
            })
        url = str(payload.get("@odata.nextLink") or "").strip()
    return results