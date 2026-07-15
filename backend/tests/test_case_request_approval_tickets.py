from types import SimpleNamespace

from app import case_request_approval_mutation
from app import case_request_approval_tickets
from app import ticket_workflow_catalog


class FakeDb:
    def __init__(self, custodians):
        self.custodians = {custodian.id: custodian for custodian in custodians}
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, _model, object_id):
        return self.custodians.get(object_id)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _ticket_workflows():
    return [
        {"key": "box_hold", "label": "Box Hold", "enabled": False},
        {
            "key": "endpoint_image",
            "label": "Endpoint Image",
            "enabled": True,
            "provider": "servicenow",
            "external_ticket_enabled": True,
            "auto_create_on_approval": True,
            "preservation_source": "jamf",
            "hold_key": "holds_endpoint",
        },
    ]


def test_mutation_debug_row_uses_configured_workflow_targets():
    custodian = SimpleNamespace(
        id=7,
        email="person@example.test",
        holds_email=False,
        holds_email_pending=False,
        holds_box=False,
        holds_box_pending=False,
        holds_rubrik_restore_pending=False,
        holds_endpoint=True,
    )
    workflows = {
        "endpoint_image": {
            "key": "endpoint_image",
            "hold_key": "holds_endpoint",
            "preservation_source": "jamf",
        }
    }

    row = case_request_approval_mutation._ticket_target_debug_row(
        custodian,
        workflows,
    )

    assert row["ticket_workflow_targets"] == ["endpoint_image"]


def test_approval_creates_configured_workflow_with_selected_provider(monkeypatch):
    custodian = SimpleNamespace(
        id=11,
        name="Example Person",
        email="person@example.test",
        holds_endpoint=True,
        custom_preservation=[],
    )
    db = FakeDb([custodian])
    case = SimpleNamespace(id=22, name="Example Case", request_ticket_entries=[])
    record = SimpleNamespace(id=33, request_type="custodian")
    actor = SimpleNamespace(id=44)
    created = []
    progress = []

    monkeypatch.setattr(
        ticket_workflow_catalog,
        "load_system_settings",
        lambda: {"ticket_workflows": _ticket_workflows()},
    )
    monkeypatch.setattr(
        case_request_approval_tickets.ticket_provider,
        "current_ticket_provider",
        lambda: "jira",
    )

    def create_ticket(**kwargs):
        created.append(kwargs)
        return {"ticket_number": "JIRA-123", "sys_id": "provider-id"}

    monkeypatch.setattr(
        case_request_approval_tickets.ticket_provider,
        "create_ticket",
        create_ticket,
    )
    monkeypatch.setattr(
        case_request_approval_tickets.case_request_core,
        "_require_employee_id",
        lambda _user: "employee-1",
    )
    monkeypatch.setattr(
        case_request_approval_tickets.case_request_core,
        "_app_base_url",
        lambda _request: "https://discovery.example.test",
    )
    monkeypatch.setattr(
        case_request_approval_tickets.case_request_core,
        "_normalize_request_ticket_entries",
        lambda entries, _case: entries,
    )
    monkeypatch.setattr(
        case_request_approval_tickets.case_request_core,
        "_sync_legacy_request_tickets",
        lambda _case, _entries: None,
    )
    monkeypatch.setattr(
        case_request_approval_tickets.case_request_core,
        "_apply_request_holds",
        lambda _case, _entries: None,
    )
    monkeypatch.setattr(
        case_request_approval_tickets.case_request_core,
        "log_event",
        lambda *_args, **_kwargs: None,
    )

    case_request_approval_tickets.create_approval_tickets(
        db=db,
        record=record,
        actor=actor,
        request=None,
        case_for_tickets=case,
        case_analyst_user=None,
        rubrik_targets=[],
        box_targets=[],
        ticket_target_debug_rows=[{"custodian_id": custodian.id}],
        ticket_errors=[],
        log_progress=lambda step, message, extra=None: progress.append(
            (step, message, extra)
        ),
    )

    assert [item["category"] for item in created] == ["endpoint_image"]
    assert created[0]["case_link"] == "https://discovery.example.test/cases/22"
    assert case.request_ticket_entries[0]["ticket"] == "JIRA-123"
    assert case.request_ticket_entries[0]["category"] == "endpoint_image"
    assert db.commits == 1
    target_progress = next(item for item in progress if item[0] == "ticket_targets")
    assert target_progress[2]["ticket_provider"] == "jira"
    assert target_progress[2]["workflow_counts"] == {"endpoint_image": 1}


def test_approval_skips_external_creation_without_selected_provider(monkeypatch):
    custodian = SimpleNamespace(
        id=11,
        name="Example Person",
        email="person@example.test",
        holds_endpoint=True,
        custom_preservation=[],
    )
    db = FakeDb([custodian])
    case = SimpleNamespace(id=22, name="Example Case", request_ticket_entries=[])

    monkeypatch.setattr(
        ticket_workflow_catalog,
        "load_system_settings",
        lambda: {"ticket_workflows": _ticket_workflows()},
    )
    monkeypatch.setattr(
        case_request_approval_tickets.ticket_provider,
        "current_ticket_provider",
        lambda: "none",
    )
    monkeypatch.setattr(
        case_request_approval_tickets.ticket_provider,
        "create_ticket",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("ticket creation should be skipped")
        ),
    )

    case_request_approval_tickets.create_approval_tickets(
        db=db,
        record=SimpleNamespace(id=33, request_type="custodian"),
        actor=SimpleNamespace(id=44),
        request=None,
        case_for_tickets=case,
        case_analyst_user=None,
        rubrik_targets=[],
        box_targets=[],
        ticket_target_debug_rows=[{"custodian_id": custodian.id}],
        ticket_errors=[],
        log_progress=lambda *_args, **_kwargs: None,
    )

    assert case.request_ticket_entries == []
    assert db.commits == 0
