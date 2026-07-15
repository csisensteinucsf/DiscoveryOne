from app import models, search_delivery_reminders, system_admin, system_admin_config


def test_public_notifications_include_search_delivery_reminder_defaults():
    public = system_admin_config.public_notifications_config({}, include_webhook=True)

    assert public["search_delivery_reminders"] == {
        "enabled": True,
        "interval_days": 7,
        "loop_seconds": 3600,
        "batch_size": 25,
    }


def test_search_delivery_reminder_settings_are_clamped_from_system_settings(monkeypatch):
    monkeypatch.setattr(
        search_delivery_reminders,
        "load_system_settings",
        lambda: {
            "notifications": {
                "search_delivery_reminders": {
                    "enabled": False,
                    "interval_days": "999",
                    "loop_seconds": "1",
                    "batch_size": "10000",
                }
            }
        },
    )

    settings = search_delivery_reminders.load_search_delivery_reminder_settings()

    assert settings["enabled"] is False
    assert settings["interval_days"] == 365
    assert settings["loop_seconds"] == 300
    assert settings["batch_size"] == 500


def test_system_notifications_save_search_delivery_reminder_settings(monkeypatch):
    store = {
        "notifications": {
            "teams": {"events": {}},
            "email": {"events": {}},
            "search_delivery_reminders": {
                "enabled": True,
                "interval_days": 7,
                "loop_seconds": 3600,
                "batch_size": 25,
            },
        }
    }

    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)

    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)
    payload = system_admin_config.NotificationsPayload(
        search_delivery_reminders={
            "enabled": False,
            "interval_days": 14,
            "loop_seconds": 900,
            "batch_size": 50,
        }
    )

    result = system_admin.sys_update_notifications(payload=payload, actor=actor, request=None, db=None)

    assert result["search_delivery_reminders"] == {
        "enabled": False,
        "interval_days": 14,
        "loop_seconds": 900,
        "batch_size": 50,
    }
    assert store["notifications"]["search_delivery_reminders"]["interval_days"] == 14


def test_system_integrations_can_persist_ai_enabled_flag(monkeypatch):
    store = {
        "enabled_integrations": {"ai": False},
        "integrations": {},
        "integration_configs": {},
        "smtp": {},
    }

    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(system_admin, "public_integration_admin_config", lambda: {"enabled": store["enabled_integrations"], "configs": store["integration_configs"]})

    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)
    payload = system_admin_config.SystemIntegrationsPayload(
        enabled_integrations={"ai": True},
        configs={"ai": {"url": "https://ai.example.test/v1/chat/completions", "model": "legal-model"}},
    )

    result = system_admin.sys_update_integrations(payload=payload, actor=actor, request=None, db=None)

    assert result["enabled"]["ai"] is True
    assert store["enabled_integrations"]["ai"] is True
    assert store["integration_configs"]["ai"]["model"] == "legal-model"
