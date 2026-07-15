from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_requests, cases, models, schemas


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


def test_bulk_custodian_update_skips_ai_for_hold_only_changes(monkeypatch, db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Bulk Update Case", requestor_email="requestor@example.com")
    cust1 = models.Custodian(case_id=case.id, name="One", email="one@example.edu")
    cust2 = models.Custodian(case_id=case.id, name="Two", email="two@example.edu")
    db_session.add_all([cust1, cust2])
    db_session.commit()
    db_session.refresh(cust1)
    db_session.refresh(cust2)

    ai_flags = []

    def fake_review(custodian, *, use_ai=True):
        ai_flags.append(use_ai)
        custodian.name_email_review_required = False
        custodian.name_email_review_reason = None
        return SimpleNamespace(source="llm", confidence=0.99)

    monkeypatch.setattr(cases, "apply_custodian_name_email_review", fake_review)

    payload = schemas.CustodianBulkUpdateRequest(
        ids=[cust1.id, cust2.id],
        patch=schemas.CustodianUpdate(holds_email=True),
    )
    result = cases.bulk_update_custodians(case.id, payload, db=db_session, request=None, _user=admin)

    assert result.updated_count == 2
    assert ai_flags == []
    refreshed = db_session.query(models.Custodian).filter_by(case_id=case.id).order_by(models.Custodian.id.asc()).all()
    assert all(bool(item.holds_email) for item in refreshed)


def test_single_custodian_identity_update_still_uses_ai(monkeypatch, db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Single Update Case", requestor_email="requestor@example.com")
    cust = models.Custodian(case_id=case.id, name="One", email="one@example.edu")
    db_session.add(cust)
    db_session.commit()
    db_session.refresh(cust)

    ai_flags = []

    def fake_review(custodian, *, use_ai=True):
        ai_flags.append(use_ai)
        custodian.name_email_review_required = False
        custodian.name_email_review_reason = None
        return SimpleNamespace(source="llm", confidence=0.99)

    monkeypatch.setattr(cases, "apply_custodian_name_email_review", fake_review)

    updated = cases.update_custodian(
        case.id,
        cust.id,
        schemas.CustodianUpdate(email="renamed@example.edu"),
        db=db_session,
        request=None,
        _user=admin,
    )

    assert updated.email == "renamed@example.edu"
    assert ai_flags == [True]


def test_case_request_custodian_model_can_skip_ai(monkeypatch):
    ai_flags = []

    def fake_review(custodian, *, use_ai=True):
        ai_flags.append(use_ai)
        custodian.name_email_review_required = False
        custodian.name_email_review_reason = None
        return SimpleNamespace(source="rules", confidence=0.95)

    monkeypatch.setattr(case_requests, "apply_custodian_name_email_review", fake_review)

    model = case_requests._custodian_model(
        1,
        {"name": "Requestor Person", "email": "requestor.person@example.edu"},
        False,
        use_ai_review=False,
    )

    assert model.email == "requestor.person@example.edu"
    assert ai_flags == [False]


def test_custodian_update_accepts_generic_person_lookup_fields(monkeypatch, db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Generic Lookup Update Case", requestor_email="requestor@example.com")
    cust = models.Custodian(case_id=case.id, name="Generic", email="generic@example.edu")
    db_session.add(cust)
    db_session.commit()
    db_session.refresh(cust)

    monkeypatch.setattr(
        cases,
        "apply_custodian_name_email_review",
        lambda custodian, *, use_ai=True: SimpleNamespace(source="rules", confidence=1.0),
    )

    updated = cases.update_custodian(
        case.id,
        cust.id,
        schemas.CustodianUpdate(
            employee_id="E67890",
            first_name="Updated",
            last_name="Person",
            department="Human Resources",
            title="HR Partner",
            current_employee=False,
        ),
        db=db_session,
        request=None,
        _user=admin,
    )

    stored = db_session.get(models.Custodian, cust.id)
    assert stored.employee_id == "E67890"
    assert stored.person_first_name == "Updated"
    assert stored.person_last_name == "Person"
    assert stored.person_department == "Human Resources"
    assert stored.person_title == "HR Partner"
    assert stored.person_current_employee is False
    assert updated.external_id == "E67890"
    assert updated.employee_id == "E67890"
    assert updated.first_name == "Updated"
    assert updated.last_name == "Person"
    assert updated.department == "Human Resources"
    assert updated.title == "HR Partner"
    assert updated.current_employee is False
