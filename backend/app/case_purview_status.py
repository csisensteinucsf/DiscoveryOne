import logging

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from . import cases as case_core
from . import case_purview_gateway as purview_core
from .case_purview_logging import log_purview_failure
from .case_purview_utils import (
    _candidate_site_keys,
    _looks_like_url,
    _normalize_site_url,
    _onedrive_personal_key,
    _personal_key_from_url,
    _purview_email_norm,
    _purview_hold_display_name,
    _purview_hold_name_match,
    _purview_site_key,
    _purview_sources_flags,
)
from .purview import PurviewAPIError, PurviewConfigError

logger = logging.getLogger(__name__)


def get_purview_status_for_case(
    *,
    case_id: int,
    db: Session,
    request: Request | None,
    user: models.User,
) -> dict:
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case_core.ensure_case_visible(case, user, db)
    if not purview_core.purview_enabled():
        return {
            "enabled": False,
            "detail": "Purview integration is not configured.",
            "case_exists": False,
        }
    display_name = (case.name or "").strip()
    if not display_name:
        return {
            "enabled": True,
            "detail": "Case must have a name before creating it in Purview.",
            "case_exists": False,
        }
    try:
        purview_case = purview_core.find_purview_case_by_display_name(display_name)
        if not purview_case:
            return {"enabled": True, "case_exists": False}
        purview_case_id = purview_case.get("id")
        hold = None
        hold_emails: list[str] = []
        hold_sources: list[dict] = []
        updated_payload = []
        if purview_case_id:
            holds = purview_core.list_purview_case_legal_holds(purview_case_id)
            target_hold_name = _purview_hold_display_name(display_name)
            hold = next((h for h in holds if _purview_hold_name_match(h, target_hold_name)), None)
            source_map: dict[str, dict] = {}
            custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
            site_id_to_emails: dict[str, set[str]] = {}
            personal_key_to_email: dict[str, str] = {}
            for cust in custodians:
                email = _purview_email_norm(getattr(cust, "email", None))
                personal_key = _onedrive_personal_key(email)
                if personal_key and email:
                    personal_key_to_email.setdefault(personal_key, email)
                raw_site = getattr(cust, "onedrive_site_id", None)
                if not raw_site:
                    continue
                site_id = _normalize_site_url(raw_site) if _looks_like_url(raw_site) else str(raw_site).strip().lower()
                if site_id and email:
                    site_id_to_emails.setdefault(site_id, set()).add(email)
            site_ids_in_holds: set[str] = set()
            for item in holds:
                hold_id = item.get("id")
                if not hold_id:
                    continue
                sources = purview_core.list_purview_hold_user_sources(purview_case_id, hold_id)
                for source in sources:
                    email = _purview_email_norm(source.get("email"))
                    if not email:
                        continue
                    flags = _purview_sources_flags(source.get("includedSources"))
                    entry = source_map.get(email) or {"email": email, "mailbox": False, "site": False}
                    if not source.get("includedSources") or flags.get("mailbox"):
                        entry["mailbox"] = True
                    if flags.get("site"):
                        entry["site"] = True
                    source_map[email] = entry
                site_sources = purview_core.list_purview_hold_site_sources(purview_case_id, hold_id)
                for source in site_sources:
                    site_id = _purview_site_key(source)
                    if not site_id:
                        continue
                    site_ids_in_holds.add(site_id)
                    site_obj = source.get("site") if isinstance(source, dict) else None
                    if isinstance(site_obj, dict):
                        web_url = site_obj.get("webUrl")
                        if isinstance(web_url, str) and web_url.strip():
                            site_ids_in_holds.add(_normalize_site_url(web_url))
                            personal_key = _personal_key_from_url(web_url)
                            if personal_key and personal_key in personal_key_to_email:
                                email = personal_key_to_email[personal_key]
                                entry = source_map.get(email) or {"email": email, "mailbox": False, "site": False}
                                entry["site"] = True
                                source_map[email] = entry
            if site_ids_in_holds:
                missing = []
                for cust in custodians:
                    email = _purview_email_norm(getattr(cust, "email", None))
                    if not email or email in {case_core.NO_EMAIL_PLACEHOLDER, case_core.UNMATCHED_EMAIL_PLACEHOLDER}:
                        continue
                    raw_site = getattr(cust, "onedrive_site_id", None)
                    if not raw_site:
                        missing.append(cust)
                        continue
                    site_key = _normalize_site_url(raw_site) if _looks_like_url(raw_site) else str(raw_site).strip().lower()
                    if site_key and site_key not in site_ids_in_holds:
                        missing.append(cust)
                if missing:
                    lookup_limit = purview_core.status_onedrive_lookup_limit()
                    if lookup_limit > 0 and len(missing) > lookup_limit:
                        logger.warning(
                            "purview_status_onedrive_resolve_skip case_id=%s count=%s limit=%s",
                            case_id,
                            len(missing),
                            lookup_limit,
                        )
                    else:
                        logger.info(
                            "purview_status_onedrive_resolve_start case_id=%s count=%s",
                            case_id,
                            len(missing),
                        )
                        updated = []
                        resolved = 0
                        for cust in missing:
                            email = _purview_email_norm(getattr(cust, "email", None))
                            if not email or email in {case_core.NO_EMAIL_PLACEHOLDER, case_core.UNMATCHED_EMAIL_PLACEHOLDER}:
                                continue
                            try:
                                resource = purview_core.get_purview_onedrive_site(email)
                            except PurviewAPIError:
                                continue
                            candidate_keys = _candidate_site_keys(resource)
                            if not candidate_keys:
                                continue
                            matched_key = next((key for key in candidate_keys if key in site_ids_in_holds), None)
                            for key in candidate_keys:
                                site_id_to_emails.setdefault(key, set()).add(email)
                            if matched_key and getattr(cust, "onedrive_site_id", None) != matched_key:
                                cust.onedrive_site_id = matched_key
                                updated.append(cust)
                            elif not getattr(cust, "onedrive_site_id", None):
                                cust.onedrive_site_id = candidate_keys[0]
                                updated.append(cust)
                            resolved += 1
                        if updated:
                            try:
                                db.add_all(updated)
                                db.commit()
                            except Exception:
                                db.rollback()
                        logger.info(
                            "purview_status_onedrive_resolve_complete case_id=%s resolved=%s",
                            case_id,
                            resolved,
                        )
                for site_id in site_ids_in_holds:
                    for email in site_id_to_emails.get(site_id, set()):
                        entry = source_map.get(email) or {"email": email, "mailbox": False, "site": False}
                        entry["site"] = True
                        source_map[email] = entry
            if site_ids_in_holds:
                mapped_sites = [
                    email for email, entry in source_map.items()
                    if isinstance(entry, dict) and entry.get("site")
                ]
                if not mapped_sites:
                    logger.warning(
                        "purview_status_site_unmapped case_id=%s hold_id=%s site_sources=%s custodians=%s",
                        case_id,
                        hold.get("id") if hold else None,
                        len(site_ids_in_holds),
                        len(custodians),
                    )
            hold_sources = list(source_map.values())
            hold_emails = sorted(source_map.keys())
            if hold_sources:
                changed = []
                for cust in custodians:
                    email = _purview_email_norm(getattr(cust, "email", None))
                    if not email or email in {case_core.NO_EMAIL_PLACEHOLDER, case_core.UNMATCHED_EMAIL_PLACEHOLDER}:
                        continue
                    flags = source_map.get(email)
                    if not flags:
                        continue
                    updated = False
                    if flags.get("mailbox"):
                        if not cust.holds_email or cust.holds_email_pending or cust.holds_email_failed:
                            cust.holds_email = True
                            cust.holds_email_pending = False
                            cust.holds_email_failed = False
                            if hasattr(cust, "holds_email_released"):
                                cust.holds_email_released = False
                            updated = True
                    if flags.get("site"):
                        if not cust.holds_onedrive or cust.holds_onedrive_pending or cust.holds_onedrive_failed:
                            cust.holds_onedrive = True
                            cust.holds_onedrive_pending = False
                            cust.holds_onedrive_failed = False
                            if hasattr(cust, "holds_onedrive_released"):
                                cust.holds_onedrive_released = False
                            updated = True
                    if updated:
                        changed.append(cust)
                if changed:
                    try:
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
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
                        for c in changed
                    ]
        return {
            "enabled": True,
            "case_exists": True,
            "purview_case_id": purview_case_id,
            "display_name": purview_case.get("displayName") or display_name,
            "hold_id": hold.get("id") if hold else None,
            "hold_display_name": hold.get("displayName") if hold else None,
            "hold_user_emails": hold_emails,
            "hold_user_sources": hold_sources,
            "updated_custodians": updated_payload,
        }
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
