from __future__ import annotations

import logging
import time
from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models, schemas
from .purview import PurviewAPIError, PurviewConfigError
from . import cases as case_core
from . import case_purview_gateway as purview_core
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
from .case_purview_utils import (
    _looks_like_url,
    _normalize_site_url,
    _purview_email_norm,
    _purview_site_key,
    _purview_sources_set,
)

logger = logging.getLogger(__name__)

def apply_purview_holds_for_case(
    case_id: int,
    payload: schemas.PurviewHoldRequest,
    db: Session,
    request: Request = None,
    _user: models.User = None,
):
    case_core.ensure_case_editable(_user)
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case_core.ensure_case_visible(case, _user, db)
    custodian_ids = sorted({int(cid) for cid in (payload.custodian_ids or []) if cid is not None})
    if not custodian_ids:
        raise HTTPException(status_code=400, detail="Select at least one custodian")
    if payload.included_sources is None:
        requested_sources = {"mailbox", "site"}
    else:
        requested_sources = _purview_sources_set(payload.included_sources)
        requested_sources = {s for s in requested_sources if s in {"mailbox", "site"}}
        if not requested_sources:
            raise HTTPException(status_code=400, detail="Select at least one hold source (mailbox or site)")
    verify_timeout_seconds = 0.0
    datasource_sync = None
    try:
        verify_timeout_seconds = float(getattr(payload, "verify_timeout_seconds", 0.0) or 0.0)
    except Exception:
        verify_timeout_seconds = 0.0
    logger.info(
        "purview_hold_apply_start case_id=%s custodian_ids=%s requested_sources=%s actor_id=%s",
        case_id,
        custodian_ids,
        sorted(requested_sources),
        getattr(_user, "id", None),
    )
    try:
        case_core.log_event(
            db,
            action="purview_hold_apply_attempt",
            actor_id=getattr(_user, "id", None),
            target_type="case",
            target_id=case.id,
            details={
                "case_id": case.id,
                "case_name": case.name,
                "custodian_ids": custodian_ids,
                "requested_sources": sorted(requested_sources),
                "verify_timeout_seconds": verify_timeout_seconds,
                "datasource_sync_enabled": bool(purview_core.add_data_sources_enabled()),
            },
            request=request,
        )
    except Exception as exc:
        case_core._debug_suppressed("suppressed exception in cases.py:3537", exc)
    if not purview_core.purview_enabled():
        logger.warning("purview_hold_apply_disabled case_id=%s", case_id)
        raise HTTPException(status_code=503, detail="Purview integration is not configured.")
    display_name = (case.name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Case must have a name before creating it in Purview")

    try:
        hold_context = build_purview_hold_apply_context(
            case=case,
            case_id=case_id,
            display_name=display_name,
        )
        purview_case = hold_context["purview_case"]
        provider_case_id = hold_context["purview_case_id"]
        holds = hold_context["holds"]
        hold = hold_context["hold"]
        hold_id = hold_context["hold_id"]
        hold_sources_flags = hold_context["hold_sources_flags"]
        hold_source_ids = hold_context["hold_source_ids"]
        site_ids_in_holds = hold_context["site_ids_in_holds"]
        case_custodians = hold_context["case_custodians"]
        case_custodian_by_email = hold_context["case_custodian_by_email"]
        case_emails = hold_context["case_emails"]
    except PurviewConfigError as exc:
        log_purview_failure(
            db,
            case,
            _user,
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
            _user,
            reason="api_error",
            message=str(exc),
            status_code=exc.status_code,
            request=request,
        )
        raise HTTPException(status_code=status, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        error_id = uuid4().hex
        logger.exception(
            "purview_hold_apply_exception error_id=%s case_id=%s actor_id=%s",
            error_id,
            case_id,
            getattr(_user, "id", None),
        )
        try:
            case_core.log_event(
                db,
                action="purview_hold_apply_failed",
                actor_id=getattr(_user, "id", None),
                target_type="case",
                target_id=getattr(case, "id", None),
                details={
                    "error_id": error_id,
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "custodian_ids": custodian_ids,
                    "requested_sources": sorted(requested_sources) if "requested_sources" in locals() else None,
                    "reason": "exception",
                    "error": str(exc),
                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:3689", exc)
        raise HTTPException(status_code=500, detail=f"Purview hold apply failed (error_id={error_id}).")

    # Optional (env-gated): sync custodians + noncustodial user/site sources before hold application.
    # This uses Microsoft Graph custodians/userSources APIs and does not call Purview portal-only endpoints.
    if purview_core.add_data_sources_enabled():
        datasource_sync = _purview_sync_case_datasources(
            db=db,
            case_id=case_id,
            purview_case_id=provider_case_id,
            custodian_ids=custodian_ids,
            requested_sources=requested_sources,
            actor_id=getattr(_user, "id", None),
            request=request,
            context="hold_apply",
        )


    results = []
    updated = []
    # Cache OneDrive site identifiers we learn while applying holds so verification can map
    # siteSources back to custodians without extra API calls.
    site_key_candidates_by_email: dict[str, set[str]] = {}

    for cid in custodian_ids:
        try:
            cust = db.query(models.Custodian).filter_by(id=cid, case_id=case_id).first()
            if not cust:
                results.append({"custodian_id": cid, "status": "not_found"})
                continue
            email = (cust.email or "").strip()
            email_norm_key = email.strip().lower() if email else ""
            if not email_norm_key or email_norm_key in {case_core.NO_EMAIL_PLACEHOLDER.lower(), case_core.UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
                if purview_core.hold_missing_email_mark_failed():
                    if "mailbox" in requested_sources:
                        _mark_mailbox_failed(cust)
                    if "site" in requested_sources:
                        _mark_site_failed(cust)
                else:
                    if "mailbox" in requested_sources:
                        cust.holds_email = True
                        cust.holds_email_pending = True
                        cust.holds_email_failed = False
                        if hasattr(cust, "holds_email_released"):
                            cust.holds_email_released = False
                    if "site" in requested_sources:
                        cust.holds_onedrive = True
                        cust.holds_onedrive_pending = True
                        cust.holds_onedrive_failed = False
                        if hasattr(cust, "holds_onedrive_released"):
                            cust.holds_onedrive_released = False
                updated.append(cust)
                results.append(
                    {
                        "custodian_id": cust.id,
                        "email": None,
                        "status": "missing_email",
                        "message": "Missing email; hold left as pending.",
                    }
                )
                continue
            email_norm = _purview_email_norm(email)
            mailbox_failed = False
            site_failed = False
            errors = []
            try:
                if email_norm not in case_emails:
                    purview_core.add_purview_case_custodian(
                        provider_case_id,
                        email=email,
                        display_name=(cust.name or "").strip() or None,
                    )
                    case_emails.add(email_norm)
            except PurviewAPIError as exc:
                errors.append(str(exc))
                if "mailbox" in requested_sources:
                    mailbox_failed = True
                if "site" in requested_sources:
                    site_failed = True
            existing_flags = hold_sources_flags.get(email_norm) or {"mailbox": False, "site": False}
            raw_site = getattr(cust, "onedrive_site_id", None)
            cust_site_key = _normalize_site_url(raw_site) if _looks_like_url(raw_site) else str(raw_site or "").strip().lower()
            if cust_site_key and cust_site_key in site_ids_in_holds:
                existing_flags["site"] = True
                hold_sources_flags[email_norm] = existing_flags
            if errors:
                if "mailbox" in requested_sources:
                    _mark_mailbox_failed(cust)
                if "site" in requested_sources:
                    _mark_site_failed(cust)
                updated.append(cust)
                results.append({
                    "custodian_id": cust.id,
                    "email": email,
                    "status": "error",
                    "message": "; ".join(errors),
                })
                continue
            already_selected = all(existing_flags.get(src) for src in requested_sources)
            if already_selected:
                if "mailbox" in requested_sources:
                    _mark_mailbox_success(cust)
                if "site" in requested_sources:
                    _mark_site_success(cust)
                updated.append(cust)
                results.append({"custodian_id": cust.id, "email": email, "status": "already_on_hold"})
                continue
            if "mailbox" in requested_sources and not existing_flags.get("mailbox"):
                try:
                    purview_core.add_purview_hold_user_source(
                        provider_case_id,
                        hold_id,
                        email=email,
                        included_sources=None,
                    )
                    existing_flags["mailbox"] = True
                    hold_sources_flags[email_norm] = existing_flags
                    _mark_mailbox_success(cust)
                except PurviewAPIError as exc:
                    mailbox_failed = True
                    errors.append(str(exc))
                    _mark_mailbox_failed(cust)
            if "site" in requested_sources and not existing_flags.get("site"):
                site_resource = None
                try:
                    site_resource = purview_core.get_purview_onedrive_site(email)
                except PurviewAPIError as exc:
                    site_failed = True
                    errors.append(str(exc))
                    _mark_site_failed(cust)
                site_id = (site_resource or {}).get("id")
                site_web_url = (site_resource or {}).get("webUrl") or (site_resource or {}).get("sharepointSiteUrl")
                sharepoint_site_id = (site_resource or {}).get("sharepointSiteId")
                bind_id_url = (site_resource or {}).get("bindIdUrl")
                bind_url = (site_resource or {}).get("bindUrl")
                canonical_site_key = _canonical_site_key(site_resource)
                candidate_keys = []
                if isinstance(site_id, str) and site_id.strip():
                    candidate_keys.append(site_id.strip().lower())
                if isinstance(site_web_url, str) and site_web_url.strip():
                    candidate_keys.append(_normalize_site_url(site_web_url))
                if isinstance(sharepoint_site_id, str) and sharepoint_site_id.strip():
                    candidate_keys.append(sharepoint_site_id.strip().lower())
                if email_norm and email_norm not in {case_core.NO_EMAIL_PLACEHOLDER.lower(), case_core.UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
                    bucket = site_key_candidates_by_email.setdefault(email_norm, set())
                    for key in candidate_keys:
                        if not key:
                            continue
                        bucket.add(_normalize_site_url(key) if _looks_like_url(key) else str(key).strip().lower())
                    if canonical_site_key:
                        bucket.add(
                            _normalize_site_url(canonical_site_key)
                            if _looks_like_url(canonical_site_key)
                            else str(canonical_site_key).strip().lower()
                        )
                if not site_failed and candidate_keys:
                    matched_key = None
                    for key in candidate_keys:
                        if key in site_ids_in_holds:
                            existing_flags["site"] = True
                            hold_sources_flags[email_norm] = existing_flags
                            matched_key = key
                            cust.onedrive_site_id = key
                            break
                if not site_failed and existing_flags.get("site"):
                    _mark_site_success(cust)
                elif not site_failed:
                    attempts = []
                    seen_attempts = set()

                    def _queue_attempt(mode: str, payload: dict, site_key: str) -> None:
                        if not payload or not site_key:
                            return
                        key = (mode, site_key)
                        if key in seen_attempts:
                            return
                        seen_attempts.add(key)
                        attempts.append((mode, payload, site_key))

                    if isinstance(site_id, str) and site_id.strip():
                        site_id_val = site_id.strip()
                        _queue_attempt("id", {"site_id": site_id_val}, site_id_val.lower())
                    if isinstance(bind_id_url, str) and bind_id_url.strip():
                        bind_id_val = bind_id_url.strip()
                        bind_key = site_id.strip().lower() if isinstance(site_id, str) and site_id.strip() else bind_id_val.lower()
                        _queue_attempt("bind_id", {"site_bind_url": bind_id_val}, bind_key)
                    if isinstance(site_web_url, str) and site_web_url.strip():
                        site_url_val = site_web_url.strip()
                        _queue_attempt("web_url", {"site_web_url": site_url_val}, _normalize_site_url(site_url_val))
                    if isinstance(bind_url, str) and bind_url.strip():
                        bind_val = bind_url.strip()
                        bind_key = _normalize_site_url(site_web_url) if isinstance(site_web_url, str) and site_web_url.strip() else bind_val.lower()
                        _queue_attempt("bind_url", {"site_bind_url": bind_val}, bind_key)
                    if isinstance(sharepoint_site_id, str) and sharepoint_site_id.strip():
                        sp_id_val = sharepoint_site_id.strip()
                        _queue_attempt("sharepoint_id", {"site_id": sp_id_val}, sp_id_val.lower())

                    last_exc = None
                    site_key = None
                    for mode, payload, key in attempts:
                        try:
                            response = purview_core.add_purview_hold_site_source(provider_case_id, hold_id, **payload)
                            response_key = _purview_site_key(response) if response else None
                            site_key = response_key or key
                            break
                        except PurviewAPIError as exc:
                            last_exc = exc
                            if _is_site_source_retryable(exc):
                                continue
                            break
                    if not site_key:
                        fallback_error = _apply_user_source_site_hold(
                            email_norm,
                            email,
                            existing_flags,
                            requested_sources=requested_sources,
                            purview_case_id=provider_case_id,
                            hold_id=hold_id,
                            hold_source_ids=hold_source_ids,
                            hold_sources_flags=hold_sources_flags,
                        )
                        if fallback_error is None:
                            if canonical_site_key:
                                cust.onedrive_site_id = canonical_site_key
                            _mark_site_success(cust)
                        else:
                            site_failed = True
                            if fallback_error:
                                errors.append(fallback_error)
                            elif last_exc:
                                errors.append(str(last_exc))
                            else:
                                errors.append("OneDrive site id not found.")
                            _mark_site_failed(cust)
                    else:
                        site_ids_in_holds.add(site_key)
                        existing_flags["site"] = True
                        hold_sources_flags[email_norm] = existing_flags
                        cust.onedrive_site_id = site_key
                        _mark_site_success(cust)
            if "mailbox" in requested_sources and existing_flags.get("mailbox") and not mailbox_failed:
                _mark_mailbox_success(cust)
            if "site" in requested_sources and existing_flags.get("site") and not site_failed:
                _mark_site_success(cust)
            updated.append(cust)
            requested_mailbox = "mailbox" in requested_sources
            requested_site = "site" in requested_sources
            any_success = (requested_mailbox and not mailbox_failed) or (requested_site and not site_failed)
            if errors:
                onedrive_missing_only = (
                    requested_site
                    and not requested_mailbox
                    and all("onedrive site id not found" in str(err).lower() for err in errors)
                )
                results.append({
                    "custodian_id": cust.id,
                    "email": email,
                    "status": "onedrive_missing" if onedrive_missing_only else ("partial_hold" if any_success else "error"),
                    "message": "; ".join(errors),
                })
            else:
                results.append({"custodian_id": cust.id, "email": email, "status": "on_hold"})
        except HTTPException:
            raise
        except Exception as exc:
            error_id = uuid4().hex
            logger.exception(
                "purview_hold_apply_loop_exception error_id=%s case_id=%s purview_case_id=%s hold_id=%s custodian_id=%s",
                error_id,
                case_id,
                provider_case_id,
                hold_id,
                cid,
            )
            try:
                case_core.log_event(
                    db,
                    action="purview_hold_apply_failed",
                    actor_id=getattr(_user, "id", None),
                    target_type="case",
                    target_id=case.id,
                    details={
                        "error_id": error_id,
                        "case_id": case.id,
                        "case_name": case.name,
                        "purview_case_id": provider_case_id,
                        "purview_hold_id": hold_id,
                        "custodian_ids": custodian_ids,
                        "custodian_id": cid,
                        "requested_sources": sorted(requested_sources),
                        "reason": "loop_exception",
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    },
                    request=request,
                )
            except Exception as exc:
                case_core._debug_suppressed("suppressed exception in cases.py:4474", exc)
            raise HTTPException(status_code=500, detail=f"Purview hold apply failed (error_id={error_id}).")

    verified_sources: Optional[dict[str, dict]] = None
    if provider_case_id and hold_id and requested_sources and updated:
        # Purview can be eventually-consistent for OneDrive site sources; allow callers to wait longer.
        max_wait = max(0.0, verify_timeout_seconds)
        start_ts = time.time()
        attempts = 3 if max_wait <= 0 else 999999
        delay_seconds = 1.5
        for attempt in range(attempts):
            try:
                verified_sources = build_hold_source_map(
                    db=db,
                    case_id=case_id,
                    purview_case_id=provider_case_id,
                    hold_id=hold_id,
                    updated=updated,
                    site_key_candidates_by_email=site_key_candidates_by_email,
                )
            except PurviewAPIError as exc:
                logger.warning(
                    "purview_hold_verify_failed case_id=%s purview_case_id=%s hold_id=%s attempt=%s error=%s",
                    case_id,
                    provider_case_id,
                    hold_id,
                    attempt + 1,
                    exc,
                )
                verified_sources = None
                break
            except Exception as exc:
                # Don't fail the whole request if verification/mapping fails unexpectedly.
                logger.exception(
                    "purview_hold_verify_exception case_id=%s purview_case_id=%s hold_id=%s attempt=%s",
                    case_id,
                    provider_case_id,
                    hold_id,
                    attempt + 1,
                )
                verified_sources = None
                break
            all_verified = True
            for cust in updated:
                email_norm = _purview_email_norm(getattr(cust, "email", None))
                if not email_norm or email_norm in {case_core.NO_EMAIL_PLACEHOLDER.lower(), case_core.UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
                    continue
                flags = verified_sources.get(email_norm) or {}
                if "mailbox" in requested_sources and not flags.get("mailbox"):
                    all_verified = False
                    break
                if should_verify_site(requested_sources) and not flags.get("site"):
                    all_verified = False
                    break
            if all_verified:
                break
            if max_wait > 0 and (time.time() - start_ts) >= max_wait:
                break
            if max_wait > 0:
                # Backoff a bit for longer waits.
                if attempt < 2:
                    delay_seconds = 2.5
                elif attempt < 5:
                    delay_seconds = 5.0
                else:
                    delay_seconds = 10.0
            if attempt < attempts - 1:
                time.sleep(delay_seconds)

    if verified_sources is not None:
        hold_sources_flags = {
            email: {"mailbox": bool(flags.get("mailbox")), "site": bool(flags.get("site"))}
            for email, flags in verified_sources.items()
        }
        results_by_id = {
            item.get("custodian_id"): item
            for item in results
            if isinstance(item, dict) and item.get("custodian_id") is not None
        }
        for cust in updated:
            email_norm = _purview_email_norm(getattr(cust, "email", None))
            if not email_norm or email_norm in {case_core.NO_EMAIL_PLACEHOLDER.lower(), case_core.UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
                continue
            flags = verified_sources.get(email_norm) or {}
            row = results_by_id.get(getattr(cust, "id", None))
            if row is not None:
                row["mailbox"] = bool(flags.get("mailbox"))
                row["site"] = bool(flags.get("site"))
            if "mailbox" in requested_sources:
                if flags.get("mailbox"):
                    _mark_mailbox_success(cust)
                elif not cust.holds_email_failed:
                    cust.holds_email = False
                    cust.holds_email_pending = True
                    if hasattr(cust, "holds_email_released"):
                        cust.holds_email_released = False
            if "site" in requested_sources:
                if flags.get("site"):
                    _mark_site_success(cust)
                elif not cust.holds_onedrive_failed:
                    cust.holds_onedrive = False
                    cust.holds_onedrive_pending = True
                    if hasattr(cust, "holds_onedrive_released"):
                        cust.holds_onedrive_released = False
            if not row or row.get("status") in {"missing_email", "not_found"}:
                continue
            mailbox_ok = ("mailbox" not in requested_sources) or flags.get("mailbox")
            site_ok = ("site" not in requested_sources) or flags.get("site")
            if mailbox_ok and site_ok:
                if row.get("status") != "already_on_hold":
                    row["status"] = "on_hold"
                row.pop("message", None)
            elif mailbox_ok or site_ok:
                row["status"] = "partial_hold"
            elif row.get("status") not in {"error", "missing_email", "not_found"}:
                row["status"] = "pending"

    try:
        db.commit()
    except Exception:
        db.rollback()
        error_id = uuid4().hex
        logger.exception(
            "purview_hold_apply_db_commit_failed error_id=%s case_id=%s purview_case_id=%s hold_id=%s custodian_ids=%s",
            error_id,
            case_id,
            provider_case_id,
            hold_id,
            custodian_ids,
        )
        try:
            case_core.log_event(
                db,
                action="purview_hold_apply_failed",
                actor_id=getattr(_user, "id", None),
                target_type="case",
                target_id=case.id,
                details={
                    "error_id": error_id,
                    "case_id": case.id,
                    "case_name": case.name,
                    "purview_case_id": provider_case_id,
                    "purview_hold_id": hold_id,
                    "custodian_ids": custodian_ids,
                    "requested_sources": sorted(requested_sources),
                    "reason": "db_commit_failed",
                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:4697", exc)
        raise HTTPException(status_code=500, detail=f"Purview hold apply failed (error_id={error_id}).")

    updated_payload = [
        {
            "id": c.id,
            "holds_email": c.holds_email,
            "holds_onedrive": c.holds_onedrive,
            "holds_email_pending": c.holds_email_pending,
            "holds_onedrive_pending": c.holds_onedrive_pending,
            "holds_email_failed": c.holds_email_failed,
            "holds_onedrive_failed": c.holds_onedrive_failed,
            "holds_email_released": getattr(c, "holds_email_released", False),
            "holds_onedrive_released": getattr(c, "holds_onedrive_released", False),
        }
        for c in updated
    ]
    try:
        try:
            case_core.log_event(
                db,
                action="purview_hold_apply",
                actor_id=getattr(_user, "id", None),
                target_type="case",
                target_id=case.id,
                details={
                    "case_id": case.id,
                    "case_name": case.name,
                    "purview_case_id": provider_case_id,
                    "purview_hold_id": hold_id,
                    "custodian_ids": custodian_ids,
                    "requested_sources": sorted(requested_sources),
                    "results": results,
                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:4734", exc)
        hold_source_rows = [
            {
                "email": email,
                "mailbox": bool(flags.get("mailbox")),
                "site": bool(flags.get("site")),
            }
            for email, flags in sorted(hold_sources_flags.items(), key=lambda item: item[0])
        ]
        status_counts: dict[str, int] = {}
        for item in results:
            status = (item.get("status") or "").strip().lower()
            if not status:
                continue
            status_counts[status] = status_counts.get(status, 0) + 1
        if any(status_counts.get(key) for key in ("error", "partial_hold", "onedrive_missing", "missing_email", "not_found")):
            logger.warning(
                "purview_hold_apply_incomplete case_id=%s purview_case_id=%s hold_id=%s status_counts=%s",
                case_id,
                provider_case_id,
                hold_id,
                status_counts,
            )
        logger.info(
            "purview_hold_apply_complete case_id=%s purview_case_id=%s hold_id=%s status_counts=%s results=%s",
            case_id,
            provider_case_id,
            hold_id,
            status_counts,
            results,
        )
        result = {
            "provider_case_id": provider_case_id,
            "purview_case_id": provider_case_id,
            "hold_id": hold_id,
            "hold_display_name": hold.get("displayName"),
            "results": results,
            "updated_custodians": updated_payload,
            "hold_user_emails": sorted(hold_sources_flags.keys()),
            "hold_user_sources": hold_source_rows,
        }
        if datasource_sync is not None:
            result["datasource_sync"] = datasource_sync
        case_core._schedule_preservation_status_poll(case_id, "purview_hold_apply")
        # When holds are applied manually (admin/analyst case view), also notify the requestor
        # with the same delayed hold-status email used for requestor-driven case requests.
        try:
            case_core._schedule_case_requestor_hold_status_email(
                case.id,
                custodian_ids,
                reason="purview_hold_applied",
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:4787", exc)
        return result
    except Exception:
        error_id = uuid4().hex
        logger.exception(
            "purview_hold_apply_response_failed error_id=%s case_id=%s purview_case_id=%s hold_id=%s",
            error_id,
            case_id,
            provider_case_id,
            hold_id,
        )
        try:
            case_core.log_event(
                db,
                action="purview_hold_apply_failed",
                actor_id=getattr(_user, "id", None),
                target_type="case",
                target_id=case.id,
                details={
                    "error_id": error_id,
                    "case_id": case.id,
                    "case_name": case.name,
                    "purview_case_id": provider_case_id,
                    "purview_hold_id": hold_id,
                    "custodian_ids": custodian_ids,
                    "requested_sources": sorted(requested_sources),
                    "reason": "response_build_failed",
                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:4818", exc)
        raise HTTPException(status_code=500, detail=f"Purview hold apply failed (error_id={error_id}).")


