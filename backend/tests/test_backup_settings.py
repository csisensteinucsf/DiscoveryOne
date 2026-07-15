from app import backups, models, system_admin_config, system_backups


def test_public_backup_settings_config_clamps_values():
    public = system_admin_config.public_backup_settings_config(
        {
            "automatic_enabled": False,
            "interval_hours": "0.25",
            "retention_hours": "99999",
        }
    )

    assert public == {
        "automatic_enabled": False,
        "interval_hours": 1.0,
        "retention_hours": 8760.0,
    }


def test_system_backup_settings_update_saves_normalized_values(monkeypatch):
    store = {"backups": {"automatic_enabled": True, "interval_hours": 6, "retention_hours": 48}}
    monkeypatch.setattr(system_backups, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_backups, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_backups, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_backups.sys_update_backup_settings(
        payload=system_admin_config.BackupSettingsPayload(
            automatic_enabled=False,
            interval_hours=12,
            retention_hours=0.5,
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["backup_settings"] == {
        "automatic_enabled": False,
        "interval_hours": 12.0,
        "retention_hours": 1.0,
    }
    assert store["backups"] == result["backup_settings"]


def test_backup_runtime_helpers_use_app_managed_settings(monkeypatch):
    monkeypatch.setenv("BACKUP_INTERVAL_HOURS", "999")
    monkeypatch.setenv("BACKUP_RETENTION_HOURS", "999")
    monkeypatch.setattr(
        backups,
        "load_system_settings",
        lambda: {
            "backups": {
                "automatic_enabled": False,
                "interval_hours": 3,
                "retention_hours": 72,
            }
        },
    )

    assert backups.backup_automatic_enabled() is False
    assert backups.backup_interval_hours() == 3.0
    assert backups.backup_retention_hours() == 72.0
