from datetime import datetime, timedelta, timezone
from typing import Optional, List
from uuid import uuid4
import base64
import hashlib
import io
import os
import secrets
import asyncio
import logging
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import pyotp
import qrcode
from email_validator import EmailNotValidError, validate_email
import jwt
from jwt import InvalidTokenError as JWTError
from fastapi import Depends, HTTPException, Response, APIRouter, Request, Body
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from .database import get_db
from .security import hash_password as _hash_password, verify_password as _verify_password
from . import models
from .audit import log_event

from .permissions import get_role, is_valid_tech_group
from .requestor_email_policy import require_allowed_requestor_email
from .session_tokens import (
    create_session_token,
    revoke_session_by_jti,
    revoke_all_sessions_for_user,
    revoke_session_by_id,
    touch_session,
    create_refresh_token,
    revoke_refresh_by_jti,
    revoke_all_refresh_for_user,
    find_valid_refresh,
)
from .emailer import send_email
from .notifications import _app_base_url, notify_user_password_change, notify_user_mfa_change, _send_teams_notification, render_email_template
from .middleware import _SharedRateLimiter, _remote_ip as _middleware_remote_ip
from .institution import load_institution_settings, load_integration_settings, sso_display_name
from .integration_settings import config_value, settings_are_authoritative
from .auth_rate_limits import TokenAttemptLimiter as _TokenAttemptLimiter, enforce_token_attempt_limit as _enforce_token_attempt_limit

ALLOWED_JWT_ALGORITHMS = {"HS256", "RS256"}
_logger = logging.getLogger(__name__)

def _debug_suppressed(context: str, exc: Exception) -> None:
    _logger.debug("%s: %s", context, exc, exc_info=True)


def _is_placeholder_secret(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return True
    placeholders = {
        "please-change-this",
        "change-me",
        "changeme",
        "password",
        "secret",
        "secret_key",
        "admin",
        "please-set-a-strong-password",
    }
    if normalized in placeholders:
        return True
    if normalized.startswith("please-") and "change" in normalized:
        return True
    if normalized.startswith("please-") and "set" in normalized:
        return True
    return False

def _load_pem_env(name: str) -> str:
    val = (os.getenv(name) or "").strip()
    if not val:
        return ""
    return val.replace("\\n", "\n").strip()

_ALLOW_INSECURE_DEV = (os.getenv("ALLOW_INSECURE_DEV") or "").strip().lower() in {"1", "true", "yes", "on"}
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set")
if not _ALLOW_INSECURE_DEV:
    if _is_placeholder_secret(SECRET_KEY) or len(SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY is insecure (placeholder or too short). Set a strong value (>= 32 chars) "
            "or set ALLOW_INSECURE_DEV=1 for local development."
        )

# Optional RSA keys for RS256 signing/verification
JWT_PRIVATE_KEY = _load_pem_env("JWT_PRIVATE_KEY")
JWT_PUBLIC_KEY = _load_pem_env("JWT_PUBLIC_KEY")
_JWT_ALLOW_HS_FALLBACK_RAW = os.getenv("JWT_ALLOW_HS_FALLBACK")

_DEFAULT_ALG = os.getenv("ALGORITHM", "HS256").strip().upper()
if _DEFAULT_ALG not in ALLOWED_JWT_ALGORITHMS:
    raise RuntimeError(f"Unsupported JWT algorithm '{_DEFAULT_ALG}'. Allowed: {', '.join(sorted(ALLOWED_JWT_ALGORITHMS))}")

USE_RS256 = bool(JWT_PRIVATE_KEY and JWT_PUBLIC_KEY)
SIGNING_ALGORITHM = "RS256" if USE_RS256 else _DEFAULT_ALG
SIGNING_KEY = JWT_PRIVATE_KEY if USE_RS256 else SECRET_KEY
ALGORITHM = SIGNING_ALGORITHM
JWT_ALLOW_HS_FALLBACK = (
    (_JWT_ALLOW_HS_FALLBACK_RAW or ("0" if USE_RS256 else "1")).strip().lower() in {"1", "true", "yes", "on"}
)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))  # default 2 hours
SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "access_token")
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "strict")
MFA_CHALLENGE_EXPIRE_MINUTES = int(os.getenv("MFA_CHALLENGE_EXPIRE_MINUTES", "5"))
TRUSTED_DEVICE_COOKIE = os.getenv("TRUSTED_DEVICE_COOKIE", "trusted_device")
TRUSTED_DEVICE_COOKIE_SAMESITE = os.getenv("TRUSTED_DEVICE_COOKIE_SAMESITE", "none")
TRUSTED_DEVICE_TTL_DAYS = int(os.getenv("TRUSTED_DEVICE_TTL_DAYS", "30"))
TRUSTED_DEVICE_MAX_PER_USER = int(os.getenv("TRUSTED_DEVICE_MAX_PER_USER", "5"))
TRUSTED_DEVICE_COOKIE_MAX_AGE = TRUSTED_DEVICE_TTL_DAYS * 24 * 60 * 60
SESSION_IDLE_TIMEOUT_MINUTES = int(os.getenv("SESSION_IDLE_TIMEOUT_MINUTES", "480"))
SESSION_ACTIVITY_UPDATE_SECONDS = int(os.getenv("SESSION_ACTIVITY_UPDATE_SECONDS", "60"))
SEED_ADMIN_USERNAME = (os.getenv("ADMIN_SEED_USERNAME") or os.getenv("ADMIN_USERNAME") or "").strip().lower()
PASSWORD_RESET_TOKEN_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_MINUTES", "30"))
PASSWORD_RESET_MAX_ACTIVE = int(os.getenv("PASSWORD_RESET_MAX_ACTIVE", "5"))
PASSWORD_RESET_REQUEST_LIMIT = int(os.getenv("PASSWORD_RESET_REQUEST_LIMIT", "10"))
PASSWORD_RESET_REQUEST_WINDOW = int(os.getenv("PASSWORD_RESET_REQUEST_WINDOW", "300"))
PASSWORD_HELP_REQUEST_LIMIT = int(os.getenv("PASSWORD_HELP_REQUEST_LIMIT", "5"))
PASSWORD_HELP_REQUEST_WINDOW = int(os.getenv("PASSWORD_HELP_REQUEST_WINDOW", "300"))
REGISTRATION_TOKEN_DAYS = int(os.getenv("REGISTRATION_TOKEN_DAYS", "3"))
REGISTRATION_DEFAULT_ROLE = os.getenv("REGISTRATION_DEFAULT_ROLE", "requestor")
MFA_MAX_ATTEMPTS = int(os.getenv("MFA_MAX_ATTEMPTS", "5"))
MFA_ATTEMPT_WINDOW = int(os.getenv("MFA_ATTEMPT_WINDOW", "300"))
_mfa_rate_limiter = _SharedRateLimiter("mfa")
_register_request_limiter = _TokenAttemptLimiter()
REGISTER_REQUEST_LIMIT = int(os.getenv("REGISTER_REQUEST_LIMIT", "20"))
REGISTER_REQUEST_WINDOW = int(os.getenv("REGISTER_REQUEST_WINDOW", "3600"))
ALLOW_INSECURE_DEV = _ALLOW_INSECURE_DEV
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))
REFRESH_COOKIE_NAME = os.getenv("REFRESH_COOKIE_NAME", "refresh_token")
REFRESH_COOKIE_SAMESITE = os.getenv("REFRESH_COOKIE_SAMESITE", "lax")
OIDC_STATE_COOKIE = os.getenv("OIDC_STATE_COOKIE", "oidc_oauth_state")
OIDC_ID_TOKEN_COOKIE = os.getenv("OIDC_ID_TOKEN_COOKIE", "oidc_id_token")

OIDC_STATE_TTL_SECONDS = max(60, int(os.getenv("OIDC_STATE_TTL_SECONDS", "600") or "600"))
OIDC_REGISTRATION_TTL_SECONDS = max(300, int(os.getenv("OIDC_REGISTRATION_TTL_SECONDS", "3600") or "3600"))
OIDC_HTTP_TIMEOUT_SECONDS = max(2.0, float(os.getenv("OIDC_HTTP_TIMEOUT_SECONDS", "10") or "10"))
OIDC_REDIRECT_PATH = "/api/auth/oidc/callback"
OIDC_LOGOUT_REDIRECT_PATH = "/api/auth/oidc/logout/callback"

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_seed_admin(user: Optional[models.User]) -> bool:
    if not user or not SEED_ADMIN_USERNAME:
        return False
    return (user.username or "").strip().lower() == SEED_ADMIN_USERNAME


def _oidc_enabled() -> bool:
    provider = str(load_integration_settings().get("sso_provider") or "local").strip().lower()
    if provider == "oidc":
        return True
    if not settings_are_authoritative():
        raw = os.getenv("OIDC_ENABLED")
        if raw is not None:
            return raw.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _sso_display_name() -> str:
    return sso_display_name()


def _public_institution_config() -> dict:
    settings = load_institution_settings()
    return {
        "org_name": settings.get("org_name") or "",
        "org_short_name": settings.get("org_short_name") or "",
        "allowed_requestor_email_domains": settings.get("allowed_requestor_email_domains") or [],
        "employee_id_label": "Employee ID",
        "sso_display_name": settings.get("sso_display_name") or "Single sign-on",
        "support_email": settings.get("support_email") or "",
    }


def _oidc_issuer() -> str:
    return config_value("oidc", "issuer", "OIDC_ISSUER").rstrip("/")


def _oidc_client_id() -> str:
    return config_value("oidc", "client_id", "OIDC_CLIENT_ID")


def _oidc_client_secret() -> str:
    return config_value("oidc", "client_secret", "OIDC_CLIENT_SECRET")


def _oidc_scopes() -> str:
    return config_value("oidc", "scopes", "OIDC_SCOPES", "openid profile email") or "openid profile email"


def _sso_login_active_for_user(user: Optional[models.User]) -> bool:
    return bool(user and _oidc_enabled() and not _is_seed_admin(user) and not getattr(user, "local_auth_only", False))


def _user_is_active(user: Optional[models.User]) -> bool:
    return bool(user and getattr(user, "is_active", True))


def _local_password_login_allowed(user: Optional[models.User]) -> bool:
    if not user:
        return not _oidc_enabled()
    return (not _oidc_enabled()) or _is_seed_admin(user) or bool(getattr(user, "local_auth_only", False))


def _oidc_is_configured() -> bool:
    return bool(_oidc_issuer() and _oidc_client_id() and _oidc_client_secret())


def _safe_next_path(value: Optional[str]) -> str:
    raw = (value or "").strip() or "/"
    if not raw.startswith("/"):
        return "/"
    if raw.startswith("//") or raw.startswith("/api/"):
        return "/"
    return raw


def _oidc_redirect_uri(request: Optional[Request]) -> str:
    explicit = config_value("oidc", "redirect_uri", "OIDC_REDIRECT_URI")
    if explicit:
        return explicit
    return f"{_app_base_url(request)}{OIDC_REDIRECT_PATH}"


def _oidc_logout_redirect_uri(request: Optional[Request]) -> str:
    explicit = config_value("oidc", "logout_redirect_uri", "OIDC_LOGOUT_REDIRECT_URI")
    if explicit:
        return explicit
    return f"{_app_base_url(request)}{OIDC_LOGOUT_REDIRECT_PATH}"


@lru_cache(maxsize=4)
def _oidc_openid_configuration(issuer: str) -> dict:
    normalized = (issuer or '').strip().rstrip('/')
    if not normalized:
        raise HTTPException(status_code=503, detail=f'{_sso_display_name()} is not configured')
    if '/.well-known' in normalized:
        raise HTTPException(status_code=503, detail=f'{_sso_display_name()} issuer configuration is invalid')
    well_known = f"{normalized}/.well-known/openid-configuration"
    try:
        with httpx.Client(timeout=OIDC_HTTP_TIMEOUT_SECONDS) as client:
            response = client.get(well_known)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f'Unable to reach the {_sso_display_name()} discovery endpoint') from exc


def _create_oidc_state_token(next_path: Optional[str]) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(seconds=OIDC_STATE_TTL_SECONDS)
    payload = {
        "purpose": "oidc_state",
        "exp": expire,
        "nonce": secrets.token_urlsafe(24),
        "next": _safe_next_path(next_path),
    }
    return jwt.encode(payload, SIGNING_KEY, algorithm=SIGNING_ALGORITHM)


def _sso_error_response(request: Optional[Request], message: str):
    target = f"{_app_base_url(request)}/login?{urlencode({'error': message})}"
    response = RedirectResponse(url=target, status_code=303)
    response.delete_cookie(OIDC_STATE_COOKIE, path="/")
    return response


def _create_sso_registration_token(claims: dict) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(seconds=OIDC_REGISTRATION_TTL_SECONDS)
    payload = {
        'purpose': 'sso_registration',
        'exp': expire,
        'sub': (claims.get('sub') or '').strip(),
        'email': (claims.get('email') or claims.get('preferred_username') or '').strip().lower(),
        'name': (claims.get('name') or claims.get('preferred_username') or '').strip(),
    }
    return jwt.encode(payload, SIGNING_KEY, algorithm=SIGNING_ALGORITHM)


def _sso_unregistered_response(request: Optional[Request], claims: dict):
    registration_token = _create_sso_registration_token(claims)
    params = {
        "error": f"You aren't registered for DiscoveryOne yet. Submit a {_sso_display_name()} account request for admin approval.",
        "sso_unregistered": "1",
        "register": "1",
        'sso_registration_token': registration_token,
    }
    display_name = (claims.get("name") or claims.get("preferred_username") or "").strip()
    email = (claims.get("email") or claims.get("preferred_username") or "").strip()
    if display_name:
        params["name"] = display_name
    if email:
        params["email"] = email
    target = f"{_app_base_url(request)}/login?{urlencode(params)}"
    response = RedirectResponse(url=target, status_code=303)
    response.delete_cookie(OIDC_STATE_COOKIE, path="/")
    return response


def _sso_user_from_claims(claims: dict, db: Session) -> Optional[models.User]:
    subject = (claims.get('sub') or '').strip()
    if subject:
        user = db.query(models.User).filter(models.User.sso_subject == subject).first()
        if user:
            return user
    candidates = []
    for key in ("email", "preferred_username", "upn"):
        value = (claims.get(key) or "").strip().lower()
        if value and value not in candidates:
            candidates.append(value)
    for identifier in candidates:
        user = _find_user_by_identifier(identifier, db)
        if user:
            return user
    return None


def _validate_oidc_id_token(id_token: str, metadata: dict, *, nonce: str) -> dict:
    try:
        jwks_client = jwt.PyJWKClient(metadata["jwks_uri"])
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=metadata.get("id_token_signing_alg_values_supported") or ["RS256"],
            audience=_oidc_client_id(),
            issuer=metadata.get("issuer") or _oidc_issuer(),
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Unable to validate {_sso_display_name()} identity token") from exc
    if (claims.get("nonce") or "") != (nonce or ""):
        raise HTTPException(status_code=401, detail=f"Invalid {_sso_display_name()} login state")
    return claims


def _exchange_oidc_code(code: str, metadata: dict, request: Optional[Request]) -> dict:
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _oidc_redirect_uri(request),
    }
    try:
        with httpx.Client(timeout=OIDC_HTTP_TIMEOUT_SECONDS) as client:
            response = client.post(
                metadata["token_endpoint"],
                data=payload,
                auth=(_oidc_client_id(), _oidc_client_secret()),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to complete {_sso_display_name()} sign-in") from exc


def _build_oidc_authorize_url(state_token: str, request: Optional[Request]) -> str:
    if not _oidc_is_configured():
        raise HTTPException(status_code=503, detail=f"{_sso_display_name()} is not configured")
    metadata = _oidc_openid_configuration(_oidc_issuer())
    state_payload = _decode_token(state_token, purpose="oidc_state")
    params = {
        "client_id": _oidc_client_id(),
        "response_type": "code",
        "scope": _oidc_scopes(),
        "redirect_uri": _oidc_redirect_uri(request),
        "state": state_token,
        "nonce": state_payload.get("nonce"),
    }
    return f"{metadata['authorization_endpoint']}?{urlencode(params)}"



def _serialize_user(user: models.User) -> dict:
    if not user:
        return {}
    role = get_role(user)
    return {
        "username": user.username,
        "first_name": getattr(user, "first_name", None),
        "last_name": getattr(user, "last_name", None),
        "is_admin": user.is_admin,
        "is_active": bool(getattr(user, "is_active", True)),
        "role": role,
        "email": getattr(user, "email", None),
        "id": user.id,
        "employee_id": getattr(user, "employee_id", None),
        "local_auth_only": bool(getattr(user, "local_auth_only", False)),
        "auth_provider": "sso" if _sso_login_active_for_user(user) else "local",
        "local_password_login_allowed": _local_password_login_allowed(user),
        "requestor_group": getattr(user, "requestor_group", None),
        "user_theme": getattr(user, "user_theme", None) or "light",
        "case_sort_mode": getattr(user, "case_sort_mode", None) or "ediscovery",
        "ntp_default_template_id": getattr(user, "ntp_default_template_id", None),
    }


def _serialize_trusted_device(device: models.TrustedDevice) -> dict:
    if not device:
        return {}
    return {
        "id": device.id,
        "label": device.label or device.user_agent or "Browser",
        "user_agent": device.user_agent,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "last_used_at": device.last_used_at.isoformat() if device.last_used_at else None,
        "expires_at": device.expires_at.isoformat() if device.expires_at else None,
    }


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _decode_token(token: str, *, purpose: Optional[str] = None) -> dict:
    """
    Decode a JWT, preferring RS256 when RSA keys are configured.
    When JWT_ALLOW_HS_FALLBACK is true, HS256 is tried if RS256 validation fails.
    """
    errors = []
    if USE_RS256:
        try:
            data = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])
            if purpose and data.get("purpose") != purpose:
                raise JWTError("purpose mismatch")
            return data
        except JWTError as exc:
            errors.append(exc)
            if not JWT_ALLOW_HS_FALLBACK:
                raise
    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        if purpose and data.get("purpose") != purpose:
            raise JWTError("purpose mismatch")
        return data
    except JWTError as exc:
        errors.append(exc)
        raise errors[-1]


def _totp_enabled(user: Optional[models.User]) -> bool:
    if _is_seed_admin(user):
        return False
    if get_role(user) == "tester":
        return False
    return bool(user and user.mfa_enabled and user.totp_secret)


def _browser_label(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    ua = (request.headers.get("user-agent") or "").strip()
    if not ua:
        return None
    return ua[:120]


def _trusted_cookie_value(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    return request.cookies.get(TRUSTED_DEVICE_COOKIE)


def _qr_data_url(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return None


def _require_mfa_allowed(user: models.User):
    if _is_seed_admin(user):
        raise HTTPException(status_code=403, detail="MFA is not available for this account")
    if _sso_login_active_for_user(user):
        raise HTTPException(status_code=403, detail=f"MFA is managed by {_sso_display_name()} for this account")


def _validate_email_address(value: str) -> str:
    try:
        return validate_email(value, allow_smtputf8=False).email
    except EmailNotValidError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _ensure_sys_admin(user: models.User):
    if get_role(user) != "sys_admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")


def _validate_new_password(password: str) -> str:
    pw = (password or "").strip()
    if len(pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    return pw


def _find_user_by_identifier(identifier: str, db: Session) -> Optional[models.User]:
    ident = (identifier or "").strip().lower()
    if not ident:
        return None
    return (
        db.query(models.User)
        .filter(
            or_(
                func.lower(models.User.username) == ident,
                func.lower(models.User.email) == ident,
            )
        )
        .first()
    )


def _cleanup_reset_tokens(db: Session) -> None:
    try:
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.expires_at <= _now()
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


def _create_reset_token(db: Session, user: models.User) -> str:
    _cleanup_reset_tokens(db)
    if PASSWORD_RESET_MAX_ACTIVE > 0:
        active = (
            db.query(models.PasswordResetToken.id)
            .filter(
                models.PasswordResetToken.user_id == user.id,
                models.PasswordResetToken.used_at.is_(None),
                models.PasswordResetToken.expires_at > _now(),
            )
            .order_by(models.PasswordResetToken.created_at.desc())
            .all()
        )
        if len(active) >= PASSWORD_RESET_MAX_ACTIVE:
            to_remove = [row.id for row in active[PASSWORD_RESET_MAX_ACTIVE - 1 :]]
            if to_remove:
                try:
                    db.query(models.PasswordResetToken).filter(
                        models.PasswordResetToken.id.in_(to_remove)
                    ).delete(synchronize_session=False)
                    db.commit()
                except Exception:
                    db.rollback()

    raw = secrets.token_urlsafe(48)
    hashed = _hash_token(raw)
    row = models.PasswordResetToken(
        user_id=user.id,
        token_hash=hashed,
        expires_at=_now() + timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES),
    )
    db.add(row)
    db.commit()
    return raw


def _invalidate_reset_tokens(db: Session, user_id: int) -> None:
    try:
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user_id,
            models.PasswordResetToken.used_at.is_(None),
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


def _send_password_reset_email(
    *,
    user: models.User,
    token: str,
    request: Optional[Request],
    db: Session,
) -> None:
    raise HTTPException(
        status_code=404,
        detail="Self-service password reset is disabled. Ask a system administrator to reset local account passwords.",
    )
    try:
        log_event(
            db,
            action="password_reset_link_request",
            target_type="user",
            target_id=user.id,
            details={"username": user.username},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("password reset audit log skipped", exc)


def _reset_user_password(db: Session, user: models.User, new_password: str, *, actor_id: Optional[int] = None, request: Optional[Request] = None) -> None:
    password = _validate_new_password(new_password)
    user.password_hash = hash_password(password)
    db.add(user)
    db.commit()
    revoke_all_sessions_for_user(db, user.id)
    try:
        log_event(
            db,
            action="user_password_change",
            target_type="user",
            target_id=user.id,
            user_id=actor_id,
            details={"username": user.username},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("password change audit log skipped", exc)
    try:
        notify_user_password_change(user)
    except Exception as exc:
        _debug_suppressed("password change notification skipped", exc)


def _admin_recipient_emails(db: Session) -> List[str]:
    emails: List[str] = []
    rows = (
        db.query(models.User.email)
        .filter(
            or_(
                models.User.role.in_(("sys_admin",)),
                models.User.is_admin.is_(True),
            )
        )
        .all()
    )
    seen = set()
    for (email,) in rows:
        addr = (email or "").strip()
        key = addr.lower()
        if addr and key not in seen:
            emails.append(addr)
            seen.add(key)
    return emails


def _notify_admin_help(db: Session, identifier: str, note: Optional[str], request: Optional[Request]) -> None:
    recipients = _admin_recipient_emails(db)
    client_ip = _client_ip(request) or "unknown"
    context = {
        "identifier": identifier or "unknown",
        "ip": client_ip,
        "note": (note or "").strip() or "-",
    }
    subject, body = render_email_template(
        "admin_help",
        default_subject="[{app_name}] Login assistance requested",
        default_body="A user requested assistance signing in to {app_name}.\n\nIdentifier: {identifier}\nIP address: {ip}\nNote: {note}",
        context=context,
    )
    if recipients and subject and body:
        try:
            send_email(
                recipients=recipients,
                subject=subject,
                body=body,
            )
        except Exception as exc:
            _debug_suppressed("admin help email skipped", exc)
    try:
        log_event(
            db,
            action="password_help_request",
            details={"identifier": identifier},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("admin help audit log skipped", exc)
    try:
        _send_teams_notification(
            "admin_help",
            {
                "identifier": identifier or "unknown",
                "ip": client_ip,
                "note": (note or "").strip() or "-",
            },
        )
    except Exception as exc:
        print(f"[notify] teams admin help failed: {exc}")


def _notify_registration_request_admins(db: Session, row: models.AccountRegistrationRequest) -> None:
    recipients = _admin_recipient_emails(db)
    subject, body = render_email_template(
        "registration_request_admins",
        default_subject="[{app_name}] New account registration request",
        default_body="A new account registration request was submitted.\n\nName: {name}\nEmail: {email}\n\nReview this request in {app_name} > System > Account Requests.",
        context={"name": row.name or "Unknown", "email": row.email or "unknown"},
    )
    if recipients and subject and body:
        try:
            send_email(
                recipients=recipients,
                subject=subject,
                body=body,
            )
        except Exception as exc:
            _debug_suppressed("registration request email skipped", exc)
    try:
        _send_teams_notification(
            "registration_request",
            {
                "name": row.name or "Unknown",
                "email": row.email or "unknown",
            },
        )
    except Exception as exc:
        print(f"[notify] teams registration request failed: {exc}")


def _notify_registration_invite(row: models.AccountRegistrationRequest, token: str, request: Optional[Request] = None) -> None:
    email = (row.email or "").strip()
    if not email:
        return
    link = f"{_app_base_url(request)}/register?token={token}"
    action_text = (
        f"activate your account and sign in with {_sso_display_name()}"
        if _oidc_enabled()
        else "set a password and enroll your authenticator app"
    )
    subject, body = render_email_template(
        "registration_invite",
        default_subject="[{app_name}] Complete your account registration",
        default_body="Hello {name},\n\nYour {app_name} account request has been approved. Use the link below to {action_text}. This link expires in {expires_hours} hours.\n\n{link}\n\nIf you did not expect this email, ignore it.",
        context={
            "name": row.name or "there",
            "action_text": action_text,
            "expires_hours": REGISTRATION_TOKEN_DAYS * 24,
            "link": link,
            "sso_display_name": _sso_display_name(),
        },
    )
    if not subject or not body:
        return
    try:
        send_email(
            recipients=[email],
            subject=subject,
            body=body,
        )
    except Exception as exc:
        _debug_suppressed("registration invite email skipped", exc)


def _notify_registration_ready(row: models.AccountRegistrationRequest, request: Optional[Request] = None) -> None:
    email = (row.email or "").strip()
    if not email:
        return
    subject, body = render_email_template(
        "registration_ready",
        default_subject="[{app_name}] Your account is ready",
        default_body="Hello {name},\n\nYour {app_name} account request has been approved and your account is ready. Sign in using your {sso_display_name} credentials.\n\nSign in: {login_link}\n\nIf you did not expect this email, ignore it.",
        context={
            "name": row.name or "there",
            "sso_display_name": _sso_display_name(),
            "login_link": f"{_app_base_url(request)}/login",
        },
    )
    if not subject or not body:
        return
    try:
        send_email(
            recipients=[email],
            subject=subject,
            body=body,
        )
    except Exception as exc:
        _debug_suppressed("registration ready email skipped", exc)


def _notify_registration_decline(row: models.AccountRegistrationRequest) -> None:
    email = (row.email or "").strip()
    if not email:
        return
    reason = row.declined_reason or "No additional details were provided."
    subject, body = render_email_template(
        "registration_decline",
        default_subject="[{app_name}] Account request update",
        default_body="Hello {name},\n\nYour {app_name} account request was declined.\n\nReason: {reason}\nPlease contact the eDiscovery administrators if you have questions.",
        context={"name": row.name or "there", "reason": reason},
    )
    if not subject or not body:
        return
    try:
        send_email(
            recipients=[email],
            subject=subject,
            body=body,
        )
    except Exception as exc:
        _debug_suppressed("registration decline email skipped", exc)


def _notify_registration_existing_account(
    *,
    recipient: str,
    username: Optional[str] = None,
    request: Optional[Request] = None,
) -> None:
    addr = (recipient or "").strip()
    if not addr:
        return
    if _oidc_enabled():
        access_guidance = f"Please sign in using your {_sso_display_name()} credentials at:\n{_app_base_url(request)}/login"
    else:
        access_guidance = "If you are having trouble accessing your account, contact a system administrator."
    subject, body = render_email_template(
        "registration_existing_account",
        default_subject="[{app_name}] Account already exists",
        default_body="You tried to register a {app_name} account, but an account already exists with this email address.\n\nUsername: {username}\n\n{access_guidance}\n\nIf you did not attempt to register, you can ignore this email.",
        context={
            "username": username or "",
            "access_guidance": access_guidance,
            "sso_display_name": _sso_display_name(),
        },
    )
    if not subject or not body:
        return
    try:
        send_email(
            recipients=[addr],
            subject=subject,
            body=body,
        )
    except Exception as exc:
        _debug_suppressed("existing account notice skipped", exc)
        return

def _generate_username(db: Session, email: str) -> str:
    base = (email.split("@")[0] or "user").lower()
    base = "".join(ch for ch in base if ch.isalnum()) or "user"
    candidate = base
    counter = 1
    while (
        db.query(models.User)
        .filter(func.lower(models.User.username) == candidate.lower())
        .first()
    ):
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def _get_registration_request(db: Session, request_id: int) -> models.AccountRegistrationRequest:
    row = db.get(models.AccountRegistrationRequest, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Registration request not found")
    return row


def _registration_by_token(db: Session, token: str) -> Optional[models.AccountRegistrationRequest]:
    if not token:
        return None
    hashed = _hash_token(token)
    return (
        db.query(models.AccountRegistrationRequest)
        .filter(models.AccountRegistrationRequest.invite_token_hash == hashed)
        .first()
    )


def _trim_trusted_devices(db: Session, user_id: int) -> None:
    if TRUSTED_DEVICE_MAX_PER_USER <= 0:
        return
    rows = (
        db.query(models.TrustedDevice.id)
        .filter(models.TrustedDevice.user_id == user_id)
        .order_by(models.TrustedDevice.created_at.desc())
        .all()
    )
    if len(rows) <= TRUSTED_DEVICE_MAX_PER_USER:
        return
    to_remove = [row.id for row in rows[TRUSTED_DEVICE_MAX_PER_USER:]]
    try:
        (
            db.query(models.TrustedDevice)
            .filter(models.TrustedDevice.id.in_(to_remove))
            .delete(synchronize_session=False)
        )
        db.commit()
    except Exception:
        db.rollback()


def _is_request_secure(request: Optional[Request]) -> bool:
    if not request:
        return False
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    if proto:
        return proto == "https"
    scheme = getattr(request.url, "scheme", "")
    try:
        return scheme.lower() == "https"
    except AttributeError:
        return False


def _remember_browser(user: models.User, response: Optional[Response], db: Session, request: Optional[Request]):
    if not response or not user:
        return
    raw = secrets.token_urlsafe(48)
    hashed = _hash_token(raw)
    label = _browser_label(request) or "Browser"
    expires_at = _now() + timedelta(days=TRUSTED_DEVICE_TTL_DAYS)
    device = models.TrustedDevice(
        user_id=user.id,
        token_hash=hashed,
        user_agent=_browser_label(request),
        label=label[:120],
        expires_at=expires_at,
    )
    try:
        db.add(device)
        db.commit()
        _trim_trusted_devices(db, user.id)
    except Exception:
        db.rollback()
        return
    secure_cookie = ALLOW_INSECURE_DEV or _is_request_secure(request)
    samesite_setting = TRUSTED_DEVICE_COOKIE_SAMESITE
    if not secure_cookie and samesite_setting.lower() == "none":
        samesite_setting = "lax"
    response.set_cookie(
        key=TRUSTED_DEVICE_COOKIE,
        value=raw,
        httponly=True,
        secure=secure_cookie,
        samesite=samesite_setting,
        path="/",
        max_age=TRUSTED_DEVICE_COOKIE_MAX_AGE,
    )


def _has_valid_trusted_device(user: models.User, request: Optional[Request], db: Session) -> bool:
    token = _trusted_cookie_value(request)
    if not token:
        return False
    hashed = _hash_token(token)
    record = (
        db.query(models.TrustedDevice)
        .filter(
            models.TrustedDevice.user_id == user.id,
            models.TrustedDevice.token_hash == hashed,
        )
        .first()
    )
    if not record:
        return False
    now = _now()
    if record.expires_at and record.expires_at <= now:
        try:
            db.delete(record)
            db.commit()
        except Exception:
            db.rollback()
        return False
    try:
        record.last_used_at = now
        db.commit()
    except Exception:
        db.rollback()
    return True


def _challenge_fingerprint(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    ua = (request.headers.get("user-agent") or "").strip()
    ip = _client_ip(request) or ""
    source = f"{ua}::{ip}".strip()
    if not source:
        return None
    return _hash_token(source)


def _create_mfa_challenge(user: models.User, request: Optional[Request]) -> str:
    expire = _now() + timedelta(minutes=MFA_CHALLENGE_EXPIRE_MINUTES)
    payload = {
        "sub": user.username,
        "uid": user.id,
        "purpose": "mfa_challenge",
        "exp": expire,
    }
    fp = _challenge_fingerprint(request)
    if fp:
        payload["fp"] = fp
    return jwt.encode(payload, SIGNING_KEY, algorithm=SIGNING_ALGORITHM)


def _verify_totp_code(secret: Optional[str], code: Optional[str]) -> bool:
    if not secret or not code:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(str(code).strip(), valid_window=1))
    except Exception:
        return False


def _complete_login(
    user: models.User,
    response: Optional[Response],
    db: Session,
    request: Optional[Request],
):
    if not _user_is_active(user):
        raise HTTPException(status_code=403, detail="Account disabled")

    token, expires_at, jti = create_access_token(user.username)
    refresh_token_value, refresh_expires_at, refresh_jti = create_access_token(
        user.username,
        expires_delta=timedelta(days=REFRESH_TOKEN_DAYS),
        jti=str(uuid4()),
    )
    try:
        create_refresh_token(
            db,
            user_id=user.id,
            token=refresh_token_value,
            jti=refresh_jti,
            expires_at=refresh_expires_at,
            user_agent=request.headers.get("user-agent") if request else None,
            ip=_client_ip(request),
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create refresh session") from exc
    if response is not None:
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=True,
            samesite=SESSION_COOKIE_SAMESITE,
            path="/",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token_value,
            httponly=True,
            secure=True,
            samesite=REFRESH_COOKIE_SAMESITE,
            path="/",
            max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        )
    try:
        create_session_token(
            db,
            user_id=user.id,
            token=token,
            jti=jti,
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent") if request else None,
            ip=_client_ip(request),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to create session") from exc
    try:
        log_event(
            db,
            action="login",
            target_type="user",
            target_id=user.id,
            user_id=user.id,
            details={"username": user.username},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("login audit log skipped", exc)
    return {
        "token_type": "bearer",
        "user": _serialize_user(user),
    }


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    ip = _middleware_remote_ip(request)
    if not ip or ip == "unknown":
        return None
    return ip


def verify_password(plain_password, hashed_password):
    return _verify_password(plain_password, hashed_password)

def hash_password(pw: str) -> str:
    return _hash_password(pw)

def create_access_token(sub: str, expires_delta: Optional[timedelta] = None, jti: Optional[str] = None):
    expire = datetime.now(tz=timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    token_jti = jti or str(uuid4())
    to_encode = {"sub": sub, "exp": expire, "jti": token_jti}
    token = jwt.encode(to_encode, SIGNING_KEY, algorithm=SIGNING_ALGORITHM)
    return token, expire, token_jti

router = APIRouter(prefix="/api/auth", tags=["auth"])

def auth_config(*args, **kwargs):
    from .auth_sso import auth_config as impl
    return impl(*args, **kwargs)


def forgot_password(*args, **kwargs):
    from .auth_sso import forgot_password as impl
    return impl(*args, **kwargs)


def complete_password_reset(*args, **kwargs):
    from .auth_sso import complete_password_reset as impl
    return impl(*args, **kwargs)


def start_sso_login(*args, **kwargs):
    from .auth_sso import start_sso_login as impl
    return impl(*args, **kwargs)


def complete_sso_login(*args, **kwargs):
    from .auth_sso import complete_sso_login as impl
    return impl(*args, **kwargs)


def _clear_auth_cookies(response: Response) -> None:
    from .auth_sso import _clear_auth_cookies as impl
    return impl(response)


def _revoke_local_session_from_request(request: Request, db: Session) -> None:
    from .auth_sso import _revoke_local_session_from_request as impl
    return impl(request, db)


def start_sso_logout(*args, **kwargs):
    from .auth_sso import start_sso_logout as impl
    return impl(*args, **kwargs)


def complete_sso_logout(*args, **kwargs):
    from .auth_sso import complete_sso_logout as impl
    return impl(*args, **kwargs)


@router.post("/token")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    response: Response = None,
    db: Session = Depends(get_db),
    request: Request = None,
):
    username_in = (form.username or "").strip().lower()
    user = (
        db.query(models.User)
        .filter(
            or_(
                func.lower(models.User.username) == username_in,
                func.lower(models.User.email) == username_in,
            )
        )
        .first()
    )

    if _oidc_enabled() and not _local_password_login_allowed(user):
        raise HTTPException(status_code=403, detail="Local sign-in is only available for the local admin account")

    # Failure path
    if not user or not verify_password(form.password, user.password_hash):
        try:
            log_event(
                db,
                action="login_failed",
                target_type="user",
                target_id=(user.id if user else None),
                user_id=None,
                details={"username": form.username},
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("login failure audit log skipped", exc)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user and not _user_is_active(user):
        raise HTTPException(status_code=403, detail="Account disabled")

    return _complete_login(user, response, db, request)

def current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    token = request.cookies.get(SESSION_COOKIE_NAME) or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = _decode_token(token)
        username = payload.get("sub")
        jti = payload.get("jti")
        if not username:
            raise HTTPException(401, "Invalid token")
        if not jti:
            raise HTTPException(401, "Invalid session token")
        user = db.query(models.User).filter(func.lower(models.User.username) == (username or "").lower()).first()
        if not user:
            raise HTTPException(401, "User not found")
        if not _user_is_active(user):
            try:
                revoke_all_sessions_for_user(db, user.id)
            except Exception:
                db.rollback()
            raise HTTPException(401, "Account disabled")
        session = (
            db.query(models.SessionToken)
            .filter(models.SessionToken.jti == jti)
            .first()
        )
        now = datetime.now(timezone.utc)
        if not session:
            raise HTTPException(401, "Session expired")
        if session.revoked_at is not None or session.expires_at <= now:
            try:
                db.delete(session)
                db.commit()
            except Exception:
                db.rollback()
            raise HTTPException(401, "Session expired")
        if str(session.user_id) != str(user.id):
            raise HTTPException(401, "Session invalid")
        last_seen = getattr(session, "last_seen_at", None)
        if SESSION_IDLE_TIMEOUT_MINUTES > 0 and last_seen is not None:
            idle_seconds = (now - last_seen).total_seconds()
            if idle_seconds > SESSION_IDLE_TIMEOUT_MINUTES * 60:
                try:
                    session.revoked_at = now
                    db.commit()
                except Exception:
                    db.rollback()
                raise HTTPException(401, "Session expired")
        try:
            touch_session(db, session.id, only_if_older_seconds=SESSION_ACTIVITY_UPDATE_SECONDS)
        except Exception as exc:
            # best-effort; do not block request
            _debug_suppressed("session activity touch skipped", exc)
        request.state.token_jti = jti
        request.state.session_token_id = session.id
        request.state.session_expires_at = session.expires_at
        request.state.session_last_seen_at = now
        return user
    except JWTError:
        raise HTTPException(401, "Token invalid or expired")

def current_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    """
    Best-effort session lookup. Returns None when no valid session is present
    instead of raising, allowing endpoints to expose non-sensitive data
    publicly while still identifying admins when available.
    """
    try:
        return current_user(request, db)
    except HTTPException as exc:
        if exc.status_code == 401:
            return None
        raise


def _refresh_session_impl(
    response: Response,
    request: Request,
    db: Session,
):
    refresh_cookie = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="No refresh token")
    record = find_valid_refresh(db, refresh_cookie, user_agent=request.headers.get("user-agent"), ip=_client_ip(request))
    if not record:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh")
    user = db.query(models.User).filter(models.User.id == int(record.user_id)).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not _user_is_active(user):
        revoke_refresh_by_jti(db, record.jti)
        raise HTTPException(status_code=401, detail="Account disabled")

    # Rotate refresh
    revoke_refresh_by_jti(db, record.jti)
    new_refresh_value, new_refresh_exp, new_refresh_jti = create_access_token(
        user.username,
        expires_delta=timedelta(days=REFRESH_TOKEN_DAYS),
        jti=str(uuid4()),
    )
    try:
        create_refresh_token(
            db,
            user_id=user.id,
            token=new_refresh_value,
            jti=new_refresh_jti,
            expires_at=new_refresh_exp,
            user_agent=request.headers.get("user-agent") if request else None,
            ip=_client_ip(request),
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to rotate refresh token") from exc

    # Issue new access

    token, expires_at, jti = create_access_token(user.username)
    try:
        create_session_token(
            db,
            user_id=user.id,
            token=token,
            jti=jti,
            expires_at=expires_at,
            user_agent=request.headers.get("user-agent") if request else None,
            ip=_client_ip(request),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to create session") from exc

    # Set cookies
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_refresh_value,
        httponly=True,
        secure=True,
        samesite=REFRESH_COOKIE_SAMESITE,
        path="/",
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
    )

    return {"access_token": token, "token_type": "bearer", "user": _serialize_user(user)}


@router.post("/refresh")
def refresh_session(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    return _refresh_session_impl(response, request, db)



@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    _revoke_local_session_from_request(request, db)
    _clear_auth_cookies(response)
    return {"ok": True}

def require_admin(user: models.User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, "Admin required")
    return user

@router.get("/me")
def me(user: models.User = Depends(current_user)):
    return _serialize_user(user)


@router.post("/preferences")
def update_preferences(
    payload: dict = Body(...),
    user: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    data = payload or {}
    updated = False
    details = {}
    theme_raw = (data.get("theme") or data.get("user_theme") or "").strip().lower()
    if theme_raw:
        if theme_raw not in {"light", "dark", "system"}:
            raise HTTPException(status_code=422, detail="theme must be light, dark, or system")
        user.user_theme = theme_raw
        updated = True
        details["theme"] = user.user_theme

    case_sort_raw = (data.get("case_sort_mode") or data.get("case_sort") or "").strip().lower()
    if case_sort_raw:
        mode = case_sort_raw
        if mode in {"ediscovery_case_name", "case_name", "name", "ediscovery"}:
            mode = "ediscovery"
        if mode in {"legal_case_name", "legal"}:
            mode = "legal"
        if mode not in {"ediscovery", "legal"}:
            raise HTTPException(status_code=422, detail="case_sort_mode must be ediscovery or legal")
        user.case_sort_mode = mode
        updated = True
        details["case_sort_mode"] = mode
    if not updated:
        raise HTTPException(status_code=400, detail="No preferences provided")
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unable to update preferences") from exc
    try:
        log_event(
            db,
            action="user_preferences_update",
            target_type="user",
            target_id=user.id,
            user_id=user.id,
            details=details or {"theme": user.user_theme},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("user preferences audit log skipped", exc)
    return _serialize_user(user)


def _serialize_session_token(row: models.SessionToken, current_id: Optional[str]) -> dict:
    return {
        "id": row.id,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
        "last_seen_at": row.last_seen_at.isoformat() if getattr(row, "last_seen_at", None) else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        "is_current": bool(current_id and str(current_id) == str(row.id)),
    }


@router.get("/sessions")
def list_sessions(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    current_id = getattr(getattr(request, "state", None), "session_token_id", None)
    rows = (
        db.query(models.SessionToken)
        .filter(models.SessionToken.user_id == str(user.id), models.SessionToken.revoked_at.is_(None))
        .order_by(models.SessionToken.created_at.desc().nullslast())
        .all()
    )
    return [_serialize_session_token(r, current_id) for r in rows]


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(current_user),
):
    current_id = getattr(getattr(request, "state", None), "session_token_id", None)
    if current_id and str(session_id) == str(current_id):
        raise HTTPException(status_code=400, detail="Use logout to end the current session")
    row = db.get(models.SessionToken, session_id)
    if not row or str(getattr(row, "user_id", "")) != str(user.id):
        raise HTTPException(status_code=404, detail="Session not found")
    if row.revoked_at is None:
        revoke_session_by_id(db, session_id, user_id=user.id)
    return {"ok": True}


def submit_registration_request(*args, **kwargs):
    from .auth_registration import submit_registration_request as impl
    return impl(*args, **kwargs)


def list_registration_requests(*args, **kwargs):
    from .auth_registration import list_registration_requests as impl
    return impl(*args, **kwargs)


def approve_registration_request(*args, **kwargs):
    from .auth_registration import approve_registration_request as impl
    return impl(*args, **kwargs)


def decline_registration_request(*args, **kwargs):
    from .auth_registration import decline_registration_request as impl
    return impl(*args, **kwargs)


def delete_registration_request(*args, **kwargs):
    from .auth_registration import delete_registration_request as impl
    return impl(*args, **kwargs)


def claim_registration(*args, **kwargs):
    from .auth_registration import claim_registration as impl
    return impl(*args, **kwargs)


def complete_registration(*args, **kwargs):
    from .auth_registration import complete_registration as impl
    return impl(*args, **kwargs)
