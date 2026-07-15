from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import case_consents, models, schemas


def _session():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    return engine, SessionLocal()


def _admin(db):
    actor = models.User(
        username="admin",
        email="admin@example.test",
        password_hash="hashed",
        role="sys_admin",
        is_admin=True,
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def test_canonical_routes_are_public_and_legacy_aliases_are_hidden():
    route_visibility = {
        (route.path, next(iter(route.methods))): route.include_in_schema
        for route in case_consents.router.routes
        if getattr(route, "methods", None)
    }

    assert route_visibility[("/api/cases/{case_id}/consents", "POST")] is True
    assert route_visibility[("/api/cases/{case_id}/consents/{consent_id}/resend", "POST")] is True
    assert route_visibility[("/api/cases/{case_id}/consents/{consent_id}/void", "POST")] is True
    assert route_visibility[("/api/cases/{case_id}/consents/{consent_id}/download", "GET")] is True
    assert route_visibility[("/api/cases/{case_id}/docusign/consents", "POST")] is False
    assert route_visibility[("/api/cases/{case_id}/docusign/consents/{consent_id}/resend", "POST")] is False
    assert route_visibility[("/api/cases/{case_id}/docusign/consents/{consent_id}/void", "POST")] is False
    assert route_visibility[("/api/cases/{case_id}/docusign/consents/{consent_id}/download", "GET")] is False


def test_request_ids_are_unique_within_provider_not_globally():
    engine, db = _session()
    try:
        db.add_all([
            models.CaseConsent(id=1, provider="provider_a", envelope_id="shared-request"),
            models.CaseConsent(id=2, provider="provider_b", envelope_id="shared-request"),
        ])
        db.commit()

        db.add(models.CaseConsent(id=3, provider="provider_a", envelope_id="shared-request"))
        try:
            db.commit()
            raise AssertionError("duplicate provider/request pair should be rejected")
        except IntegrityError:
            db.rollback()
    finally:
        db.close()
        engine.dispose()

def test_resend_dispatches_to_persisted_provider_and_keeps_legacy_response_key(monkeypatch):
    engine, db = _session()
    try:
        actor = _admin(db)
        case = models.Case(name="Provider ownership")
        db.add(case)
        db.commit()
        consent = models.CaseConsent(
            id=901,
            case_id=case.id,
            provider="owner_sign",
            envelope_id="request-901",
            status="sent",
        )
        db.add(consent)
        db.commit()
        captured = {}

        def fake_resend(request_id, *, provider=None):
            captured.update(request_id=request_id, provider=provider)
            return "provider-api"

        monkeypatch.setattr(case_consents, "resend_request", fake_resend)
        monkeypatch.setattr(case_consents, "log_event", lambda *_args, **_kwargs: None)

        response = case_consents.resend_consent_request(
            case.id,
            consent.id,
            db=db,
            request=None,
            actor=actor,
        )

        assert captured == {"request_id": "request-901", "provider": "owner_sign"}
        assert response["provider"] == "owner_sign"
        assert response["request_id"] == "request-901"
        assert response["envelope_id"] == "request-901"
        serialized = schemas.CaseConsent.model_validate(consent)
        assert serialized.request_id == serialized.envelope_id == "request-901"
    finally:
        db.close()
        engine.dispose()
