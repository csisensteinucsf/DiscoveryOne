from app import consent_notifications, models, system_admin, system_admin_config


def test_public_consent_notification_config_clamps_values():
    public = system_admin_config.public_consent_notification_config(
        {
            "completed_email_enabled": False,
            "weekly_pending_enabled": False,
            "weekly_weekday": "99",
            "weekly_hour": "-1",
            "weekly_minute": "999",
            "weekly_timezone": "America/Los_Angeles",
        }
    )

    assert public == {
        "completed_email_enabled": False,
        "weekly_pending_enabled": False,
        "weekly_weekday": 6,
        "weekly_hour": 0,
        "weekly_minute": 59,
        "weekly_timezone": "America/Los_Angeles",
    }


def test_system_notifications_update_saves_consent_notification_settings(monkeypatch):
    store = {
        "notifications": {
            "teams": {"events": {}},
            "email": {"events": {}},
            "search_delivery_reminders": {"enabled": True, "interval_days": 7, "loop_seconds": 3600, "batch_size": 25},
            "consent_notifications": {
                "completed_email_enabled": True,
                "weekly_pending_enabled": True,
                "weekly_weekday": 4,
                "weekly_hour": 8,
                "weekly_minute": 0,
                "weekly_timezone": "UTC",
            },
        }
    }
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_notifications(
        payload=system_admin_config.NotificationsPayload(
            consent_notifications={
                "completed_email_enabled": False,
                "weekly_pending_enabled": True,
                "weekly_weekday": 2,
                "weekly_hour": 16,
                "weekly_minute": 30,
                "weekly_timezone": "America/Los_Angeles",
            }
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["consent_notifications"] == {
        "completed_email_enabled": False,
        "weekly_pending_enabled": True,
        "weekly_weekday": 2,
        "weekly_hour": 16,
        "weekly_minute": 30,
        "weekly_timezone": "America/Los_Angeles",
    }
    assert store["notifications"]["consent_notifications"] == result["consent_notifications"]


def test_consent_notification_runtime_helpers_use_app_managed_settings(monkeypatch):
    monkeypatch.setenv("CONSENT_COMPLETED_EMAIL_DISABLE", "1")
    monkeypatch.setenv("CONSENT_WEEKLY_EMAIL_DISABLE", "1")
    monkeypatch.setenv("CONSENT_WEEKLY_EMAIL_WEEKDAY", "0")
    monkeypatch.setenv("CONSENT_WEEKLY_EMAIL_HOUR", "1")
    monkeypatch.setenv("CONSENT_WEEKLY_EMAIL_MINUTE", "2")
    monkeypatch.setenv("CONSENT_WEEKLY_EMAIL_TIMEZONE", "UTC")
    monkeypatch.setattr(
        consent_notifications,
        "load_system_settings",
        lambda: {
            "notifications": {
                "consent_notifications": {
                    "completed_email_enabled": True,
                    "weekly_pending_enabled": True,
                    "weekly_weekday": 3,
                    "weekly_hour": 14,
                    "weekly_minute": 45,
                    "weekly_timezone": "America/New_York",
                }
            }
        },
    )

    assert consent_notifications.consent_completed_email_enabled() is True
    assert consent_notifications.consent_weekly_pending_enabled() is True
    assert consent_notifications.consent_weekly_schedule() == {
        "weekday": 3,
        "hour": 14,
        "minute": 45,
        "timezone": "America/New_York",
    }
