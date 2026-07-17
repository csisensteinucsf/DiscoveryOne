from fastapi import Request, APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from datetime import datetime, timezone, timedelta
import secrets

from .database import get_db
from . import models, schemas
from .auth import current_user as get_current_user, _is_seed_admin, _oidc_enabled, SESSION_IDLE_TIMEOUT_MINUTES
from .audit import log_event
from .notifications import notify_user_password_change
from .security import hash_password
from .permissions import is_sys_admin, is_valid_tech_group
from .requestor_email_policy import require_allowed_requestor_email
from .session_tokens import revoke_all_auth_tokens_for_user
from .safe_log import debug_suppressed as _debug_suppressed
from .login_history import last_login_map

router = APIRouter(prefix="/api/users", tags=["users"])


def get_current_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if not getattr(user, "is_admin", False):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def _serialize_user(user: models.User, last_login: datetime | None = None) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "employee_id": getattr(user, "employee_id", None),
        "role": getattr(user, "role", None) or ("sys_admin" if user.is_admin else "analyst"),
        "is_admin": bool(user.is_admin),
        "is_active": bool(getattr(user, "is_active", True)),
        "local_auth_only": bool(getattr(user, "local_auth_only", False)),
        "requestor_group": user.requestor_group,
        "last_login": last_login.isoformat() if last_login else None,
        "user_theme": getattr(user, "user_theme", None) or "light",
        "case_sort_mode": getattr(user, "case_sort_mode", None) or "ediscovery",
    }


def _display_name(user: models.User) -> str:
    first = (getattr(user, "first_name", None) or "").strip()
    last = (getattr(user, "last_name", None) or "").strip()
    return " ".join(part for part in (first, last) if part) or (getattr(user, "username", None) or "").strip() or f"User {getattr(user, 'id', '')}"


def _normalize_group(*args, **kwargs):
    from .users_groups import _normalize_group as impl
    return impl(*args, **kwargs)


def _group_label(*args, **kwargs):
    from .users_groups import _group_label as impl
    return impl(*args, **kwargs)


def _clean_group_label(*args, **kwargs):
    from .users_groups import _clean_group_label as impl
    return impl(*args, **kwargs)


def _group_label_map(*args, **kwargs):
    from .users_groups import _group_label_map as impl
    return impl(*args, **kwargs)


def _all_requestor_groups(*args, **kwargs):
    from .users_groups import _all_requestor_groups as impl
    return impl(*args, **kwargs)


@router.get("")
def list_users(
    db: Session = Depends(get_db), request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    """
    Sys admins see the full list. Other roles only receive their own record so the
    System page can render in a read-only mode.
    """
    if is_sys_admin(actor):
        rows = db.query(models.User).order_by(models.User.id.asc()).all()
    else:
        rows = [actor]
    ids = [getattr(r, "id", None) for r in rows if getattr(r, "id", None) is not None]
    last_seen_map = last_login_map(db, ids)
    return [_serialize_user(row, last_seen_map.get(str(getattr(row, "id", "")))) for row in rows]


@router.get("/active")
def list_active_users(
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_admin),
):
    now = datetime.now(timezone.utc)
    query = (
        db.query(models.SessionToken)
        .filter(models.SessionToken.revoked_at.is_(None))
        .filter(models.SessionToken.expires_at > now)
    )
    if SESSION_IDLE_TIMEOUT_MINUTES > 0:
        idle_cutoff = now - timedelta(minutes=SESSION_IDLE_TIMEOUT_MINUTES)
        query = query.filter(
            models.SessionToken.last_seen_at.is_(None)
            | (models.SessionToken.last_seen_at >= idle_cutoff)
        )
    sessions = query.order_by(models.SessionToken.last_seen_at.desc().nullslast()).all()

    user_ids: set[int] = set()
    for session in sessions:
        try:
            user_ids.add(int(getattr(session, "user_id", 0) or 0))
        except Exception:
            continue
    users_by_id = {
        int(row.id): row
        for row in db.query(models.User).filter(models.User.id.in_(user_ids)).all()
    } if user_ids else {}

    by_user: dict[int, dict] = {}
    for session in sessions:
        try:
            user_id = int(getattr(session, "user_id", 0) or 0)
        except Exception:
            continue
        user = users_by_id.get(user_id)
        if not user:
            continue
        item = by_user.setdefault(
            user_id,
            {
                "id": user_id,
                "name": _display_name(user),
                "email": getattr(user, "email", None),
                "username": getattr(user, "username", None),
                "role": getattr(user, "role", None) or ("sys_admin" if getattr(user, "is_admin", False) else "analyst"),
                "session_count": 0,
                "last_seen_at": None,
                "expires_at": None,
                "ip": None,
                "user_agent": None,
            },
        )
        item["session_count"] += 1
        last_seen = getattr(session, "last_seen_at", None)
        if item["last_seen_at"] is None or (last_seen and last_seen > item["last_seen_at"]):
            item["last_seen_at"] = last_seen
            item["expires_at"] = getattr(session, "expires_at", None)
            item["ip"] = getattr(session, "ip", None)
            item["user_agent"] = getattr(session, "user_agent", None)

    users = sorted(by_user.values(), key=lambda item: item.get("last_seen_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for item in users:
        if item.get("last_seen_at"):
            item["last_seen_at"] = item["last_seen_at"].isoformat()
        if item.get("expires_at"):
            item["expires_at"] = item["expires_at"].isoformat()
    return {
        "count": len(users),
        "users": users,
        "idle_timeout_minutes": SESSION_IDLE_TIMEOUT_MINUTES,
    }


@router.get("/analysts")
def list_analysts(
    db: Session = Depends(get_db), request: Request = None,
    user: models.User = Depends(get_current_user),
):
    if not is_sys_admin(user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    rows = (
        db.query(models.User)
        .filter(
            models.User.username != "admin",
            models.User.role.in_(("analyst", "sys_admin")),
            models.User.is_active.is_(True),
        )
        .order_by(models.User.username.asc())
        .all()
    )
    return [{"id": row.id, "username": row.username} for row in rows]


def list_groups(*args, **kwargs):
    from .users_groups import list_groups as impl
    return impl(*args, **kwargs)


def create_group(*args, **kwargs):
    from .users_groups import create_group as impl
    return impl(*args, **kwargs)


def update_group(*args, **kwargs):
    from .users_groups import update_group as impl
    return impl(*args, **kwargs)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db), request: Request = None,
    _admin: models.User = Depends(get_current_admin),
):
    email = (payload.email or payload.username or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    username = email
    first_name = (payload.first_name or "").strip()
    last_name = (payload.last_name or "").strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=400, detail="First name and last name are required")
    requestor_group = (payload.requestor_group or "").strip() or None
    employee_id = (payload.employee_id or "").strip() or None

    existing = db.query(models.User).filter(models.User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    email_conflict = (
        db.query(models.User)
        .filter(models.User.email == email)
        .first()
    )
    if email_conflict:
        raise HTTPException(status_code=400, detail="Email already exists")

    # Determine role; prefer explicit role, then legacy is_admin flag.
    if payload.role:
        role = payload.role
    elif payload.is_admin is not None:
        role = "sys_admin" if payload.is_admin else "analyst"
    else:
        role = "analyst"

    if role == "tech":
        if not requestor_group:
            raise HTTPException(status_code=422, detail="Tech accounts require a ticket group (a configured ticket workflow group)")
        if not is_valid_tech_group(requestor_group):
            raise HTTPException(status_code=422, detail="Tech group must be a configured ticket workflow group")
    if role == "requestor":
        require_allowed_requestor_email(email, label="Requestor account email")

    is_admin = role == "sys_admin"
    local_auth_only = bool(getattr(payload, "local_auth_only", False))
    password = (payload.password or "").strip()
    if not password and (local_auth_only or not _oidc_enabled()):
        raise HTTPException(status_code=400, detail="Password is required for local credential accounts")
    if not password:
        password = secrets.token_urlsafe(32)

    u = models.User(
        username=username,
        password_hash=hash_password(password),
        is_admin=is_admin,
        email=email,
        role=role,
        first_name=first_name,
        last_name=last_name,
        requestor_group=requestor_group,
        employee_id=employee_id,
        local_auth_only=local_auth_only,
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)

    try:
        log_event(
            db,
            action="user_create",
            actor_id=_admin.id,
            target_type="user",
            target_id=u.id,
            details={"username": u.username, "email": u.email, "role": u.role},
            request=request,
        )
    except Exception as exc:
        # Never block user creation on audit log failure.
        _debug_suppressed("suppressed exception in users.py:164", exc)

    return u


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db), request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    # Update username, email, role, and optionally password.
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    editing_self = actor.id == u.id
    allow_admin_fields = is_sys_admin(actor)
    if not editing_self and not allow_admin_fields:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    if editing_self and payload.password:
        raise HTTPException(
            status_code=403,
            detail="Self-service password changes are disabled. Ask another system administrator to reset the password or use the configured seed admin password.",
        )

    original_username = u.username
    original_email = getattr(u, "email", None)
    original_first = getattr(u, "first_name", None)
    original_last = getattr(u, "last_name", None)
    original_role = getattr(u, "role", None) or ("sys_admin" if u.is_admin else "analyst")
    original_group = getattr(u, "requestor_group", None)
    original_is_admin = u.is_admin
    original_local_auth_only = bool(getattr(u, "local_auth_only", False))
    original_is_active = bool(getattr(u, "is_active", True))

    if editing_self and not allow_admin_fields:
        forbidden_fields = []
        if payload.username is not None:
            forbidden_fields.append("username")
        if payload.email is not None:
            forbidden_fields.append("email")
        if payload.role is not None or payload.is_admin is not None:
            forbidden_fields.append("role")
        if payload.requestor_group is not None:
            forbidden_fields.append("requestor_group")
        if payload.local_auth_only is not None:
            forbidden_fields.append("local_auth_only")
        if payload.is_active is not None:
            forbidden_fields.append("is_active")
        if forbidden_fields:
            raise HTTPException(
                status_code=403,
                detail=f"Only administrators can update: {', '.join(forbidden_fields)}",
            )

    # Username
    if payload.username is not None:
        new_name = payload.username.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="Username cannot be empty")
        conflict = (
            db.query(models.User)
            .filter(and_(models.User.username == new_name, models.User.id != u.id))
            .first()
        )
        if conflict:
            raise HTTPException(status_code=400, detail="Username already exists")
        u.username = new_name

    # Email
    if payload.email is not None:
        new_email = (payload.email or "").strip().lower() or None
        if new_email:
            conflict = (
                db.query(models.User)
                .filter(and_(models.User.email == new_email, models.User.id != u.id))
                .first()
            )
            if conflict:
                raise HTTPException(status_code=400, detail="Email already exists")
        u.email = new_email
        if new_email:
            u.username = new_email

    if payload.employee_id is not None:
        u.employee_id = (payload.employee_id or "").strip() or None

    # Role / is_admin
    current_role = getattr(u, "role", None) or original_role
    if allow_admin_fields:
        if payload.role is not None:
            new_role = payload.role
        elif payload.is_admin is not None:
            new_role = "sys_admin" if payload.is_admin else "analyst"
        else:
            new_role = current_role
    else:
        new_role = current_role

    pending_group = original_group
    if payload.requestor_group is not None:
        pending_group = (payload.requestor_group or "").strip() or None
    if new_role == "tech":
        if not pending_group:
            raise HTTPException(status_code=422, detail="Tech accounts require a ticket group (a configured ticket workflow group)")
        if not is_valid_tech_group(pending_group):
            raise HTTPException(status_code=422, detail="Tech group must be a configured ticket workflow group")
    if new_role == "requestor":
        require_allowed_requestor_email(getattr(u, "email", None), label="Requestor account email")

    u.role = new_role
    u.is_admin = new_role == "sys_admin"

    local_auth_only = original_local_auth_only
    if allow_admin_fields and payload.local_auth_only is not None:
        local_auth_only = bool(payload.local_auth_only)
    if allow_admin_fields and local_auth_only and not original_local_auth_only and not (payload.password and payload.password.strip()):
        raise HTTPException(status_code=400, detail="Set a password when switching this account to local credentials")
    u.local_auth_only = local_auth_only

    if allow_admin_fields and payload.is_active is not None:
        next_is_active = bool(payload.is_active)
        if editing_self and original_is_active and not next_is_active:
            raise HTTPException(status_code=400, detail="You cannot disable your own account")
        u.is_active = next_is_active

    password_changed = False
    auth_mode_changed = original_local_auth_only != bool(getattr(u, "local_auth_only", False))
    active_state_changed = original_is_active != bool(getattr(u, "is_active", True))
    # Password
    if payload.password:
        pw = payload.password.strip()
        if pw:
            u.password_hash = hash_password(pw)
            password_changed = True

    if payload.requestor_group is not None:
        u.requestor_group = pending_group

    if payload.first_name is not None:
        first = (payload.first_name or "").strip()
        if not first:
            raise HTTPException(status_code=400, detail="First name cannot be empty")
        u.first_name = first
    if payload.last_name is not None:
        last = (payload.last_name or "").strip()
        if not last:
            raise HTTPException(status_code=400, detail="Last name cannot be empty")
        u.last_name = last

    db.add(u)
    if password_changed or auth_mode_changed or active_state_changed:
        revoke_all_auth_tokens_for_user(db, u.id, commit=False)
    db.commit()
    db.refresh(u)
    if password_changed:
        try:
            notify_user_password_change(u)
        except Exception as exc:
            _debug_suppressed("suppressed exception in users.py:281", exc)

    # Audit
    try:
        details = {
            "target_username": u.username,
            "target_email": getattr(u, "email", None),
            "target_first_name": getattr(u, "first_name", None),
            "target_last_name": getattr(u, "last_name", None),
        }
        if original_username != u.username:
            details["username"] = {"from": original_username, "to": u.username}
        if original_email != u.email:
            details["email"] = {"from": original_email, "to": u.email}
        if original_first != u.first_name:
            details["first_name"] = {"from": original_first, "to": u.first_name}
        if original_last != u.last_name:
            details["last_name"] = {"from": original_last, "to": u.last_name}
        if original_role != u.role:
            details["role"] = {"from": original_role, "to": u.role}
        if original_group != u.requestor_group:
            details["requestor_group"] = {"from": original_group, "to": u.requestor_group}
        if original_is_admin != u.is_admin:
            details["is_admin"] = {"from": original_is_admin, "to": u.is_admin}
        if original_local_auth_only != bool(getattr(u, "local_auth_only", False)):
            details["local_auth_only"] = {"from": original_local_auth_only, "to": bool(getattr(u, "local_auth_only", False))}
        if original_is_active != bool(getattr(u, "is_active", True)):
            details["is_active"] = {"from": original_is_active, "to": bool(getattr(u, "is_active", True))}
        if any(key not in {"target_username", "target_email", "target_first_name", "target_last_name"} for key in details):
            log_event(
                db,
                action="user_update",
                actor_id=actor.id,
                target_type="user",
                target_id=u.id,
                details=details,
                request=request,
            )
    except Exception as exc:
        _debug_suppressed("suppressed exception in users.py:311", exc)

    return u


@router.put("/{user_id}")
def replace_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db), request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    # PUT behaves the same as PATCH for this resource.
    return update_user(user_id, payload, db=db, request=request, actor=actor)


@router.post("/{user_id}/password", status_code=204)
def reset_password(
    user_id: int,
    payload: schemas.PasswordReset,
    db: Session = Depends(get_db), request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    pw = (payload.resolved() or "").strip()
    if not pw:
        raise HTTPException(status_code=422, detail="password is required")
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    editing_self = actor.id == user_id
    if editing_self:
        raise HTTPException(
            status_code=403,
            detail="Self-service password changes are disabled. Ask another system administrator to reset the password or use the configured seed admin password.",
        )
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    user.password_hash = hash_password(pw)
    db.add(user)
    revoke_all_auth_tokens_for_user(db, user.id, commit=False)
    db.commit()
    try:
        log_event(
            db,
            action="user_password_change",
            actor_id=actor.id,
            target_type="user",
            target_id=user.id,
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in users.py:357", exc)
    try:
        notify_user_password_change(user)
    except Exception as exc:
        _debug_suppressed("suppressed exception in users.py:361", exc)
    return Response(status_code=204)


# Legacy path kept for compatibility.
@router.post("/{user_id}/reset_password", status_code=204)
def reset_password_compat(
    user_id: int,
    payload: schemas.PasswordReset,
    db: Session = Depends(get_db), request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    return reset_password(user_id, payload, db=db, request=request, actor=actor)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db), request: Request = None,
    _admin: models.User = Depends(get_current_admin),
):
    u = db.get(models.User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    if _is_seed_admin(u):
        raise HTTPException(status_code=400, detail="Built-in admin account cannot be deleted")

    _uid = u.id
    _username = u.username
    _email = getattr(u, "email", None)

    revoke_all_auth_tokens_for_user(db, _uid, commit=False)
    db.delete(u)
    db.commit()
    try:
        log_event(db,
            action="user_delete",
            target_type="user",
            target_id=_uid,
            user_id=_admin.id,
            details={"username": _username, "email": _email},  request=request)
    except Exception as exc:
        _debug_suppressed("suppressed exception in users.py:440", exc)
    return Response(status_code=204)



