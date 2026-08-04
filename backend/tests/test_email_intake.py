from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_request_approval_mutation, case_requestors, email_intake_graph, email_intake_service, integration_settings, models
from app.case_requestors import normalize_requestor_entries
from app.email_intake_graph import EmailIntakeSettings
from app.email_intake_matching import extract_case_request_payload, normalize_graph_message, template_matches


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def settings(**overrides):
    values = {
        "enabled": True,
        "tenant_id": "tenant",
        "client_id": "client",
        "client_secret": "secret",
        "mailbox": "intake@example.edu",
        "folder_id": "inbox",
        "poll_interval_seconds": 60,
        "max_messages_per_poll": 50,
        "sender_policy": "any",
        "allowed_senders": (),
        "allowed_sender_domains": (),
        "graph_base": "https://graph.microsoft.com/v1.0",
        "scope": "https://graph.microsoft.com/.default",
        "requestor_from_sender": True,
        "process_existing_on_first_run": False,
        "startup_delay_seconds": 0,
        "timeout_seconds": 30.0,
        "retry_count": 2,
    }
    values.update(overrides)
    return EmailIntakeSettings(**values)


def sample_graph_message(**overrides):
    value = {
        "id": "immutable-message-1",
        "internetMessageId": "<one@example.test>",
        "changeKey": "change-1",
        "receivedDateTime": "2026-08-03T12:30:00Z",
        "from": {"emailAddress": {"address": "outside@law.example"}},
        "toRecipients": [{"emailAddress": {"address": "intake@example.edu"}}],
        "subject": "New matter request",
        "body": {
            "contentType": "html",
            "content": "<p>Case Name: Matter Alpha</p><script>alert(1)</script><p>Matter Number: MAT-7</p><p>Custodians: Person One &lt;person.one@example.edu&gt;</p>",
        },
        "hasAttachments": False,
    }
    value.update(overrides)
    return value


def test_html_is_plain_text_and_template_extracts_supported_case_fields():
    email = normalize_graph_message(sample_graph_message())
    assert "alert(1)" not in email.body_text
    template = SimpleNamespace(
        sender_pattern="*@law.example",
        recipient_pattern="intake@example.edu",
        subject_pattern="New matter*",
        body_markers=json.dumps(["Matter Number:"]),
        field_markers=json.dumps({
            "case_name": "Case Name:",
            "matter_number": "Matter Number:",
            "custodians": "Custodians:",
        }),
        default_values=json.dumps({"internal_counsel": "Counsel Name"}),
        hold_name="Initial Hold",
    )
    matched, failures = template_matches(template, email)
    assert matched is True
    assert failures == []
    payload = extract_case_request_payload(template, email)
    assert payload["name"] == "Matter Alpha"
    assert payload["legal_case_name"] == "Matter Alpha"
    assert payload["matter_number"] == "MAT-7"
    assert payload["internal_counsel"] == "Counsel Name"
    assert payload["hold_name"] == "Initial Hold"
    assert payload["custodians"] == [{"name": "Person One", "email": "person.one@example.edu", "holds": {}}]


def test_process_message_creates_one_pending_case_request(monkeypatch, db_session):
    template = models.EmailIntakeTemplate(
        name="New matter",
        enabled=True,
        priority=10,
        subject_pattern="New matter*",
        body_markers=json.dumps(["Case Name:"]),
        field_markers=json.dumps({"case_name": "Case Name:", "matter_number": "Matter Number:"}),
        default_values=json.dumps({"outside_counsel": "Outside Firm"}),
        hold_name="Complaint Hold",
    )
    message = models.EmailIntakeMessage(
        mailbox="intake@example.edu",
        graph_message_id="immutable-message-1",
        internet_message_id="<one@example.test>",
        status="received",
        sender="outside@law.example",
        recipients=json.dumps(["intake@example.edu"]),
        subject="New matter request",
        body_text="Case Name: Matter Alpha\nMatter Number: MAT-7",
        attachment_count=0,
    )
    db_session.add_all([template, message])
    db_session.commit()
    db_session.refresh(message)
    monkeypatch.setattr(email_intake_service, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(email_intake_service.case_request_core, "notify_case_request_submitted", lambda *args, **kwargs: None)

    first = email_intake_service.process_message(db_session, message, settings())
    assert first["status"] == "pending_request"
    request = db_session.get(models.CaseRequest, first["case_request_id"])
    payload = json.loads(request.payload)
    assert request.status == "pending"
    assert request.requestor_email == "outside@law.example"
    assert payload["matter_number"] == "MAT-7"
    assert payload["outside_counsel"] == "Outside Firm"
    assert payload["hold_name"] == "Complaint Hold"

    second = email_intake_service.process_message(db_session, message, settings())
    assert second["case_request_id"] == request.id
    assert db_session.query(models.CaseRequest).count() == 1


def test_external_requestor_policy_bypass_is_keyword_only_and_explicit(db_session, monkeypatch):
    monkeypatch.setattr("app.case_requestors.require_allowed_requestor_email", lambda value: (_ for _ in ()).throw(RuntimeError("blocked")))
    with pytest.raises(RuntimeError):
        normalize_requestor_entries(db_session, [], "outside@law.example")
    rows = normalize_requestor_entries(db_session, [], "outside@law.example", allow_external=True)
    assert rows[0]["email"] == "outside@law.example"


def test_trusted_email_intake_request_approves_external_requestor_and_named_hold(monkeypatch, db_session):
    analyst = models.User(
        username="analyst",
        email="analyst@example.edu",
        password_hash="hashed",
        role="sys_admin",
        is_admin=True,
    )
    request = models.CaseRequest(
        request_type="new_case",
        status="pending",
        case_name="External Matter",
        requestor_email="outside@law.example",
        payload=json.dumps({}),
    )
    db_session.add_all([analyst, request])
    db_session.flush()
    source = models.EmailIntakeMessage(
        mailbox="intake@example.edu",
        graph_message_id="trusted-message",
        status="pending_request",
        case_request_id=request.id,
        sender="outside@law.example",
    )
    db_session.add(source)
    db_session.commit()
    monkeypatch.setattr(case_request_approval_mutation.case_request_core, "_case_naming_mode", lambda: "legal_case_name")
    monkeypatch.setattr(case_requestors, "require_allowed_requestor_email", lambda value: (_ for _ in ()).throw(RuntimeError("organization policy blocked")))

    case_request_approval_mutation.apply_approval_request_mutation(
        db=db_session,
        record=request,
        payload={
            "legal_case_name": "External Matter",
            "internal_counsel": "Internal Counsel",
            "outside_counsel": "Outside Firm",
            "matter_number": "MAT-8",
            "description": "Intake notes",
            "hold_name": "Demand Hold",
            "requestors": [{"email": "outside@law.example", "is_primary": True}],
            "custodians": [],
        },
        analyst_id=analyst.id,
        actor=analyst,
        request=None,
    )
    db_session.commit()
    case = db_session.get(models.Case, request.case_id)
    assert case.requestor == "outside@law.example"
    assert case.internal_counsel == "Internal Counsel"
    assert case.outside_counsel == "Outside Firm"
    assert case.matter_number == "MAT-8"
    assert case.description == "Intake notes"
    assert case.holds[0].name == "Demand Hold"

def test_email_intake_validation_requires_graph_values_and_accepts_complete_config():
    with pytest.raises(ValueError, match="Email Intake is enabled"):
        integration_settings.validate_integration_settings(
            enabled_integrations={"email_intake": True},
            providers={},
            configs={"email_intake": {}},
        )
    integration_settings.validate_integration_settings(
        enabled_integrations={"email_intake": True},
        providers={},
        configs={
            "email_intake": {
                "tenant_id": "tenant",
                "client_id": "client",
                "client_secret": "secret",
                "mailbox": "intake@example.edu",
                "folder_id": "inbox",
                "graph_base": "https://graph.microsoft.com/v1.0",
                "poll_interval_seconds": 60,
                "max_messages_per_poll": 50,
                "sender_policy": "any",
            }
        },
    )


def test_delta_poll_preserves_next_link_for_bounded_continuation(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"value": [sample_graph_message()], "@odata.nextLink": "https://graph.microsoft.com/next-page"}

    seen = []
    monkeypatch.setattr(email_intake_graph, "_request", lambda config, method, url: seen.append((method, url)) or FakeResponse())
    rows, cursor, caught_up = email_intake_graph.delta_messages(settings(max_messages_per_poll=1), None)
    assert len(rows) == 1
    assert cursor == "https://graph.microsoft.com/next-page"
    assert caught_up is False
    assert "/users/intake%40example.edu/mailFolders/inbox/messages/delta" in seen[0][1]


def test_first_poll_establishes_baseline_without_persisting_historical_mail(monkeypatch, db_session):
    monkeypatch.setattr(
        email_intake_service,
        "delta_messages",
        lambda *_: ([sample_graph_message()], "https://graph.microsoft.com/delta-current", True),
    )
    result = email_intake_service.poll_mailbox(db_session, settings=settings())
    assert result["processed"] == 0
    assert result["baseline_skipped"] == 1
    assert result["baseline_pending"] is False
    assert db_session.query(models.EmailIntakeMessage).count() == 0
    cursor = db_session.query(models.EmailIntakeCursor).one()
    assert cursor.delta_link == "https://graph.microsoft.com/delta-current"
    assert cursor.baseline_pending is False

def test_attachments_are_scanned_individually_and_as_archive(monkeypatch, tmp_path):
    message = SimpleNamespace(attachment_count=1, graph_message_id="message-1")
    monkeypatch.setattr(email_intake_service, "message_attachments", lambda *_: [{
        "name": "evidence.txt",
        "content": b"evidence",
        "supported": True,
        "is_inline": False,
    }])
    scans = []
    monkeypatch.setattr(email_intake_service, "scan_payload", lambda payload, filename, **kwargs: scans.append((filename, payload)))
    monkeypatch.setattr(email_intake_service.case_request_core, "CASE_REQUEST_UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(email_intake_service.case_request_core, "MAX_UPLOAD_BYTES", 10_000_000)
    name, path, size, count = email_intake_service._request_attachment_zip(settings(), message)
    assert name == "email-attachments.zip"
    assert path and size > 0 and count == 1
    assert [item[0] for item in scans] == ["evidence.txt", "email-attachments.zip"]