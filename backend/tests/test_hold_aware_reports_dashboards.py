from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import dashboard_resolvers, models, reports


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


def _seed(db):
    user = models.User(
        username="admin",
        email="admin@example.edu",
        password_hash="hashed",
        role="sys_admin",
        is_admin=True,
    )
    case = models.Case(name="Hold Report Matter", requestor="requestor@example.edu")
    db.add_all([user, case])
    db.flush()
    custodian = models.Custodian(
        case_id=case.id,
        name="Shared Person",
        email="shared@example.edu",
        ntp_status="acknowledged",
        consent_status="received",
    )
    hold = models.CaseHold(case_id=case.id, name="Hold A", status="active")
    db.add_all([custodian, hold])
    db.flush()
    membership = models.HoldCustodian(
        hold_id=hold.id,
        custodian_id=custodian.id,
        ntp_status="not sent",
        consent_status="sent",
    )
    search = models.Search(
        case_id=case.id,
        name="Search One",
        status_search="performed",
        status_export="performed",
    )
    db.add_all([membership, search])
    db.flush()
    source = models.HoldPreservationSource(
        hold_custodian_id=membership.id,
        source_key="email",
        source_label="Email",
        status="pending",
    )
    hold_search = models.HoldSearch(
        hold_id=hold.id,
        search_id=search.id,
        status_search="not performed",
        status_export="not performed",
        status_delivery="not performed",
    )
    db.add_all([source, hold_search])
    db.commit()
    return user, case


def test_reports_use_hold_membership_status_instead_of_legacy_custodian_status(db_session):
    _user, case = _seed(db_session)

    summary = reports._cases_summary_items(db_session, {case.id}, open_only=False)[0]
    status_rows = reports._ntp_consent_summary_items(db_session, {case.id})
    by_key = {(row["type"], row["status"]): row["count"] for row in status_rows}

    assert summary["holds_total"] == 1
    assert summary["custodian_hold_links"] == 1
    assert summary["ntp_acknowledged"] == 0
    assert summary["ntp_sent"] == 0
    assert summary["consent_sent"] == 1
    assert summary["search_done"] == 0
    assert by_key[("NTP", "not sent")] == 1
    assert by_key[("Consent", "sent")] == 1


def test_dashboard_metrics_use_hold_sources_and_hold_search_links(db_session):
    user, _case = _seed(db_session)

    ntp = dashboard_resolvers._resolve_ntp_status(db_session, user, config={"open_only": True})
    holds = dashboard_resolvers._resolve_hold_status(db_session, user, config={"open_only": True})
    searches = dashboard_resolvers._resolve_search_status(db_session, user, config={"open_only": True})

    assert ntp["by_status"] == {"not sent": 1}
    assert holds["pending_any"] == 1
    assert holds["pending_by_type"] == {"email": 1}
    assert searches["search_performed"] == 0
    assert searches["search_not_performed"] == 1