from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import cases, models, schemas


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


def _create_user(db_session, **overrides):
    role = overrides.pop("role", "requestor")
    email = overrides.pop("email", None)
    username = overrides.pop("username", email or f"{role}@example.com")
    user = models.User(
        username=username,
        email=email,
        first_name=overrides.pop("first_name", "Test"),
        last_name=overrides.pop("last_name", "User"),
        password_hash=overrides.pop("password_hash", "hashed"),
        is_admin=overrides.pop("is_admin", role == "sys_admin"),
        role=role,
        requestor_group=overrides.pop("requestor_group", None),
        **overrides,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_apply_ntp_not_required_defaults_uses_manual_reason_for_manual_na():
    case = models.Case(name="Case A", claimant="")
    custodian = models.Custodian(case_id=1, name="User", email="user@example.edu", ntp_status="na")
    custodian.ntp_not_required_reason = "Legal approved exception"

    cases._apply_ntp_not_required_defaults(case, custodian)

    assert custodian.ntp_status == "na"
    assert custodian.ntp_not_required_reason == "Legal approved exception"


def test_requestor_can_update_only_ntp_and_consent_status_fields(db_session, monkeypatch):
    monkeypatch.setattr(cases, "apply_custodian_name_email_review", lambda *_args, **_kwargs: SimpleNamespace(source=None, confidence=None))
    monkeypatch.setattr(cases, "log_event", lambda *_args, **_kwargs: None)
    actor = _create_user(db_session, role="requestor", email="requestor@example.com")
    case = models.Case(name="Case A", requestor="requestor@example.com")
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    custodian = models.Custodian(
        case_id=case.id,
        name="Custodian",
        email="custodian@example.edu",
        ntp_status="not sent",
        consent_status="not sent",
    )
    db_session.add(custodian)
    db_session.commit()
    db_session.refresh(custodian)

    updated = cases.update_custodian(
        case.id,
        custodian.id,
        schemas.CustodianUpdate(
            ntp_status="na",
            ntp_not_required_reason="Outside counsel only",
            consent_status="na",
            consent_not_required_reason="Third-party records only",
        ),
        db=db_session,
        request=None,
        _user=actor,
    )

    assert updated.ntp_status == "na"
    assert updated.ntp_not_required_reason == "Outside counsel only"
    assert updated.consent_status == "na"
    assert updated.consent_not_required_reason == "Third-party records only"


def test_requestor_cannot_update_other_custodian_fields(db_session):
    actor = _create_user(db_session, role="requestor", email="requestor@example.com")
    case = models.Case(name="Case A", requestor="requestor@example.com")
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    custodian = models.Custodian(case_id=case.id, name="Custodian", email="custodian@example.edu")
    db_session.add(custodian)
    db_session.commit()
    db_session.refresh(custodian)

    with pytest.raises(HTTPException) as exc:
        cases.update_custodian(
            case.id,
            custodian.id,
            schemas.CustodianUpdate(name="Changed"),
            db=db_session,
            request=None,
            _user=actor,
        )

    assert exc.value.status_code == 403
    assert "NTP and consent statuses" in exc.value.detail


def test_create_case_ignores_legacy_ler_hr_fields(db_session, monkeypatch):
    monkeypatch.setattr(cases, "log_event", lambda *_args, **_kwargs: None)
    actor = _create_user(db_session, role="sys_admin", email="admin@example.com")

    created = cases.create_case(
        schemas.CaseCreate(
            name="Case LER 1",
            is_ler_hr=True,
            claimant="Request summary text",
            ler_representative="  Jane Representative  ",
        ),
        db=db_session,
        request=None,
        _user=actor,
    )

    stored = db_session.get(models.Case, created.id)

    assert created.is_ler_hr is False
    assert created.ler_representative is None
    assert created.servicenow_inc_number is None
    assert stored is not None
    assert stored.is_ler_hr is False
    assert stored.ler_representative is None


def test_update_case_clears_legacy_ler_hr_fields(db_session, monkeypatch):
    monkeypatch.setattr(cases, "log_event", lambda *_args, **_kwargs: None)
    actor = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = models.Case(
        name="Case LER 2",
        is_ler_hr=True,
        claimant="Request summary text",
        ler_representative="Jane Representative",
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    updated = cases.update_case(
        case.id,
        schemas.CaseUpdate(is_ler_hr=True, ler_representative="Other Rep", servicenow_inc_number="INC999"),
        db=db_session,
        request=None,
        _user=actor,
    )

    stored = db_session.get(models.Case, case.id)

    assert updated.is_ler_hr is False
    assert updated.ler_representative is None
    assert updated.servicenow_inc_number is None
    assert stored is not None
    assert stored.is_ler_hr is False
    assert stored.ler_representative is None


def test_extract_servicenow_error_message_prefers_transform_error():
    from app import servicenow

    message = servicenow._extract_servicenow_error_message(
        [
            {
                "transform_map": "Incident Integration Inbound",
                "table": "incident",
                "status": "error",
                "error_message": "Unable to find Incident Keyword Access_Log_Request in ServiceNow.; Target record not found",
            }
        ],
        {},
    )

    assert message == "Unable to find Incident Keyword Access_Log_Request in ServiceNow.; Target record not found"
