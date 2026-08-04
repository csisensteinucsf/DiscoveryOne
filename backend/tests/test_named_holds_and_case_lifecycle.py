from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_custodian_bulk_import, case_custodians, case_holds, case_purview, case_update, cases, hold_workflows, models, schemas


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(case_holds, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(cases, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_update.case_core, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_update.case_core, "notify_case_requestor_case_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_update.case_core, "_maybe_create_box_hold_release_ticket", lambda *args, **kwargs: None)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def create_user(db, role="sys_admin", suffix="admin"):
    user = models.User(
        username=suffix,
        email=suffix + "@example.edu",
        password_hash="hashed",
        role=role,
        is_admin=role == "sys_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_case(db, name="Matter One"):
    case = models.Case(name=name, legal_case_name=name, requestor="requestor@example.edu")
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


def create_hold(db, case, *, name="Hold A", custodians=(), sort_order=0):
    hold = models.CaseHold(case_id=case.id, name=name, status="active", sort_order=sort_order)
    db.add(hold)
    db.flush()
    ids = [int(custodian.id) for custodian in custodians]
    if ids:
        case_holds.assign_custodians_to_hold(
            db,
            case_id=case.id,
            hold_id=hold.id,
            custodian_ids=ids,
        )
    return hold


def test_default_hold_copies_legacy_member_workflow_and_preservation(monkeypatch, db_session):
    monkeypatch.setattr(
        case_holds,
        "configured_hold_catalog",
        lambda enabled_only=True: [
            ("email", "holds_email", "Email"),
            ("slack", "holds_slack", "Slack"),
        ],
    )
    case = create_case(db_session)
    custodian = models.Custodian(
        case_id=case.id,
        name="Person One",
        email="person.one@example.edu",
        ntp_status="sent",
        consent_status="received",
        holds_email=True,
        holds_slack_pending=True,
    )
    db_session.add(custodian)
    db_session.commit()

    hold = create_hold(db_session, case, custodians=[custodian])
    db_session.commit()

    membership = db_session.query(models.HoldCustodian).filter_by(hold_id=hold.id, custodian_id=custodian.id).one()
    sources = {
        row.source_key: row.status
        for row in db_session.query(models.HoldPreservationSource).filter_by(hold_custodian_id=membership.id).all()
    }
    assert hold.name == "Hold A"
    assert membership.ntp_status == "sent"
    assert membership.consent_status == "received"
    assert sources == {"email": "active", "slack": "pending"}


def test_same_custodian_can_have_independent_status_in_multiple_holds(monkeypatch, db_session):
    monkeypatch.setattr(
        case_holds,
        "configured_hold_catalog",
        lambda enabled_only=True: [("email", "holds_email", "Email")],
    )
    admin = create_user(db_session)
    case = create_case(db_session)
    custodian = models.Custodian(
        case_id=case.id,
        name="Person One",
        email="person.one@example.edu",
        holds_email=True,
    )
    db_session.add(custodian)
    db_session.commit()
    first = create_hold(db_session, case, custodians=[custodian])
    db_session.commit()

    second_payload = case_holds.CaseHoldCreate(name="Hold B")
    second_data = case_holds.create_case_hold(
        case.id,
        second_payload,
        db=db_session,
        request=None,
        user=admin,
    )
    second_id = second_data["id"]
    case_holds.add_hold_custodians(
        case.id,
        second_id,
        case_holds.HoldCustodianAssignment(custodian_ids=[custodian.id]),
        db=db_session,
        request=None,
        user=admin,
    )
    case_holds.update_hold_preservation(
        case.id,
        second_id,
        custodian.id,
        "email",
        case_holds.HoldPreservationUpdate(status="released"),
        db=db_session,
        request=None,
        user=admin,
    )

    first_membership = db_session.query(models.HoldCustodian).filter_by(hold_id=first.id, custodian_id=custodian.id).one()
    second_membership = db_session.query(models.HoldCustodian).filter_by(hold_id=second_id, custodian_id=custodian.id).one()
    first_status = db_session.query(models.HoldPreservationSource).filter_by(
        hold_custodian_id=first_membership.id,
        source_key="email",
    ).one().status
    second_status = db_session.query(models.HoldPreservationSource).filter_by(
        hold_custodian_id=second_membership.id,
        source_key="email",
    ).one().status

    assert first_status == "active"
    assert second_status == "released"


def test_close_and_reopen_track_closed_at(db_session):
    analyst = create_user(db_session, role="analyst", suffix="analyst")
    case = create_case(db_session)

    closed = case_update.update_case_record(
        case_id=case.id,
        payload=schemas.CaseUpdate(closed=True),
        db=db_session,
        request=None,
        user=analyst,
    )
    assert closed.closed is True
    assert closed.closed_at is not None

    reopened = case_update.update_case_record(
        case_id=case.id,
        payload=schemas.CaseUpdate(closed=False),
        db=db_session,
        request=None,
        user=analyst,
    )
    assert reopened.closed is False
    assert reopened.closed_at is None


def test_case_stats_report_active_and_total_named_hold_counts(db_session):
    admin = create_user(db_session, suffix="hold-count-admin")
    case = create_case(db_session, name="Hold Count Matter")
    db_session.add_all([
        models.CaseHold(case_id=case.id, name="Hold A", status="active", sort_order=0),
        models.CaseHold(case_id=case.id, name="Hold B", status="closed", sort_order=1),
    ])
    db_session.commit()

    result = cases.case_stats(
        {"case_ids": [case.id]},
        db=db_session,
        request=None,
        _user=admin,
    )

    assert result[str(case.id)]["namedHoldCount"] == 2
    assert result[str(case.id)]["namedHoldActiveCount"] == 1

def test_permanent_delete_is_admin_only_and_history_requires_reason(monkeypatch, db_session):
    admin = create_user(db_session, role="sys_admin", suffix="admin-delete")
    analyst = create_user(db_session, role="analyst", suffix="analyst-delete")
    case = create_case(db_session, name="Delete Guard Matter")
    db_session.add(models.CaseNote(case_id=case.id, body="Important history"))
    db_session.commit()
    monkeypatch.setattr(cases, "notify_case_requestor_case_event", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as non_admin:
        cases.delete_case(case.id, db=db_session, request=None, _user=analyst)
    assert non_admin.value.status_code == 403

    with pytest.raises(HTTPException) as history_block:
        cases.delete_case(case.id, db=db_session, request=None, _user=admin)
    assert history_block.value.status_code == 409
    assert history_block.value.detail["history"]["notes"] == 1

    with pytest.raises(HTTPException) as short_reason:
        cases.delete_case(
            case.id,
            override=True,
            override_reason="too short",
            db=db_session,
            request=None,
            _user=admin,
        )
    assert short_reason.value.status_code == 422

    result = cases.delete_case(
        case.id,
        override=True,
        override_reason="Duplicate test case created in error",
        db=db_session,
        request=None,
        _user=admin,
    )
    assert result == {"ok": True}
    assert db_session.get(models.Case, case.id) is None

def test_named_hold_preservation_automation_falls_back_to_manual_tracking(monkeypatch, db_session):
    monkeypatch.setattr(
        case_holds,
        "configured_hold_catalog",
        lambda enabled_only=True: [("slack", "holds_slack", "Slack")],
    )
    monkeypatch.setattr(case_holds, "_source_automation_ready", lambda _source: False)
    admin = create_user(db_session, suffix="manual-preservation")
    case = create_case(db_session, name="Manual Preservation")
    custodian = models.Custodian(
        case_id=case.id,
        name="Shared Person",
        email="shared@example.edu",
    )
    db_session.add(custodian)
    db_session.commit()
    hold = create_hold(db_session, case, custodians=[custodian])
    db_session.commit()

    result = case_holds.automate_hold_preservation(
        case.id,
        hold.id,
        custodian.id,
        "slack",
        case_holds.HoldPreservationAutomation(enabled=True),
        db=db_session,
        request=None,
        user=admin,
    )

    assert result["mode"] == "manual"
    assert result["automation_ready"] is False
    membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=hold.id,
        custodian_id=custodian.id,
    ).one()
    source = db_session.query(models.HoldPreservationSource).filter_by(
        hold_custodian_id=membership.id,
        source_key="slack",
    ).one()
    assert source.status == "pending"
    db_session.refresh(custodian)
    assert custodian.holds_slack_pending is True


def test_named_hold_preservation_uses_configured_source_adapter(monkeypatch, db_session):
    monkeypatch.setattr(
        case_holds,
        "configured_hold_catalog",
        lambda enabled_only=True: [("slack", "holds_slack", "Slack")],
    )
    monkeypatch.setattr(case_holds, "_source_automation_ready", lambda _source: True)
    calls = []
    monkeypatch.setattr(
        case_holds,
        "sync_hold_or_raise",
        lambda case, custodian, **kwargs: calls.append((case.id, custodian.id, kwargs)) or {"status": "enabled"},
    )
    admin = create_user(db_session, suffix="auto-preservation")
    case = create_case(db_session, name="Automated Preservation")
    custodian = models.Custodian(
        case_id=case.id,
        name="Automated Person",
        email="automated@example.edu",
    )
    db_session.add(custodian)
    db_session.commit()
    hold = create_hold(db_session, case, custodians=[custodian])
    db_session.commit()

    result = case_holds.automate_hold_preservation(
        case.id,
        hold.id,
        custodian.id,
        "slack",
        case_holds.HoldPreservationAutomation(enabled=True),
        db=db_session,
        request=None,
        user=admin,
    )

    assert result["mode"] == "automated"
    assert calls and calls[0][2]["source_key"] == "slack"
    membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=hold.id,
        custodian_id=custodian.id,
    ).one()
    source = db_session.query(models.HoldPreservationSource).filter_by(
        hold_custodian_id=membership.id,
        source_key="slack",
    ).one()
    assert source.status == "active"

def test_provider_hold_route_updates_only_selected_named_hold(monkeypatch, db_session):
    admin = create_user(db_session, suffix="provider-route")
    case = create_case(db_session, name="Provider Route")
    custodian = models.Custodian(
        case_id=case.id,
        name="Shared Provider Person",
        email="provider@example.edu",
    )
    db_session.add(custodian)
    db_session.commit()
    first_hold = create_hold(db_session, case, custodians=[custodian])
    second_hold = models.CaseHold(case_id=case.id, name="Hold B", sort_order=1)
    db_session.add(second_hold)
    db_session.flush()
    case_holds.assign_custodians_to_hold(
        db_session,
        case_id=case.id,
        hold_id=second_hold.id,
        custodian_ids=[custodian.id],
    )
    db_session.commit()
    second_membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=second_hold.id,
        custodian_id=custodian.id,
    ).one()
    first_membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=first_hold.id,
        custodian_id=custodian.id,
    ).one()

    monkeypatch.setattr(
        case_purview.preservation_provider,
        "apply_holds",
        lambda **_kwargs: {
            "results": [{"custodian_id": custodian.id, "status": "on_hold"}],
            "updated_custodians": [{
                "id": custodian.id,
                "holds_email": True,
                "holds_email_pending": False,
                "holds_email_failed": False,
                "holds_email_released": False,
            }],
        },
    )
    result = case_purview.apply_purview_holds(
        case.id,
        schemas.PreservationHoldRequest(
            case_hold_id=first_hold.id,
            custodian_ids=[custodian.id],
            included_sources=["mailbox"],
        ),
        db=db_session,
        request=None,
        _user=admin,
    )

    assert result["case_hold_id"] == first_hold.id
    first_source = db_session.query(models.HoldPreservationSource).filter_by(
        hold_custodian_id=first_membership.id,
        source_key="email",
    ).one()
    second_source = db_session.query(models.HoldPreservationSource).filter_by(
        hold_custodian_id=second_membership.id,
        source_key="email",
    ).one()
    assert first_source.status == "active"
    assert second_source.status == "not_started"


def test_searches_support_multiple_holds_and_allow_no_assignment(db_session):
    case = create_case(db_session, name="Search Hold Matter")
    first_hold = create_hold(db_session, case)
    second_hold = models.CaseHold(case_id=case.id, name="Hold B", sort_order=1)
    db_session.add(second_hold)
    db_session.flush()

    shared_search = models.Search(case_id=case.id, name="Shared Search")
    db_session.add(shared_search)
    db_session.flush()
    assigned = hold_workflows.set_search_holds(
        db_session,
        search=shared_search,
        hold_ids=[first_hold.id, second_hold.id],
    )
    shared_search.status_search = "performed"
    shared_search.status_export = "performed"
    hold_workflows.sync_search_hold_statuses(db_session, shared_search)

    default_search = models.Search(case_id=case.id, name="Default Search")
    db_session.add(default_search)
    db_session.flush()
    default_assigned = hold_workflows.set_search_holds(
        db_session,
        search=default_search,
        hold_ids=None,
    )
    db_session.commit()

    assert assigned == [first_hold.id, second_hold.id]
    rows = db_session.query(models.HoldSearch).filter_by(search_id=shared_search.id).all()
    assert {row.hold_id for row in rows} == {first_hold.id, second_hold.id}
    assert {row.status_search for row in rows} == {"performed"}
    assert {row.status_export for row in rows} == {"performed"}
    assert default_assigned == []
    default_rows = db_session.query(models.HoldSearch).filter_by(search_id=default_search.id).all()
    assert default_rows == []
def test_bulk_custodian_import_assigns_every_selected_hold_atomically(monkeypatch, db_session):
    admin = create_user(db_session, suffix="multi-hold-import")
    case = create_case(db_session, name="Multi Hold Import")
    first_hold = create_hold(db_session, case)
    second_hold = models.CaseHold(case_id=case.id, name="Hold B", status="active", sort_order=1)
    db_session.add(second_hold)
    db_session.commit()
    monkeypatch.setattr(case_custodians, "_bulk_import_log_summary", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_custodians, "_log_custodian_create_success", lambda *args, **kwargs: None)

    result = case_custodian_bulk_import.bulk_import_custodians_for_case(
        case_id=case.id,
        payload=schemas.CustodianBulkCreateRequest(
            custodians=[
                schemas.CustodianCreate(
                    name="Multi Hold Person",
                    email="multi.hold@example.edu",
                )
            ],
            hold_ids=[first_hold.id, second_hold.id],
        ),
        db=db_session,
        request=None,
        user=admin,
    )

    assert result.created_count == 1
    custodian_id = result.created[0].id
    memberships = db_session.query(models.HoldCustodian).filter_by(custodian_id=custodian_id).all()
    assert {membership.hold_id for membership in memberships} == {first_hold.id, second_hold.id}
def test_closing_case_requires_all_holds_to_be_closed_first(db_session):
    analyst = create_user(db_session, role="analyst", suffix="hold-close-analyst")
    case = create_case(db_session, name="Active Hold Closure")
    hold = create_hold(db_session, case)
    db_session.commit()

    with pytest.raises(HTTPException) as blocked:
        case_update.update_case_record(
            case_id=case.id,
            payload=schemas.CaseUpdate(closed=True),
            db=db_session,
            request=None,
            user=analyst,
        )

    assert blocked.value.status_code == 409
    assert blocked.value.detail["code"] == "case_closure_blocked"
    assert blocked.value.detail["active_holds"][0]["hold_id"] == hold.id
    db_session.refresh(case)
    db_session.refresh(hold)
    assert case.closed is False
    assert hold.status == "active"

    hold.status = "closed"
    db_session.add(hold)
    db_session.commit()
    closed = case_update.update_case_record(
        case_id=case.id,
        payload=schemas.CaseUpdate(closed=True),
        db=db_session,
        request=None,
        user=analyst,
    )

    db_session.refresh(hold)
    assert closed.closed is True
    assert hold.status == "closed"
    assert hold.status == "closed"


def test_matter_level_custodian_bridge_updates_all_existing_holds(db_session):
    case = create_case(db_session, name="Legacy Bridge Matter")
    custodian = models.Custodian(case_id=case.id, name="Legacy Person", email="legacy@example.edu")
    db_session.add(custodian)
    db_session.flush()
    first_hold = create_hold(db_session, case, custodians=[custodian])
    second_hold = models.CaseHold(case_id=case.id, name="Hold B", status="active", sort_order=1)
    db_session.add(second_hold)
    db_session.flush()
    case_holds.assign_custodians_to_hold(
        db_session,
        case_id=case.id,
        hold_id=second_hold.id,
        custodian_ids=[custodian.id],
    )
    second_membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=second_hold.id,
        custodian_id=custodian.id,
    ).one()
    hold_workflows.set_membership_consent_status(db_session, second_membership, "sent")

    custodian.consent_status = "received"
    hold_workflows.sync_legacy_custodian_to_default_hold(
        db_session,
        custodian,
        changed_fields={"consent_status"},
    )
    db_session.commit()

    first_membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=first_hold.id,
        custodian_id=custodian.id,
    ).one()
    db_session.refresh(second_membership)
    assert first_membership.consent_status == "received"
    assert second_membership.consent_status == "received"


def test_global_not_required_policy_updates_all_holds_but_preserves_ack(db_session):
    case = create_case(db_session, name="Policy Across Holds")
    custodian = models.Custodian(case_id=case.id, name="Policy Person", email="policy@example.edu")
    db_session.add(custodian)
    db_session.flush()
    first_hold = create_hold(db_session, case, custodians=[custodian])
    second_hold = models.CaseHold(case_id=case.id, name="Hold B", status="active", sort_order=1)
    db_session.add(second_hold)
    db_session.flush()
    case_holds.assign_custodians_to_hold(
        db_session,
        case_id=case.id,
        hold_id=second_hold.id,
        custodian_ids=[custodian.id],
    )
    memberships = db_session.query(models.HoldCustodian).filter_by(custodian_id=custodian.id).all()
    first = next(item for item in memberships if item.hold_id == first_hold.id)
    second = next(item for item in memberships if item.hold_id == second_hold.id)
    hold_workflows.set_membership_ntp_status(db_session, first, "sent")
    hold_workflows.set_membership_ntp_status(db_session, second, "acknowledged")

    custodian.ntp_status = "silent"
    custodian.ntp_not_required_reason = "Separated employee"
    custodian.consent_status = "implied"
    custodian.consent_not_required_reason = "Separated employee"
    hold_workflows.sync_custodian_not_required_policy_to_memberships(db_session, custodian)
    db_session.commit()

    db_session.refresh(first)
    db_session.refresh(second)
    assert first.ntp_status == "silent"
    assert second.ntp_status == "acknowledged"
    assert {first.consent_status, second.consent_status} == {"implied"}


def test_request_consent_proof_is_assigned_only_to_explicit_hold(db_session):
    from types import SimpleNamespace
    from app import case_requests

    case = create_case(db_session, name="Request Proof Hold")
    custodian = models.Custodian(case_id=case.id, name="Proof Person", email="proof@example.edu")
    db_session.add(custodian)
    db_session.flush()
    hold = create_hold(db_session, case, name="Request Hold", custodians=[custodian])
    proof = models.CaseRequestConsentProof(
        case_id=case.id,
        custodian_name=custodian.name,
        custodian_email=custodian.email,
        stored_filename="proof-default-hold.pdf",
        original_filename="proof.pdf",
        content_type="application/pdf",
        size=1,
    )
    db_session.add(proof)
    db_session.flush()
    record = SimpleNamespace(case_id=case.id, consent_proofs=[proof], payload='{"hold_name":"Request Hold"}')

    case_requests._assign_request_proofs_to_default_hold(db_session, record)
    db_session.commit()

    membership = db_session.get(models.HoldCustodian, proof.hold_custodian_id)
    assert membership is not None
    assert membership.custodian_id == custodian.id
    assert membership.hold_id == hold.id
    assert membership.consent_status == "received"
