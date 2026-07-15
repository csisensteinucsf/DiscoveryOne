from app import account_reviews, models, system_admin, system_admin_config


def test_public_account_review_config_clamps_values():
    public = system_admin_config.public_account_review_config(
        {
            "enabled": False,
            "interval_days": "99999",
            "check_interval_hours": "0.25",
            "last_sent_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert public == {
        "enabled": False,
        "interval_days": 3650,
        "check_interval_hours": 1.0,
        "last_sent_at": "2026-01-01T00:00:00+00:00",
    }


def test_system_account_review_update_preserves_last_sent_and_saves_normalized(monkeypatch):
    store = {
        "account_review": {
            "enabled": True,
            "interval_days": 120,
            "check_interval_hours": 12,
            "last_sent_at": "2026-01-01T00:00:00+00:00",
        }
    }
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_account_review(
        payload=system_admin_config.AccountReviewPayload(
            enabled=False,
            interval_days=45,
            check_interval_hours=0.5,
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["account_review"] == {
        "enabled": False,
        "interval_days": 45,
        "check_interval_hours": 1.0,
        "last_sent_at": "2026-01-01T00:00:00+00:00",
    }
    assert store["account_review"] == result["account_review"]


def test_account_review_runtime_helpers_use_app_managed_settings(monkeypatch):
    monkeypatch.setenv("ACCOUNT_REVIEW_EMAIL_DISABLE", "1")
    monkeypatch.setenv("ACCOUNT_REVIEW_INTERVAL_DAYS", "999")
    monkeypatch.setenv("ACCOUNT_REVIEW_CHECK_INTERVAL_HOURS", "999")
    monkeypatch.setattr(
        account_reviews,
        "load_system_settings",
        lambda: {
            "account_review": {
                "enabled": True,
                "interval_days": 30,
                "check_interval_hours": 2,
                "last_sent_at": None,
            }
        },
    )

    assert account_reviews._review_enabled() is True
    assert account_reviews._review_interval_days() == 30
    assert account_reviews._review_check_interval_seconds() == 7200.0
