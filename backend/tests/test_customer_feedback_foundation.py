from __future__ import annotations

import asyncio
import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import (
    case_closure_readiness,
    case_custodians,
    case_holds,
    case_import,
    case_request_approval_mutation,
    case_request_files,
    case_templates,
    case_update,
    cases,
    hold_workflows,
    models,
    schemas,
)


@pytest.fixture()
def db_session(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(case_templates, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(cases, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_update.case_core, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_update.case_core, "notify_case_requestor_case_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_update.case_core, "_maybe_create_box_hold_release_ticket", lambda *args, **kwargs: None)
    monkeypatch.setattr(case_custodians, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        case_custodians,
        "apply_custodian_name_email_review",
        lambda custodian, *, use_ai=True: SimpleNamespace(source="rules", confidence=1.0),
    )
    monkeypatch.setenv("CASE_IMPORT_REPORT_DIR", str(tmp_path / "import-reports"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))

    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def _user(db, *, username: str, role: str = "sys_admin") -> models.User:
    user = models.User(
        username=username,
        email=f"{username}@example.edu",
        password_hash="hashed",
        role=role,
        is_admin=role == "sys_admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _case(db, *, name: str) -> models.Case:
    row = models.Case(name=name, legal_case_name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Name", "Email"])
    sheet.append(["Imported Person", "imported.person@example.edu"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_case_template_crud_and_only_one_default(db_session):
    admin = _user(db_session, username="template-admin")
    first = case_templates.create_case_template(
        schemas.CaseTemplateCreate(
            name="Investigation",
            description="Internal investigation defaults",
            enabled=True,
            is_default=True,
            sort_order=20,
            defaults={"closure_nag_days": 45},
            field_rules={"matter_number": {"visible": True, "required": False}},
        ),
        request=None,
        db=db_session,
        user=admin,
    )
    second = case_templates.create_case_template(
        schemas.CaseTemplateCreate(
            name="Litigation",
            enabled=True,
            is_default=True,
            sort_order=10,
        ),
        request=None,
        db=db_session,
        user=admin,
    )

    assert db_session.get(models.CaseTemplate, first["id"]).is_default is False
    assert db_session.get(models.CaseTemplate, second["id"]).is_default is True
    assert [row["name"] for row in case_templates.list_case_templates(db=db_session, user=admin)] == [
        "Litigation",
        "Investigation",
    ]

    updated = case_templates.update_case_template(
        first["id"],
        schemas.CaseTemplateUpdate(
            description="Updated description",
            enabled=False,
            defaults={"closure_nag_days": 60},
        ),
        request=None,
        db=db_session,
        user=admin,
    )
    assert updated["description"] == "Updated description"
    assert updated["enabled"] is False
    assert updated["defaults"] == {"closure_nag_days": 60}

    case_templates.delete_case_template(first["id"], request=None, db=db_session, user=admin)
    assert db_session.get(models.CaseTemplate, first["id"]) is None


def test_case_template_applies_defaults_hidden_fields_and_required_fields_without_creating_hold(db_session):
    admin = _user(db_session, username="template-rules-admin")
    created = case_templates.create_case_template(
        schemas.CaseTemplateCreate(
            name="Claims",
            defaults={
                "claimant": "Default Claimant",
                "matter_number": "DEFAULT-MATTER",
            },
            field_rules={
                "internal_counsel": {"visible": True, "required": True},
                "matter_number": {"visible": False, "required": False},
                "outside_counsel": {"visible": False, "required": False},
            },
        ),
        request=None,
        db=db_session,
        user=admin,
    )

    with pytest.raises(HTTPException) as missing_required:
        case_templates.apply_case_template(
            db_session,
            schemas.CaseCreate(name="Missing Counsel", case_template_id=created["id"]),
        )
    assert missing_required.value.status_code == 422
    assert missing_required.value.detail["fields"] == ["internal_counsel"]

    result = cases.create_case(
        schemas.CaseCreate(
            name="Template Matter",
            case_template_id=created["id"],
            internal_counsel="Counsel Name",
            matter_number="USER-SUPPLIED",
            outside_counsel="Must be removed because this field is hidden",
        ),
        db=db_session,
        request=None,
        _user=admin,
    )
    stored = db_session.get(models.Case, result.id)
    assert stored.case_template_id == created["id"]
    assert stored.claimant == "Default Claimant"
    assert stored.matter_number == "DEFAULT-MATTER"
    assert stored.outside_counsel is None
    assert db_session.query(models.CaseHold).filter_by(case_id=stored.id).count() == 0

    with pytest.raises(HTTPException, match="cannot be required while hidden"):
        case_templates.create_case_template(
            schemas.CaseTemplateCreate(
                name="Invalid Rules",
                field_rules={"claimant": {"visible": False, "required": True}},
            ),
            request=None,
            db=db_session,
            user=admin,
        )


def test_case_template_today_start_date_round_trips_through_case_create(db_session):
    admin = _user(db_session, username="template-date-admin")
    template = case_templates.create_case_template(
        schemas.CaseTemplateCreate(
            name="Today Start Date",
            defaults={"start_date_mode": "today"},
        ),
        request=None,
        db=db_session,
        user=admin,
    )

    result = cases.create_case(
        schemas.CaseCreate(name="Today Template Matter", case_template_id=template["id"]),
        db=db_session,
        request=None,
        _user=admin,
    )
    assert result.start_date is not None


def test_test_case_flag_round_trips_through_template_create_and_case_update(db_session):
    admin = _user(db_session, username="test-case-admin")
    template = case_templates.create_case_template(
        schemas.CaseTemplateCreate(
            name="Test Matter",
            defaults={"is_test_case": True},
            field_rules={"is_test_case": {"visible": True, "required": False}},
        ),
        request=None,
        db=db_session,
        user=admin,
    )

    created = cases.create_case(
        schemas.CaseCreate(name="Designated Test Case", case_template_id=template["id"]),
        db=db_session,
        request=None,
        _user=admin,
    )
    stored = db_session.get(models.Case, created.id)
    assert stored.is_test_case is True
    assert created.is_test_case is True

    updated = case_update.update_case_record(
        case_id=created.id,
        payload=schemas.CaseUpdate(is_test_case=False),
        db=db_session,
        request=None,
        user=admin,
    )
    assert updated.is_test_case is False
    assert db_session.get(models.Case, created.id).is_test_case is False


def test_case_create_schema_treats_blank_optional_start_date_as_none():
    payload = schemas.CaseCreate(name="Blank Start Date", start_date="")

    assert payload.start_date is None


def test_case_template_custom_fields_are_validated_snapshotted_and_editable(db_session):
    admin = _user(db_session, username="custom-fields-admin")

    with pytest.raises(HTTPException, match="requires at least one option"):
        case_templates.create_case_template(
            schemas.CaseTemplateCreate(
                name="Invalid Custom Fields",
                custom_fields=[
                    {
                        "key": "business_unit",
                        "label": "Business unit",
                        "field_type": "select",
                        "options": [],
                    }
                ],
            ),
            request=None,
            db=db_session,
            user=admin,
        )

    template = case_templates.create_case_template(
        schemas.CaseTemplateCreate(
            name="Organization Matter",
            custom_fields=[
                {
                    "key": "business_unit",
                    "label": "Business unit",
                    "field_type": "select",
                    "required": True,
                    "options": ["Legal", "HR"],
                },
                {
                    "key": "estimated_volume",
                    "label": "Estimated volume",
                    "field_type": "number",
                    "default_value": 12.5,
                },
                {
                    "key": "urgent",
                    "label": "Urgent",
                    "field_type": "checkbox",
                },
            ],
        ),
        request=None,
        db=db_session,
        user=admin,
    )
    assert template["custom_fields"][1]["default_value"] == 12.5

    with pytest.raises(HTTPException) as missing_required:
        case_templates.apply_case_template(
            db_session,
            schemas.CaseCreate(name="Missing Business Unit", case_template_id=template["id"]),
        )
    assert missing_required.value.detail["fields"] == ["custom_fields.business_unit"]

    created = cases.create_case(
        schemas.CaseCreate(
            name="Custom Field Matter",
            case_template_id=template["id"],
            custom_fields={"business_unit": "Legal"},
        ),
        db=db_session,
        request=None,
        _user=admin,
    )
    assert created.custom_fields["business_unit"]["value"] == "Legal"
    assert created.custom_fields["estimated_volume"]["value"] == 12.5
    assert created.custom_fields["urgent"]["value"] is False

    updated = case_update.update_case_record(
        case_id=created.id,
        payload=schemas.CaseUpdate(custom_fields={"business_unit": "HR", "urgent": True}),
        db=db_session,
        request=None,
        user=admin,
    )
    assert updated.custom_fields["business_unit"]["value"] == "HR"
    assert updated.custom_fields["estimated_volume"]["value"] == 12.5
    assert updated.custom_fields["urgent"]["value"] is True

    case_templates.update_case_template(
        template["id"],
        schemas.CaseTemplateUpdate(
            custom_fields=[
                {
                    "key": "business_unit",
                    "label": "Department",
                    "field_type": "select",
                    "required": True,
                    "options": ["Legal", "HR", "Finance"],
                }
            ]
        ),
        request=None,
        db=db_session,
        user=admin,
    )
    stored = db_session.get(models.Case, created.id)
    assert stored.custom_fields["business_unit"]["label"] == "Business unit"
    assert "estimated_volume" in stored.custom_fields

    with pytest.raises(HTTPException) as unknown_field:
        case_update.update_case_record(
            case_id=created.id,
            payload=schemas.CaseUpdate(custom_fields={"not_in_snapshot": "value"}),
            db=db_session,
            request=None,
            user=admin,
        )
    assert unknown_field.value.detail["fields"] == ["not_in_snapshot"]



def test_used_case_template_cannot_be_deleted(db_session):
    admin = _user(db_session, username="used-template-admin")
    template = case_templates.create_case_template(
        schemas.CaseTemplateCreate(name="Used Template"),
        request=None,
        db=db_session,
        user=admin,
    )
    cases.create_case(
        schemas.CaseCreate(name="Uses Template", case_template_id=template["id"]),
        db=db_session,
        request=None,
        _user=admin,
    )

    with pytest.raises(HTTPException) as blocked:
        case_templates.delete_case_template(template["id"], request=None, db=db_session, user=admin)
    assert blocked.value.status_code == 409


def test_direct_case_creation_creates_no_implicit_hold(db_session):
    admin = _user(db_session, username="direct-create-admin")
    created = cases.create_case(
        schemas.CaseCreate(name="Direct Matter"),
        db=db_session,
        request=None,
        _user=admin,
    )
    assert db_session.query(models.CaseHold).filter_by(case_id=created.id).count() == 0


def test_new_case_request_approval_creates_no_implicit_hold(monkeypatch, db_session):
    analyst = _user(db_session, username="request-approval-analyst", role="analyst")
    request_record = models.CaseRequest(
        request_type="new_case",
        status="pending",
        case_name="Requested Matter",
        requestor_email="requestor@example.edu",
        payload=json.dumps({}),
    )
    db_session.add(request_record)
    db_session.commit()
    monkeypatch.setattr(
        case_request_approval_mutation.case_request_core,
        "_case_naming_mode",
        lambda: "legal_case_name",
    )

    case_request_approval_mutation.apply_approval_request_mutation(
        db=db_session,
        record=request_record,
        payload={
            "legal_case_name": "Requested Matter",
            "custodians": [],
            "requestors": [{"email": "requestor@example.edu", "is_primary": True}],
        },
        analyst_id=analyst.id,
        actor=analyst,
        request=None,
    )
    db_session.commit()

    assert request_record.case_id is not None
    assert db_session.query(models.CaseHold).filter_by(case_id=request_record.case_id).count() == 0


def test_spreadsheet_import_case_creation_creates_no_implicit_hold(db_session):
    result = case_import.CaseSpreadsheetImporter(db_session).import_uploads(
        [("Imported Matter.xlsx", _workbook_bytes())]
    )

    assert len(result["created_cases"]) == 1
    case_id = result["created_cases"][0]["id"]
    assert db_session.query(models.CaseHold).filter_by(case_id=case_id).count() == 0
    assert db_session.query(models.HoldCustodian).count() == 0


def test_custodian_can_remain_unassigned_and_explicit_hold_assignment_still_works(db_session):
    admin = _user(db_session, username="custodian-assignment-admin")
    case = _case(db_session, name="Custodian Assignment Matter")

    unassigned = cases.add_custodian(
        case.id,
        schemas.CustodianCreate(name="Matter Only Person"),
        db=db_session,
        request=None,
        _user=admin,
    )
    assert db_session.query(models.CaseHold).filter_by(case_id=case.id).count() == 0
    assert db_session.query(models.HoldCustodian).filter_by(custodian_id=unassigned.id).count() == 0

    hold = models.CaseHold(case_id=case.id, name="Discovery Hold", status="active")
    db_session.add(hold)
    db_session.commit()
    assigned = cases.add_custodian(
        case.id,
        schemas.CustodianCreate(name="Assigned Person", hold_ids=[hold.id]),
        db=db_session,
        request=None,
        _user=admin,
    )
    membership = db_session.query(models.HoldCustodian).filter_by(
        hold_id=hold.id,
        custodian_id=assigned.id,
    ).one()
    assert membership.ntp_status == "not sent"
    assert membership.consent_status == "not sent"
    assert db_session.query(models.HoldCustodian).filter_by(custodian_id=unassigned.id).count() == 0


def test_closure_readiness_blocks_active_hold_and_preservation_then_allows_closure(db_session):
    analyst = _user(db_session, username="closure-analyst", role="analyst")
    case = _case(db_session, name="Closure Readiness Matter")
    custodian = models.Custodian(case_id=case.id, name="Preserved Person")
    hold = models.CaseHold(case_id=case.id, name="Active Hold", status="active")
    db_session.add_all([custodian, hold])
    db_session.flush()
    membership = models.HoldCustodian(hold_id=hold.id, custodian_id=custodian.id)
    db_session.add(membership)
    db_session.flush()
    source = models.HoldPreservationSource(
        hold_custodian_id=membership.id,
        source_key="email",
        source_label="Email",
        status="active",
    )
    db_session.add(source)
    db_session.commit()

    active_hold_result = case_closure_readiness.case_closure_readiness(db_session, case.id)
    assert active_hold_result["ready"] is False
    assert active_hold_result["active_holds"][0]["hold_name"] == "Active Hold"
    with pytest.raises(HTTPException) as blocked_close:
        case_update.update_case_record(
            case_id=case.id,
            payload=schemas.CaseUpdate(closed=True),
            db=db_session,
            request=None,
            user=analyst,
        )
    assert blocked_close.value.status_code == 409
    assert blocked_close.value.detail["code"] == "case_closure_blocked"

    hold.status = "closed"
    db_session.commit()
    preservation_result = case_closure_readiness.case_closure_readiness(db_session, case.id)
    assert preservation_result["ready"] is False
    assert preservation_result["active_holds"] == []
    assert preservation_result["preservation_blockers"][0]["status"] == "active"

    source.status = "released"
    db_session.commit()
    clear_result = case_closure_readiness.case_closure_readiness(db_session, case.id)
    assert clear_result == {
        "ready": True,
        "active_holds": [],
        "preservation_blockers": [],
        "blocking_count": 0,
    }
    closed = case_update.update_case_record(
        case_id=case.id,
        payload=schemas.CaseUpdate(closed=True),
        db=db_session,
        request=None,
        user=analyst,
    )
    assert closed.closed is True


def test_close_case_request_approval_uses_same_closure_gate(db_session):
    analyst = _user(db_session, username="closure-request-analyst", role="analyst")
    case = _case(db_session, name="Closure Request Gate")
    hold = models.CaseHold(case_id=case.id, name="Unreleased Hold", status="active")
    request_record = models.CaseRequest(
        request_type="close_case",
        status="pending",
        case_id=case.id,
        case_name=case.name,
        requestor_email="requestor@example.edu",
        payload=json.dumps({"case_id": case.id}),
    )
    db_session.add_all([hold, request_record])
    db_session.commit()

    with pytest.raises(HTTPException) as blocked:
        case_request_approval_mutation.apply_approval_request_mutation(
            db=db_session,
            record=request_record,
            payload={"case_id": case.id},
            analyst_id=analyst.id,
            actor=analyst,
            request=None,
        )

    assert blocked.value.status_code == 409
    assert blocked.value.detail["code"] == "case_closure_blocked"
    db_session.refresh(case)
    assert case.closed is False


def test_silent_implied_and_awoc_status_rules(db_session):
    case = _case(db_session, name="Status Rules Matter")
    custodian = models.Custodian(case_id=case.id, name="Status Person")
    hold = models.CaseHold(case_id=case.id, name="Status Hold", status="active")
    db_session.add_all([custodian, hold])
    db_session.flush()
    membership = models.HoldCustodian(hold_id=hold.id, custodian_id=custodian.id)
    db_session.add(membership)
    db_session.flush()

    with pytest.raises(HTTPException, match="reason is required"):
        hold_workflows.set_membership_ntp_status(db_session, membership, "silent")
    hold_workflows.set_membership_ntp_status(
        db_session,
        membership,
        "silent",
        not_required_reason="No notice is sent for this Hold",
    )
    assert membership.ntp_status == "silent"
    assert db_session.get(models.Custodian, custodian.id).ntp_status == "silent"

    with pytest.raises(HTTPException, match="reason is required"):
        hold_workflows.set_membership_consent_status(db_session, membership, "implied")
    hold_workflows.set_membership_consent_status(
        db_session,
        membership,
        "implied",
        not_required_reason="Consent is implied by policy",
    )
    assert membership.consent_status == "implied"

    with pytest.raises(HTTPException, match="Upload an AWOC document"):
        hold_workflows.set_membership_consent_status(db_session, membership, "awoc")

    db_session.add(
        models.CaseRequestConsentProof(
            case_id=case.id,
            hold_custodian_id=membership.id,
            custodian_name=custodian.name,
            stored_filename="standard-proof.pdf",
            original_filename="standard-proof.pdf",
            content_type="application/pdf",
            size=100,
            proof_type="standard",
        )
    )
    db_session.flush()
    with pytest.raises(HTTPException, match="Upload an AWOC document"):
        hold_workflows.set_membership_consent_status(db_session, membership, "awoc")

    db_session.add(
        models.CaseRequestConsentProof(
            case_id=case.id,
            hold_custodian_id=membership.id,
            custodian_name=custodian.name,
            stored_filename="awoc-proof.pdf",
            original_filename="awoc-proof.pdf",
            content_type="application/pdf",
            size=100,
            proof_type="awoc",
        )
    )
    db_session.flush()
    hold_workflows.set_membership_consent_status(db_session, membership, "awoc")
    assert membership.consent_status == "awoc"
    assert db_session.get(models.Custodian, custodian.id).consent_status == "awoc"


def test_awoc_upload_sets_case_level_consent_without_a_hold(db_session, monkeypatch):
    actor = _user(db_session, username="awoc-admin")
    case = _case(db_session, name="AWOC Upload Matter")
    custodian = models.Custodian(
        case_id=case.id,
        name="AWOC Person",
        email="awoc.person@example.edu",
    )
    db_session.add(custodian)
    db_session.commit()
    db_session.autoflush = False

    async def fake_read_blob(*_args, **_kwargs):
        return {
            "filename": "awoc-consent.pdf",
            "content_type": "application/pdf",
            "size": 100,
            "data": b"awoc",
        }

    monkeypatch.setattr(case_request_files, "_read_consent_proof_blob", fake_read_blob)
    monkeypatch.setattr(case_request_files, "_write_consent_proof_file", lambda _blob: "stored-awoc-consent.pdf")
    monkeypatch.setattr(case_request_files, "_cleanup_consent_proof_file", lambda *_args: None)
    monkeypatch.setattr(case_request_files, "_sync_case_documentation_counters", lambda *_args: None)
    monkeypatch.setattr(case_request_files, "log_event", lambda *_args, **_kwargs: None)

    class UploadRequest:
        async def form(self):
            return {
                "file": SimpleNamespace(filename="awoc-consent.pdf"),
                "custodian_id": str(custodian.id),
                "custodian_name": custodian.name,
                "custodian_email": custodian.email,
                "proof_type": "awoc",
            }

    result = asyncio.run(
        case_request_files.upload_case_consent_proof(
            case.id,
            UploadRequest(),
            db=db_session,
            actor=actor,
        )
    )

    db_session.refresh(custodian)
    proof = (
        db_session.query(models.CaseRequestConsentProof)
        .filter(
            models.CaseRequestConsentProof.proof_type == "awoc",
        )
        .one()
    )
    assert proof.hold_custodian_id is None
    assert custodian.consent_status == "awoc"
    assert proof.id is not None
    assert result["proof_type"] == "awoc"
