from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, ntp


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


def _create_reminder(db_session, *, case_id: int, custodian_id: int, status: str = "cancelled"):
    token = models.NTPTargetToken(token=f"token-{custodian_id}", case_id=case_id, custodian_id=custodian_id)
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    reminder = models.NTPReminder(
        case_id=case_id,
        custodian_id=custodian_id,
        token_id=token.id,
        interval_days=14,
        next_send_at=datetime.now(timezone.utc) - timedelta(days=1),
        stop_after=datetime.now(timezone.utc) + timedelta(days=7),
        status=status,
    )
    db_session.add(reminder)
    db_session.commit()
    db_session.refresh(reminder)
    return reminder


def test_bulk_reactivate_ntp_reminders_updates_eligible_and_reports_failures(db_session):
    admin = _create_user(db_session, role="sys_admin", email="admin@example.com")
    case = _create_case(db_session, name="Reminder Case", requestor_email="requestor@example.com")
    cust1 = models.Custodian(case_id=case.id, name="One", email="one@example.edu", ntp_status="sent")
    cust2 = models.Custodian(case_id=case.id, name="Two", email="two@example.edu", ntp_status="acknowledged")
    db_session.add_all([cust1, cust2])
    db_session.commit()
    db_session.refresh(cust1)
    db_session.refresh(cust2)
    reminder1 = _create_reminder(db_session, case_id=case.id, custodian_id=cust1.id, status="cancelled")
    reminder2 = _create_reminder(db_session, case_id=case.id, custodian_id=cust2.id, status="cancelled")

    result = ntp.bulk_update_case_ntp_reminders(
        case.id,
        ntp.NTPReminderBulkUpdatePayload(custodian_ids=[cust1.id, cust2.id], enabled=True),
        db=db_session,
        user=admin,
    )

    assert result["updated_count"] == 1
    assert result["failed_count"] == 1
    db_session.refresh(reminder1)
    db_session.refresh(reminder2)
    assert reminder1.status == "active"
    assert reminder2.status == "cancelled"
