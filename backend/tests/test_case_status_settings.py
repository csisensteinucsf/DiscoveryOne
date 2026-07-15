from app import case_status_summary, models, system_admin, system_admin_config


def test_public_case_status_config_clamps_values():
    public = system_admin_config.public_case_status_config(
        {
            "ntp_ack_days": "0",
            "consent_received_days": "99999",
        }
    )

    assert public == {
        "ntp_ack_days": 1,
        "consent_received_days": 3650,
    }


def test_system_case_status_update_saves_normalized_values(monkeypatch):
    store = {"case_status": {"ntp_ack_days": 7, "consent_received_days": 7}}
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_case_status(
        payload=system_admin_config.CaseStatusPayload(
            ntp_ack_days=14,
            consent_received_days=0,
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["case_status"] == {
        "ntp_ack_days": 14,
        "consent_received_days": 1,
    }
    assert store["case_status"] == result["case_status"]


def test_case_status_runtime_helpers_use_app_managed_settings(monkeypatch):
    monkeypatch.setenv("SLA_NTP_ACK_DAYS", "999")
    monkeypatch.setenv("SLA_CONSENT_RECEIVED_DAYS", "999")
    monkeypatch.setattr(
        case_status_summary,
        "load_system_settings",
        lambda: {
            "case_status": {
                "ntp_ack_days": 5,
                "consent_received_days": 11,
            }
        },
    )

    assert case_status_summary.sla_ntp_ack_days() == 5
    assert case_status_summary.sla_consent_received_days() == 11
