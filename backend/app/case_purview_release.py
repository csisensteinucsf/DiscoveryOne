from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models, schemas
from .purview import PurviewAPIError, PurviewConfigError
from . import cases as case_core
from . import case_purview_gateway as purview_core
from .case_purview_utils import (
    _candidate_site_keys,
    _extract_email_candidates,
    _looks_like_url,
    _normalize_site_url,
    _onedrive_personal_key,
    _personal_key_from_url,
    _purview_email_norm,
    _purview_hold_display_name,
    _purview_hold_name_match,
    _purview_site_key,
    _purview_sources_set,
)

def release_purview_holds_for_case(
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
    requested_sources = _purview_sources_set(payload.included_sources) if payload.included_sources is not None else {"mailbox", "site"}
    requested_sources = {s for s in requested_sources if s in {"mailbox", "site"}}
    delete_hold_policy = bool(getattr(payload, "delete_hold_policy", False))
    if not requested_sources:
        raise HTTPException(status_code=400, detail="Select at least one hold source (mailbox or site)")
    custodian_ids = sorted({int(cid) for cid in (payload.custodian_ids or []) if cid is not None})
    if not purview_core.purview_enabled():
        raise HTTPException(status_code=503, detail="Purview integration is not configured.")
    display_name = (case.name or "").strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="Case must have a name before releasing holds")
    def _log_release_event(action: str, details: dict) -> None:
        try:
            case_core.log_event(
                db,
                action=action,
                actor_id=getattr(_user, "id", None),
                target_type="case",
                target_id=case.id,
                details=details,
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:4858", exc)
    def _log_release_status(status: str, extra: Optional[dict] = None) -> None:
        details = {
            "case_id": case.id,
            "case_name": case.name,
            "status": status,
            "custodian_ids": custodian_ids,
            "requested_sources": sorted(requested_sources),
            "release_mode": "delete_policy" if delete_hold_policy else "remove_sources",
        }
        if extra:
            details.update(extra)
        _log_release_event("purview_hold_release", details)
    def _log_release_error(reason: str, message: str, status_code: Optional[int] = None) -> None:
        details = {
            "case_id": case.id,
            "case_name": case.name,
            "reason": reason,
            "error": message,
            "custodian_ids": custodian_ids,
            "requested_sources": sorted(requested_sources),
            "release_mode": "delete_policy" if delete_hold_policy else "remove_sources",
        }
        if status_code is not None:
            details["status_code"] = status_code
        _log_release_event("purview_hold_release_failed", details)
    try:
        purview_case = purview_core.find_purview_case_by_display_name(display_name)
        if not purview_case:
            _log_release_status("no_case")
            return {"status": "no_case", "results": []}
        provider_case_id = purview_case.get("id")
        if not provider_case_id:
            _log_release_status("no_case_id")
            return {"status": "no_case_id", "results": []}
        holds = purview_core.list_purview_case_legal_holds(provider_case_id)
        target_hold_name = _purview_hold_display_name(display_name)
        hold = next((h for h in holds if _purview_hold_name_match(h, target_hold_name)), None)
        if not hold:
            _log_release_status("no_hold", {"purview_case_id": provider_case_id})
            return {"status": "no_hold", "results": []}
        hold_id = hold.get("id")
        if not hold_id:
            _log_release_status("no_hold_id", {"purview_case_id": provider_case_id})
            return {"status": "no_hold_id", "results": []}
    except PurviewConfigError as exc:
        _log_release_error("config_error", str(exc))
        raise HTTPException(status_code=503, detail=str(exc))
    except PurviewAPIError as exc:
        status = exc.status_code or 502
        if status < 400 or status >= 600:
            status = 502
        _log_release_error("api_error", str(exc), exc.status_code)
        raise HTTPException(status_code=status, detail=str(exc))

    custodian_query = db.query(models.Custodian).filter(models.Custodian.case_id == case_id)
    if custodian_ids:
        custodian_query = custodian_query.filter(models.Custodian.id.in_(custodian_ids))
    custodians = custodian_query.all()
    if not custodian_ids:
        custodian_ids = [c.id for c in custodians]
    if not custodians:
        _log_release_status("no_custodians", {"purview_case_id": provider_case_id, "purview_hold_id": hold_id})
        return {"status": "no_custodians", "results": []}

    if delete_hold_policy:
        try:
            purview_core.delete_purview_case_legal_hold(provider_case_id, hold_id)
        except PurviewAPIError as exc:
            status = exc.status_code or 502
            if status < 400 or status >= 600:
                status = 502
            _log_release_error("delete_hold_policy", str(exc), exc.status_code)
            raise HTTPException(status_code=status, detail=str(exc))
        results = []
        updated = []
        for cust in custodians:
            email = (getattr(cust, "email", None) or "").strip()
            email_was_held = bool(
                cust.holds_email
                or cust.holds_email_pending
                or cust.holds_email_failed
                or getattr(cust, "holds_email_released", False)
            )
            site_was_held = bool(
                cust.holds_onedrive
                or cust.holds_onedrive_pending
                or cust.holds_onedrive_failed
                or getattr(cust, "holds_onedrive_released", False)
            )
            if "mailbox" in requested_sources:
                cust.holds_email = False
                cust.holds_email_pending = False
                cust.holds_email_failed = False
                if hasattr(cust, "holds_email_released"):
                    cust.holds_email_released = email_was_held
            if "site" in requested_sources:
                cust.holds_onedrive = False
                cust.holds_onedrive_pending = False
                cust.holds_onedrive_failed = False
                if hasattr(cust, "holds_onedrive_released"):
                    cust.holds_onedrive_released = site_was_held
            updated.append(cust)
            results.append({
                "custodian_id": cust.id,
                "email": email or None,
                "status": "hold_deleted",
                "mailbox": "mailbox" in requested_sources,
                "site": "site" in requested_sources,
            })
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        status_counts: dict[str, int] = {}
        for item in results:
            status = (item.get("status") or "").strip().lower()
            if not status:
                continue
            status_counts[status] = status_counts.get(status, 0) + 1
        try:
            case_core.log_event(
                db,
                action="purview_hold_release",
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
                    "release_mode": "delete_policy",
                    "status_counts": status_counts,
                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:4999", exc)
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
        result = {
            "status": "hold_deleted",
            "provider_case_id": provider_case_id,
            "purview_case_id": provider_case_id,
            "hold_id": hold_id,
            "results": results,
            "updated_custodians": updated_payload,
            "status_counts": status_counts,
        }
        try:
            case_core._maybe_create_box_hold_release_ticket(
                db,
                case=case,
                actor=_user,
                request=request,
                source="release_all_holds",
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:5031", exc)
        case_core._schedule_preservation_status_poll(case_id, "purview_hold_release")
        return result

    try:
        user_sources = purview_core.list_purview_hold_user_sources(provider_case_id, hold_id)
    except PurviewAPIError as exc:
        status = exc.status_code or 502
        if status < 400 or status >= 600:
            status = 502
        _log_release_error("list_user_sources", str(exc), exc.status_code)
        raise HTTPException(status_code=status, detail=str(exc))
    user_sources_count = len(user_sources or [])
    user_sources_by_email: dict[str, dict[str, Any]] = {}
    user_sources_by_id: dict[str, Any] = {}
    for source in user_sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        source_id = source_id.strip()
        included = source.get("includedSources")
        user_sources_by_id[source_id.lower()] = included
        for email_key in _extract_email_candidates(source):
            user_sources_by_email.setdefault(email_key, {})[source_id] = included
        email_field = source.get("email")
        if isinstance(email_field, str) and email_field.strip():
            user_sources_by_email.setdefault(email_field.strip().lower(), {})[source_id] = included

    personal_key_to_email: dict[str, str] = {}
    for cust in custodians:
        email_norm = _purview_email_norm(getattr(cust, "email", None))
        personal_key = _onedrive_personal_key(email_norm)
        if personal_key and email_norm:
            personal_key_to_email.setdefault(personal_key, email_norm)

    try:
        site_sources = purview_core.list_purview_hold_site_sources(provider_case_id, hold_id)
    except PurviewAPIError as exc:
        status = exc.status_code or 502
        if status < 400 or status >= 600:
            status = 502
        _log_release_error("list_site_sources", str(exc), exc.status_code)
        raise HTTPException(status_code=status, detail=str(exc))
    site_sources_count = len(site_sources or [])
    site_sources_by_key: dict[str, set[str]] = {}
    site_sources_by_email: dict[str, set[str]] = {}
    for source in site_sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            continue
        site_source_id = source_id.strip()
        site_key = _purview_site_key(source)
        if site_key:
            site_sources_by_key.setdefault(site_key, set()).add(site_source_id)
        site_obj = source.get("site") if isinstance(source, dict) else None
        if isinstance(site_obj, dict):
            web_url = site_obj.get("webUrl")
            if isinstance(web_url, str) and web_url.strip():
                site_sources_by_key.setdefault(_normalize_site_url(web_url), set()).add(site_source_id)
                personal_key = _personal_key_from_url(web_url)
                if personal_key and personal_key in personal_key_to_email:
                    email_norm = personal_key_to_email[personal_key]
                    site_sources_by_email.setdefault(email_norm, set()).add(site_source_id)

    results = []
    updated = []
    # Cache OneDrive site identifiers we learned while applying holds so verification can map
    # siteSources back to custodians without extra API calls.
    site_key_candidates_by_email: dict[str, set[str]] = {}
    deleted_site_source_ids: set[str] = set()

    purview_case_custodian_ids_by_email: dict[str, str] = {}
    if len(custodians) <= 10:
        try:
            pcustodians = purview_core.list_purview_case_custodians(provider_case_id)
            for pc in pcustodians:
                if not isinstance(pc, dict):
                    continue
                pc_id = (pc.get("id") or "").strip()
                pc_email = _purview_email_norm(pc.get("email"))
                if pc_id and pc_email and pc_email not in purview_case_custodian_ids_by_email:
                    purview_case_custodian_ids_by_email[pc_email] = pc_id.strip().lower()
        except PurviewAPIError:
            purview_case_custodian_ids_by_email = {}

    for cust in custodians:
        email = (getattr(cust, "email", None) or "").strip()
        email_norm = _purview_email_norm(email)
        errors = []
        removed_mailbox = False
        removed_site = False
        mailbox_error = False
        site_error = False
        email_was_held = bool(cust.holds_email or cust.holds_email_pending or cust.holds_email_failed)
        site_was_held = bool(cust.holds_onedrive or cust.holds_onedrive_pending or cust.holds_onedrive_failed)
        already_released_email = bool(getattr(cust, "holds_email_released", False))
        already_released_site = bool(getattr(cust, "holds_onedrive_released", False))

        release_mailbox = "mailbox" in requested_sources
        release_site = "site" in requested_sources

        user_source_entries: list[tuple[str, Any]] = []
        if email_norm and (release_mailbox or release_site):
            candidates = [email_norm]
            for candidate in (purview_core.resolve_purview_user_emails(email_norm) or []):
                if isinstance(candidate, str) and candidate.strip():
                    candidates.append(candidate.strip().lower())
            try:
                user_id = purview_core.resolve_purview_user_id(email_norm)
            except PurviewAPIError:
                user_id = None
            if isinstance(user_id, str) and user_id.strip():
                candidates.append(user_id.strip().lower())
            purview_case_custodian_id = purview_case_custodian_ids_by_email.get(email_norm)
            if isinstance(purview_case_custodian_id, str) and purview_case_custodian_id.strip():
                candidates.append(purview_case_custodian_id.strip().lower())
            candidates = list(dict.fromkeys(candidates))
            combined: dict[str, Any] = {}
            for candidate in candidates:
                for source_id, included in (user_sources_by_email.get(candidate) or {}).items():
                    combined.setdefault(source_id, included)
                # Some tenants use non-email IDs for userSources; try direct id match as a last resort.
                if candidate in user_sources_by_id:
                    combined.setdefault(candidate, user_sources_by_id.get(candidate))
            user_source_entries = list(combined.items())

        for user_source_id, included in user_source_entries:
            raw_included = included if isinstance(included, list) else None
            current = _purview_sources_set(raw_included)
            if not raw_included and not current:
                current = {"mailbox"}
            to_remove: set[str] = set()
            if release_mailbox:
                to_remove.add("mailbox")
            if release_site:
                to_remove.add("site")
            affected = current & to_remove
            if not affected:
                continue
            remaining = current - to_remove
            try:
                if remaining:
                    purview_core.update_purview_hold_user_source(
                        provider_case_id,
                        hold_id,
                        user_source_id,
                        included_sources=sorted(remaining),
                    )
                else:
                    deleted = purview_core.delete_purview_hold_user_source(provider_case_id, hold_id, user_source_id)
                    if not deleted:
                        continue
                if "mailbox" in affected:
                    removed_mailbox = True
                if "site" in affected:
                    removed_site = True
            except PurviewAPIError as exc:
                if "mailbox" in affected:
                    mailbox_error = True
                if "site" in affected:
                    site_error = True
                errors.append(str(exc))

        if release_site and email_norm:
            site_source_ids: set[str] = set()
            site_source_ids.update(site_sources_by_email.get(email_norm, set()))
            raw_site = getattr(cust, "onedrive_site_id", None)
            if raw_site:
                site_key = _normalize_site_url(raw_site) if _looks_like_url(raw_site) else str(raw_site).strip().lower()
                site_source_ids.update(site_sources_by_key.get(site_key, set()))
            if not site_source_ids:
                try:
                    resource = purview_core.get_purview_onedrive_site(email_norm)
                except PurviewAPIError:
                    resource = None
                    site_error = True
                for key in _candidate_site_keys(resource):
                    site_source_ids.update(site_sources_by_key.get(key, set()))
            for site_source_id in site_source_ids:
                if site_source_id in deleted_site_source_ids:
                    removed_site = True
                    continue
                try:
                    deleted = purview_core.delete_purview_hold_site_source(provider_case_id, hold_id, site_source_id)
                    if not deleted:
                        continue
                    deleted_site_source_ids.add(site_source_id)
                    removed_site = True
                except PurviewAPIError as exc:
                    site_error = True
                    errors.append(str(exc))

        if release_mailbox:
            if removed_mailbox and not mailbox_error:
                cust.holds_email = False
                cust.holds_email_pending = False
                cust.holds_email_failed = False
            elif email_was_held:
                cust.holds_email = True
                cust.holds_email_pending = False
                cust.holds_email_failed = True
            if hasattr(cust, "holds_email_released"):
                cust.holds_email_released = bool(already_released_email or (removed_mailbox and not mailbox_error))

        if release_site:
            if removed_site and not site_error:
                cust.holds_onedrive = False
                cust.holds_onedrive_pending = False
                cust.holds_onedrive_failed = False
            elif site_was_held:
                cust.holds_onedrive = True
                cust.holds_onedrive_pending = False
                cust.holds_onedrive_failed = True
            if hasattr(cust, "holds_onedrive_released"):
                cust.holds_onedrive_released = bool(already_released_site or (removed_site and not site_error))
        updated.append(cust)

        if errors:
            results.append({
                "custodian_id": cust.id,
                "email": email or None,
                "status": "error",
                "message": "; ".join(errors),
            })
        elif removed_mailbox or removed_site:
            results.append({
                "custodian_id": cust.id,
                "email": email or None,
                "status": "released",
                "mailbox": removed_mailbox,
                "site": removed_site,
            })
        else:
            results.append({
                "custodian_id": cust.id,
                "email": email or None,
                "status": "not_found",
            })

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    status_counts: dict[str, int] = {}
    for item in results:
        status = (item.get("status") or "").strip().lower()
        if not status:
            continue
        status_counts[status] = status_counts.get(status, 0) + 1
    try:
        case_core.log_event(
            db,
            action="purview_hold_release",
            actor_id=getattr(_user, "id", None),
            target_type="case",
            target_id=case.id,
            details={
                "case_id": case.id,
                "case_name": case.name,
                "purview_case_id": provider_case_id,
                "purview_hold_id": hold_id,
                "purview_hold_display_name": hold.get("displayName") if isinstance(hold, dict) else None,
                "custodian_ids": custodian_ids,
                "requested_sources": sorted(requested_sources),
                "release_mode": "delete_policy" if delete_hold_policy else "remove_sources",
                "status_counts": status_counts,
                "results": results,
                "hold_user_sources_count": user_sources_count,
                "hold_site_sources_count": site_sources_count,
            },
            request=request,
        )
    except Exception as exc:
        case_core._debug_suppressed("suppressed exception in cases.py:5310", exc)
    if status_counts.get("error"):
        try:
            case_core.log_event(
                db,
                action="purview_hold_release_failed",
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
                    "release_mode": "delete_policy" if delete_hold_policy else "remove_sources",
                    "status_counts": status_counts,
                },
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:5332", exc)

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
    result = {
        "status": "error" if status_counts.get("error") else ("released" if status_counts.get("released") else "not_found"),
        "provider_case_id": provider_case_id,
        "purview_case_id": provider_case_id,
        "hold_id": hold_id,
        "results": results,
        "updated_custodians": updated_payload,
        "status_counts": status_counts,
        "hold_user_sources_count": user_sources_count,
        "hold_site_sources_count": site_sources_count,
    }
    case_core._schedule_preservation_status_poll(case_id, "purview_hold_release")
    return result

