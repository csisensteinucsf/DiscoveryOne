from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from .app_branding import app_display_name
from . import models
from .auth import require_admin
from .integration_settings import config_value


router = APIRouter(prefix="/api/slack/oauth", tags=["slack_oauth"])


def _cfg(key: str, env_name: str, default: str = "") -> str:
    return config_value("slack", key, env_name, default).strip()


def _state_ttl_seconds() -> int:
    try:
        value = int(_cfg("oauth_state_ttl_seconds", "SLACK_OAUTH_STATE_TTL_SECONDS", "900") or "900")
    except (TypeError, ValueError):
        value = 900
    return max(60, min(3600, value))


def _state_secret() -> str:
    return _cfg("oauth_state_secret", "SLACK_OAUTH_STATE_SECRET", os.getenv("SECRET_KEY") or "")


def _oauth_config_error() -> str:
    return (
        "Slack OAuth is not configured. Configure the Slack OAuth client ID, client secret, "
        "redirect URI, and state secret in System > Integrations."
    )


def _ensure_oauth_configured() -> None:
    if not _cfg("client_id", "SLACK_CLIENT_ID") or not _cfg("client_secret", "SLACK_CLIENT_SECRET") or not _cfg("oauth_redirect_uri", "SLACK_OAUTH_REDIRECT_URI") or not _state_secret():
        raise HTTPException(status_code=503, detail=_oauth_config_error())
    if not _cfg("oauth_scope", "SLACK_OAUTH_SCOPE") and not _cfg("oauth_user_scope", "SLACK_OAUTH_USER_SCOPE"):
        raise HTTPException(status_code=503, detail="Slack OAuth scopes are missing. Configure scopes in System > Integrations.")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * ((4 - (len(value) % 4)) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _build_state_payload() -> Dict[str, Any]:
    return {
        "ts": int(time.time()),
        "nonce": secrets.token_urlsafe(16),
    }


def _sign_state(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_state_secret().encode("utf-8"), raw, hashlib.sha256).digest()
    return _b64url_encode(raw + b"." + sig)


def _unsign_state(token: str) -> Dict[str, Any]:
    try:
        decoded = _b64url_decode(token)
        raw, sig = decoded.rsplit(b".", 1)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc

    expected = hmac.new(_state_secret().encode("utf-8"), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state payload") from exc

    ts = int(payload.get("ts") or 0)
    age = int(time.time()) - ts
    if age < 0 or age > _state_ttl_seconds():
        raise HTTPException(status_code=400, detail="OAuth state expired")

    return payload


def _validate_proxy_shared_secret(request: Request) -> None:
    shared_secret = _cfg("shared_secret", "SLACK_SHARED_SECRET")
    if not shared_secret:
        return
    supplied = (request.headers.get("X-Proxy-Shared-Secret") or "").strip()
    if not supplied or not hmac.compare_digest(supplied, shared_secret):
        raise HTTPException(status_code=403, detail="Invalid proxy shared secret")


def _build_authorize_url(state: str) -> str:
    params = {
        "client_id": _cfg("client_id", "SLACK_CLIENT_ID"),
        "redirect_uri": _cfg("oauth_redirect_uri", "SLACK_OAUTH_REDIRECT_URI"),
        "state": state,
    }
    oauth_scope = _cfg("oauth_scope", "SLACK_OAUTH_SCOPE")
    oauth_user_scope = _cfg("oauth_user_scope", "SLACK_OAUTH_USER_SCOPE")
    if oauth_scope:
        params["scope"] = oauth_scope
    if oauth_user_scope:
        params["user_scope"] = oauth_user_scope
    return f"{_cfg('oauth_authorize_url', 'SLACK_OAUTH_AUTHORIZE_URL', 'https://slack.com/oauth/v2/authorize')}?{urlencode(params)}"


def _exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    form = {
        "client_id": _cfg("client_id", "SLACK_CLIENT_ID"),
        "client_secret": _cfg("client_secret", "SLACK_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": _cfg("oauth_redirect_uri", "SLACK_OAUTH_REDIRECT_URI"),
    }
    try:
        resp = httpx.post(_cfg("oauth_access_url", "SLACK_OAUTH_ACCESS_URL", "https://slack.com/api/oauth.v2.access"), data=form, timeout=30)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Unable to reach Slack OAuth endpoint: {exc}") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Slack OAuth endpoint returned HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Slack OAuth endpoint returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Slack OAuth endpoint returned an unexpected payload")

    if not data.get("ok"):
        err = (data.get("error") or "oauth_exchange_failed").strip()
        raise HTTPException(status_code=502, detail=f"Slack OAuth token exchange failed: {err}")

    return data


def _mask(value: Optional[str]) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 10:
        return "*" * len(text)
    return f"{text[:6]}...{text[-4:]}"


def _callback_page(title: str, body: str, *, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Slack OAuth</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 24px; color: #111827; }}
      .card {{ max-width: 760px; border: 1px solid #d1d5db; border-radius: 10px; padding: 16px; }}
      h1 {{ margin-top: 0; font-size: 20px; }}
      pre {{ background: #f9fafb; border: 1px solid #e5e7eb; padding: 12px; overflow: auto; }}
    </style>
  </head>
  <body>
    <div class=\"card\">
      <h1>{html.escape(title)}</h1>
      {body}
    </div>
  </body>
</html>""",
        status_code=status_code,
    )


@router.get("/authorize_url")
def slack_oauth_authorize_url(_: models.User = Depends(require_admin)):
    _ensure_oauth_configured()
    state = _sign_state(_build_state_payload())
    return {
        "authorize_url": _build_authorize_url(state),
        "state": state,
        "redirect_uri": _cfg("oauth_redirect_uri", "SLACK_OAUTH_REDIRECT_URI"),
        "ttl_seconds": _state_ttl_seconds(),
    }


@router.get("/callback")
def slack_oauth_callback(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    _validate_proxy_shared_secret(request)

    if error:
        body = f"<p>Slack returned an error: <strong>{html.escape(error)}</strong>.</p>"
        return _callback_page("Slack authorization not completed", body, status_code=400)

    _ensure_oauth_configured()

    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state")
    _unsign_state(state)

    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    data = _exchange_code_for_tokens(code)

    authed_user = data.get("authed_user") if isinstance(data.get("authed_user"), dict) else {}
    user_token = (authed_user.get("access_token") or "").strip()
    bot_token = (data.get("access_token") or "").strip()
    team = data.get("team") if isinstance(data.get("team"), dict) else {}
    team_name = (team.get("name") or "").strip()

    token_to_use = user_token or bot_token
    token_display = _mask(token_to_use)

    body = (
        "<p>Slack OAuth callback succeeded and the authorization code was exchanged.</p>"
        f"<p><strong>Team:</strong> {html.escape(team_name or 'unknown')}</p>"
        f"<p><strong>Use this token in {html.escape(app_display_name())}:</strong> <code>{html.escape(token_display)}</code></p>"
        "<p>Paste this token into the Slack Legal Holds token field in System &gt; Integrations.</p>"
    )

    if not token_to_use:
        body += "<p><strong>Warning:</strong> Slack did not return a token in this response.</p>"

    return _callback_page("Slack authorization complete", body, status_code=200)
