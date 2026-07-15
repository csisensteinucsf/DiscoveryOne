from pathlib import Path

import pytest

from app import integration_settings, ntp, system_admin_config


REPO_ROOT = Path(__file__).resolve().parents[2]


def _bridge_settings(*, enabled=True):
    return {
        "initial_setup_completed": True,
        "enabled_integrations": {"ntp_ack_bridge": enabled},
        "integration_configs": {
            "ntp_ack_bridge": {
                "bridge_url": "https://dmz.example.edu/ack?token={token}",
                "display_url": "https://dmz.example.edu/",
                "shared_secret": integration_settings.encrypt_secret("bridge-secret"),
            }
        },
        "ntp": {},
    }


def test_dmz_bridge_is_system_only_and_has_required_warning():
    catalog = (REPO_ROOT / "frontend/src/pages/setupCatalog.js").read_text(encoding="utf-8")
    setup_block = catalog.split("export const SETUP_INTEGRATION_FLAGS", 1)[1].split(
        "export const SYSTEM_INTEGRATION_FLAGS", 1
    )[0]
    system_block = catalog.split("export const SYSTEM_INTEGRATION_FLAGS", 1)[1].split(
        "export const INTEGRATION_FLAGS", 1
    )[0]
    config_ui = (
        REPO_ROOT / "frontend/src/pages/SystemCoreIntegrationConfigSections.jsx"
    ).read_text(encoding="utf-8")
    ntp_ui = (REPO_ROOT / "frontend/src/pages/SystemNtpPanel.jsx").read_text(
        encoding="utf-8"
    )

    assert "ntp_ack_bridge" not in setup_block
    assert "ntp_ack_bridge" in system_block
    assert (
        "Do not set this up until you have run the DMZ helper script to build the DMZ Server."
        in config_ui
    )
    assert "External acknowledgement bridge URL" not in ntp_ui
    assert "Acknowledgement bridge shared secret" not in ntp_ui


def test_dmz_bridge_secret_is_encrypted_and_masked(monkeypatch):
    stored = integration_settings.sanitize_integration_config(
        "ntp_ack_bridge",
        {
            "bridge_url": "https://dmz.example.edu/ack?token={token}",
            "display_url": "https://dmz.example.edu/",
            "shared_secret": "bridge-secret",
        },
    )

    assert stored["shared_secret"].startswith("enc:v1:")
    assert integration_settings.decrypt_secret(stored["shared_secret"]) == "bridge-secret"

    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {"integration_configs": {"ntp_ack_bridge": stored}},
    )
    public = integration_settings.public_integration_config("ntp_ack_bridge")
    assert public["shared_secret"] == integration_settings.MASKED_SECRET_VALUE


def test_dmz_bridge_validation_requires_helper_values():
    with pytest.raises(ValueError, match="missing external acknowledgement bridge URL"):
        integration_settings.validate_integration_settings(
            enabled_integrations={"ntp_ack_bridge": True},
            providers={},
            configs={"ntp_ack_bridge": {}},
        )

    with pytest.raises(ValueError, match="must be a valid HTTPS URL"):
        integration_settings.validate_integration_settings(
            enabled_integrations={"ntp_ack_bridge": True},
            providers={},
            configs={
                "ntp_ack_bridge": {
                    "bridge_url": "http://dmz.example.edu/ack?token={token}",
                    "display_url": "https://dmz.example.edu/",
                    "shared_secret": "bridge-secret",
                }
            },
        )

    with pytest.raises(ValueError, match=r"must include \{token\}"):
        integration_settings.validate_integration_settings(
            enabled_integrations={"ntp_ack_bridge": True},
            providers={},
            configs={
                "ntp_ack_bridge": {
                    "bridge_url": "https://dmz.example.edu/ack",
                    "display_url": "https://dmz.example.edu/",
                    "shared_secret": "bridge-secret",
                }
            },
        )

    integration_settings.validate_integration_settings(
        enabled_integrations={"ntp_ack_bridge": True},
        providers={},
        configs=_bridge_settings()["integration_configs"],
    )


def test_enabled_dmz_bridge_controls_ntp_links_and_callback_secret(monkeypatch):
    monkeypatch.setattr(ntp, "load_system_settings", lambda: _bridge_settings())

    assert (
        ntp._build_ack_link("https://app.example.edu", "token-123")
        == "https://dmz.example.edu/ack?token=token-123"
    )
    assert ntp.ntp_ack_automate_secret() == "bridge-secret"
    assert ntp._ack_display_url("https://app.example.edu") == "https://dmz.example.edu/"


def test_disabled_configured_dmz_bridge_uses_direct_manual_acknowledgement(monkeypatch):
    monkeypatch.setattr(
        ntp,
        "load_system_settings",
        lambda: _bridge_settings(enabled=False),
    )

    assert (
        ntp._build_ack_link("https://app.example.edu", "token-123")
        == "https://app.example.edu/api/ntp/ack/token-123"
    )
    assert ntp.ntp_ack_automate_secret() == ""
    assert ntp._ack_display_url("https://app.example.edu") == "https://app.example.edu/ntp/ack"


def test_dmz_bridge_is_in_public_system_integration_config(monkeypatch):
    monkeypatch.setattr(
        system_admin_config,
        "public_integration_config_summary",
        lambda: {"providers": {}, "enabled": {}},
    )
    monkeypatch.setattr(
        system_admin_config,
        "public_integration_config",
        lambda name: {"name": name},
    )

    payload = system_admin_config.public_integration_admin_config()
    assert payload["configs"]["ntp_ack_bridge"] == {"name": "ntp_ack_bridge"}