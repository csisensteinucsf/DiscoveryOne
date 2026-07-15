from app import models, system_admin, system_admin_config


def test_institution_settings_update_normalizes_policy(monkeypatch):
    store = {"institution": {}}

    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        system_admin_config,
        "load_institution_settings",
        lambda: dict(store.get("institution") or {}),
    )
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_institution(
        payload=system_admin_config.InstitutionSettingsPayload(
            org_name="Example University",
            org_short_name="Example",
            allowed_requestor_email_domains=["@Example.edu", "law.example.edu"],
            requestor_email_exceptions=["Outside.Counsel@example.com"],
            sso_display_name="Example SSO",
            support_email="Support@example.edu",
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["institution"]["org_name"] == "Example University"
    assert result["institution"]["allowed_requestor_email_domains"] == [
        "example.edu",
        "law.example.edu",
    ]
    assert result["institution"]["requestor_email_exceptions"] == [
        "outside.counsel@example.com"
    ]
    assert store["institution"]["support_email"] == "support@example.edu"


def test_public_institution_config_hides_exception_addresses_by_default(monkeypatch):
    monkeypatch.setattr(
        system_admin_config,
        "load_institution_settings",
        lambda: {
            "org_name": "Example University",
            "requestor_email_exceptions": ["outside.counsel@example.com"],
        },
    )

    public = system_admin_config.public_institution_config()
    admin = system_admin_config.public_institution_config(include_exceptions=True)

    assert "requestor_email_exceptions" not in public
    assert admin["requestor_email_exceptions"] == ["outside.counsel@example.com"]
