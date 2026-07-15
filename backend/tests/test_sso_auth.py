from types import SimpleNamespace

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from app import auth, models
from app.main import app
from app.database import SessionLocal


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def strong_test_signing_key(monkeypatch):
    key = "test-secret-key-that-is-at-least-thirty-two-bytes-long-12345"
    monkeypatch.setattr(auth, "SECRET_KEY", key)
    monkeypatch.setattr(auth, "SIGNING_KEY", key)
    monkeypatch.setattr(auth, "SIGNING_ALGORITHM", "HS256")
    monkeypatch.setattr(auth, "USE_RS256", False)
    monkeypatch.setattr(auth, "JWT_ALLOW_HS_FALLBACK", True)


def test_auth_config_reports_sso_flag_and_configuration(client, monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example.edu/oauth2/default")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sso_enabled"] is True
    assert payload["sso_configured"] is True
    assert payload["sso_login_url"] == "/api/auth/oidc/login"
    assert payload["sso_logout_url"] == "/api/auth/oidc/logout"
    assert payload["local_password_admin_only"] is True


def test_auth_config_accepts_generic_oidc_env_names(client, monkeypatch):
    monkeypatch.delenv("OIDC_ENABLED", raising=False)
    monkeypatch.setattr(auth, "load_integration_settings", lambda: {"sso_provider": "oidc"})
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example.edu/oauth2/default")
    monkeypatch.setenv("OIDC_CLIENT_ID", "client-id")
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "client-secret")

    response = client.get("/api/auth/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sso_enabled"] is True
    assert payload["sso_configured"] is True
    assert payload["local_password_admin_only"] is True


def test_local_password_login_allowed_only_for_seed_admin_when_sso_enabled(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    monkeypatch.setattr(auth, "SEED_ADMIN_USERNAME", "admin")

    admin_user = SimpleNamespace(username="admin", local_auth_only=False)
    analyst_user = SimpleNamespace(username="analyst@example.com", local_auth_only=False)
    local_only_user = SimpleNamespace(username="service.account", local_auth_only=True)

    assert auth._local_password_login_allowed(admin_user) is True
    assert auth._local_password_login_allowed(analyst_user) is False
    assert auth._local_password_login_allowed(local_only_user) is True
    assert auth._local_password_login_allowed(None) is False


def test_safe_next_path_rejects_external_and_api_targets():
    assert auth._safe_next_path("/cases") == "/cases"
    assert auth._safe_next_path("https://evil.example") == "/"
    assert auth._safe_next_path("//evil.example") == "/"
    assert auth._safe_next_path("/api/auth/token") == "/"


def test_serialize_user_reports_sso_auth_provider(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    monkeypatch.setattr(auth, "SEED_ADMIN_USERNAME", "admin")

    user = models.User(
        username="analyst@example.com",
        email="analyst@example.com",
        role="analyst",
        is_admin=False,
    )

    payload = auth._serialize_user(user)

    assert payload["auth_provider"] == "sso"
    assert payload["local_password_login_allowed"] is False



def test_serialize_user_keeps_local_auth_for_seed_admin(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    monkeypatch.setattr(auth, "SEED_ADMIN_USERNAME", "admin")

    user = models.User(
        username="admin",
        email="admin@example.com",
        role="sys_admin",
        is_admin=True,
    )

    payload = auth._serialize_user(user)

    assert payload["auth_provider"] == "local"
    assert payload["local_password_login_allowed"] is True



def test_serialize_user_keeps_local_auth_for_local_only_account(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    monkeypatch.setattr(auth, "SEED_ADMIN_USERNAME", "admin")

    user = models.User(
        username="service.account",
        email="service.account@example.com",
        role="analyst",
        is_admin=False,
        local_auth_only=True,
    )

    payload = auth._serialize_user(user)

    assert payload["auth_provider"] == "local"
    assert payload["local_password_login_allowed"] is True
    assert payload["local_auth_only"] is True



def test_sso_unregistered_response_prefills_registration(monkeypatch):
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "1")
    request = SimpleNamespace(base_url="http://testserver/")

    response = auth._sso_unregistered_response(
        request,
        {"name": "Taylor Analyst", "email": "taylor@example.edu"},
    )

    location = response.headers["location"]
    assert "sso_unregistered=1" in location
    assert "register=1" in location
    assert "Taylor+Analyst" in location
    assert "taylor%40example.edu" in location


def test_start_sso_login_redirects_when_oidc_discovery_fails(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    monkeypatch.setattr(auth, "_build_oidc_authorize_url", lambda *_args, **_kwargs: (_ for _ in ()).throw(fastapi.HTTPException(status_code=503, detail="Single sign-on issuer configuration is invalid")))

    response = auth.start_sso_login(request=SimpleNamespace(base_url="http://testserver/"), next="/")

    assert response.status_code == 303
    assert "login?error=Single+sign-on+issuer+configuration+is+invalid" in response.headers["location"]



def _clear_registration_state(db):
    db.query(models.AccountRegistrationRequest).delete()
    db.query(models.User).delete()
    db.commit()


def test_sso_registration_request_stores_verified_subject(monkeypatch):
    monkeypatch.setattr(auth, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, "_notify_registration_request_admins", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(auth, "_validate_email_address", lambda value: value.strip().lower())

    db = SessionLocal()
    try:
        _clear_registration_state(db)
        token = auth._create_sso_registration_token(
            {"sub": "sso-subject-1", "email": "taylor@example.edu", "name": "Taylor Analyst"}
        )

        response = auth.submit_registration_request(
            {
                "name": "Taylor Analyst",
                "email": "taylor@example.edu",
                "source": "sso",
                "sso_registration_token": token,
            },
            db=db,
            request=None,
        )

        row = db.query(models.AccountRegistrationRequest).filter(models.AccountRegistrationRequest.email == "taylor@example.edu").first()
        assert response == {"ok": True}
        assert row is not None
        assert row.sso_subject == "sso-subject-1"
    finally:
        _clear_registration_state(db)
        db.close()


def test_sso_approval_creates_user_and_sends_ready_email(monkeypatch):
    monkeypatch.setenv("OIDC_ENABLED", "1")
    sent = []
    monkeypatch.setattr(auth, "send_email", lambda **kwargs: sent.append(kwargs))
    monkeypatch.setattr(auth, "log_event", lambda *args, **kwargs: None)

    db = SessionLocal()
    try:
        _clear_registration_state(db)
        admin = models.User(
            username="admin",
            email="admin@example.com",
            password_hash="seed",
            role="sys_admin",
            is_admin=True,
        )
        row = models.AccountRegistrationRequest(
            name="Taylor Analyst",
            email="taylor@example.edu",
            status="pending",
            sso_subject="sso-subject-1",
        )
        db.add_all([admin, row])
        db.commit()

        response = auth.approve_registration_request(
            row.id,
            {"role": "requestor", "requestor_group": "Legal"},
            db=db,
            user=admin,
            request=None,
        )

        db.refresh(row)
        created = db.query(models.User).filter(models.User.email == "taylor@example.edu").first()

        assert response == {"ok": True}
        assert created is not None
        assert created.role == "requestor"
        assert created.requestor_group == "legal"
        assert created.sso_subject == "sso-subject-1"
        assert row.status == "completed"
        assert row.invite_token_hash is None
        assert row.invite_token_expires_at is None
        assert row.completed_at is not None
        assert sent
        assert sent[-1]["subject"] == "[DiscoveryOne] Your account is ready"
        assert "Single sign-on credentials" in sent[-1]["body"]
    finally:
        _clear_registration_state(db)
        db.close()


def test_local_approval_keeps_invite_flow(monkeypatch):
    monkeypatch.delenv("OIDC_ENABLED", raising=False)
    sent = []
    monkeypatch.setattr(auth, "send_email", lambda **kwargs: sent.append(kwargs))
    monkeypatch.setattr(auth, "log_event", lambda *args, **kwargs: None)

    db = SessionLocal()
    try:
        _clear_registration_state(db)
        admin = models.User(
            username="admin",
            email="admin@example.com",
            password_hash="seed",
            role="sys_admin",
            is_admin=True,
        )
        row = models.AccountRegistrationRequest(
            name="Taylor Analyst",
            email="taylor@example.edu",
            status="pending",
        )
        db.add_all([admin, row])
        db.commit()

        response = auth.approve_registration_request(
            row.id,
            {"role": "requestor", "requestor_group": "Legal"},
            db=db,
            user=admin,
            request=None,
        )

        db.refresh(row)
        created = db.query(models.User).filter(models.User.email == "taylor@example.edu").first()

        assert response == {"ok": True}
        assert created is None
        assert row.status == "approved"
        assert row.invite_token_hash
        assert row.invite_token_expires_at is not None
        assert row.invite_totp_secret is None
        assert sent
        assert sent[-1]["subject"] == "[DiscoveryOne] Complete your account registration"
    finally:
        _clear_registration_state(db)
        db.close()


def test_sso_user_lookup_prefers_persisted_subject():
    db = SessionLocal()
    try:
        _clear_registration_state(db)
        user = models.User(
            username="analyst@example.edu",
            email="old@example.edu",
            password_hash="seed",
            role="analyst",
            is_admin=False,
            sso_subject="subject-123",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        matched = auth._sso_user_from_claims({"sub": "subject-123", "email": "new@example.edu"}, db)

        assert matched is not None
        assert matched.id == user.id
    finally:
        _clear_registration_state(db)
        db.close()
