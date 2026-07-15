from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_requests, models


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


class DummyForm(dict):
    def multi_items(self):
        return list(self.items())


class DummyRequest:
    def __init__(self, form_data):
        self._form_data = DummyForm(form_data)
        self.client = SimpleNamespace(host="testclient")
        self.headers = {}

    async def form(self):
        return self._form_data


def _create_user(db_session, *, role: str, email: str, username: str | None = None):
    user = models.User(
        username=username or email,
        email=email,
        first_name="Test",
        last_name="User",
        password_hash="hashed",
        role=role,
        is_admin=(role == "sys_admin"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_case(db_session, *, name: str, requestor_email: str):
    case = models.Case(name=name, requestor=requestor_email)
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


def test_ensure_unique_custodian_emails_rejects_case_insensitive_duplicates():
    with pytest.raises(HTTPException) as exc:
        case_requests._ensure_unique_custodian_emails(
            [
                {"name": "One", "email": "dup@example.edu"},
                {"name": "Two", "email": "DUP@EXAMPLE.EDU"},
            ]
        )

    assert exc.value.status_code == 409
    assert "Duplicate custodian email" in exc.value.detail


def test_create_case_request_rejects_duplicate_existing_case_email(db_session):
    actor = _create_user(db_session, role="requestor", email="requestor@example.com")
    case = _create_case(db_session, name="Case A", requestor_email=actor.email)
    db_session.add(models.Custodian(case_id=case.id, name="Existing", email="dup@example.edu"))
    db_session.commit()

    request = DummyRequest(
        {
            "request_type": "custodian",
            "data": json.dumps(
                {
                    "case_id": case.id,
                    "custodian_entry_mode": "manual",
                    "custodians": [
                        {"name": "Duplicate", "email": "dup@example.edu"},
                    ],
                }
            ),
        }
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(case_requests.create_case_request(request=request, db=db_session, actor=actor))

    assert exc.value.status_code == 409
    assert "already assigned to this case" in exc.value.detail


def test_approve_case_request_rejects_duplicate_existing_case_email(db_session):
    reviewer = _create_user(db_session, role="sys_admin", email="admin@example.com")
    requestor = _create_user(db_session, role="requestor", email="requestor@example.com")
    case = _create_case(db_session, name="Case A", requestor_email=requestor.email)
    db_session.add(models.Custodian(case_id=case.id, name="Existing", email="dup@example.edu"))
    record = models.CaseRequest(
        request_type="custodian",
        status="pending",
        case_id=case.id,
        case_name=case.name,
        payload=json.dumps(
            {
                "case_id": case.id,
                "custodian_entry_mode": "manual",
                "custodians": [
                    {"name": "Duplicate", "email": "dup@example.edu"},
                ],
            }
        ),
        requestor_id=requestor.id,
        requestor_email=requestor.email,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    with pytest.raises(HTTPException) as exc:
        case_requests.approve_case_request(record.id, db=db_session, actor=reviewer, request=None)

    assert exc.value.status_code == 409
    assert "already assigned to this case" in exc.value.detail
