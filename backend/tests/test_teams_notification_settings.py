from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import models, notifications, system_admin, system_admin_config
from app.integration_settings import MASKED_SECRET_VALUE, decrypt_secret


def _admin() -> models.User:
    return models.User(id=1, username="admin", role="sys_admin", is_admin=True)


def _store() -> dict:
    return {
        "initial_setup_completed": True,
        "notifications": {
            "teams": {
                "webhook_url": "",
                "events": {},
            },
            "email": {"events": {}},
        },
    }


def _install_store(monkeypatch, store: dict) -> None:
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: store)
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(system_admin_config, "load_system_settings", lambda: store)
    monkeypatch.setattr(notifications, "load_system_settings", lambda: store)


def test_teams_webhook_is_encrypted_masked_and_decrypted_at_runtime(monkeypatch):
    store = _store()
    _install_store(monkeypatch, store)
    raw_url = "https://example.webhook.office.com/incoming/secret"

    result = system_admin.sys_update_notifications(
        payload=system_admin_config.NotificationsPayload(
            teams={"webhook_url": raw_url, "events": {}}
        ),
        actor=_admin(),
        request=None,
        db=None,
    )

    stored = store["notifications"]["teams"]["webhook_url"]
    assert stored.startswith("enc:v1:")
    assert raw_url not in stored
    assert decrypt_secret(stored) == raw_url
    assert result["teams"]["webhook_url"] == MASKED_SECRET_VALUE
    assert result["teams"]["webhook_configured"] is True
    assert notifications._teams_config()["webhook_url"] == raw_url


def test_blank_teams_webhook_preserves_existing_secret_and_clear_is_explicit(monkeypatch):
    store = _store()
    _install_store(monkeypatch, store)
    raw_url = "https://example.webhook.office.com/incoming/secret"

    system_admin.sys_update_notifications(
        payload=system_admin_config.NotificationsPayload(
            teams={"webhook_url": raw_url, "events": {}}
        ),
        actor=_admin(),
        request=None,
        db=None,
    )
    stored = store["notifications"]["teams"]["webhook_url"]

    system_admin.sys_update_notifications(
        payload=system_admin_config.NotificationsPayload(
            teams={"webhook_url": "", "events": {}}
        ),
        actor=_admin(),
        request=None,
        db=None,
    )
    assert store["notifications"]["teams"]["webhook_url"] == stored

    result = system_admin.sys_update_notifications(
        payload=system_admin_config.NotificationsPayload(
            teams={"webhook_url": "", "clear_webhook": True, "events": {}}
        ),
        actor=_admin(),
        request=None,
        db=None,
    )
    assert store["notifications"]["teams"]["webhook_url"] == ""
    assert result["teams"]["webhook_url"] == ""
    assert result["teams"]["webhook_configured"] is False


def test_teams_webhook_rejects_non_https_urls(monkeypatch):
    store = _store()
    _install_store(monkeypatch, store)

    with pytest.raises(HTTPException) as exc_info:
        system_admin.sys_update_notifications(
            payload=system_admin_config.NotificationsPayload(
                teams={"webhook_url": "http://example.test/webhook", "events": {}}
            ),
            actor=_admin(),
            request=None,
            db=None,
        )

    assert exc_info.value.status_code == 422
    assert "HTTPS" in str(exc_info.value.detail)
    assert store["notifications"]["teams"]["webhook_url"] == ""


def test_public_notifications_never_return_raw_webhook(monkeypatch):
    store = _store()
    raw_url = "https://example.webhook.office.com/incoming/secret"
    store["notifications"]["teams"]["webhook_url"] = raw_url
    monkeypatch.setattr(system_admin_config, "load_system_settings", lambda: store)

    public = system_admin_config.public_notifications_config(
        store["notifications"],
        include_webhook=True,
    )

    assert public["teams"]["webhook_url"] == MASKED_SECRET_VALUE
    assert raw_url not in str(public)
