from types import SimpleNamespace

from app import case_request_tickets


def _custodian(**overrides):
    values = {
        "id": 1,
        "email": "person@example.test",
        "holds_archive": False,
        "holds_archive_pending": False,
        "holds_archive_failed": False,
        "holds_archive_released": False,
        "holds_restore": False,
        "holds_restore_pending": True,
        "holds_restore_failed": False,
        "holds_restore_released": False,
        "holds_email": False,
        "holds_email_pending": True,
        "holds_email_released": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _case(custodian):
    return SimpleNamespace(custodians=[custodian])


def test_manual_hold_tracking_ignores_external_completion(monkeypatch):
    workflow = {
        "manual_archive": {
            "hold_key": "holds_archive",
            "manual_status_tracking": True,
            "hold_operation": "hold",
        }
    }
    monkeypatch.setattr(
        case_request_tickets,
        "_request_ticket_category_lookup",
        lambda: workflow,
    )
    custodian = _custodian()

    case_request_tickets._apply_request_holds(
        _case(custodian),
        [
            {
                "category": "manual_archive",
                "custodian_id": custodian.id,
                "is_closed": True,
            }
        ],
    )

    assert custodian.holds_archive is True
    assert custodian.holds_archive_pending is True
    assert custodian.holds_archive_failed is False
    assert custodian.holds_archive_released is False


def test_manual_release_tracking_initializes_pending_release(monkeypatch):
    workflow = {
        "manual_archive_release": {
            "hold_key": "holds_archive",
            "manual_status_tracking": True,
            "hold_operation": "release",
        }
    }
    monkeypatch.setattr(
        case_request_tickets,
        "_request_ticket_category_lookup",
        lambda: workflow,
    )
    custodian = _custodian(
        holds_archive=True,
        holds_archive_pending=False,
        holds_archive_failed=True,
    )

    case_request_tickets._apply_request_holds(
        _case(custodian),
        [
            {
                "category": "manual_archive_release",
                "custodian_id": custodian.id,
            }
        ],
    )

    assert custodian.holds_archive is True
    assert custodian.holds_archive_pending is True
    assert custodian.holds_archive_failed is False
    assert custodian.holds_archive_released is False


def test_completed_workflow_satisfies_configured_source(monkeypatch):
    workflow = {
        "restore_job": {
            "hold_key": "holds_restore",
            "manual_status_tracking": False,
            "hold_operation": "hold",
            "completion_satisfies_source": "email",
        }
    }
    monkeypatch.setattr(
        case_request_tickets,
        "_request_ticket_category_lookup",
        lambda: workflow,
    )
    custodian = _custodian()

    case_request_tickets._apply_request_holds(
        _case(custodian),
        [
            {
                "category": "restore_job",
                "custodian_id": custodian.id,
                "is_closed": True,
            }
        ],
    )

    assert custodian.holds_restore is True
    assert custodian.holds_restore_pending is False
    assert custodian.holds_email is True
    assert custodian.holds_email_pending is False
    assert custodian.holds_email_released is False


def test_completed_automatic_release_applies_release_transition(monkeypatch):
    workflow = {
        "archive_release": {
            "hold_key": "holds_archive",
            "manual_status_tracking": False,
            "hold_operation": "release",
        }
    }
    monkeypatch.setattr(
        case_request_tickets,
        "_request_ticket_category_lookup",
        lambda: workflow,
    )
    custodian = _custodian(
        holds_archive=True,
        holds_archive_pending=True,
    )

    case_request_tickets._apply_request_holds(
        _case(custodian),
        [
            {
                "category": "archive_release",
                "custodian_id": custodian.id,
                "is_closed": True,
            }
        ],
    )

    assert custodian.holds_archive is False
    assert custodian.holds_archive_pending is False
    assert custodian.holds_archive_released is True
