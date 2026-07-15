import logging
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from . import cases as case_core

logger = logging.getLogger(__name__)


def log_purview_failure(
    db: Session,
    case: models.Case,
    user: models.User,
    *,
    reason: str,
    message: str,
    status_code: Optional[int] = None,
    request: Request | None = None,
) -> None:
    details = {
        "case_id": getattr(case, "id", None),
        "case_name": getattr(case, "name", None),
        "reason": reason,
        "error": message,
    }
    if status_code is not None:
        details["status_code"] = status_code
    logger.error("Purview operation failed: %s", details)
    try:
        case_core.log_event(
            db,
            action="purview_case_create_failed",
            actor_id=getattr(user, "id", None),
            target_type="case",
            target_id=getattr(case, "id", None),
            details=details,
            request=request,
        )
    except Exception as exc:
        case_core._debug_suppressed("suppressed exception in case_purview_logging.log_purview_failure", exc)
