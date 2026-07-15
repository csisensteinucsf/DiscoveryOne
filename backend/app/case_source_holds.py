from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .audit import log_event
from .hold_source_provider import (
    hold_source_automation_ready,
    hold_source_label,
    sync_custodian_hold,
)
from .hold_source_provider_registry import (
    HoldSourceConfigurationError,
    HoldSourceOperationError,
    HoldSourceSubjectNotFound,
    normalize_hold_source_key,
)

logger = logging.getLogger(__name__)


def _state_field(source_key: str, suffix: str | None = None) -> str:
    base = f"holds_{normalize_hold_source_key(source_key)}"
    return f"{base}_{suffix}" if suffix else base


def apply_hold_sync_state(
    custodian: Any,
    *,
    source_key: str,
    enable: bool,
) -> None:
    setattr(custodian, _state_field(source_key), bool(enable))
    setattr(custodian, _state_field(source_key, "pending"), False)
    setattr(custodian, _state_field(source_key, "failed"), False)
    setattr(custodian, _state_field(source_key, "released"), not bool(enable))


def apply_hold_sync_failure_state(
    custodian: Any,
    *,
    source_key: str,
    enable: bool,
) -> None:
    setattr(custodian, _state_field(source_key), bool(enable))
    setattr(custodian, _state_field(source_key, "pending"), False)
    setattr(custodian, _state_field(source_key, "failed"), True)
    setattr(custodian, _state_field(source_key, "released"), False)


def _audit(
    db: Session | None,
    *,
    action: str,
    details: dict[str, Any],
    actor_id: int | None,
    case_id: int | None,
    request: Request | None,
) -> None:
    if db is None:
        return
    try:
        log_event(
            db,
            action=action,
            actor_id=actor_id,
            target_type="case",
            target_id=case_id,
            details=details,
            request=request,
        )
    except Exception:
        logger.debug("Unable to write hold source audit event", exc_info=True)


def sync_hold_or_raise(
    case: Any,
    custodian: Any,
    *,
    source_key: str,
    enable: bool,
    email_override: Optional[str] = None,
    db: Optional[Session] = None,
    actor_id: Optional[int] = None,
    request: Request = None,
    source: str = "case_detail",
    continue_on_subject_not_found: bool = False,
) -> dict[str, Any]:
    normalized_source = normalize_hold_source_key(source_key)
    display_name = hold_source_label(normalized_source)
    email = (
        email_override
        if email_override is not None
        else getattr(custodian, "email", None)
    ) or ""
    email = email.strip()
    details = {
        "source_key": normalized_source,
        "provider_label": display_name,
        "case_id": getattr(case, "id", None),
        "case_name": getattr(case, "name", None),
        "custodian_id": getattr(custodian, "id", None),
        "custodian_name": getattr(custodian, "name", None),
        "custodian_email": email,
        "enable": bool(enable),
        "workflow_source": source,
    }

    if not hold_source_automation_ready(normalized_source):
        logger.info(
            "%s hold automation is not configured; preserving manual state: %s",
            display_name,
            details,
        )
        return {
            "source_key": normalized_source,
            "provider": "none",
            "status": "skipped",
            "reason": "automation_not_configured",
        }

    logger.info("Hold source sync attempt: %s", details)
    _audit(
        db,
        action="hold_source_sync_attempt",
        details=details,
        actor_id=actor_id,
        case_id=getattr(case, "id", None),
        request=request,
    )

    try:
        result = sync_custodian_hold(
            source_key=normalized_source,
            case=case,
            custodian=custodian,
            custodian_email=email,
            enable=enable,
            db=db,
            request=request,
            actor_id=actor_id,
        )
    except HoldSourceConfigurationError as error:
        failed = {**details, "reason": "config_error", "error": str(error)}
        logger.error("Hold source sync failed: %s", failed)
        _audit(
            db,
            action="hold_source_sync_failed",
            details=failed,
            actor_id=actor_id,
            case_id=getattr(case, "id", None),
            request=request,
        )
        raise HTTPException(status_code=503, detail=str(error)) from error
    except HoldSourceSubjectNotFound as error:
        failed = {
            **details,
            "reason": "subject_not_found",
            "error": str(error),
            "error_code": error.error_code,
            "status_code": error.status_code,
        }
        logger.error("Hold source sync failed: %s", failed)
        _audit(
            db,
            action="hold_source_sync_failed",
            details=failed,
            actor_id=actor_id,
            case_id=getattr(case, "id", None),
            request=request,
        )
        if continue_on_subject_not_found and enable:
            apply_hold_sync_failure_state(
                custodian,
                source_key=normalized_source,
                enable=True,
            )
            return {
                "source_key": normalized_source,
                "provider": normalized_source,
                "status": "failed",
                "reason": "subject_not_found",
                "continued": True,
            }
        raise HTTPException(
            status_code=502,
            detail=f"{display_name} hold sync failed: {error}",
        ) from error
    except HoldSourceOperationError as error:
        failed = {
            **details,
            "reason": "provider_error",
            "error": str(error),
            "error_code": error.error_code,
            "status_code": error.status_code,
        }
        logger.error("Hold source sync failed: %s", failed)
        _audit(
            db,
            action="hold_source_sync_failed",
            details=failed,
            actor_id=actor_id,
            case_id=getattr(case, "id", None),
            request=request,
        )
        raise HTTPException(
            status_code=502,
            detail=f"{display_name} hold sync failed: {error}",
        ) from error

    if result.get("status") == "skipped":
        return result

    apply_hold_sync_state(
        custodian,
        source_key=normalized_source,
        enable=enable,
    )
    completed = {**details, "provider_result": result}
    logger.info("Hold source sync succeeded: %s", completed)
    _audit(
        db,
        action="hold_source_sync",
        details=completed,
        actor_id=actor_id,
        case_id=getattr(case, "id", None),
        request=request,
    )
    return result


def sync_hold_transition(
    case: Any,
    custodian: Any,
    *,
    source_key: str,
    before_enabled: bool,
    before_email: Optional[str],
    db: Optional[Session] = None,
    actor_id: Optional[int] = None,
    request: Request = None,
    source: str = "case_detail",
) -> None:
    after_enabled = bool(getattr(custodian, _state_field(source_key), False))
    after_email = (getattr(custodian, "email", None) or "").strip()
    previous_email = (before_email or "").strip()
    email_changed = after_email.lower() != previous_email.lower()

    if before_enabled and (not after_enabled or email_changed):
        sync_hold_or_raise(
            case,
            custodian,
            source_key=source_key,
            enable=False,
            email_override=previous_email or None,
            db=db,
            actor_id=actor_id,
            request=request,
            source=source,
        )

    if after_enabled and (not before_enabled or email_changed):
        sync_hold_or_raise(
            case,
            custodian,
            source_key=source_key,
            enable=True,
            db=db,
            actor_id=actor_id,
            request=request,
            source=source,
        )
