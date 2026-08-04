from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import (
    case_ticketing_emails,
    docusign_webhook,
    logs,
    models,
    notes,
    notes_support,
    ntp,
    reports,
    servicenow,
    session_tokens,
)


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


def _user(role: str, *, user_id: int = 1, username: str | None = None):
    return SimpleNamespace(
        id=user_id,
        role=role,
        is_admin=role == "sys_admin",
        username=username or f"{role}-user",
        email=f"{role}@example.edu",
    )


def test_note_author_is_always_authenticated_username(monkeypatch):
    created = []

    class FakeDB:
        def add(self, row):
            row.id = 41
            row.attachments = []
            created.append(row)

        def commit(self):
            return None

        def refresh(self, _row):
            return None

        def get(self, *_args):
            return SimpleNamespace(name="TEST Case")

    monkeypatch.setattr(notes, "_ensure_case", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notes, "ensure_case_editable", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notes, "_sync_case_note_counters", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(notes, "log_event", lambda *_args, **_kwargs: None)
    actor = _user("analyst", username="actual-analyst")

    notes.create_note(
        7,
        notes.NoteCreate(body="record note", author="forged-admin"),
        db=FakeDB(),
        request=None,
        user=actor,
    )

    assert created[0].author == "actual-analyst"


def test_ticket_notes_allow_tester_read_but_block_tester_write():
    tester = _user("tester")
    notes_support._ensure_ticket_note_access(tester, write=False)
    with pytest.raises(HTTPException) as exc:
        notes_support._ensure_ticket_note_access(tester, write=True)
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    ("endpoint", "role"),
    [("ticket", "requestor"), ("ticket", "tester"), ("hold", "tester")],
)
def test_restricted_roles_cannot_trigger_ticket_or_hold_emails(monkeypatch, endpoint, role):
    case = SimpleNamespace(id=10, request_ticket_entries=[])
    db = SimpleNamespace(get=lambda *_args: case)
    monkeypatch.setattr(
        case_ticketing_emails.ticket_core,
        "ensure_case_visible",
        lambda *_args, **_kwargs: None,
    )
    actor = _user(role)
    with pytest.raises(HTTPException) as exc:
        if endpoint == "ticket":
            case_ticketing_emails.send_external_ticket_email(
                10,
                SimpleNamespace(entry_id="entry-1"),
                db=db,
                _user=actor,
            )
        else:
            case_ticketing_emails.send_requestor_hold_status_email(
                10,
                db=db,
                request=None,
                _user=actor,
            )
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["requestor", "analyst", "tester", "tech"])
def test_global_audit_log_scope_requires_sys_admin(role):
    with pytest.raises(HTTPException) as exc:
        logs._log_scope(None, _user(role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["requestor", "tester", "tech"])
def test_case_timeline_requires_case_editor(role):
    with pytest.raises(HTTPException) as exc:
        reports._case_timeline_items(None, 10, 100, _user(role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("bulk", [False, True])
def test_tester_cannot_modify_ntp_reminders(monkeypatch, bulk):
    class FakeDB:
        def get(self, *_args):
            return SimpleNamespace(id=10)

    monkeypatch.setattr(ntp, "ensure_case_visible", lambda *_args, **_kwargs: None)
    actor = _user("tester")
    with pytest.raises(HTTPException) as exc:
        if bulk:
            ntp.bulk_update_case_ntp_reminders(
                10,
                ntp.NTPReminderBulkUpdatePayload(custodian_ids=[5], enabled=False),
                db=FakeDB(),
                user=actor,
            )
        else:
            ntp.update_case_ntp_reminders(
                10,
                5,
                ntp.NTPReminderUpdatePayload(enabled=False),
                db=FakeDB(),
                user=actor,
            )
    assert exc.value.status_code == 403


def test_ntp_acknowledgement_get_page_does_not_process_token(monkeypatch):
    class FakeDB:
        def close(self):
            return None

    monkeypatch.setattr(ntp, "SessionLocal", FakeDB)
    monkeypatch.setattr(
        ntp,
        "_find_ntp_token",
        lambda *_args: SimpleNamespace(used_at=None, created_at=datetime.now(timezone.utc)),
    )
    monkeypatch.setattr(ntp, "_process_ntp_ack", lambda *_args: pytest.fail("GET must not acknowledge"))
    response = ntp.acknowledge_ntp("opaque-token", action_path="/ntp/ack/opaque-token")
    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert 'method="post"' in body.lower()
    assert "Confirm acknowledgement" in body


def test_unused_ntp_token_expires_after_configured_lifetime(monkeypatch):
    monkeypatch.setattr(ntp, "ntp_ack_token_ttl_days", lambda: 90)
    token = SimpleNamespace(
        used_at=None,
        created_at=datetime.now(timezone.utc) - timedelta(days=91),
    )
    assert ntp._ntp_token_expired(token, now=datetime.now(timezone.utc)) is True


@pytest.mark.parametrize(
    ("current", "incoming", "allowed"),
    [
        ("sent", "delivered", True),
        ("delivered", "sent", False),
        ("completed", "sent", False),
        ("completed", "completed", False),
        ("declined", "completed", False),
    ],
)
def test_docusign_status_transitions_are_monotonic_and_idempotent(current, incoming, allowed):
    assert docusign_webhook._should_apply_status_transition(current, incoming) is allowed


def test_refresh_token_can_only_be_consumed_once(db_session):
    raw_token = "refresh-token-value"
    row = models.RefreshToken(
        id=str(uuid4()),
        user_id="22",
        jti=str(uuid4()),
        token_hash=session_tokens._fingerprint(raw_token),
        user_agent="pytest-browser",
        ip="127.0.0.1",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        revoked_at=None,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()

    first = session_tokens.consume_valid_refresh(
        db_session,
        raw_token,
        user_agent="pytest-browser",
        ip="127.0.0.1",
    )
    second = session_tokens.consume_valid_refresh(
        db_session,
        raw_token,
        user_agent="pytest-browser",
        ip="127.0.0.1",
    )

    assert first is not None
    assert second is None


@pytest.mark.parametrize("value", ["INC123^ORactive=true", "INC1,INC2", "INC 123", "INC123@javascript"])
def test_servicenow_ticket_numbers_reject_encoded_query_metacharacters(value):
    with pytest.raises(servicenow.ServiceNowError):
        servicenow._normalize_ticket_numbers([value])


def test_servicenow_ticket_numbers_accept_common_identifiers():
    assert servicenow._normalize_ticket_numbers(["INC0012345", "REQ-2026_0042"]) == [
        "INC0012345",
        "REQ-2026_0042",
    ]


def test_only_provider_managed_ticket_entries_are_eligible_for_remote_lookup():
    assert notes is not None  # keep import-time route composition covered
    assert servicenow is not None
    from app import case_ticketing

    entries = [
        {"id": "manual", "ticket": "INC001", "provider_managed": False},
        {"id": "provider", "ticket": "INC002", "provider_managed": True},
    ]
    assert case_ticketing._provider_managed_ticket_numbers(entries) == ["INC002"]
