from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import cases, models, schemas


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(cases, "log_event", lambda *args, **kwargs: None)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def _create_user(db_session, *, role: str, email: str):
    user = models.User(
        username=email,
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


def test_bulk_import_skips_duplicates_and_disables_ai(monkeypatch, db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Bulk Import Case", requestor_email="requestor@example.com")
    db_session.add(models.Custodian(case_id=case.id, name="Existing", email="existing@example.edu"))
    db_session.commit()

    ai_flags = []

    def fake_review(custodian, *, use_ai=True):
        ai_flags.append(use_ai)
        custodian.name_email_review_required = False
        custodian.name_email_review_reason = None
        return SimpleNamespace(source="rules", confidence=0.95)

    monkeypatch.setattr(cases, "apply_custodian_name_email_review", fake_review)

    payload = schemas.CustodianBulkCreateRequest(
        custodians=[
            schemas.CustodianCreate(name="Unique Person", email="unique@example.edu"),
            schemas.CustodianCreate(name="Existing Dup", email="existing@example.edu"),
            schemas.CustodianCreate(name="Batch Dup 1", email="batchdup@example.edu"),
            schemas.CustodianCreate(name="Batch Dup 2", email="BATCHDUP@example.edu"),
        ]
    )

    result = cases.bulk_import_custodians(case.id, payload, db=db_session, request=None, _user=admin)

    assert result.created_count == 2
    assert result.duplicate_count == 2
    assert result.failed_count == 0
    assert sorted(c.email for c in result.created) == ["batchdup@example.edu", "unique@example.edu"]
    assert ai_flags == [False, False]
    assert db_session.query(models.Custodian).filter_by(case_id=case.id).count() == 3


def test_single_add_still_uses_ai_review(monkeypatch, db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Single Add Case", requestor_email="requestor@example.com")

    ai_flags = []

    def fake_review(custodian, *, use_ai=True):
        ai_flags.append(use_ai)
        custodian.name_email_review_required = False
        custodian.name_email_review_reason = None
        return SimpleNamespace(source="llm" if use_ai else "rules", confidence=0.99)

    monkeypatch.setattr(cases, "apply_custodian_name_email_review", fake_review)

    payload = schemas.CustodianCreate(name="Single Person", email="single@example.edu")
    created = cases.add_custodian(case.id, payload, db=db_session, request=None, _user=admin)

    assert created.email == "single@example.edu"
    assert ai_flags == [True]


def test_custodian_create_accepts_generic_person_lookup_fields(monkeypatch, db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Generic Lookup Create Case", requestor_email="requestor@example.com")

    monkeypatch.setattr(
        cases,
        "apply_custodian_name_email_review",
        lambda custodian, *, use_ai=True: SimpleNamespace(source="rules", confidence=1.0),
    )

    created = cases.add_custodian(
        case.id,
        schemas.CustodianCreate(
            name="Generic Person",
            email="generic@example.edu",
            external_id="E12345",
            first_name="Generic",
            last_name="Person",
            department_id="D100",
            department="Legal Operations",
            title="Records Manager",
            current_employee=True,
        ),
        db=db_session,
        request=None,
        _user=admin,
    )

    stored = db_session.get(models.Custodian, created.id)
    assert stored.employee_id == "E12345"
    assert stored.person_first_name == "Generic"
    assert stored.person_last_name == "Person"
    assert stored.person_department_id == "D100"
    assert stored.person_department == "Legal Operations"
    assert stored.person_title == "Records Manager"
    assert stored.person_current_employee is True
    assert created.external_id == "E12345"
    assert created.employee_id == "E12345"
    assert created.first_name == "Generic"
    assert created.last_name == "Person"
    assert created.department_id == "D100"
    assert created.department == "Legal Operations"
    assert created.title == "Records Manager"
    assert created.current_employee is True
