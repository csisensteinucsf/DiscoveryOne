import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_consents, custodians_summary, models


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(custodians_summary, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_consents, "log_event", lambda *args, **kwargs: None)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def create_user(db, role="sys_admin", suffix="admin"):
    user = models.User(
        username=suffix,
        email=f"{suffix}@example.test",
        password_hash="hashed",
        role=role,
        is_admin=role == "sys_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_directory_custodians_are_saved_without_a_case_and_merged_into_list(db_session):
    actor = create_user(db_session)
    payload = custodians_summary.DirectoryCustodianBatch(custodians=[
        {"first_name": "Jane", "last_name": "Doe", "email": "JANE.DOE@example.test", "campus": "Main", "department": "Legal"},
        {"first_name": "Jane", "last_name": "Duplicate", "email": "jane.doe@example.test", "campus": "Main"},
        {"first_name": "John", "last_name": "Smith", "email": "john.smith@example.test", "campus": "South"},
    ])

    result = custodians_summary.add_directory_custodians(
        payload=payload,
        request=None,
        db=db_session,
        actor=actor,
    )

    assert result["created_count"] == 2
    assert result["duplicate_count"] == 1
    assert db_session.query(models.CustodianDirectoryEntry).count() == 2
    rows = custodians_summary.list_custodians(q=None, db=db_session, actor=actor)
    assert [(row["name"], row["email"]) for row in rows] == [
        ("Jane Doe", "jane.doe@example.test"),
        ("John Smith", "john.smith@example.test"),
    ]
    assert all(row["open_cases"] == [] and row["closed_cases"] == [] for row in rows)
    assert rows[0]["first_name"] == "Jane"
    assert rows[0]["campus"] == "Main"
    assert rows[0]["department"] == "Legal"


def test_requestors_cannot_add_directory_custodians(db_session):
    actor = create_user(db_session, role="requestor", suffix="requestor")
    payload = custodians_summary.DirectoryCustodianBatch(custodians=[
        {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.test", "campus": "Main"},
    ])

    with pytest.raises(HTTPException) as exc:
        custodians_summary.add_directory_custodians(
            payload=payload,
            request=None,
            db=db_session,
            actor=actor,
        )

    assert exc.value.status_code == 403


def test_consent_request_is_case_level_and_does_not_require_a_hold(db_session, monkeypatch):
    actor = create_user(db_session)
    case = models.Case(name="Case Consent", legal_case_name="Legal Consent")
    db_session.add(case)
    db_session.flush()
    custodian = models.Custodian(
        case_id=case.id,
        name="Jane Doe",
        email="jane@example.test",
    )
    db_session.add(custodian)
    db_session.commit()

    monkeypatch.setattr(case_consents, "current_esignature_provider", lambda: "test_provider")
    monkeypatch.setattr(case_consents, "send_consent_request", lambda **kwargs: "request-123")

    result = case_consents.send_consent_request_route(
        case_id=case.id,
        payload={
            "record_type": "Email",
            "custodians": [{"custodian_id": custodian.id}],
        },
        db=db_session,
        request=None,
        actor=actor,
    )

    assert result["ok"] is True
    consent = db_session.query(models.CaseConsent).one()
    assert consent.case_id == case.id
    assert consent.custodian_id == custodian.id
    assert consent.hold_custodian_id is None
    db_session.refresh(custodian)
    assert custodian.consent_status == "sent"
