from datetime import date, timedelta

from app import case_request_settings, case_requests, models, system_admin, system_admin_config


def test_public_case_request_settings_config_clamps_values():
    public = system_admin_config.public_case_request_settings_config(
        {
            "requestor_stats_show_global": True,
            "hold_automation_allow_override": True,
            "auto_rubrik_restore_for_separated_email_holds": True,
            "pending_cleanup_days": "0",
            "pending_cleanup_interval_hours": "999",
            "hold_status_email_delay_seconds": "999999",
            "preservation_auto_apply_max_attempts": "0",
            "preservation_auto_apply_delay_seconds": "9999",
            "preservation_status_max_seconds": "999999",
            "preservation_status_interval_seconds": "0",
        }
    )

    assert public == {
        "requestor_stats_show_global": True,
        "hold_automation_allow_override": True,
        "auto_rubrik_restore_for_separated_email_holds": True,
        "pending_cleanup_days": 1.0,
        "pending_cleanup_interval_hours": 168.0,
        "hold_status_email_delay_seconds": 86400.0,
        "preservation_auto_apply_max_attempts": 1,
        "preservation_auto_apply_delay_seconds": 3600.0,
        "preservation_status_max_seconds": 86400.0,
        "preservation_status_interval_seconds": 1.0,
    }


def test_system_case_request_settings_update_saves_normalized_values(monkeypatch):
    store = {"case_requests": {}}
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_case_request_settings(
        payload=system_admin_config.CaseRequestSettingsPayload(
            requestor_stats_show_global=True,
            hold_automation_allow_override=True,
            auto_rubrik_restore_for_separated_email_holds=True,
            pending_cleanup_days=45,
            pending_cleanup_interval_hours=0,
            hold_status_email_delay_seconds=30,
            preservation_auto_apply_max_attempts=5,
            preservation_auto_apply_delay_seconds=1.5,
            preservation_status_max_seconds=120,
            preservation_status_interval_seconds=0,
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["case_requests"]["requestor_stats_show_global"] is True
    assert result["case_requests"]["hold_automation_allow_override"] is True
    assert result["case_requests"]["auto_rubrik_restore_for_separated_email_holds"] is True
    assert result["case_requests"]["pending_cleanup_days"] == 45.0
    assert result["case_requests"]["pending_cleanup_interval_hours"] == 1.0
    assert result["case_requests"]["preservation_status_interval_seconds"] == 1.0
    assert store["case_requests"] == result["case_requests"]


def test_case_request_runtime_helpers_use_app_managed_settings(monkeypatch):
    monkeypatch.setenv("CASE_REQUEST_STATS_REQUESTOR_SHOW_GLOBAL", "0")
    monkeypatch.setenv("CASE_REQUEST_HOLD_AUTOMATION_ALLOW_OVERRIDE", "0")
    monkeypatch.setenv("CASE_REQUEST_PENDING_CLEANUP_DAYS", "999")
    monkeypatch.setattr(
        case_request_settings,
        "load_system_settings",
        lambda: {
            "case_requests": {
                "requestor_stats_show_global": True,
                "hold_automation_allow_override": True,
                "auto_rubrik_restore_for_separated_email_holds": True,
                "pending_cleanup_days": 9,
                "pending_cleanup_interval_hours": 4,
                "hold_status_email_delay_seconds": 12,
                "preservation_auto_apply_max_attempts": 6,
                "preservation_auto_apply_delay_seconds": 1.25,
                "preservation_status_max_seconds": 44,
                "preservation_status_interval_seconds": 3,
            }
        },
    )

    assert case_request_settings.requestor_stats_show_global() is True
    assert case_request_settings.hold_automation_allow_override() is True
    assert case_request_settings.auto_rubrik_restore_for_separated_email_holds() is True
    assert case_request_settings.pending_cleanup_days() == 9.0
    assert case_request_settings.pending_cleanup_interval_hours() == 4.0
    assert case_request_settings.hold_status_email_delay_seconds() == 12.0
    assert case_request_settings.preservation_auto_apply_max_attempts() == 6
    assert case_request_settings.preservation_auto_apply_delay_seconds() == 1.25
    assert case_request_settings.preservation_status_max_seconds() == 44.0
    assert case_request_settings.preservation_status_interval_seconds() == 3.0


def test_preservation_timing_helpers_read_legacy_purview_keys(monkeypatch):
    monkeypatch.setattr(
        case_request_settings,
        "load_system_settings",
        lambda: {
            "case_requests": {
                "purview_auto_apply_max_attempts": 7,
                "purview_auto_apply_delay_seconds": 1.75,
                "purview_approval_status_max_seconds": 55,
                "purview_approval_status_interval_seconds": 4,
            }
        },
    )

    assert case_request_settings.preservation_auto_apply_max_attempts() == 7
    assert case_request_settings.preservation_auto_apply_delay_seconds() == 1.75
    assert case_request_settings.preservation_status_max_seconds() == 55.0
    assert case_request_settings.preservation_status_interval_seconds() == 4.0

def test_auto_rubrik_restore_setting_defaults_off(monkeypatch):
    monkeypatch.setattr(case_request_settings, "load_system_settings", lambda: {"case_requests": {}})

    assert case_request_settings.auto_rubrik_restore_for_separated_email_holds() is False


def _separated_email_custodian_payload():
    return {
        "name": "Separated Person",
        "email": "person@example.edu",
        "employment_end_date": (date.today() - timedelta(days=120)).isoformat(),
        "holds": {"email": "pending"},
    }


def test_separated_email_custodians_do_not_get_auto_rubrik_flags_by_default(monkeypatch):
    monkeypatch.setattr(case_requests, "case_request_auto_rubrik_restore_for_separated_email_holds", lambda: False)
    monkeypatch.setattr(case_requests, "is_organization_email", lambda value: True)
    monkeypatch.setattr(case_requests, "apply_custodian_name_email_review", lambda *args, **kwargs: None)

    custodian = case_requests._custodian_model(1, _separated_email_custodian_payload(), False, use_ai_review=False)

    assert custodian.holds_email is True
    assert custodian.holds_rubrik_restore is False
    assert custodian.holds_rubrik_restore_pending is False
    assert getattr(custodian, "_auto_rubrik_flag") is False


def test_separated_email_custodians_get_auto_rubrik_flags_when_enabled(monkeypatch):
    monkeypatch.setattr(case_requests, "case_request_auto_rubrik_restore_for_separated_email_holds", lambda: True)
    monkeypatch.setattr(case_requests, "is_organization_email", lambda value: True)
    monkeypatch.setattr(case_requests, "apply_custodian_name_email_review", lambda *args, **kwargs: None)

    custodian = case_requests._custodian_model(1, _separated_email_custodian_payload(), False, use_ai_review=False)

    assert custodian.holds_email is True
    assert custodian.holds_rubrik_restore is True
    assert custodian.holds_rubrik_restore_pending is True
    assert getattr(custodian, "_auto_rubrik_flag") is True
