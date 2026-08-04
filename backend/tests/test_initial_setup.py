import json
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import integration_settings, models, setup


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


@pytest.fixture()
def settings_store(monkeypatch):
    monkeypatch.setenv("SETUP_BOOTSTRAP_SECRET", "test-bootstrap-secret-1234567890")
    store = {
        "initial_setup_completed": False,
        "initial_setup_completed_at": None,
        "initial_setup_version": 1,
        "institution": {},
        "enabled_integrations": {},
        "integrations": {},
        "logos": [],
        "active_logo": None,
    }

    def load():
        return dict(store)

    def save(data):
        store.clear()
        store.update(data)

    monkeypatch.setattr(setup, "load_system_settings", load)
    monkeypatch.setattr(setup, "save_system_settings", save)
    monkeypatch.setattr(setup, "log_event", lambda *args, **kwargs: None)
    return store


def test_setup_status_is_required_without_sys_admin(db_session, settings_store):
    status = setup.setup_status(db=db_session)

    assert status["required"] is True
    assert status["completed"] is False
    assert status["has_sys_admin"] is False


def test_setup_router_can_be_registered():
    app = FastAPI()
    app.include_router(setup.router)

    paths = {route.path for route in setup.router.routes if hasattr(route, "path")}
    assert "/api/setup/status" in paths
    assert "/api/setup/complete" in paths


def test_setup_complete_creates_admin_and_persists_settings(db_session, settings_store):
    payload = {
        "org_name": "Example University",
        "org_short_name": "Example",
        "app_base_url": "https://discovery.example.edu",
        "allowed_hosts": ["discovery.example.edu"],
        "allowed_requestor_email_domains": ["example.edu"],
        "requestor_email_exceptions": ["outside.counsel@example.com"],
        "sso_display_name": "Example SSO",
        "support_email": "support@example.edu",
        "admin_username": "admin",
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "enabled_integrations": {"smtp": True, "person_lookup": True},
        "integrations": {"person_lookup_provider": "csv", "sso_provider": "local"},
        "smtp": {
            "host": "smtp.example.edu",
            "port": 587,
            "from_address": "ediscovery@example.edu",
            "use_tls": True,
        },
        "integration_configs": {
            "oidc": {"issuer": "https://idp.example.edu", "client_secret": "oidc-secret"},
            "person_lookup": {"csv_path": "/data/people.csv"},
            "servicenow": {"base_url": "https://snow.example.edu", "password": "snow-secret"},
        },
        "preservation_sources": [
            {"key": "email", "label": "Email (O365/Google)", "enabled": True, "built_in": True},
            {"key": "onedrive", "label": "OneDrive", "enabled": True, "built_in": True},
            {"key": "gdrive", "label": "Google Drive", "enabled": True, "built_in": True},
            {"key": "box", "label": "Box", "enabled": True, "built_in": True},
            {"key": "dropbox", "label": "Dropbox", "enabled": True, "built_in": True},
            {"key": "slack", "label": "Slack", "enabled": True, "built_in": True},
            {"key": "zoom", "label": "Zoom", "enabled": True, "built_in": True},
        ],
    }

    result = setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    admin = db_session.query(models.User).filter(models.User.username == "admin").one()
    assert result["ok"] is True
    assert result["setup"]["completed"] is True
    assert admin.role == "sys_admin"
    assert admin.email is None
    assert admin.first_name == "System"
    assert admin.last_name == "Administrator"
    assert admin.is_admin is True
    assert admin.local_auth_only is True
    assert settings_store["initial_setup_completed"] is True
    assert settings_store["deployment"]["app_base_url"] == "https://discovery.example.edu"
    assert settings_store["deployment"]["allowed_hosts"] == ["discovery.example.edu"]
    assert settings_store["deployment"]["tls"]["mode"] == "self_signed"
    assert settings_store["institution"]["org_name"] == "Example University"
    assert set(settings_store["institution"]) == {"org_name", "org_short_name", "allowed_requestor_email_domains", "requestor_email_exceptions", "sso_display_name", "support_email"}
    assert settings_store["institution"]["allowed_requestor_email_domains"] == ["example.edu"]
    assert settings_store["institution"]["requestor_email_exceptions"] == ["outside.counsel@example.com"]
    assert settings_store["enabled_integrations"]["smtp"] is True
    assert settings_store["smtp"]["host"] == "smtp.example.edu"
    assert settings_store["integrations"]["person_lookup_provider"] == "csv"
    assert settings_store["integration_configs"]["oidc"]["issuer"] == "https://idp.example.edu"
    assert settings_store["integration_configs"]["oidc"]["client_secret"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(settings_store["integration_configs"]["oidc"]["client_secret"]) == "oidc-secret"
    assert settings_store["integration_configs"]["servicenow"]["password"].startswith("enc:v1:")
    assert {"key": "gdrive", "label": "Google Drive", "enabled": True, "built_in": True} in settings_store["preservation_sources"]
    assert {"key": "dropbox", "label": "Dropbox", "enabled": True, "built_in": True} in settings_store["preservation_sources"]
    assert {"key": "zoom", "label": "Zoom", "enabled": True, "built_in": True} in settings_store["preservation_sources"]
    assert not any(item["key"] == "rubrik" for item in settings_store["preservation_sources"])


def test_setup_complete_keeps_smtp_disabled_when_default_provider_is_stale(db_session, settings_store):
    payload = {
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "enabled_integrations": {"smtp": False},
        "integrations": {"mail_provider": "smtp"},
        "smtp": {
            "port": 587,
            "use_tls": True,
            "use_ssl": False,
            "timeout_seconds": 15,
        },
    }

    setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    assert settings_store["enabled_integrations"]["smtp"] is False
    assert settings_store["integrations"]["mail_provider"] == "none"

def test_setup_complete_is_rejected_after_sys_admin_exists(db_session, settings_store):
    admin = models.User(
        username="existing-admin",
        password_hash="hashed",
        role="sys_admin",
        is_admin=True,
    )
    db_session.add(admin)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        setup.complete_setup(
            payload=json.dumps({"bootstrap_secret": "test-bootstrap-secret-1234567890", "admin_username": "admin", "admin_password": "ChangeMeNow!123"}),
            logo=None,
            request=None,
            db=db_session,
        )

    assert exc.value.status_code == 409


def test_setup_complete_accepts_servicenow_oauth_credentials(db_session, settings_store):
    payload = {
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "enabled_integrations": {"servicenow": True},
        "integrations": {"ticket_provider": "servicenow"},
        "integration_configs": {
            "servicenow": {
                "base_url": "https://snow.example.edu",
                "auth_type": "oauth",
                "oauth_client_id": "snow-client",
                "oauth_client_secret": "snow-secret",
                "oauth_token_url": "https://snow.example.edu/oauth_token.do",
            },
        },
    }

    setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    servicenow_config = settings_store["integration_configs"]["servicenow"]
    assert servicenow_config["auth_type"] == "oauth"
    assert servicenow_config["oauth_client_id"] == "snow-client"
    assert servicenow_config["oauth_client_secret"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(servicenow_config["oauth_client_secret"]) == "snow-secret"


def test_setup_complete_encrypts_docusign_connect_keys(db_session, settings_store):
    payload = {
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "enabled_integrations": {"docusign": True},
        "integrations": {"esign_provider": "docusign"},
        "integration_configs": {
            "docusign": {
                "base_url": "https://demo.docusign.net/restapi",
                "account_id": "acct",
                "template_id": "template",
                "integration_key": "integration",
                "user_id": "user",
                "private_key": "private",
                "connect_key": "connect-secret",
                "resend_allow_recipient_correction_fallback": True,
            }
        },
    }

    setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    docusign_config = settings_store["integration_configs"]["docusign"]
    assert docusign_config["connect_key"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(docusign_config["connect_key"]) == "connect-secret"
    assert docusign_config["resend_allow_recipient_correction_fallback"] is True


def test_setup_complete_persists_ai_enabled_flag_and_config(db_session, settings_store):
    payload = {
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "enabled_integrations": {"ai": True},
        "integration_configs": {
            "ai": {
                "url": "https://ai.example.test/v1/chat/completions",
                "model": "legal-model",
                "api_key": "ai-secret",
            }
        },
    }

    setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    assert settings_store["enabled_integrations"]["ai"] is True
    assert settings_store["integration_configs"]["ai"]["url"] == "https://ai.example.test/v1/chat/completions"
    assert settings_store["integration_configs"]["ai"]["model"] == "legal-model"
    assert settings_store["integration_configs"]["ai"]["api_key"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(settings_store["integration_configs"]["ai"]["api_key"]) == "ai-secret"


def test_integration_config_merge_preserves_masked_secret():
    existing = {
        "base_url": "https://old.example.edu",
        "password": integration_settings.encrypt_secret("existing-secret"),
    }

    merged = integration_settings.merge_integration_config(
        "servicenow",
        existing,
        {
            "base_url": "https://new.example.edu",
            "password": integration_settings.MASKED_SECRET_VALUE,
            "table": "incident",
        },
    )

    assert merged["base_url"] == "https://new.example.edu"
    assert merged["table"] == "incident"
    assert integration_settings.decrypt_secret(merged["password"]) == "existing-secret"


def test_integration_config_merge_replaces_secret():
    existing = {"password": integration_settings.encrypt_secret("old-secret")}

    merged = integration_settings.merge_integration_config(
        "servicenow",
        existing,
        {"password": "new-secret"},
    )

    assert merged["password"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(merged["password"]) == "new-secret"


def test_setup_complete_normalizes_case_naming_alias(db_session, settings_store):
    payload = {
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "case_naming": {"mode": "date"},
    }

    setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    assert settings_store["case_naming"] == {"mode": "created_date"}


def test_setup_complete_rejects_unsupported_case_naming(db_session, settings_store):
    payload = {
        "bootstrap_secret": "test-bootstrap-secret-1234567890",
        "admin_password": "ChangeMeNow!123",
        "case_naming": {"mode": "campus_specific_sequence"},
    }

    with pytest.raises(HTTPException) as exc:
        setup.complete_setup(payload=json.dumps(payload), logo=None, request=None, db=db_session)

    assert exc.value.status_code == 422
    assert "Unsupported eDiscovery case naming option" in exc.value.detail



def test_setup_complete_rejects_missing_or_invalid_bootstrap_secret(db_session, settings_store):
    for supplied in ("", "attacker-controlled-code"):
        with pytest.raises(HTTPException) as exc:
            setup.complete_setup(
                payload=json.dumps(
                    {
                        "bootstrap_secret": supplied,
                        "admin_password": "ChangeMeNow!123",
                    }
                ),
                logo=None,
                request=None,
                db=db_session,
            )
        assert exc.value.status_code == 403

    assert db_session.query(models.User).count() == 0
    assert settings_store["initial_setup_completed"] is False


def test_setup_lock_uses_postgresql_transaction_advisory_lock():
    calls = []

    class Dialect:
        name = "postgresql"

    class Bind:
        dialect = Dialect()

    class FakeSession:
        def get_bind(self):
            return Bind()

        def execute(self, statement, params):
            calls.append((str(statement), params))

    setup._acquire_setup_transaction_lock(FakeSession())

    assert len(calls) == 1
    assert "pg_advisory_xact_lock" in calls[0][0]
    assert calls[0][1] == {"setup_lock_key": setup.SETUP_LOCK_KEY}


def test_concurrent_setup_completions_create_exactly_one_admin(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'setup-race.db'}",
        connect_args={"check_same_thread": False},
    )
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    store_lock = threading.Lock()
    store = {
        "initial_setup_completed": False,
        "initial_setup_completed_at": None,
        "initial_setup_version": 1,
        "institution": {},
        "enabled_integrations": {},
        "integrations": {},
        "logos": [],
        "active_logo": None,
    }

    def load():
        with store_lock:
            return dict(store)

    def save(data):
        with store_lock:
            store.clear()
            store.update(data)

    monkeypatch.setenv("SETUP_BOOTSTRAP_SECRET", "test-bootstrap-secret-1234567890")
    monkeypatch.setattr(setup, "load_system_settings", load)
    monkeypatch.setattr(setup, "save_system_settings", save)
    monkeypatch.setattr(setup, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(setup, "hash_password", lambda value: "hashed-password")
    payload = json.dumps(
        {
            "bootstrap_secret": "test-bootstrap-secret-1234567890",
            "admin_password": "ChangeMeNow!123",
        }
    )
    barrier = threading.Barrier(2)

    def run_attempt():
        with SessionLocal() as db:
            barrier.wait(timeout=5)
            try:
                setup.complete_setup(
                    payload=payload,
                    logo=None,
                    request=None,
                    db=db,
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(lambda _: run_attempt(), range(2)))
        with SessionLocal() as db:
            assert db.query(models.User).count() == 1
            assert db.query(models.User).one().username == "admin"
    finally:
        engine.dispose()

    assert statuses == [200, 409]


def test_tls_private_key_uses_owner_only_permissions(tmp_path, monkeypatch):
    chmod_calls = []
    monkeypatch.setattr(setup, "TLS_DIR", tmp_path)
    monkeypatch.setattr(setup, "scan_payload", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        Path,
        "chmod",
        lambda self, mode: chmod_calls.append((self.name, mode)),
    )

    class Upload:
        def __init__(self, filename, payload):
            self.filename = filename
            self.content_type = "application/x-pem-file"
            self.file = BytesIO(payload)

    settings = {}
    setup._store_tls_file(
        settings=settings,
        file=Upload("server.key", b"-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----\n"),
        request=None,
        kind="private_key",
    )
    setup._store_tls_file(
        settings=settings,
        file=Upload("server.crt", b"-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----\n"),
        request=None,
        kind="certificate",
    )

    assert any(mode == 0o600 for _name, mode in chmod_calls)
    assert any(mode == 0o644 for _name, mode in chmod_calls)