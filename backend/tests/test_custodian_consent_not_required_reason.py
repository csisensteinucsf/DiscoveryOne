import pytest

fastapi = pytest.importorskip("fastapi")


def test_apply_consent_not_required_defaults_sets_separated_reason():
    from app import cases, models

    case = models.Case(name="Case A", claimant="")
    custodian = models.Custodian(case_id=1, name="User", email="user@example.edu", consent_status="sent")
    custodian.employment_status = "separated_90"
    custodian.consent_not_required_reason = "custom reason"

    cases._apply_consent_not_required_defaults(case, custodian)

    assert custodian.consent_status == "implied"
    assert custodian.consent_not_required_reason == cases.CONSENT_NOT_REQUIRED_REASON_SEPARATED


def test_apply_consent_not_required_defaults_sets_claimant_reason():
    from app import cases, models

    case = models.Case(name="Case A", claimant="Jane Doe")
    custodian = models.Custodian(case_id=1, name="Jane Doe", email="jane@example.edu", consent_status="not sent")

    cases._apply_consent_not_required_defaults(case, custodian)

    assert custodian.consent_status == "implied"
    assert custodian.consent_not_required_reason == cases.CONSENT_NOT_REQUIRED_REASON_CLAIMANT


def test_apply_consent_not_required_defaults_sets_default_reason_for_manual_implied():
    from app import cases, models

    case = models.Case(name="Case A", claimant="")
    custodian = models.Custodian(case_id=1, name="User", email="user@example.edu", consent_status="implied")
    custodian.consent_not_required_reason = ""

    cases._apply_consent_not_required_defaults(case, custodian)

    assert custodian.consent_status == "implied"
    assert custodian.consent_not_required_reason == cases.CONSENT_NOT_REQUIRED_REASON_DEFAULT


def test_apply_consent_not_required_defaults_clears_reason_when_consent_required():
    from app import cases, models

    case = models.Case(name="Case A", claimant="")
    custodian = models.Custodian(case_id=1, name="User", email="user@example.edu", consent_status="received")
    custodian.consent_not_required_reason = "not needed"

    cases._apply_consent_not_required_defaults(case, custodian)

    assert custodian.consent_status == "received"
    assert custodian.consent_not_required_reason is None
