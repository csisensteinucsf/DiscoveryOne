from types import SimpleNamespace

from app import (
    case_slack_holds,
    case_source_holds,
    preservation_provider,
    preservation_provider_registry,
)


def test_registered_preservation_provider_handles_all_operations(monkeypatch):
    calls = []

    class ExamplePreservationProvider:
        name = "example_preservation"
        display_name = "Example Preservation"

        def is_available(self):
            return True

        def status_poll_delay_seconds(self):
            return 17.25

        def create_case(self, *, case_id, context):
            calls.append(("create", case_id, context))
            return {"created": True}

        def get_status(self, *, case_id, context):
            calls.append(("status", case_id, context))
            return {"status": "ready"}

        def apply_holds(self, *, case_id, payload, context):
            calls.append(("apply", case_id, payload, context))
            return {"applied": True}

        def release_holds(self, *, case_id, payload, context):
            calls.append(("release", case_id, payload, context))
            return {"released": True}

    preservation_provider_registry.register_preservation_provider(
        "example_preservation",
        ExamplePreservationProvider,
        display_name="Example Preservation",
    )
    monkeypatch.setattr(
        preservation_provider,
        "current_preservation_provider",
        lambda: "example_preservation",
    )
    try:
        assert preservation_provider.preservation_automation_ready() is True
        assert preservation_provider.status_poll_delay_seconds() == 17.25
        assert preservation_provider.create_case(case_id=7, db="db") == {
            "created": True
        }
        assert preservation_provider.get_status(case_id=7, db="db") == {
            "status": "ready"
        }
        assert preservation_provider.apply_holds(
            case_id=7,
            payload={"sources": ["email"]},
            db="db",
        ) == {"applied": True}
        assert preservation_provider.release_holds(
            case_id=7,
            payload={"sources": ["email"]},
            db="db",
        ) == {"released": True}
        assert [entry[0] for entry in calls] == [
            "create",
            "status",
            "apply",
            "release",
        ]
    finally:
        preservation_provider_registry.unregister_preservation_provider(
            "example_preservation"
        )


def test_provider_result_normalizes_case_id_and_keeps_legacy_alias():
    from app.preservation_provider_adapters import _provider_result

    from_legacy = _provider_result({"purview_case_id": "legacy-id"})
    assert from_legacy["provider_case_id"] == "legacy-id"
    assert from_legacy["purview_case_id"] == "legacy-id"

    from_generic = _provider_result({"provider_case_id": "provider-id"})
    assert from_generic["provider_case_id"] == "provider-id"
    assert from_generic["purview_case_id"] == "provider-id"


def test_generic_status_scheduler_uses_provider_facade(monkeypatch):
    from app import cases

    status_calls = []

    class FakeDB:
        def close(self):
            return None

    class FakeTimer:
        def __init__(self, delay, callback):
            self.delay = delay
            self.callback = callback
            self.daemon = False
            self.cancelled = False

        def start(self):
            return None

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr(
        cases.preservation_provider,
        "preservation_automation_ready",
        lambda: True,
    )
    monkeypatch.setattr(
        cases.preservation_provider,
        "status_poll_delay_seconds",
        lambda: 7.5,
    )
    monkeypatch.setattr(
        cases.preservation_provider,
        "get_status",
        lambda **kwargs: status_calls.append(kwargs),
    )
    monkeypatch.setattr(cases, "SessionLocal", FakeDB)
    monkeypatch.setattr(cases.threading, "Timer", FakeTimer)

    cases._preservation_poll_timers.clear()
    cases._schedule_preservation_status_poll(13, "test")
    timer = cases._preservation_poll_timers[(13, 0, 7)]
    assert timer.delay == 7.5

    timer.callback()

    assert status_calls == [
        {"case_id": 13, "db": status_calls[0]["db"], "request": None, "user": None, "case_hold_id": None}
    ]
    assert isinstance(status_calls[0]["db"], FakeDB)
    assert cases._preservation_poll_timers == {}


def test_none_provider_preserves_manual_request_hold_fallback(monkeypatch):
    from app import case_request_approval_preservation as approval

    custodian = SimpleNamespace(
        holds_email=True,
        holds_email_pending=False,
        holds_email_failed=False,
        holds_rubrik_restore=True,
        holds_rubrik_restore_pending=True,
        holds_rubrik_restore_failed=False,
    )
    record = SimpleNamespace(
        request_type="custodian",
        id=11,
        case_id=22,
        case_name="Manual Case",
    )
    actor = SimpleNamespace(id=3)

    monkeypatch.setattr(
        approval.preservation_provider,
        "preservation_automation_ready",
        lambda: False,
    )
    monkeypatch.setattr(
        approval.preservation_provider,
        "preservation_provider_label",
        lambda: "Preservation provider",
    )
    monkeypatch.setattr(
        approval.preservation_provider,
        "create_case",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("automation ran")),
    )
    monkeypatch.setattr(
        approval.case_request_core,
        "_filter_rubrik_targets_after_preservation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("filter ran")),
    )

    kept = approval.run_approval_preservation_holds(
        db=object(),
        record=record,
        actor=actor,
        request=None,
        preservation_hold_groups={("mailbox",): [1]},
        hold_notification_ids=[1],
        rubrik_targets=[custodian],
        log_progress=lambda *args: None,
    )

    assert kept == [custodian]
    assert custodian.holds_email is True
    assert custodian.holds_rubrik_restore is True
    assert custodian.holds_rubrik_restore_pending is True


def test_slack_without_integration_preserves_manual_hold_state(monkeypatch):
    case = SimpleNamespace(id=1, name="Case One", slack_hold_policy_id=None)
    custodian = SimpleNamespace(
        id=2,
        name="Custodian",
        email="custodian@example.test",
        holds_slack=True,
        holds_slack_pending=True,
        holds_slack_failed=False,
        holds_slack_released=False,
        slack_user_id=None,
    )
    monkeypatch.setattr(
        case_source_holds,
        "hold_source_automation_ready",
        lambda source_key: False,
    )

    case_slack_holds.sync_slack_hold_or_raise(
        case,
        custodian,
        enable=True,
    )

    assert custodian.holds_slack is True
    assert custodian.holds_slack_pending is True
    assert custodian.holds_slack_failed is False
    assert custodian.holds_slack_released is False

def test_preservation_routes_include_generic_and_legacy_paths():
    from app import case_purview

    paths = {route.path for route in case_purview.router.routes}

    assert "/api/cases/{case_id}/preservation_provider/case" in paths
    assert "/api/cases/{case_id}/preservation_provider/status" in paths
    assert "/api/cases/{case_id}/preservation_provider/holds" in paths
    assert "/api/cases/{case_id}/preservation_provider/holds/release" in paths
    assert "/api/cases/{case_id}/purview_case" in paths
    assert "/api/cases/{case_id}/purview_status" in paths
