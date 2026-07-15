"""Account registration auth routes.

This module keeps the self-service/admin registration workflow separate from
login, OIDC, session, and MFA behavior in auth.py. Shared helpers still live in
``auth.py`` for compatibility with existing tests and monkeypatches.
"""

from datetime import timedelta
import secrets

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from jwt import InvalidTokenError as JWTError
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import auth as auth_core, models
from .app_branding import app_display_name
from .database import get_db
from .permissions import is_valid_tech_group
from .requestor_email_policy import require_allowed_requestor_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register_request")
def submit_registration_request(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    request: Request = None,
):
    name = (payload.get("name") or "").strip()
    email_raw = (payload.get("email") or "").strip()
    source = (payload.get("source") or "self_service").strip().lower() or "self_service"
    sso_registration_token = (payload.get('sso_registration_token') or '').strip()
    if source not in {"self_service", "sso"}:
        source = "self_service"
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not email_raw:
        raise HTTPException(status_code=400, detail="Email is required")
    email = auth_core._validate_email_address(email_raw)
    sso_subject = None
    if source == 'sso':
        if not sso_registration_token:
            raise HTTPException(status_code=400, detail=f'{auth_core._sso_display_name()} verification is required for this request')
        try:
            sso_payload = auth_core._decode_token(sso_registration_token, purpose='sso_registration')
        except JWTError as exc:
            raise HTTPException(status_code=400, detail=f'{auth_core._sso_display_name()} verification is invalid or expired') from exc
        token_email = auth_core._validate_email_address((sso_payload.get('email') or '').strip())
        sso_subject = (sso_payload.get('sub') or '').strip()
        if not sso_subject:
            raise HTTPException(status_code=400, detail=f'{auth_core._sso_display_name()} verification is invalid or expired')
        if email.lower() != token_email.lower():
            raise HTTPException(status_code=400, detail=f'Email must match the verified {auth_core._sso_display_name()} account')
    if auth_core.REGISTER_REQUEST_LIMIT > 0:
        client_ip = auth_core._client_ip(request) or "unknown"
        allowed, retry = auth_core._register_request_limiter.allow(client_ip, window=auth_core.REGISTER_REQUEST_WINDOW, limit=auth_core.REGISTER_REQUEST_LIMIT)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many registration requests from this client",
                headers={"Retry-After": str(retry)},
            )
    exists = (
        db.query(models.User)
        .filter(func.lower(models.User.email) == email.lower())
        .first()
    )
    if exists:
        # Email the user guidance instead of creating another registration request.
        # Keep the response generic to avoid account enumeration.
        try:
            allowed, _retry = auth_core._existing_account_notice_limiter.allow(
                f"existing_account_notice:{email.lower()}",
                window=auth_core.REGISTER_REQUEST_WINDOW,
                limit=max(1, min(auth_core.REGISTER_REQUEST_LIMIT, 3)),
            )
            if allowed:
                auth_core._notify_registration_existing_account(
                    recipient=email,
                    username=getattr(exists, "username", None),
                    request=request,
                )
        except Exception as exc:
            auth_core._debug_suppressed("registration existing-account notice skipped", exc)
        try:
            auth_core.log_event(
                db,
                action="registration_request_existing_account",
                target_type="user",
                target_id=getattr(exists, "id", None),
                details={"email": email, "source": source},
                request=request,
            )
        except Exception as exc:
            auth_core._debug_suppressed("registration existing-account audit log skipped", exc)
        return {"ok": True}
    duplicate_query = db.query(models.AccountRegistrationRequest).filter(
        models.AccountRegistrationRequest.status.in_(("pending", "approved"))
    )
    if sso_subject:
        duplicate = duplicate_query.filter(
            or_(
                func.lower(models.AccountRegistrationRequest.email) == email.lower(),
                models.AccountRegistrationRequest.sso_subject == sso_subject,
            )
        ).first()
    else:
        duplicate = duplicate_query.filter(
            func.lower(models.AccountRegistrationRequest.email) == email.lower(),
        ).first()
    if duplicate:
        # If the prior request was approved but the invite expired, allow the user to re-request.
        if (duplicate.status or "").strip().lower() == "approved":
            expires_at = getattr(duplicate, "invite_token_expires_at", None)
            if not expires_at or expires_at <= auth_core._now():
                try:
                    duplicate.status = "declined"
                    duplicate.declined_reason = "Expired registration invite; user requested a new registration."
                    db.add(duplicate)
                    db.commit()
                    duplicate = None
                except Exception:
                    db.rollback()
        if duplicate:
            return {"ok": True}
    row = models.AccountRegistrationRequest(name=name, email=email, status="pending", sso_subject=sso_subject)
    db.add(row)
    db.commit()
    try:
        auth_core.log_event(
            db,
            action="registration_request_submit",
            target_type="account_registration",
            target_id=row.id,
            details={"name": row.name, "email": row.email, "source": source, "sso_subject": sso_subject or None},
            request=request,
        )
    except Exception as exc:
        auth_core._debug_suppressed("registration submit audit log skipped", exc)
    auth_core._notify_registration_request_admins(db, row)
    return {"ok": True}


@router.get("/register_requests")
def list_registration_requests(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_core.current_user),
):
    auth_core._ensure_sys_admin(user)
    rows = (
        db.query(models.AccountRegistrationRequest)
        .filter(models.AccountRegistrationRequest.status.in_(("pending", "approved")))
        .order_by(models.AccountRegistrationRequest.created_at.desc())
        .all()
    )
    result = []
    for row in rows:
        result.append(
            {
                "id": row.id,
                "name": row.name,
                "email": row.email,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "declined_reason": row.declined_reason,
                "role": getattr(row, "role", None),
                "requestor_group": getattr(row, "requestor_group", None),
                "invite_token_expires_at": row.invite_token_expires_at.isoformat() if row.invite_token_expires_at else None,
            }
        )
    return result


@router.post("/register_requests/{request_id}/approve")
def approve_registration_request(
    request_id: int,
    payload: dict = Body(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_core.current_user),
    request: Request = None,
):
    auth_core._ensure_sys_admin(user)
    row = auth_core._get_registration_request(db, request_id)
    if row.status not in {"pending", "approved"}:
        raise HTTPException(status_code=400, detail="Request is not pending")
    role_raw = ""
    try:
        role_raw = (payload or {}).get("role") or ""
    except Exception:
        role_raw = ""
    role = (role_raw or "").strip().lower()
    if not role:
        raise HTTPException(status_code=400, detail="Role is required to approve this request")
    if role == "admin":
        role = "sys_admin"
    allowed_roles = {"sys_admin", "analyst", "requestor", "tech"}
    if role not in allowed_roles:
        raise HTTPException(status_code=400, detail="Role must be admin, analyst, requestor, or tech")
    group_raw = ""
    try:
        group_raw = (payload or {}).get("requestor_group") or ""
    except Exception:
        group_raw = ""
    group = (group_raw or "").strip().lower()
    if role in {"requestor", "tech"}:
        if not group:
            raise HTTPException(status_code=400, detail="Department/group is required to approve this request")
        if role == "tech" and not is_valid_tech_group(group):
            raise HTTPException(status_code=400, detail="Tech group must be a configured ticket workflow group")
    else:
        group = group or None
    if role == "requestor":
        require_allowed_requestor_email(row.email, label="Requestor account email")

    row.status = "approved"
    row.approved_at = auth_core._now()
    row.approved_by_id = user.id
    row.requestor_group = group
    row.role = role

    if auth_core._oidc_enabled():
        email = (row.email or "").strip().lower()
        sso_subject = (getattr(row, 'sso_subject', None) or '').strip() or None
        existing_user = None
        if sso_subject:
            existing_user = db.query(models.User).filter(models.User.sso_subject == sso_subject).first()
        if not existing_user:
            existing_user = (
                db.query(models.User)
                .filter(func.lower(models.User.email) == email)
                .first()
            )
        name_parts = (row.name or "").strip().split()
        first_name = name_parts[0] if name_parts else email
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else None
        if sso_subject:
            subject_conflict_query = db.query(models.User).filter(models.User.sso_subject == sso_subject)
            if existing_user:
                subject_conflict_query = subject_conflict_query.filter(models.User.id != existing_user.id)
            subject_conflict = subject_conflict_query.first()
            if subject_conflict:
                raise HTTPException(status_code=400, detail=f'This {auth_core._sso_display_name()} identity is already linked to another {app_display_name()} account')
        if existing_user:
            existing_user.email = email
            existing_user.first_name = first_name
            existing_user.last_name = last_name
            existing_user.role = role
            existing_user.is_admin = role == "sys_admin"
            existing_user.requestor_group = group if role in {"requestor", "tech"} else None
            if sso_subject:
                existing_user.sso_subject = sso_subject
            db.add(existing_user)
        else:
            existing_user = models.User(
                username=auth_core._generate_username(db, email),
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_admin=(role == "sys_admin"),
                requestor_group=(group if role in {"requestor", "tech"} else None),
                password_hash=auth_core.hash_password(secrets.token_urlsafe(32)),
                sso_subject=sso_subject,
            )
            db.add(existing_user)
        row.invite_token_hash = None
        row.invite_token_expires_at = None
        row.status = "completed"
        row.completed_at = row.completed_at or auth_core._now()
        db.add(row)
        db.commit()
        auth_core._notify_registration_ready(row, request)
    else:
        token_value = secrets.token_urlsafe(48)
        row.invite_token_hash = auth_core._hash_token(token_value)
        row.invite_token_expires_at = auth_core._now() + timedelta(days=auth_core.REGISTRATION_TOKEN_DAYS)
        db.add(row)
        db.commit()
        auth_core._notify_registration_invite(row, token_value, request)
    try:
        auth_core.log_event(
            db,
            action="registration_request_approve",
            target_type="account_registration",
            target_id=row.id,
            actor_id=user.id,
            details={
                "request_id": row.id,
                "email": row.email,
                "name": row.name,
                "role": role,
                "requestor_group": group,
                "delivery": "sso_ready_email" if auth_core._oidc_enabled() else "local_invite",
            },
            request=request,
        )
    except Exception as exc:
        auth_core._debug_suppressed("registration approve audit log skipped", exc)
    return {"ok": True}


@router.post("/register_requests/{request_id}/decline")
def decline_registration_request(
    request_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_core.current_user),
    request: Request = None,
):
    auth_core._ensure_sys_admin(user)
    row = auth_core._get_registration_request(db, request_id)
    if row.status not in {"pending", "approved"}:
        raise HTTPException(status_code=400, detail="Request is not pending")
    reason = (payload.get("reason") or "").strip()
    row.status = "declined"
    row.declined_reason = reason or None
    row.invite_token_hash = None
    row.invite_token_expires_at = None
    row.invite_totp_secret = None
    db.add(row)
    db.commit()
    auth_core._notify_registration_decline(row)
    try:
        auth_core.log_event(
            db,
            action="registration_request_decline",
            target_type="account_registration",
            target_id=row.id,
            actor_id=user.id,
            details={"request_id": row.id, "reason": reason or None, "email": row.email},
            request=request,
        )
    except Exception as exc:
        auth_core._debug_suppressed("registration decline audit log skipped", exc)
    return {"ok": True}


@router.delete("/register_requests/{request_id}")
def delete_registration_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth_core.current_user),
    request: Request = None,
):
    auth_core._ensure_sys_admin(user)
    row = auth_core._get_registration_request(db, request_id)
    status = (row.status or "").strip().lower()
    if status == "completed":
        raise HTTPException(status_code=400, detail="Completed requests cannot be removed")
    request_details = {
        "request_id": row.id,
        "email": row.email,
        "name": row.name,
        "status": row.status,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }
    db.delete(row)
    db.commit()
    try:
        auth_core.log_event(
            db,
            action="registration_request_delete",
            target_type="account_registration",
            target_id=request_id,
            actor_id=user.id,
            details=request_details,
            request=request,
        )
    except Exception as exc:
        auth_core._debug_suppressed("registration delete audit log skipped", exc)
    return {"ok": True}


@router.get("/register/claim")
def claim_registration(
    token: str,
    db: Session = Depends(get_db),
):
    row = auth_core._registration_by_token(db, token)
    if not row or row.status != "approved" or not row.invite_token_expires_at:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if row.invite_token_expires_at <= auth_core._now():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    return {
        "name": row.name,
        "email": row.email,
        "expires_at": row.invite_token_expires_at.isoformat(),
        "sso_enabled": auth_core._oidc_enabled(),
        "sso_display_name": auth_core._sso_display_name(),
    }


@router.post("/register/complete")
def complete_registration(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    request: Request = None,
):
    token = (payload.get("token") or "").strip()
    password = (payload.get("password") or payload.get("new_password") or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="token is required")
    sso_enabled = auth_core._oidc_enabled()
    if not sso_enabled and not password:
        raise HTTPException(status_code=400, detail="Password is required")
    row = auth_core._registration_by_token(db, token)
    if not row or row.status != "approved" or not row.invite_token_hash:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if not row.invite_token_expires_at or row.invite_token_expires_at <= auth_core._now():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    if not sso_enabled:
        auth_core._validate_new_password(password)
    email = row.email.lower()
    role = (getattr(row, "role", None) or auth_core.REGISTRATION_DEFAULT_ROLE or "requestor").strip().lower()
    if role == "admin":
        role = "sys_admin"
    if role not in {"sys_admin", "analyst", "requestor", "tech"}:
        role = "requestor"
    if role == "requestor":
        require_allowed_requestor_email(email, label="Requestor account email")
    if role == "tech":
        group = (row.requestor_group or "").strip()
        if not group or not is_valid_tech_group(group):
            raise HTTPException(status_code=400, detail="Tech registration requires a valid ticket group")
    first_name = row.name.split()[0] if row.name else email
    last_name = " ".join(row.name.split()[1:]) if row.name and len(row.name.split()) > 1 else None
    username = auth_core._generate_username(db, email)
    new_user = models.User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_admin=(role == "sys_admin"),
        requestor_group=(row.requestor_group if role in {"requestor", "tech"} else None),
        password_hash=auth_core.hash_password(password if not sso_enabled else secrets.token_urlsafe(32)),
    )
    db.add(new_user)
    row.status = "completed"
    row.completed_at = auth_core._now()
    row.invite_token_hash = None
    row.invite_token_expires_at = None
    row.invite_totp_secret = None
    db.commit()
    return {"ok": True}
