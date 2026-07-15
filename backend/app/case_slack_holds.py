from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from .case_source_holds import (
    apply_hold_sync_state,
    sync_hold_or_raise as _sync_source_hold_or_raise,
    sync_hold_transition as _sync_source_hold_transition,
)


# Compatibility entry points for existing case workflows and extensions.
def apply_slack_hold_sync_state(custodian: Any, *, enable: bool) -> None:
    apply_hold_sync_state(custodian, source_key="slack", enable=enable)


def sync_slack_hold_or_raise(
    case: Any,
    custodian: Any,
    *,
    enable: bool,
    email_override: Optional[str] = None,
    db: Optional[Session] = None,
    actor_id: Optional[int] = None,
    request: Request = None,
    source: str = "case_detail",
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
    )


def sync_slack_hold_transition(
    case: Any,
    custodian: Any,
    *,
    before_holds_slack: bool,
    before_email: Optional[str],
    db: Optional[Session] = None,
    actor_id: Optional[int] = None,
    request: Request = None,
    source: str = "case_detail",
) -> None:
    _sync_source_hold_transition(
        case,
        custodian,
        source_key="slack",
        before_enabled=before_holds_slack,
        before_email=before_email,
        db=db,
        actor_id=actor_id,
        request=request,
        source=source,
    )