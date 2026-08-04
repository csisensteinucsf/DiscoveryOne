import json
import logging
import re
import time
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, selectinload

from . import models, preservation_provider, schemas
from .auth import current_user as get_current_user
from .database import get_db
from .hold_workflows import resolve_hold_memberships, set_membership_preservation_status
from .purview import PurviewAPIError, PurviewConfigError
from . import cases as case_core
from .case_purview_datasources import _purview_sync_case_datasources
from .case_purview_logging import log_purview_failure
from .case_purview_hold_setup import build_purview_hold_apply_context
from .case_purview_hold_apply import (
    apply_user_source_site_hold as _apply_user_source_site_hold,
    build_hold_source_map,
    is_item_not_found as _is_item_not_found,
    is_site_source_retryable as _is_site_source_retryable,
    mark_mailbox_failed as _mark_mailbox_failed,
    mark_mailbox_success as _mark_mailbox_success,
    mark_site_failed as _mark_site_failed,
    mark_site_success as _mark_site_success,
    should_verify_site,
)
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])

@router.post("/{case_id}/preservation_provider/case")
@router.post("/{case_id}/purview_case", include_in_schema=False)
def create_case_in_purview(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    return preservation_provider.create_case(
        case_id=case_id,
        db=db,
        request=request,
        user=_user,
    )

def _purview_utils():
    from . import case_purview_utils
    return case_purview_utils


def _purview_email_norm(value: Optional[str]) -> str:
    return _purview_utils()._purview_email_norm(value)


def _purview_name_norm(value: Optional[str]) -> str:
    return _purview_utils()._purview_name_norm(value)


def _extract_email_candidates(payload: Any, *, max_depth: int = 3, max_values: int = 10) -> set[str]:
    return _purview_utils()._extract_email_candidates(payload, max_depth=max_depth, max_values=max_values)


def _purview_hold_display_name(case_name: str) -> str:
    return _purview_utils()._purview_hold_display_name(case_name)


def _purview_hold_name_match(hold: dict, target_name: str) -> bool:
    return _purview_utils()._purview_hold_name_match(hold, target_name)


def _purview_sources_set(included_sources: Optional[list]) -> set[str]:
    return _purview_utils()._purview_sources_set(included_sources)


def _purview_sources_flags(included_sources: Optional[list]) -> dict:
    return _purview_utils()._purview_sources_flags(included_sources)


def _normalize_site_url(value: Optional[str]) -> str:
    return _purview_utils()._normalize_site_url(value)


def _looks_like_url(value: Optional[str]) -> bool:
    return _purview_utils()._looks_like_url(value)


def _normalize_personal_key(value: Optional[str]) -> Optional[str]:
    return _purview_utils()._normalize_personal_key(value)


def _onedrive_personal_key(email: Optional[str]) -> Optional[str]:
    return _purview_utils()._onedrive_personal_key(email)


def _personal_key_from_url(url: Optional[str]) -> Optional[str]:
    return _purview_utils()._personal_key_from_url(url)


def _canonical_site_key(resource: Optional[dict]) -> Optional[str]:
    return _purview_utils()._canonical_site_key(resource)


def _candidate_site_keys(resource: Optional[dict]) -> list[str]:
    return _purview_utils()._candidate_site_keys(resource)


def _purview_site_key(source: dict) -> Optional[str]:
    return _purview_utils()._purview_site_key(source)


@router.get("/{case_id}/preservation_provider/status")
@router.get("/{case_id}/purview_status", include_in_schema=False)
def get_purview_status(
    case_id: int,
    case_hold_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    return preservation_provider.get_status(
        case_id=case_id,
        db=db,
        request=request,
        user=_user,
        case_hold_id=case_hold_id,
    )

def _provider_source_pairs(payload: schemas.PreservationHoldRequest) -> list[tuple[str, str]]:
    requested = set(payload.included_sources or ["mailbox", "site"])
    pairs = []
    if "mailbox" in requested:
        pairs.append(("mailbox", "email"))
    if "site" in requested:
        pairs.append(("site", "onedrive"))
    if not pairs:
        raise HTTPException(status_code=400, detail="Select at least one hold source")
    return pairs


def _mark_hold_memberships(
    db: Session,
    memberships: dict[int, models.HoldCustodian],
    sources: list[tuple[str, str]],
    status: str,
    *,
    error: str | None = None,
) -> None:
    for membership in memberships.values():
        for _provider_source, source in sources:
            set_membership_preservation_status(
                db,
                membership,
                source,
                status,
                last_error=error,
            )


def _sync_provider_hold_result(
    db: Session,
    memberships: dict[int, models.HoldCustodian],
    sources: list[tuple[str, str]],
    result: Any,
    *,
    release: bool,
) -> None:
    updated = {
        int(item.get("id")): item
        for item in (result.get("updated_custodians") if isinstance(result, dict) else []) or []
        if isinstance(item, dict) and item.get("id") is not None
    }
    results = {
        int(item.get("custodian_id")): item
        for item in (result.get("results") if isinstance(result, dict) else []) or []
        if isinstance(item, dict) and item.get("custodian_id") is not None
    }
    for custodian_id, membership in memberships.items():
        update = updated.get(int(custodian_id), {})
        operation = results.get(int(custodian_id), {})
        operation_status = str(operation.get("status") or "").strip().lower()
        for _provider_source, source in sources:
            prefix = "holds_email" if source == "email" else "holds_onedrive"
            if bool(update.get(prefix + "_failed")) or operation_status in {"error", "not_found"}:
                status = "failed"
            elif bool(update.get(prefix + "_pending")) or operation_status in {"partial_hold", "missing_email", "onedrive_missing"}:
                status = "pending"
            elif release or bool(update.get(prefix + "_released")):
                status = "released"
            elif bool(update.get(prefix)) or operation_status in {"on_hold", "already_on_hold"}:
                status = "active"
            else:
                status = "pending"
            set_membership_preservation_status(
                db,
                membership,
                source,
                status,
                last_error=str(operation.get("message") or "").strip() or None,
            )


def _run_hold_provider_operation(
    *,
    case_id: int,
    payload: schemas.PreservationHoldRequest,
    db: Session,
    request: Request | None,
    user: models.User,
    release: bool,
):
    hold, memberships = resolve_hold_memberships(
        db,
        case_id=case_id,
        custodian_ids=payload.custodian_ids,
        case_hold_id=payload.case_hold_id,
    )
    sources = _provider_source_pairs(payload)
    _mark_hold_memberships(db, memberships, sources, "pending")
    db.commit()
    operation = preservation_provider.release_holds if release else preservation_provider.apply_holds
    try:
        result = operation(
            case_id=case_id,
            payload=payload,
            db=db,
            request=request,
            user=user,
        )
    except HTTPException as exc:
        db.rollback()
        fresh = {
            int(row.custodian_id): row
            for row in db.query(models.HoldCustodian)
            .filter(models.HoldCustodian.id.in_([item.id for item in memberships.values()]))
            .all()
        }
        _mark_hold_memberships(db, fresh, sources, "failed", error=str(exc.detail))
        db.commit()
        raise
    _sync_provider_hold_result(db, memberships, sources, result, release=release)
    db.commit()
    if isinstance(result, dict):
        return {**result, "case_hold_id": hold.id, "case_hold_name": hold.name}
    return result


@router.post("/{case_id}/preservation_provider/holds")
@router.post("/{case_id}/purview_holds", include_in_schema=False)
def apply_purview_holds(
    case_id: int,
    payload: schemas.PreservationHoldRequest,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    return _run_hold_provider_operation(
        case_id=case_id,
        payload=payload,
        db=db,
        request=request,
        user=_user,
        release=False,
    )
@router.post("/{case_id}/preservation_provider/holds/release")
@router.post("/{case_id}/purview_holds/release", include_in_schema=False)
def release_purview_holds(
    case_id: int,
    payload: schemas.PreservationHoldRequest,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    return _run_hold_provider_operation(
        case_id=case_id,
        payload=payload,
        db=db,
        request=request,
        user=_user,
        release=True,
    )