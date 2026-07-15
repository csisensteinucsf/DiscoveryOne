from app import models, notifications, system_admin, system_admin_config


def test_normalize_deployment_config_requires_https_and_adds_base_host():
    public = system_admin_config.normalize_deployment_config(
        {
            "app_base_url": "https://discoveryone.example.edu/app",
            "allowed_hosts": ["discoveryone.local:48080", "https://discoveryone.example.edu/ignored"],
        }
    )

    assert public == {
        "app_base_url": "https://discoveryone.example.edu/app",
        "allowed_hosts": ["discoveryone.local", "discoveryone.example.edu"],
    }


def test_normalize_deployment_config_rejects_http():
    try:
        system_admin_config.normalize_deployment_config({"app_base_url": "http://example.edu"})
    except ValueError as exc:
        assert "https" in str(exc).lower()
    else:
        raise AssertionError("http URL should be rejected")


def test_system_deployment_update_preserves_tls_and_saves_normalized_values(monkeypatch):
    store = {
        "deployment": {
            "app_base_url": "",
            "allowed_hosts": [],
            "tls": {"mode": "self_signed", "common_name": "nas.local"},
        }
    }
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_deployment(
        payload=system_admin_config.DeploymentPayload(
            app_base_url="https://d1.example.edu",
            allowed_hosts=["d1.example.edu:48080", "d1-alt.example.edu"],
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["deployment"] == {
        "app_base_url": "https://d1.example.edu",
        "allowed_hosts": ["d1.example.edu", "d1-alt.example.edu"],
    }
    assert store["deployment"]["tls"] == {"mode": "self_signed", "common_name": "nas.local"}


def test_app_base_url_prefers_stored_deployment_over_legacy_env(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://env.example.edu")
    monkeypatch.setattr(
        notifications,
        "load_system_settings",
        lambda: {
            "deployment": {
                "app_base_url": "https://stored.example.edu",
                "allowed_hosts": ["stored.example.edu"],
            }
        },
    )

    assert notifications._app_base_url() == "https://stored.example.edu"
    assert notifications._host_is_allowed("stored.example.edu") is True
