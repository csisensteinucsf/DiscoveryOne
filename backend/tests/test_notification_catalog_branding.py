from app import app_branding, notifications, system_settings


def test_branded_subject_uses_configured_app_name(monkeypatch):
    monkeypatch.delenv("APP_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.setattr(
        system_settings,
        "load_system_settings",
        lambda: {"branding": {"app_name": "LegalHold Pro"}},
    )

    assert app_branding.branded_subject("Test message") == "[LegalHold Pro] Test message"


def test_notification_hold_status_keys_use_configured_preservation_sources(monkeypatch):
    monkeypatch.setattr(
        notifications,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [
            ("email", "holds_email", "Mail"),
            ("gdrive", "holds_gdrive", "Google Drive"),
        ],
    )

    assert notifications._configured_hold_status_keys() == [("email", "Mail"), ("gdrive", "Google Drive")]


def test_notification_hold_status_fallback_excludes_rubrik(monkeypatch):
    monkeypatch.setattr(notifications, "configured_builtin_hold_fields", lambda enabled_only=True: [])

    keys = notifications._configured_hold_status_keys()

    assert ("rubrik_restore", "Rubrik restore") not in keys
    assert ("email", "Email") in keys
    assert ("gdrive", "Google Drive") in keys


def test_app_display_name_supports_module_specific_legacy_env_fallback(monkeypatch):
    monkeypatch.setenv("ACK_BRAND_NAME", "Notice Portal")
    monkeypatch.delenv("APP_DISPLAY_NAME", raising=False)
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.setattr(system_settings, "load_system_settings", lambda: {"branding": {"app_name": ""}})

    assert app_branding.app_display_name(fallback_env_names=("ACK_BRAND_NAME", "APP_DISPLAY_NAME")) == "Notice Portal"


def test_ticket_assignee_template_default_is_provider_neutral():
    template = system_settings.DEFAULT_SETTINGS["notifications"]["email"]["events"]["external_ticket_assignee_details"]

    assert "External ticket" in template["body"]
    assert "ServiceNow ticket" not in template["body"]


def test_external_ticket_email_template_uses_legacy_servicenow_key_as_fallback(monkeypatch):
    monkeypatch.setattr(
        notifications,
        "load_system_settings",
        lambda: {
            "notifications": {
                "email": {
                    "events": {
                        "servicenow_ticket_assignee_details": {
                            "enabled": True,
                            "subject": "Legacy {ticket}",
                            "body": "Legacy body {ticket}",
                        }
                    }
                }
            },
            "branding": {"app_name": "DiscoveryOne"},
        },
    )

    subject, body = notifications.render_email_template(
        "external_ticket_assignee_details",
        default_subject="Default {ticket}",
        default_body="Default body {ticket}",
        context={"ticket": "INC001"},
    )

    assert subject == "Legacy INC001"
    assert body == "Legacy body INC001"


def test_app_display_name_ignores_legacy_env_after_setup(monkeypatch):
    monkeypatch.setenv("ACK_BRAND_NAME", "Legacy Name")
    monkeypatch.setattr(
        system_settings,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "branding": {"app_name": ""},
        },
    )

    assert app_branding.app_display_name(
        fallback_env_names=("ACK_BRAND_NAME", "APP_DISPLAY_NAME")
    ) == "DiscoveryOne"