import re
from typing import Any, Optional

from . import models
from .institution import is_organization_email as _is_organization_email


def _normalize_person_label(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9@]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _custodian_matches_claimant(*, claimant: str | None, name: str | None, email: str | None) -> bool:
    claim = _normalize_person_label(claimant)
    if not claim or claim in {"na", "n/a"}:
        return False
    email_norm = _normalize_person_label(email)
    if "@" in claim and email_norm and email_norm == claim:
        return True
    name_norm = _normalize_person_label(name)
    if not name_norm:
        return False
    if name_norm == claim:
        return True
    if len(claim) >= 4 and (claim in name_norm or name_norm in claim):
        return True
    return False

NTP_NOT_REQUIRED_REASON_DEFAULT = "ntp not required"
NTP_NOT_REQUIRED_REASON_SEPARATED = "separated"
NTP_NOT_REQUIRED_REASON_CLAIMANT = "claimant"
NTP_NOT_REQUIRED_REASON_NON_ORG = "non-organization email"
CONSENT_NOT_REQUIRED_REASON_DEFAULT = "consent not required"
CONSENT_NOT_REQUIRED_REASON_SEPARATED = "separated, consent not required"
CONSENT_NOT_REQUIRED_REASON_CLAIMANT = "claimant, consent inherently provided"


def _normalize_optional_text(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _ntp_not_required_auto_reason(case: models.Case, custodian: models.Custodian) -> Optional[str]:
    emp_status = (getattr(custodian, "employment_status", None) or "").strip().lower()
    if emp_status.startswith("separated"):
        return NTP_NOT_REQUIRED_REASON_SEPARATED
    email = getattr(custodian, "email", None)
    if email and not _is_organization_email(email):
        return NTP_NOT_REQUIRED_REASON_NON_ORG
    if _custodian_matches_claimant(
        claimant=getattr(case, "claimant", None),
        name=getattr(custodian, "name", None),
        email=getattr(custodian, "email", None),
    ):
        return NTP_NOT_REQUIRED_REASON_CLAIMANT
    return None


def _apply_ntp_not_required_defaults(case: models.Case, custodian: models.Custodian) -> None:
    ntp_status = (getattr(custodian, "ntp_status", None) or "").strip().lower()
    manual_reason = _normalize_optional_text(getattr(custodian, "ntp_not_required_reason", None))
    auto_reason = _ntp_not_required_auto_reason(case, custodian)
    if ntp_status == "na":
        custodian.ntp_not_required_reason = manual_reason or auto_reason or NTP_NOT_REQUIRED_REASON_DEFAULT
    else:
        custodian.ntp_not_required_reason = None


def _consent_not_required_auto_reason(case: models.Case, custodian: models.Custodian) -> Optional[str]:
    emp_status = (getattr(custodian, "employment_status", None) or "").strip().lower()
    if emp_status.startswith("separated"):
        return CONSENT_NOT_REQUIRED_REASON_SEPARATED
    if _custodian_matches_claimant(
        claimant=getattr(case, "claimant", None),
        name=getattr(custodian, "name", None),
        email=getattr(custodian, "email", None),
    ):
        return CONSENT_NOT_REQUIRED_REASON_CLAIMANT
    return None


def _apply_consent_not_required_defaults(case: models.Case, custodian: models.Custodian) -> None:
    auto_reason = _consent_not_required_auto_reason(case, custodian)
    if auto_reason:
        custodian.consent_status = "na"
        custodian.consent_not_required_reason = auto_reason
        return

    consent_status = (getattr(custodian, "consent_status", None) or "").strip().lower()
    manual_reason = _normalize_optional_text(getattr(custodian, "consent_not_required_reason", None))
    if consent_status == "na":
        custodian.consent_not_required_reason = manual_reason or CONSENT_NOT_REQUIRED_REASON_DEFAULT
    else:
        custodian.consent_not_required_reason = None
