"""Authentication configuration and SSO routes.

The SSO/OIDC HTTP surface is kept separate from local password/session handling
so future identity-provider work can stay scoped to this module.
"""

from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from . import auth as auth_core, models
from .app_branding import app_display_name
from .database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/config")
def auth_config():
    return {
        "sso_enabled": auth_core._oidc_enabled(),
        "sso_configured": auth_core._oidc_is_configured(),
        "sso_login_url": "/api/auth/oidc/login" if auth_core._oidc_enabled() else None,
        "sso_logout_url": "/api/auth/oidc/logout" if auth_core._oidc_enabled() else None,
        "sso_display_name": auth_core._sso_display_name(),
        "institution": auth_core._public_institution_config(),
        "local_password_admin_only": bool(auth_core._oidc_enabled()),
    }


@router.post("/password/forgot")
def forgot_password(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    request: Request = None,
):
    raise HTTPException(
        status_code=404,
        detail="Self-service password reset is disabled. Ask a system administrator to reset local account passwords.",
    )


@router.post("/password/reset")
def complete_password_reset(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    request: Request = None,
):
    raise HTTPException(
        status_code=404,
        detail="Self-service password reset is disabled. Ask a system administrator to reset local account passwords.",
    )

@router.get("/oidc/login")
def start_sso_login(
    request: Request,
    next: Optional[str] = None,
):
    if not auth_core._oidc_enabled():
        raise HTTPException(status_code=404, detail=f"{auth_core._sso_display_name()} sign-in is not enabled")
    state_token = auth_core._create_oidc_state_token(next)
    try:
        authorize_url = auth_core._build_oidc_authorize_url(state_token, request)
    except HTTPException as exc:
        return auth_core._sso_error_response(request, exc.detail if isinstance(exc.detail, str) else f'Unable to start {auth_core._sso_display_name()} sign-in')
    except Exception:
        return auth_core._sso_error_response(request, f'Unable to start {auth_core._sso_display_name()} sign-in')
    response = RedirectResponse(url=authorize_url, status_code=303)
    response.set_cookie(
        key=auth_core.OIDC_STATE_COOKIE,
        value=state_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=auth_core.OIDC_STATE_TTL_SECONDS,
    )
    return response


@router.get("/oidc/callback")
def complete_sso_login(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if not auth_core._oidc_enabled():
        raise HTTPException(status_code=404, detail=f"{auth_core._sso_display_name()} sign-in is not enabled")
    if error:
        return auth_core._sso_error_response(request, error_description or error or f"{auth_core._sso_display_name()} sign-in failed")
    if not code or not state:
        return auth_core._sso_error_response(request, f"{auth_core._sso_display_name()} callback is missing required parameters")
    cookie_state = request.cookies.get(auth_core.OIDC_STATE_COOKIE)
    if not cookie_state or cookie_state != state:
        return auth_core._sso_error_response(request, f"{auth_core._sso_display_name()} login state could not be verified")
    try:
        state_payload = auth_core._decode_token(state, purpose="oidc_state")
        metadata = auth_core._oidc_openid_configuration(auth_core._oidc_issuer())
        token_payload = auth_core._exchange_oidc_code(code, metadata, request)
        claims = auth_core._validate_oidc_id_token(token_payload.get("id_token") or "", metadata, nonce=state_payload.get("nonce") or "")
        user = auth_core._sso_user_from_claims(claims, db)
        if user and getattr(user, "local_auth_only", False):
            return auth_core._sso_error_response(request, f"This {app_display_name()} account uses local credentials. Use email and password to sign in.")
        if not user:
            return auth_core._sso_unregistered_response(request, claims)
        subject = (claims.get('sub') or '').strip()
        if subject and not getattr(user, 'sso_subject', None):
            subject_conflict = db.query(models.User).filter(models.User.sso_subject == subject, models.User.id != user.id).first()
            if subject_conflict:
                return auth_core._sso_error_response(request, f'This {auth_core._sso_display_name()} identity is already linked to another {app_display_name()} account.')
            user.sso_subject = subject
            db.add(user)
            db.commit()
            db.refresh(user)
    except HTTPException as exc:
        return auth_core._sso_error_response(request, exc.detail if isinstance(exc.detail, str) else f"{auth_core._sso_display_name()} sign-in failed")
    except Exception:
        return auth_core._sso_error_response(request, f"{auth_core._sso_display_name()} sign-in failed")

    next_path = auth_core._safe_next_path(state_payload.get("next"))
    response = RedirectResponse(url=f"{auth_core._app_base_url(request)}{next_path}", status_code=303)
    response.delete_cookie(auth_core.OIDC_STATE_COOKIE, path="/")
    response.set_cookie(
        key=auth_core.OIDC_ID_TOKEN_COOKIE,
        value=token_payload.get("id_token") or "",
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
        max_age=auth_core.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    auth_core._complete_login(user, response, db, request)
    return response


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(auth_core.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(auth_core.REFRESH_COOKIE_NAME, path="/")
    response.delete_cookie(auth_core.OIDC_STATE_COOKIE, path="/")
    response.delete_cookie(auth_core.OIDC_ID_TOKEN_COOKIE, path="/")


def _revoke_local_session_from_request(request: Request, db: Session) -> None:
    jti = getattr(getattr(request, "state", None), "token_jti", None)
    auth_core.revoke_session_by_jti(db, jti)
    refresh_cookie = request.cookies.get(auth_core.REFRESH_COOKIE_NAME)
    if refresh_cookie:
        try:
            record = auth_core.find_valid_refresh(db, refresh_cookie, user_agent=request.headers.get("user-agent"), ip=auth_core._client_ip(request))
            if record:
                auth_core.revoke_refresh_by_jti(db, record.jti)
        except Exception as exc:
            auth_core._debug_suppressed("logout refresh revoke skipped", exc)


@router.get("/oidc/logout")
def start_sso_logout(
    request: Request,
    next: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user = auth_core.current_user_optional(request, db)
    local_next = auth_core._safe_next_path(next or "/login")
    state_token = auth_core._create_oidc_state_token(local_next)
    if not auth_core._oidc_enabled() or not auth_core._oidc_is_configured() or not user or auth_core._is_seed_admin(user):
        response = RedirectResponse(url=f"{auth_core._app_base_url(request)}{local_next}", status_code=303)
        _revoke_local_session_from_request(request, db)
        _clear_auth_cookies(response)
        return response
    try:
        metadata = auth_core._oidc_openid_configuration(auth_core._oidc_issuer())
    except Exception:
        response = RedirectResponse(url=f"{auth_core._app_base_url(request)}{local_next}", status_code=303)
        _revoke_local_session_from_request(request, db)
        _clear_auth_cookies(response)
        return response
    logout_endpoint = metadata.get("end_session_endpoint") or f"{auth_core._oidc_issuer()}/v1/logout"
    params = {
        "post_logout_redirect_uri": auth_core._oidc_logout_redirect_uri(request),
        "state": state_token,
    }
    id_token_hint = (request.cookies.get(auth_core.OIDC_ID_TOKEN_COOKIE) or "").strip()
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    response = RedirectResponse(url=f"{logout_endpoint}?{urlencode(params)}", status_code=303)
    _revoke_local_session_from_request(request, db)
    _clear_auth_cookies(response)
    return response


@router.get("/oidc/logout/callback")
def complete_sso_logout(
    request: Request,
    state: Optional[str] = None,
):
    next_path = "/login"
    if state:
        try:
            next_path = auth_core._safe_next_path((auth_core._decode_token(state, purpose="oidc_state") or {}).get("next") or "/login")
        except Exception:
            next_path = "/login"
    response = RedirectResponse(url=f"{auth_core._app_base_url(request)}{next_path}", status_code=303)
    _clear_auth_cookies(response)
    return response
