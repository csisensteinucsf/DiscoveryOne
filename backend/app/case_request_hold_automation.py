from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from . import models
from .permissions import get_role
from .safe_log import debug_suppressed
from .case_request_settings import hold_automation_allow_override
from .hold_workflows import sync_legacy_custodian_to_default_hold

NO_EMAIL_PLACEHOLDER = "NoEmail"
UNMATCHED_EMAIL_PLACEHOLDER = "UNMATCHED"
def pick_auto_approver(db: Session, case: Optional[models.Case]) -> Optional[models.User]:
    """Choose a non-requestor actor for auto-approval automation."""
    try:
        analyst_id = getattr(case, "analyst_id", None) if case else None
        if analyst_id:
            analyst = db.get(models.User, analyst_id)
            if analyst and get_role(analyst) in {"analyst", "sys_admin"}:
                return analyst
    except Exception as exc:
        debug_suppressed("suppressed exception in case_request_hold_automation.py:pick_auto_approver_analyst", exc)
    try:
        admin = (
            db.query(models.User)
            .filter(models.User.username == "admin")
            .first()
        )
        if admin and get_role(admin) == "sys_admin":
            return admin
    except Exception as exc:
        debug_suppressed("suppressed exception in case_request_hold_automation.py:pick_auto_approver_admin", exc)
    try:
        return (
            db.query(models.User)
            .filter((models.User.role == "sys_admin") | (models.User.is_admin.is_(True)))
            .order_by(models.User.id.asc())
            .first()
        )
    except Exception:
        return None


def has_hold(model: models.Custodian, attr: str) -> bool:
    return bool(getattr(model, attr, False) or getattr(model, f"{attr}_pending", False))


def allow_hold_automation(model: models.Custodian) -> bool:
    if hold_automation_allow_override():
        return True
    return not bool(getattr(model, "person_lookup_overridden", False))


def has_usable_email(model: models.Custodian) -> bool:
    email = (getattr(model, "email", None) or "").strip()
    if not email:
        return False
    norm = email.lower()
    if norm in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        return False
    return "@" in norm


def provider_email_hold_complete(model: models.Custodian) -> bool:
    email_ok = (
        bool(getattr(model, "holds_email", False))
        and not bool(getattr(model, "holds_email_pending", False))
        and not bool(getattr(model, "holds_email_failed", False))
    )
    return bool(email_ok)


def clear_rubrik_restore_hold_flags(model: models.Custodian) -> None:
    model.holds_rubrik_restore = False
    model.holds_rubrik_restore_pending = False
    model.holds_rubrik_restore_failed = False
    if hasattr(model, "holds_rubrik_restore_released"):
        try:
            model.holds_rubrik_restore_released = False
        except Exception as exc:
            debug_suppressed("suppressed exception in case_request_hold_automation.py:clear_rubrik_released", exc)
    if hasattr(model, "_auto_rubrik_flag"):
        try:
            model._auto_rubrik_flag = False  # type: ignore[attr-defined]
        except Exception as exc:
            debug_suppressed("suppressed exception in case_request_hold_automation.py:clear_auto_rubrik", exc)


def filter_rubrik_targets_after_preservation(
    db: Session,
    rubrik_targets: list[models.Custodian],
) -> list[models.Custodian]:
    if not rubrik_targets:
        return []
    keep: list[models.Custodian] = []
    cleared: list[models.Custodian] = []
    for cust in rubrik_targets:
        if provider_email_hold_complete(cust):
            clear_rubrik_restore_hold_flags(cust)
            try:
                sync_legacy_custodian_to_default_hold(db, cust, changed_fields={"holds_rubrik_restore"})
            except Exception as exc:
                debug_suppressed("suppressed default-hold sync after Rubrik cleanup", exc)
            cleared.append(cust)
        else:
            keep.append(cust)
    if cleared:
        try:
            db.add_all(cleared)
        except Exception:
            try:
                for cust in cleared:
                    db.add(cust)
            except Exception as exc:
                debug_suppressed("suppressed exception in case_request_hold_automation.py:add_cleared", exc)
        try:
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception as exc:
                debug_suppressed("suppressed exception in case_request_hold_automation.py:rollback_cleared", exc)
    return keep

# Compatibility names for extensions written before provider-neutral automation.
def purview_email_hold_complete(model: models.Custodian) -> bool:
    return provider_email_hold_complete(model)


def filter_rubrik_targets_after_purview(
    db: Session,
    rubrik_targets: list[models.Custodian],
) -> list[models.Custodian]:
    return filter_rubrik_targets_after_preservation(db, rubrik_targets)
