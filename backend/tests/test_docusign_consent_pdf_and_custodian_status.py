from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import case_consents, case_holds, cases, docusign_webhook, models
from app.custodians_summary import custodian_detail, list_custodians


def _session():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal()


def _admin(db):
    user = models.User(
        username="admin",
        email="admin@example.edu",
        password_hash="hashed",
        role="sys_admin",
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_completed_docusign_pdf_is_saved_as_case_consent_proof(tmp_path, monkeypatch):
    engine, db = _session()
    try:
        actor = _admin(db)
        monkeypatch.setattr(docusign_webhook, "CASE_REQUEST_PROOF_DIR", tmp_path)
        monkeypatch.setattr(
            docusign_webhook,
            "download_completed_document",
            lambda _request_id, **_kwargs: (b"%PDF-1.4 signed", "combined.pdf"),
        )
        monkeypatch.setattr(docusign_webhook, "scan_payload", lambda *_args, **_kwargs: None)
        case = models.Case(name="2026-Test", consent_proof_count=0)
        db.add(case)
        db.commit()
        custodian = models.Custodian(case_id=case.id, name="Jane Custodian", email="jane@example.edu", consent_status="sent")
        db.add(custodian)
        db.commit()
        consent = models.CaseConsent(
            id=1001,
            case_id=case.id,
            custodian_id=custodian.id,
            custodian_name=custodian.name,
            custodian_email=custodian.email,
            envelope_id="env-123",
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(consent)
        db.commit()

        proof = docusign_webhook._save_completed_docusign_pdf(
            db,
            consent=consent,
            custodian=custodian,
            request=None,
        )

        assert proof is not None
        assert proof.case_id == case.id
        assert proof.case_request_id is None
        assert proof.original_filename == "docusign-env-123.pdf"
        assert proof.content_type == "application/pdf"
        assert (tmp_path / proof.stored_filename).read_bytes() == b"%PDF-1.4 signed"
        db.refresh(case)
        db.refresh(custodian)
        assert case.consent_proof_count == 1
        assert custodian.consent_status == "received"
        consent_rows = cases.list_case_consents(case.id, db=db, actor=actor)
        assert consent_rows[0]["provider"] == "docusign"
        assert consent_rows[0]["request_id"] == "env-123"
        assert consent_rows[0]["envelope_id"] == "env-123"
        assert consent_rows[0]["proof_downloaded"] is True
        assert consent_rows[0]["proof_id"] == proof.id

        second = docusign_webhook._save_completed_docusign_pdf(
            db,
            consent=consent,
            custodian=custodian,
            request=None,
        )
        assert second.id == proof.id
        assert db.query(models.CaseRequestConsentProof).count() == 1
    finally:
        db.close()
        engine.dispose()


def test_custodian_views_include_per_case_consent_status():
    engine, db = _session()
    try:
        actor = _admin(db)
        case = models.Case(name="2026-Test")
        db.add(case)
        db.commit()
        custodian = models.Custodian(case_id=case.id, name="Jane Custodian", email="jane@example.edu", consent_status="sent")
        db.add(custodian)
        db.commit()
        db.add(
            models.CaseConsent(
                id=1002,
                case_id=case.id,
                custodian_id=custodian.id,
                custodian_name=custodian.name,
                custodian_email=custodian.email,
                envelope_id="env-456",
                status="delivered",
            )
        )
        db.commit()

        rows = list_custodians(q=None, db=db, actor=actor)
        jane = next(row for row in rows if row["email"] == "jane@example.edu")
        assert "consent" not in jane["open_cases"][0]

        detail = custodian_detail(email="jane@example.edu", db=db, actor=actor)
        assert detail["cases"][0]["consent"]["status"] == "delivered"
        assert detail["cases"][0]["consent"]["custodian_status"] == "sent"
        assert detail["cases"][0]["consent"]["source"] == "docusign"
    finally:
        db.close()
        engine.dispose()

def test_consent_send_and_completion_are_isolated_to_selected_hold(tmp_path, monkeypatch):
    engine, db = _session()
    try:
        actor = _admin(db)
        case = models.Case(name="Two Hold Consent")
        db.add(case)
        db.commit()
        custodian = models.Custodian(
            case_id=case.id,
            name="Shared Custodian",
            email="shared@example.edu",
            consent_status="not sent",
        )
        db.add(custodian)
        db.commit()
        first_hold = models.CaseHold(case_id=case.id, name="Hold A", status="active", sort_order=0)
        db.add(first_hold)
        db.flush()
        case_holds.assign_custodians_to_hold(
            db,
            case_id=case.id,
            hold_id=first_hold.id,
            custodian_ids=[custodian.id],
        )
        second_hold = models.CaseHold(case_id=case.id, name="Hold B", sort_order=1)
        db.add(second_hold)
        db.flush()
        second_membership = models.HoldCustodian(
            hold_id=second_hold.id,
            custodian_id=custodian.id,
            consent_status="not sent",
        )
        db.add(second_membership)
        db.commit()
        first_membership = db.query(models.HoldCustodian).filter_by(
            hold_id=first_hold.id,
            custodian_id=custodian.id,
        ).one()

        monkeypatch.setattr(case_consents, "current_esignature_provider", lambda: "docusign")
        monkeypatch.setattr(case_consents, "send_consent_request", lambda **_kwargs: "env-hold-a")
        monkeypatch.setattr(case_consents, "log_event", lambda *_args, **_kwargs: None)
        result = case_consents.send_consent_request_route(
            case.id,
            {
                "case_hold_id": first_hold.id,
                "record_type": "Email",
                "custodians": [{"custodian_id": custodian.id}],
            },
            db=db,
            request=None,
            actor=actor,
        )

        assert result["ok"] is True
        consent = db.query(models.CaseConsent).filter_by(envelope_id="env-hold-a").one()
        assert consent.hold_custodian_id == first_membership.id
        db.refresh(first_membership)
        db.refresh(second_membership)
        assert first_membership.consent_status == "sent"
        assert second_membership.consent_status == "not sent"

        consent.status = "completed"
        db.add(consent)
        db.commit()
        monkeypatch.setattr(docusign_webhook, "CASE_REQUEST_PROOF_DIR", tmp_path)
        monkeypatch.setattr(
            docusign_webhook,
            "download_completed_document",
            lambda _request_id, **_kwargs: (b"%PDF-1.4 signed", "combined.pdf"),
        )
        monkeypatch.setattr(docusign_webhook, "scan_payload", lambda *_args, **_kwargs: None)
        docusign_webhook._save_completed_docusign_pdf(
            db,
            consent=consent,
            custodian=custodian,
            request=None,
        )

        db.refresh(first_membership)
        db.refresh(second_membership)
        assert first_membership.consent_status == "received"
        assert second_membership.consent_status == "not sent"
    finally:
        db.close()
        engine.dispose()
