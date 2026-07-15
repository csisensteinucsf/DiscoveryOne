from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from .case_source_holds import (
    apply_hold_sync_failure_state,
    apply_hold_sync_state,
    sync_hold_or_raise as _sync_source_hold_or_raise,
)


# Compatibility entry points for request-approval workflows.
def apply_slack_hold_sync_state(custodian: Any, *, enable: bool) -> None:
    apply_hold_sync_state(custodian, source_key="slack", enable=enable)


def apply_slack_hold_sync_failure_state(custodian: Any, *, enable: bool) -> None:
    apply_hold_sync_failure_state(
        custodian,
        source_key="slack",
        enable=enable,
    )


def sync_slack_hold_for_custodian_or_raise(
    case: Any,
    custodian: Any,
    *,
    enable: bool,
    email_override: Optional[str] = None,
    db: Optional[Session] = None,
    actor_id: Optional[int] = None,
    request: Request = None,
    source: str = "case_request_approve",
    continue_on_user_not_found: bool = False,
) -> dict[str, Any]:
    return _sync_source_hold_or_raise(
        case,
        custodian,
        source_key="slack",
        enable=enable,
        email_override=email_override,
        db=db,
        actor_id=actor_id,
        request=request,
        source=source,
        continue_on_subject_not_found=continue_on_user_not_found,
    )