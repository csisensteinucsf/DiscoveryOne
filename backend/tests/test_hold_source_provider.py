from types import SimpleNamespace

from app import (
    case_source_holds,
    hold_source_provider,
    hold_source_provider_registry,
)


def _case_and_custodian(source_key="example"):
    case = SimpleNamespace(id=7, name="Example Case")
    custodian = SimpleNamespace(
        id=12,
        name="Example Custodian",
        email="custodian@example.test",
    )
    setattr(custodian, f"holds_{source_key}", True)
    setattr(custodian, f"holds_{source_key}_pending", True)
    setattr(custodian, f"holds_{source_key}_failed", False)
    setattr(custodian, f"holds_{source_key}_released", False)
    return case, custodian


def test_registered_hold_source_provider_receives_neutral_context():
    calls = []

    class ExampleProvider:
        source_key = "example"
        display_name = "Example Hold Service"

        def is_available(self):
            return True

        def sync_custodian_hold(
            self,
            *,
            case,
            custodian,
            custodian_email,
            enable,
            context,
        ):
            calls.append(
                (case, custodian, custodian_email, enable, context)
            )
            return {
                "source_key": self.source_key,
                "provider": self.source_key,
                "status": "enabled",
                "provider_case_id": "case-7",
                "provider_subject_id": "subject-12",
            }

    hold_source_provider_registry.register_hold_source_provider(
        "example",
        ExampleProvider,
        display_name="Example Hold Service",
    )
    try:
        case, custodian = _case_and_custodian()
        result = hold_source_provider.sync_custodian_hold(
            source_key="example",
            case=case,
            custodian=custodian,
            custodian_email=custodian.email,
            enable=True,
            db="db",
            request="request",
            actor_id=5,
        )

        assert result["provider_case_id"] == "case-7"
        assert calls[0][0] is case
        assert calls[0][1] is custodian
        assert calls[0][2] == "custodian@example.test"
        assert calls[0][3] is True
        assert calls[0][4].db == "db"
        assert calls[0][4].request == "request"
        assert calls[0][4].actor_id == 5
    finally:
        hold_source_provider_registry.unregister_hold_source_provider(
            "example"
        )


def test_shared_orchestration_applies_success_state():
    class ExampleProvider:
        source_key = "example"
        display_name = "Example Hold Service"

        def is_available(self):
            return True

        def sync_custodian_hold(self, **kwargs):
            return {
                "source_key": self.source_key,
                "provider": self.source_key,
                "status": "enabled",
            }

    hold_source_provider_registry.register_hold_source_provider(
        "example",
        ExampleProvider,
    )
    try:
        case, custodian = _case_and_custodian()
        result = case_source_holds.sync_hold_or_raise(
            case,
            custodian,
            source_key="example",
            enable=True,
        )

        assert result["status"] == "enabled"
        assert custodian.holds_example is True
        assert custodian.holds_example_pending is False
        assert custodian.holds_example_failed is False
        assert custodian.holds_example_released is False
    finally:
        hold_source_provider_registry.unregister_hold_source_provider(
            "example"
        )


def test_subject_not_found_can_continue_as_failed_manual_follow_up():
    class MissingSubjectProvider:
        source_key = "example"
        display_name = "Example Hold Service"

        def is_available(self):
            return True

        def sync_custodian_hold(self, **kwargs):
            raise hold_source_provider_registry.HoldSourceSubjectNotFound(
                "Subject was not found",
                error_code="subject_not_found",
                status_code=404,
            )

    hold_source_provider_registry.register_hold_source_provider(
        "example",
        MissingSubjectProvider,
    )
    try:
        case, custodian = _case_and_custodian()
        result = case_source_holds.sync_hold_or_raise(
            case,
            custodian,
            source_key="example",
            enable=True,
            continue_on_subject_not_found=True,
        )

        assert result["status"] == "failed"
        assert result["continued"] is True
        assert custodian.holds_example is True
        assert custodian.holds_example_pending is False
        assert custodian.holds_example_failed is True
        assert custodian.holds_example_released is False
    finally:
        hold_source_provider_registry.unregister_hold_source_provider(
            "example"
        )
