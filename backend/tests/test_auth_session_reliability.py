from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app import auth, models


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


def _request(path: str, *, method: str = "GET", access_token: str | None = None) -> Request:
    headers = [(b"user-agent", b"pytest-browser")]
    if access_token:
        cookie = f"{auth.SESSION_COOKIE_NAME}={access_token}; csrf=test-csrf"
        headers.append((b"cookie", cookie.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


def _user(db, *, username: str = "analyst@example.edu", password: str = "CorrectPassword123"):
    row = models.User(
        username=username,
        email=username,
        password_hash=auth.hash_password(password),
        role="analyst",
        is_admin=False,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _session(db, user, *, token: str, jti: str, expires_at, last_seen_at=None):
    row = auth.create_session_token(
        db,
        user_id=user.id,
        token=token,
        jti=jti,
        expires_at=expires_at,
        user_agent="pytest-browser",
        ip="127.0.0.1",
    )
    if last_seen_at is not None:
        row.last_seen_at = last_seen_at
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def test_idle_session_is_revoked_and_returns_expired(db_session, monkeypatch):
    user = _user(db_session)
    token, expires_at, jti = auth.create_access_token(user.username, expires_delta=timedelta(minutes=30))
    row = _session(
        db_session,
        user,
        token=token,
        jti=jti,
        expires_at=expires_at,
        last_seen_at=auth._now() - timedelta(minutes=10),
    )
    monkeypatch.setattr(auth, "SESSION_IDLE_TIMEOUT_MINUTES", 5)

    with pytest.raises(HTTPException) as exc_info:
        auth.current_user(_request("/api/cases", access_token=token), db_session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Session expired"
    db_session.refresh(row)
    assert row.revoked_at is not None


def test_logout_accepts_expired_access_token_revokes_session_and_clears_cookies(db_session):
    user = _user(db_session)
    token, expired_at, jti = auth.create_access_token(user.username, expires_delta=timedelta(seconds=-1))
    row = _session(db_session, user, token=token, jti=jti, expires_at=expired_at)
    response = Response()

    result = auth.logout(
        response=response,
        request=_request("/api/auth/logout", method="POST", access_token=token),
        db=db_session,
    )

    assert result == {"ok": True}
    db_session.refresh(row)
    assert row.revoked_at is not None
    set_cookie = "\n".join(
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    )
    for cookie_name in (
        auth.SESSION_COOKIE_NAME,
        auth.REFRESH_COOKIE_NAME,
        auth.OIDC_STATE_COOKIE,
        auth.OIDC_ID_TOKEN_COOKIE,
    ):
        assert f"{cookie_name}=" in set_cookie
        assert "Max-Age=0" in set_cookie


def test_login_succeeds_immediately_after_expired_logout_without_server_state_reset(db_session, monkeypatch):
    user = _user(db_session)
    expired_token, expired_at, jti = auth.create_access_token(user.username, expires_delta=timedelta(seconds=-1))
    _session(db_session, user, token=expired_token, jti=jti, expires_at=expired_at)
    request = _request("/api/auth/logout", method="POST", access_token=expired_token)
    auth.logout(Response(), request, db_session)

    monkeypatch.setattr(auth, "_oidc_enabled", lambda: False)
    monkeypatch.setattr(auth, "_has_valid_trusted_device", lambda *_args: False)
    response = Response()
    result = auth.login(
        SimpleNamespace(username=user.username, password="CorrectPassword123"),
        response=response,
        db=db_session,
        request=_request("/api/auth/token", method="POST"),
    )

    assert result["user"]["username"] == user.username
    assert result["token_type"] == "bearer"
    set_cookie = "\n".join(
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    )
    assert f"{auth.SESSION_COOKIE_NAME}=" in set_cookie
    assert db_session.query(models.SessionToken).filter(models.SessionToken.revoked_at.is_(None)).count() == 1

def test_authenticated_user_payload_includes_session_deadlines(db_session, monkeypatch):
    user = _user(db_session)
    token, expires_at, jti = auth.create_access_token(user.username, expires_delta=timedelta(minutes=30))
    _session(db_session, user, token=token, jti=jti, expires_at=expires_at)
    monkeypatch.setattr(auth, "SESSION_IDLE_TIMEOUT_MINUTES", 17)
    request = _request("/api/auth/me", access_token=token)

    resolved_user = auth.current_user(request, db_session)
    result = auth.me(request=request, user=resolved_user)

    assert result["session_expires_at"] == request.state.session_expires_at.isoformat()
    assert result["session_idle_timeout_minutes"] == 17


def test_login_payload_includes_session_deadlines(db_session, monkeypatch):
    user = _user(db_session)
    monkeypatch.setattr(auth, "_oidc_enabled", lambda: False)
    monkeypatch.setattr(auth, "_has_valid_trusted_device", lambda *_args: False)
    monkeypatch.setattr(auth, "SESSION_IDLE_TIMEOUT_MINUTES", 23)

    result = auth.login(
        SimpleNamespace(username=user.username, password="CorrectPassword123"),
        response=Response(),
        db=db_session,
        request=_request("/api/auth/token", method="POST"),
    )

    assert result["user"]["session_expires_at"]
    assert result["user"]["session_idle_timeout_minutes"] == 23
