import copy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import auth, case_requests, emailer, integration_settings, models, permissions, schemas, smtp_mail_provider, system_admin, users


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


def _create_user(db_session, **overrides):
    role = overrides.pop("role", "requestor")
    email = overrides.pop("email", None)
    username = overrides.pop("username", email or f"{role}@example.com")
    user = models.User(
        username=username,
        email=email,
        first_name=overrides.pop("first_name", "Test"),
        last_name=overrides.pop("last_name", "User"),
        password_hash=overrides.pop("password_hash", "hashed"),
        is_admin=overrides.pop("is_admin", role == "sys_admin"),
        role=role,
        requestor_group=overrides.pop("requestor_group", None),
        employee_id=overrides.pop("employee_id", None),
        **overrides,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_non_admin_self_edit_rejects_sensitive_identity_fields(db_session):
    actor = _create_user(
        db_session,
        role="requestor",
        email="requestor@example.com",
        requestor_group="legal",
    )

    with pytest.raises(HTTPException) as email_exc:
        users.update_user(actor.id, schemas.UserUpdate(email="new@example.com"), db=db_session, actor=actor)
    assert email_exc.value.status_code == 403
    assert "email" in email_exc.value.detail

    with pytest.raises(HTTPException) as group_exc:
        users.update_user(actor.id, schemas.UserUpdate(requestor_group="finance"), db=db_session, actor=actor)
    assert group_exc.value.status_code == 403
    assert "requestor_group" in group_exc.value.detail

    with pytest.raises(HTTPException) as active_exc:
        users.update_user(actor.id, schemas.UserUpdate(is_active=False), db=db_session, actor=actor)
    assert active_exc.value.status_code == 403
    assert "is_active" in active_exc.value.detail


def test_non_admin_self_edit_allows_profile_fields_but_not_password(db_session):
    actor = _create_user(
        db_session,
        role="analyst",
        email="analyst@example.com",
        employee_id="E-111111",
    )
    original_hash = actor.password_hash

    updated = users.update_user(
        actor.id,
        schemas.UserUpdate(
            first_name="Updated",
            last_name="Analyst",
            employee_id="E-222222",
        ),
        db=db_session,
        actor=actor,
    )

    assert updated.first_name == "Updated"
    assert updated.last_name == "Analyst"
    assert updated.employee_id == "E-222222"
    assert updated.email == "analyst@example.com"
    assert updated.password_hash == original_hash

    with pytest.raises(HTTPException) as exc:
        users.update_user(
            actor.id,
            schemas.UserUpdate(password="NewPassword123"),
            db=db_session,
            actor=actor,
        )

    assert exc.value.status_code == 403
    assert "Self-service password changes are disabled" in exc.value.detail


def test_sys_admin_can_reset_other_local_account_password(db_session, monkeypatch):
    monkeypatch.setattr(users, "notify_user_password_change", lambda *_args, **_kwargs: None)
    admin = _create_user(
        db_session,
        role="sys_admin",
        email="admin@example.com",
        is_admin=True,
    )
    target = _create_user(
        db_session,
        role="tester",
        email="local.test@example.edu",
    )
    original_hash = target.password_hash

    users.reset_password(
        target.id,
        schemas.PasswordReset(password="NewPassword123"),
        db=db_session,
        actor=admin,
    )

    db_session.refresh(target)
    assert target.password_hash != original_hash


def test_self_password_reset_endpoint_is_disabled(db_session):
    actor = _create_user(
        db_session,
        role="sys_admin",
        email="admin@example.com",
        is_admin=True,
    )

    with pytest.raises(HTTPException) as exc:
        users.reset_password(
            actor.id,
            schemas.PasswordReset(password="NewPassword123"),
            db=db_session,
            actor=actor,
        )

    assert exc.value.status_code == 403
    assert "Self-service password changes are disabled" in exc.value.detail


def test_public_self_service_password_reset_endpoints_are_disabled():
    with pytest.raises(HTTPException) as forgot_exc:
        auth.forgot_password({"identifier": "admin", "method": "reset_link"}, db=None, request=None)
    assert forgot_exc.value.status_code == 404
    assert "Self-service password reset is disabled" in forgot_exc.value.detail

    with pytest.raises(HTTPException) as reset_exc:
        auth.complete_password_reset({"token": "unused", "new_password": "NewPassword123"}, db=None, request=None)
    assert reset_exc.value.status_code == 404
    assert "Self-service password reset is disabled" in reset_exc.value.detail


def test_sys_admin_cannot_disable_own_account(db_session):
    actor = _create_user(
        db_session,
        role="sys_admin",
        email="admin@example.com",
        is_admin=True,
    )

    with pytest.raises(HTTPException) as exc:
        users.update_user(actor.id, schemas.UserUpdate(is_active=False), db=db_session, actor=actor)

    assert exc.value.status_code == 400
    assert exc.value.detail == "You cannot disable your own account"


def test_ensure_not_requestor_blocks_tester_accounts():
    with pytest.raises(HTTPException) as exc:
        permissions.ensure_not_requestor(SimpleNamespace(id=11, role="tester", is_admin=False))

    assert exc.value.status_code == 403
    assert "read-only" in exc.value.detail.lower()


@pytest.mark.parametrize("role", ["tester", "tech"])
def test_case_request_endpoints_reject_non_request_access_roles(role):
    actor = SimpleNamespace(id=7, role=role, is_admin=False)

    with pytest.raises(HTTPException) as stats_exc:
        case_requests.request_stats(db=None, actor=actor)
    assert stats_exc.value.status_code == 403

    with pytest.raises(HTTPException) as mine_exc:
        case_requests.list_mine(db=None, actor=actor)
    assert mine_exc.value.status_code == 403


@pytest.mark.parametrize("role", ["tester", "tech"])
def test_case_request_review_endpoints_require_reviewer_role(role):
    actor = SimpleNamespace(id=9, role=role, is_admin=False)

    with pytest.raises(HTTPException) as list_exc:
        case_requests.list_requests(db=None, actor=actor)
    assert list_exc.value.status_code == 403

    with pytest.raises(HTTPException) as approve_exc:
        case_requests.approve_case_request(1, db=None, actor=actor)
    assert approve_exc.value.status_code == 403

    with pytest.raises(HTTPException) as progress_exc:
        case_requests.get_case_request_progress(1, db=None, actor=actor)
    assert progress_exc.value.status_code == 403

    with pytest.raises(HTTPException) as decline_exc:
        case_requests.decline_case_request(1, payload={"reason": "nope"}, db=None, actor=actor)
    assert decline_exc.value.status_code == 403



def test_sys_update_smtp_stores_auth_settings_securely(monkeypatch):
    saved = {}
    existing = {
        "smtp": {
            "host": "old.smtp.local",
            "port": 25,
            "from_address": "old@example.com",
            "username": "old-user",
            "password": "existing-secret",
            "use_tls": True,
            "use_ssl": True,
        }
    }
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: copy.deepcopy(existing))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda settings: saved.setdefault("settings", copy.deepcopy(settings)))
    monkeypatch.setattr(system_admin, "log_event", lambda *_args, **_kwargs: None)

    actor = SimpleNamespace(id=1, role="sys_admin", is_admin=True)
    payload = system_admin.SMTPConfigPayload(
        host="smtp.example.com",
        port=587,
        from_address="alerts@example.com",
        username="smtp-user",
        password="new-secret",
        use_tls=True,
        use_ssl=False,
    )

    result = system_admin.sys_update_smtp(payload, actor=actor, db=None)

    smtp = saved["settings"]["smtp"]
    assert smtp["host"] == "smtp.example.com"
    assert smtp["port"] == 587
    assert smtp["from_address"] == "alerts@example.com"
    assert smtp["username"] == "smtp-user"
    assert smtp["password"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(smtp["password"]) == "new-secret"
    assert smtp["use_tls"] is True
    assert smtp["use_ssl"] is False
    assert result["smtp"] == {
        "host": "smtp.example.com",
        "port": 587,
        "username": "smtp-user",
        "from_address": "alerts@example.com",
        "use_tls": True,
        "use_ssl": False,
        "timeout_seconds": 15.0,
        "password": integration_settings.MASKED_SECRET_VALUE,
    }



def test_load_smtp_settings_prefers_saved_auth_and_tls_over_env_fallbacks(monkeypatch):
    monkeypatch.setattr(
        smtp_mail_provider,
        "load_system_settings",
        lambda: {
            "smtp": {
                "host": "smtp.example.com",
                "port": 2525,
                "from_address": "alerts@example.com",
                "username": "legacy-user",
                "password": "legacy-pass",
                "use_tls": True,
                "use_ssl": True,
            }
        },
    )
    monkeypatch.setenv("SMTP_USERNAME", "env-user")
    monkeypatch.setenv("SMTP_PASSWORD", "env-pass")
    monkeypatch.setenv("SMTP_USE_TLS", "1")
    monkeypatch.setenv("SMTP_USE_SSL", "1")

    settings = emailer.load_smtp_settings()

    assert settings.host == "smtp.example.com"
    assert settings.port == 2525
    assert settings.sender == "alerts@example.com"
    assert settings.username == "legacy-user"
    assert settings.password == "legacy-pass"
    assert settings.use_tls is False
    assert settings.use_ssl is True


def test_load_smtp_settings_uses_env_fallbacks_when_saved_values_are_empty(monkeypatch):
    monkeypatch.setattr(
        smtp_mail_provider,
        "load_system_settings",
        lambda: {
            "smtp": {
                "host": "",
                "port": "",
                "from_address": "",
                "username": "",
                "password": None,
                "use_tls": None,
                "use_ssl": None,
            }
        },
    )
    monkeypatch.setenv("SMTP_HOST", "smtp.env.example.com")
    monkeypatch.setenv("SMTP_PORT", "2526")
    monkeypatch.setenv("SMTP_FROM_ADDRESS", "env-alerts@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "env-user")
    monkeypatch.setenv("SMTP_PASSWORD", "env-pass")
    monkeypatch.setenv("SMTP_USE_TLS", "1")
    monkeypatch.setenv("SMTP_USE_SSL", "0")

    settings = emailer.load_smtp_settings()

    assert settings.host == "smtp.env.example.com"
    assert settings.port == 2526
    assert settings.sender == "env-alerts@example.com"
    assert settings.username == "env-user"
    assert settings.password == "env-pass"
    assert settings.use_tls is True
    assert settings.use_ssl is False
