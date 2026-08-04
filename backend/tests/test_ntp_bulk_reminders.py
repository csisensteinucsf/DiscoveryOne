from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_holds, models, ntp


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


def _create_reminder(
    db_session,
    *,
    case_id: int,
    custodian_id: int,
    hold_custodian_id: int,
    status: str = "cancelled",
    token_suffix: str = "",
):
    token = models.NTPTargetToken(
        token=f"token-{custodian_id}{token_suffix}",
        case_id=case_id,
        custodian_id=custodian_id,
        hold_custodian_id=hold_custodian_id,
    )
    db_session.add(token)
    db_session.commit()
    db_session.refresh(token)
    reminder = models.NTPReminder(
        case_id=case_id,
        custodian_id=custodian_id,
        hold_custodian_id=hold_custodian_id,
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
    hold = case_holds.ensure_default_hold(db_session, case, assign_existing=True)
    db_session.commit()
    membership1 = db_session.query(models.HoldCustodian).filter_by(hold_id=hold.id, custodian_id=cust1.id).one()
    membership2 = db_session.query(models.HoldCustodian).filter_by(hold_id=hold.id, custodian_id=cust2.id).one()
    reminder1 = _create_reminder(
        db_session,
        case_id=case.id,
        custodian_id=cust1.id,
        hold_custodian_id=membership1.id,
        status="cancelled",
    )
    reminder2 = _create_reminder(
        db_session,
        case_id=case.id,
        custodian_id=cust2.id,
        hold_custodian_id=membership2.id,
        status="cancelled",
    )

    result = ntp.bulk_update_case_ntp_reminders(
        case.id,
        ntp.NTPReminderBulkUpdatePayload(
            case_hold_id=hold.id,
            custodian_ids=[cust1.id, cust2.id],
            enabled=True,
        ),
        db=db_session,
        user=admin,
    )

    assert result["updated_count"] == 1
    assert result["failed_count"] == 1
    db_session.refresh(reminder1)
    db_session.refresh(reminder2)
    assert reminder1.status == "active"
    assert reminder2.status == "cancelled"

def test_acknowledgement_changes_only_the_token_hold_membership(monkeypatch, db_session):
    case = _create_case(db_session, name="Two Hold Case", requestor_email="requestor@example.com")
    custodian = models.Custodian(
        case_id=case.id,
        name="Shared Person",
        email="shared@example.edu",
        ntp_status="sent",
    )
    db_session.add(custodian)
    db_session.commit()
    first_hold = case_holds.ensure_default_hold(db_session, case, assign_existing=True)
    second_hold = models.CaseHold(case_id=case.id, name="Hold B", sort_order=1)
    db_session.add(second_hold)
    db_session.flush()
    second_membership = models.HoldCustodian(
        hold_id=second_hold.id,
        custodian_id=custodian.id,
        ntp_status="sent",
    )
    db_session.add(second_membership)
    db_session.commit()
    first_membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=first_hold.id,
        custodian_id=custodian.id,
    ).one()

    token, raw_token = ntp._create_ntp_token(
        db_session,
        case_id=case.id,
        custodian_id=custodian.id,
        template_id=None,
        hold_custodian_id=first_membership.id,
    )
    first_reminder = models.NTPReminder(
        case_id=case.id,
        custodian_id=custodian.id,
        hold_custodian_id=first_membership.id,
        token_id=token.id,
        interval_days=14,
        next_send_at=datetime.now(timezone.utc) + timedelta(days=1),
        stop_after=datetime.now(timezone.utc) + timedelta(days=30),
        status="active",
    )
    second_token, _ = ntp._create_ntp_token(
        db_session,
        case_id=case.id,
        custodian_id=custodian.id,
        template_id=None,
        hold_custodian_id=second_membership.id,
    )
    second_reminder = models.NTPReminder(
        case_id=case.id,
        custodian_id=custodian.id,
        hold_custodian_id=second_membership.id,
        token_id=second_token.id,
        interval_days=14,
        next_send_at=datetime.now(timezone.utc) + timedelta(days=1),
        stop_after=datetime.now(timezone.utc) + timedelta(days=30),
        status="active",
    )
    db_session.add_all([first_reminder, second_reminder])
    db_session.commit()
    first_membership_id = first_membership.id
    second_membership_id = second_membership.id
    first_reminder_id = first_reminder.id
    second_reminder_id = second_reminder.id

    monkeypatch.setattr(ntp, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(ntp, "log_event", lambda *args, **kwargs: None)
    result = ntp._process_ntp_ack(raw_token)

    assert result["status"] == "recorded"
    first_membership = db_session.get(models.HoldCustodian, first_membership_id)
    second_membership = db_session.get(models.HoldCustodian, second_membership_id)
    first_reminder = db_session.get(models.NTPReminder, first_reminder_id)
    second_reminder = db_session.get(models.NTPReminder, second_reminder_id)
    assert first_membership.ntp_status == "acknowledged"
    assert second_membership.ntp_status == "sent"
    assert first_reminder.status == "completed"
    assert second_reminder.status == "active"
