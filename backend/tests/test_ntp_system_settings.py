from app import integration_settings, models, ntp, startup_maintenance, system_admin, system_admin_config


def test_public_ntp_config_masks_ack_secret_and_clamps_values():
    public = system_admin_config.public_ntp_config(
        {
            "archive_bcc_address": "archive@example.edu",
            "archive_copy_required": True,
            "reserved_archive_bcc_addresses": "records@example.edu",
            "ack_automate_url": "https://dmz.example.edu/ack?token={token}",
            "ack_display_url": "https://ediscovery.example.edu/acknowledge",
            "ack_automate_secret": integration_settings.encrypt_secret("shared-secret"),
            "reminder_interval_days": "999",
            "reminder_duration_days": "99999",
            "reminder_loop_seconds": "1",
        }
    )

    assert public["archive_bcc_address"] == "archive@example.edu"
    assert public["archive_copy_required"] is True
    assert public["ack_display_url"] == "https://ediscovery.example.edu/acknowledge"
    assert public["ack_automate_secret"] == integration_settings.MASKED_SECRET_VALUE
    assert public["reminder_interval_days"] == 365
    assert public["reminder_duration_days"] == 3650
    assert public["reminder_loop_seconds"] == 30


def test_system_ntp_update_encrypts_and_preserves_ack_secret(monkeypatch):
    encrypted = integration_settings.encrypt_secret("existing-secret")
    store = {
        "ntp": {
            "archive_bcc_address": "",
            "ack_automate_secret": encrypted,
        }
    }
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_ntp(
        payload=system_admin_config.NTPConfigPayload(
            archive_bcc_address="archive@example.edu",
            archive_copy_required=True,
            reserved_archive_bcc_addresses="records@example.edu, records@example.edu",
            ack_automate_url="https://dmz.example.edu/ack?token={token}",
            ack_display_url="https://ediscovery.example.edu/acknowledge",
            ack_automate_secret=integration_settings.MASKED_SECRET_VALUE,
            reminder_interval_days=14,
            reminder_duration_days=90,
            reminder_loop_seconds=900,
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["ntp"]["ack_automate_secret"] == integration_settings.MASKED_SECRET_VALUE
    assert integration_settings.decrypt_secret(store["ntp"]["ack_automate_secret"]) == "existing-secret"
    assert store["ntp"]["archive_bcc_address"] == "archive@example.edu"
    assert store["ntp"]["archive_copy_required"] is True
    assert store["ntp"]["reserved_archive_bcc_addresses"] == "records@example.edu"
    assert store["ntp"]["ack_display_url"] == "https://ediscovery.example.edu/acknowledge"

    system_admin.sys_update_ntp(
        payload=system_admin_config.NTPConfigPayload(ack_automate_secret="new-secret"),
        actor=actor,
        request=None,
        db=None,
    )

    assert integration_settings.decrypt_secret(store["ntp"]["ack_automate_secret"]) == "new-secret"


def test_ntp_runtime_settings_use_app_managed_values(monkeypatch):
    monkeypatch.delenv("NTP_ACK_AUTOMATE_URL", raising=False)
    monkeypatch.delenv("NTP_ACK_AUTOMATE_SECRET", raising=False)
    monkeypatch.delenv("NTP_ACK_DISPLAY_URL", raising=False)
    monkeypatch.delenv("NTP_REMINDER_INTERVAL_DAYS", raising=False)
    monkeypatch.delenv("NTP_REMINDER_DURATION_DAYS", raising=False)
    monkeypatch.delenv("NTP_REMINDER_LOOP_SECONDS", raising=False)
    monkeypatch.setattr(
        ntp,
        "load_system_settings",
        lambda: {
            "ntp": {
                "ack_automate_url": "https://dmz.example.edu/ack?token={token}",
                "ack_automate_secret": integration_settings.encrypt_secret("stored-secret"),
                "ack_display_url": "https://ediscovery.example.edu/acknowledge",
                "reminder_interval_days": 21,
                "reminder_duration_days": 120,
                "reminder_loop_seconds": 450,
                "archive_bcc_address": "archive@example.edu",
                "archive_copy_required": True,
                "reserved_archive_bcc_addresses": "records@example.edu",
            }
        },
    )

    assert ntp._build_ack_link("https://app.example.edu", "token-123") == "https://dmz.example.edu/ack?token=token-123"
    assert ntp.ntp_ack_automate_secret() == "stored-secret"
    assert ntp._ack_display_url("https://app.example.edu") == "https://ediscovery.example.edu/acknowledge"
    assert ntp.ntp_reminder_interval_days() == 21
    assert ntp.ntp_reminder_duration_days() == 120
    assert ntp.ntp_reminder_loop_seconds() == 450
    assert ntp.ntp_default_archive_bcc() == "archive@example.edu"
    assert ntp.ntp_archive_copy_required() is True
    assert ntp.ntp_reserved_archive_bcc_addresses() == {"records@example.edu"}


def test_ntp_legacy_env_is_ignored_after_setup(monkeypatch):
    monkeypatch.setenv("NTP_ACK_AUTOMATE_URL", "https://legacy.example.test/ack")
    monkeypatch.setenv("NTP_ACK_AUTOMATE_SECRET", "legacy-secret")
    monkeypatch.setenv("NTP_REMINDER_INTERVAL_DAYS", "99")
    monkeypatch.setattr(
        ntp,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "ntp": {
                "ack_automate_url": "",
                "ack_automate_secret": "",
                "reminder_interval_days": "",
            },
        },
    )

    assert ntp.ntp_ack_automate_url() == ""
    assert ntp.ntp_ack_automate_secret() == ""
    assert ntp.ntp_reminder_interval_days() == 14

def test_ntp_template_bcc_normalization_uses_stored_reserved_addresses(monkeypatch):
    monkeypatch.setenv(
        "NTP_TEMPLATE_BCC_RESERVED_ADDRESSES",
        "legacy-reserved@example.edu",
    )
    monkeypatch.setattr(
        startup_maintenance,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "ntp": {
                "reserved_archive_bcc_addresses": "stored-reserved@example.edu",
            },
        },
    )

    normalized = startup_maintenance._normalize_ntp_template_bcc_storage(
        "stored-reserved@example.edu, legacy-reserved@example.edu, keep@example.edu"
    )

    assert normalized == "legacy-reserved@example.edu, keep@example.edu"