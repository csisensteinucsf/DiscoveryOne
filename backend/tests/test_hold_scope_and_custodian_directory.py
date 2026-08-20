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


def test_custodian_profile_edit_updates_directory_and_matter_records(db_session, monkeypatch):
    actor = create_user(db_session, suffix="profile-editor")
    matter = models.Case(name="Profile Matter", legal_case_name="Profile Matter")
    db_session.add(matter)
    db_session.flush()
    directory = models.CustodianDirectoryEntry(
        name="Jane Doe",
        email="jane.doe@example.test",
        first_name="Jane",
        last_name="Doe",
        campus="Main",
        department="Legal",
    )
    custodian = models.Custodian(
        case_id=matter.id,
        name="Jane Doe",
        email="jane.doe@example.test",
        campus="Main",
        person_first_name="Jane",
        person_last_name="Doe",
        person_department="Legal",
    )
    db_session.add_all([directory, custodian])
    db_session.commit()
    events = []
    monkeypatch.setattr(custodians_summary, "log_event", lambda *args, **kwargs: events.append(kwargs))

    result = custodians_summary.update_custodian_profile(
        payload=custodians_summary.DirectoryCustodianInput(
            first_name="Janet",
            last_name="Smith",
            email="janet.smith@example.test",
            campus="West",
            department="Compliance",
            employee_id="E123",
            title="Counsel",
            employment_status="Active",
        ),
        request=None,
        email="jane.doe@example.test",
        name=None,
        db=db_session,
        actor=actor,
    )

    db_session.refresh(directory)
    db_session.refresh(custodian)
    assert (directory.name, directory.email, directory.campus) == (
        "Janet Smith",
        "janet.smith@example.test",
        "West",
    )
    assert (custodian.name, custodian.email, custodian.person_department) == (
        "Janet Smith",
        "janet.smith@example.test",
        "Compliance",
    )
    assert custodian.employee_id == "E123"
    assert result["can_edit"] is True
    assert result["directory_id"] == directory.id
    assert result["first_name"] == "Janet"
    assert events[-1]["action"] == "custodian_directory_update"
    assert events[-1]["details"]["changes"]["email"] == {
        "old": "jane.doe@example.test",
        "new": "janet.smith@example.test",
    }