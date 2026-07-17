import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pyotp
import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import auth, auth_registration, models, schemas, users


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/auth/token",
            "raw_path": b"/api/auth/token",
            "query_string": b"",
            "headers": [(b"user-agent", b"pytest-browser")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


def _user(db, *, username="analyst@example.edu", password="CorrectPassword123", **overrides):
    row = models.User(
        username=username,
        email=overrides.pop("email", username),
        password_hash=auth.hash_password(password),
        role=overrides.pop("role", "analyst"),
        is_admin=overrides.pop("is_admin", False),
        is_active=overrides.pop("is_active", True),
        **overrides,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_password_login_requires_mfa_before_creating_session(db_session, monkeypatch):
    secret = pyotp.random_base32()
    user = _user(db_session, mfa_enabled=True, totp_secret=secret)
    request = _request()
    completed = []

    monkeypatch.setattr(auth, "_oidc_enabled", lambda: False)
    monkeypatch.setattr(auth, "_has_valid_trusted_device", lambda *_args: False)
    monkeypatch.setattr(auth, "_complete_login", lambda *_args: completed.append(True))

    result = auth.login(
        SimpleNamespace(username=user.username, password="CorrectPassword123"),
        response=Response(),
        db=db_session,
        request=request,
    )

    assert result["mfa_required"] is True
    assert result["mfa_token"]
    assert completed == []
    claims = auth._decode_token(result["mfa_token"], purpose="mfa_challenge")
    assert claims["uid"] == user.id


def test_valid_mfa_challenge_completes_login(db_session, monkeypatch):
    secret = pyotp.random_base32()
    user = _user(db_session, mfa_enabled=True, totp_secret=secret)
    request = _request()
    challenge = auth._create_mfa_challenge(user, request)

    class AllowLimiter:
        async def allow(self, *_args, **_kwargs):
            return True, 0

    monkeypatch.setattr(auth, "_mfa_rate_limiter", AllowLimiter())
    monkeypatch.setattr(auth, "_complete_login", lambda current, *_args: {"user_id": current.id})

    result = asyncio.run(
        auth.verify_mfa(
            {"mfa_token": challenge, "code": pyotp.TOTP(secret).now()},
            response=Response(),
            db=db_session,
            request=request,
        )
    )

    assert result == {"user_id": user.id}


def test_invalid_mfa_code_does_not_complete_login(db_session, monkeypatch):
    secret = pyotp.random_base32()
    user = _user(db_session, mfa_enabled=True, totp_secret=secret)
    request = _request()
    challenge = auth._create_mfa_challenge(user, request)

    class AllowLimiter:
        async def allow(self, *_args, **_kwargs):
            return True, 0

    monkeypatch.setattr(auth, "_mfa_rate_limiter", AllowLimiter())
    monkeypatch.setattr(auth, "_complete_login", lambda *_args: pytest.fail("login must not complete"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            auth.verify_mfa(
                {"mfa_token": challenge, "code": "000000"},
                response=Response(),
                db=db_session,
                request=request,
            )
        )
    assert exc.value.status_code == 401


def test_oidc_subject_mismatch_cannot_fall_back_to_email(db_session):
    _user(
        db_session,
        username="linked@example.edu",
        email="linked@example.edu",
        password="unused-password",
        sso_subject="persisted-subject",
    )

    with pytest.raises(HTTPException) as exc:
        auth._sso_user_from_claims(
            {"sub": "attacker-subject", "email": "linked@example.edu", "email_verified": True},
            db_session,
        )
    assert exc.value.status_code == 401


def test_oidc_first_binding_requires_verified_email(db_session):
    user = _user(
        db_session,
        username="unlinked@example.edu",
        email="unlinked@example.edu",
        password="unused-password",
    )

    assert auth._sso_user_from_claims(
        {"sub": "new-subject", "email": user.email, "email_verified": False},
        db_session,
    ) is None
    matched = auth._sso_user_from_claims(
        {"sub": "new-subject", "email": user.email, "email_verified": True},
        db_session,
    )
    assert matched.id == user.id


@pytest.mark.parametrize("operation", ["patch", "put", "password", "legacy_password"])
def test_credential_change_routes_revoke_access_and_refresh_tokens(db_session, monkeypatch, operation):
    admin = _user(
        db_session,
        username="admin@example.edu",
        role="sys_admin",
        is_admin=True,
    )
    target = _user(db_session, username="target@example.edu")
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    session = models.SessionToken(
        id=str(uuid4()),
        user_id=str(target.id),
        jti=str(uuid4()),
        token_hash="session-hash-" + operation,
        expires_at=expires,
    )
    refresh = models.RefreshToken(
        id=str(uuid4()),
        user_id=str(target.id),
        jti=str(uuid4()),
        token_hash="refresh-hash-" + operation,
        expires_at=expires,
    )
    db_session.add_all([session, refresh])
    db_session.commit()
    monkeypatch.setattr(users, "notify_user_password_change", lambda *_args, **_kwargs: None)

    if operation == "patch":
        users.update_user(
            target.id,
            schemas.UserUpdate(password="ReplacementPassword123"),
            db=db_session,
            actor=admin,
        )
    elif operation == "put":
        users.replace_user(
            target.id,
            schemas.UserUpdate(password="ReplacementPassword123"),
            db=db_session,
            actor=admin,
        )
    elif operation == "password":
        users.reset_password(
            target.id,
            schemas.PasswordReset(password="ReplacementPassword123"),
            db=db_session,
            actor=admin,
        )
    else:
        users.reset_password_compat(
            target.id,
            schemas.PasswordReset(password="ReplacementPassword123"),
            db=db_session,
            actor=admin,
        )

    db_session.expire_all()
    assert db_session.get(models.SessionToken, session.id).revoked_at is not None
    assert db_session.get(models.RefreshToken, refresh.id).revoked_at is not None


def test_unverified_email_provider_can_request_admin_review_for_existing_account(db_session, monkeypatch):
    user = _user(
        db_session,
        username="existing@example.edu",
        email="existing@example.edu",
        password="unused-password",
    )
    token = auth._create_sso_registration_token(
        {
            "sub": "provider-subject-123",
            "email": user.email,
            "name": "Existing User",
        }
    )

    class AllowLimiter:
        def allow(self, *_args, **_kwargs):
            return True, 0

    monkeypatch.setattr(auth, "_validate_email_address", lambda value: value.strip().lower())
    monkeypatch.setattr(auth, "_register_request_limiter", AllowLimiter())
    monkeypatch.setattr(auth, "_notify_registration_request_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth, "log_event", lambda *_args, **_kwargs: None)

    result = auth_registration.submit_registration_request(
        {
            "name": "Existing User",
            "email": user.email,
            "source": "sso",
            "sso_registration_token": token,
        },
        db=db_session,
        request=None,
    )

    request = db_session.query(models.AccountRegistrationRequest).one()
    assert result == {"ok": True}
    assert request.status == "pending"
    assert request.sso_subject == "provider-subject-123"
    assert db_session.get(models.User, user.id).sso_subject is None
