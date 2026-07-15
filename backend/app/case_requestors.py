import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from . import models
from .app_branding import app_display_name, branded_subject
from .audit import log_event
from .auth import _oidc_enabled, current_user as get_current_user
from .database import get_db
from .emailer import send_email
from .institution import sso_display_name
from .notifications import _app_base_url
from .permissions import ensure_case_editable, ensure_case_visible
from .requestor_email_policy import require_allowed_requestor_email
from .safe_log import debug_suppressed as _debug_suppressed

router = APIRouter(prefix="/api/cases", tags=["cases"])

REGISTRATION_TOKEN_DAYS = int(os.getenv("REGISTRATION_TOKEN_DAYS", "7"))


def normalize_requestor_email(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        result = validate_email(text, allow_smtputf8=True, check_deliverability=False)
        return require_allowed_requestor_email(result.normalized)
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="requestor must be a valid email address")


def normalize_requestor_entries(
    db: Session,
    items: Optional[List[dict]],
    fallback_email: Optional[str] = None,
) -> List[dict]:
    entries: List[dict] = []
    seen: set[str] = set()
    for raw in items or []:
        email_val = raw.get("email") if isinstance(raw, dict) else getattr(raw, "email", None)
        email = normalize_requestor_email(email_val)
        if not email:
            continue
        email_key = email.lower()
        if email_key in seen:
            continue
        seen.add(email_key)

        user = None
        try:
            user_id = raw.get("user_id") if isinstance(raw, dict) else getattr(raw, "user_id", None)
            if user_id:
                user = db.get(models.User, user_id)
        except Exception:
            user = None
        if user is None:
            user = (
                db.query(models.User)
                .filter(
                    models.User.role == "requestor",
                    or_(
                        func.lower(models.User.email) == email_key,
                        func.lower(models.User.username) == email_key,
                    ),
                )
                .first()
            )

        requestor_group = ((raw.get("requestor_group") if isinstance(raw, dict) else getattr(raw, "requestor_group", None)) or "").strip() or None
        if not requestor_group and user is not None:
            requestor_group = (getattr(user, "requestor_group", None) or "").strip() or None

        entries.append(
            {
                "email": email,
                "user_id": getattr(user, "id", None),
                "requestor_group": requestor_group,
                "is_primary": bool(raw.get("is_primary") if isinstance(raw, dict) else getattr(raw, "is_primary", False)),
            }
        )

    if not entries and fallback_email:
        email = normalize_requestor_email(fallback_email)
        if email:
            entries.append({"email": email, "user_id": None, "requestor_group": None, "is_primary": True})

    if not entries:
        return []

    primary_idx = next((i for i, row in enumerate(entries) if row.get("is_primary")), 0)
    for idx, row in enumerate(entries):
        row["is_primary"] = idx == primary_idx
    return entries


def apply_case_requestors(case: models.Case, entries: List[dict]) -> None:
    case.requestors = []
    primary_email = None
    for row in entries:
        model = models.CaseRequestor(
            email=row.get("email"),
            user_id=row.get("user_id"),
            requestor_group=row.get("requestor_group"),
            is_primary=bool(row.get("is_primary")),
        )
        if model.is_primary and model.email:
            primary_email = model.email
        case.requestors.append(model)
    case.requestor = primary_email


def derive_name_from_email(email: str) -> str:
    """
    Best-effort derivation of a readable name from an email local-part.
    """
    local = (email or "").split("@")[0].strip()
    if not local:
        return ""
    parts = [p for p in local.replace(".", " ").replace("_", " ").replace("-", " ").split() if p]
    if not parts:
        return ""
    first = parts[0].capitalize()
    last = " ".join(p.capitalize() for p in parts[1:]).strip()
    return f"{first} {last}".strip()


def user_display_name(user: models.User) -> str:
    """
    Render a readable name for a user with safe fallbacks.
    """
    if not user:
        return ""
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    combined = " ".join(part for part in (first, last) if part)
    return combined or (getattr(user, "email", "") or getattr(user, "username", "") or "")


def ensure_registration_invite(
    db: Session,
    *,
    email: str,
    name: Optional[str],
    requestor_group: Optional[str],
) -> Tuple[models.AccountRegistrationRequest, str]:
    """
    Create or refresh an approved registration invite for the given email.
    Returns the record and the plaintext invite token.
    """
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email is required for invite")
    normalized_group = (requestor_group or "").strip().lower() or None
    if not normalized_group:
        raise HTTPException(status_code=400, detail="requestor_group is required for requestor invites")
    now = datetime.now(timezone.utc)
    token_value = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token_value.encode("utf-8")).hexdigest()
    expires_at = now + timedelta(days=REGISTRATION_TOKEN_DAYS)

    existing = (
        db.query(models.AccountRegistrationRequest)
        .filter(func.lower(models.AccountRegistrationRequest.email) == normalized_email)
        .order_by(models.AccountRegistrationRequest.created_at.desc())
        .first()
    )
    row: models.AccountRegistrationRequest
    if existing:
        row = existing
        row.name = row.name or name or derive_name_from_email(normalized_email) or normalized_email
        row.status = "approved"
        row.approved_at = row.approved_at or now
        row.invite_token_hash = token_hash
        row.invite_token_expires_at = expires_at
        row.requestor_group = normalized_group
        row.role = "requestor"
    else:
        row = models.AccountRegistrationRequest(
            name=name or derive_name_from_email(normalized_email) or normalized_email,
            email=normalized_email,
            status="approved",
            approved_at=now,
            invite_token_hash=token_hash,
            invite_token_expires_at=expires_at,
            requestor_group=normalized_group,
            role="requestor",
        )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return row, token_value


@router.post("/{case_id}/invite_requestor")
def invite_case_requestor(
    case_id: int,
    payload: dict = Body(default_factory=dict),
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    ensure_case_editable(_user)

    desired_email = None
    try:
        desired_email = (payload or {}).get("email")
    except Exception:
        desired_email = None
    email = normalize_requestor_email(desired_email or getattr(case, "requestor", None))
    if not email:
        raise HTTPException(status_code=400, detail="Case does not have a requestor email")

    existing_user = db.query(models.User).filter(func.lower(models.User.email) == email.lower()).first()
    if existing_user:
        return {"ok": False, "reason": "user_exists"}

    name_raw = ""
    try:
        name_raw = (payload or {}).get("name") or ""
    except Exception:
        name_raw = ""
    name = (name_raw or "").strip() or derive_name_from_email(email) or email
    group_raw = ""
    try:
        group_raw = (payload or {}).get("requestor_group") or ""
    except Exception:
        group_raw = ""
    group = (group_raw or "").strip().lower() or None

    try:
        row, token_value = ensure_registration_invite(
            db,
            email=email,
            name=name,
            requestor_group=group,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Unable to start invite") from exc

    case_label = getattr(case, "name", None) or f"Case #{case.id}"
    legal_label = (getattr(case, "legal_case_name", None) or "").strip()
    link = f"{_app_base_url(request)}/register?token={token_value}"
    case_descriptor = f"{case_label} - {legal_label}" if legal_label else case_label
    account_action = (
        f"activate your {app_display_name()} account and sign in with {sso_display_name()}"
        if _oidc_enabled()
        else "register an account"
    )
    body = (
        f"You have been added as a requestor to a {app_display_name()} case. That case is {case_descriptor}.\n\n"
        f"Though an account in the {app_display_name()} system is not required, it will allow you to follow along with the case, request changes to custodians or searches, and other valuable needs.\n"
        f"Please click the following link to {account_action}:\n"
        f"{link}"
    )
    subject_case = case_descriptor
    try:
        send_email(
            recipients=[email],
            subject=branded_subject(f"Register to follow your case: {subject_case}"),
            body=body,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_requestors.py:invite_email", exc)
    try:
        log_event(
            db,
            action="case_requestor_invite",
            target_type="case",
            target_id=case.id,
            actor_id=_user.id,
            details={
                "case_id": case.id,
                "case_name": getattr(case, "name", None),
                "requestor_email": email,
                "registration_request_id": getattr(row, "id", None),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_requestors.py:invite_audit", exc)
    return {"ok": True}