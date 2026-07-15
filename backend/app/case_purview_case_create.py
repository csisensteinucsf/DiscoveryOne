import logging

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from . import cases as case_core
from . import case_purview_gateway as purview_core
from .case_purview_datasources import _purview_sync_case_datasources
from .case_purview_logging import log_purview_failure
from .purview import PurviewAPIError, PurviewConfigError

logger = logging.getLogger(__name__)


def create_purview_case_for_case(
    *,
    case_id: int,
    db: Session,
    request: Request | None,
    user: models.User,
) -> dict:
    case_core.ensure_case_editable(user)
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case_core.ensure_case_visible(case, user, db)
    logger.info(
        "purview_case_create_start case_id=%s case_name=%s actor_id=%s",
        case.id,
        case.name,
        getattr(user, "id", None),
    )
    display_name = (case.name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Case must have a name before creating it in Purview")
    description = (case.description or "").strip() or None
    try:
        existing = purview_core.find_purview_case_by_display_name(display_name)
    except PurviewConfigError as exc:
        log_purview_failure(
            db,
            case,
            user,
            reason="config_error",
            message=str(exc),
            request=request,
        )
        raise HTTPException(status_code=503, detail=str(exc))
    except PurviewAPIError as exc:
        status = exc.status_code or 502
        if status < 400 or status >= 600:
            status = 502
        log_purview_failure(
            db,
            case,
            user,
            reason="api_error",
            message=str(exc),
            status_code=exc.status_code,
            request=request,
        )
        raise HTTPException(status_code=status, detail=str(exc))
    if existing:
        provider_case_id = existing.get("id")
        logger.info(
            "purview_case_exists case_id=%s purview_case_id=%s display_name=%s",
            case.id,
            provider_case_id,
            existing.get("displayName") or display_name,
        )
        result = {
            "provider_case_id": provider_case_id,
            "purview_case_id": provider_case_id,
            "display_name": existing.get("displayName") or display_name,
            "status": "exists",
        }
        if purview_core.add_data_sources_enabled() and isinstance(provider_case_id, str) and provider_case_id:
            sync_result = _purview_sync_case_datasources(
                db=db,
                case_id=case.id,
                purview_case_id=provider_case_id,
                requested_sources={"mailbox", "site"},
                actor_id=getattr(user, "id", None),
                request=request,
                context="case_create_exists",
            )
            result["datasource_sync"] = sync_result
        case_core._schedule_preservation_status_poll(case.id, "purview_case_exists")
        return result
    try:
        logger.info(
            "purview_case_create_request case_id=%s display_name=%s",
            case.id,
            display_name,
        )
        created = purview_core.create_purview_case(display_name=display_name, description=description)
    except PurviewConfigError as exc:
        log_purview_failure(
            db,
            case,
            user,
            reason="config_error",
            message=str(exc),
            request=request,
        )
        raise HTTPException(status_code=503, detail=str(exc))
    except PurviewAPIError as exc:
        status = exc.status_code or 502
        if status < 400 or status >= 600:
            status = 502
        log_purview_failure(
            db,
            case,
            user,
            reason="api_error",
            message=str(exc),
            status_code=exc.status_code,
            request=request,
        )
        raise HTTPException(status_code=status, detail=str(exc))
    provider_case_id = created.get("id")
    logger.info(
        "purview_case_created case_id=%s purview_case_id=%s display_name=%s",
        case.id,
        provider_case_id,
        created.get("displayName") or display_name,
    )
    try:
        case_core.log_event(
            db,
            action="purview_case_create",
            actor_id=getattr(user, "id", None),
            target_type="case",
            target_id=case.id,
            details={
                "case_name": case.name,
                "purview_case_id": created.get("id"),
                "purview_display_name": created.get("displayName"),
            },
            request=request,
        )
    except Exception as exc:
        case_core._debug_suppressed("suppressed exception in case_purview_case_create.create_purview_case_for_case", exc)
    result = {
        "provider_case_id": provider_case_id,
        "purview_case_id": provider_case_id,
        "display_name": created.get("displayName") or display_name,
        "status": "created",
    }
    if purview_core.add_data_sources_enabled() and isinstance(provider_case_id, str) and provider_case_id:
        sync_result = _purview_sync_case_datasources(
            db=db,
            case_id=case.id,
            purview_case_id=provider_case_id,
            requested_sources={"mailbox", "site"},
            actor_id=getattr(user, "id", None),
            request=request,
            context="case_create_created",
        )
        result["datasource_sync"] = sync_result
    case_core._schedule_preservation_status_poll(case.id, "purview_case_created")
    return result
