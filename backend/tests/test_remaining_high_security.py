import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_request_create, models, note_attachments, ntp_rendering


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


def _user(db, username, role):
    row = models.User(
        username=username,
        email=username,
        password_hash="unused",
        role=role,
        is_admin=role == "sys_admin",
        is_active=True,
        requestor_group="legal" if role == "requestor" else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_ntp_sender_variables_cannot_add_cc_or_bcc_recipients():
    cleaned = ntp_rendering._normalize_variables(
        {
            "case_name": "Matter",
            "cc": "attacker@example.com",
            "bcc": "hidden@example.com",
        }
    )

    assert cleaned == {"case_name": "Matter"}
    assert ntp_rendering._merge_cc_lists("approved@example.edu", cleaned.get("cc")) == [
        "approved@example.edu"
    ]


@pytest.mark.parametrize("write", [True, False])
def test_active_note_attachments_require_system_admin(write):
    note = SimpleNamespace(audience="active")
    analyst = SimpleNamespace(role="analyst", is_admin=False)

    with pytest.raises(HTTPException) as exc:
        note_attachments._ensure_note_attachment_access(note, analyst, write=write)

    assert exc.value.status_code == 403


def test_active_note_attachment_access_allows_system_admin():
    note = SimpleNamespace(audience="active")
    admin = SimpleNamespace(role="sys_admin", is_admin=True)
    note_attachments._ensure_note_attachment_access(note, admin, write=True)
    note_attachments._ensure_note_attachment_access(note, admin, write=False)


def test_requestor_custodian_request_remains_pending_for_review(db_session, monkeypatch):
    actor = _user(db_session, "requestor@example.edu", "requestor")
    case = models.Case(
        name="Pending Review Matter",
        requestor=actor.email,
        is_private=False,
        closed=False,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    class FormRequest:
        async def form(self):
            return {
                "request_type": "custodian",
                "data": json.dumps({"case_id": case.id, "custodians": []}),
            }

    async def no_proofs(*_args, **_kwargs):
        return {}

    core = case_request_create.case_request_core
    persisted_proofs = []
    monkeypatch.setattr(core, "ensure_case_request_access", lambda *_args: None)
    monkeypatch.setattr(core, "_enforce_pending_limits", lambda *_args: None)
    monkeypatch.setattr(core, "_extract_consent_proof_blobs", no_proofs)
    monkeypatch.setattr(core, "_collect_custodians_from_payload", lambda *_args: [])
    monkeypatch.setattr(core, "_ensure_unique_custodian_emails", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "log_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "notify_case_request_submitted", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core, "_serialize_request", lambda record, **_kwargs: {"status": record.status})
    monkeypatch.setattr(core, "MAX_PENDING_STORAGE_BYTES", 0)
    monkeypatch.setattr(
        core,
        "_persist_consent_proofs",
        lambda _db, record, consents, blobs: persisted_proofs.append(
            (record.id, consents, blobs)
        ),
    )

    result = asyncio.run(
        case_request_create.create_case_request(
            FormRequest(),
            db=db_session,
            actor=actor,
        )
    )

    record = db_session.query(models.CaseRequest).one()
    assert result == {"status": "pending"}
    assert record.status == "pending"
    assert persisted_proofs == [(record.id, [], {})]
    assert record.reviewed_at is None
    assert record.reviewed_by_id is None
    assert db_session.query(models.Custodian).count() == 0
