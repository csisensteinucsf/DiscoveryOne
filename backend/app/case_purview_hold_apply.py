from typing import Optional

from sqlalchemy.orm import Session

from . import models
from . import cases as case_core
from . import case_purview_gateway as purview_core
from .purview import PurviewAPIError
from .case_purview_utils import (
    _candidate_site_keys,
    _looks_like_url,
    _normalize_site_url,
    _onedrive_personal_key,
    _personal_key_from_url,
    _purview_email_norm,
    _purview_site_key,
    _purview_sources_flags,
)


def mark_mailbox_success(cust: models.Custodian) -> None:
    cust.holds_email = True
    cust.holds_email_pending = False
    cust.holds_email_failed = False
    if hasattr(cust, "holds_email_released"):
        cust.holds_email_released = False


def mark_site_success(cust: models.Custodian) -> None:
    cust.holds_onedrive = True
    cust.holds_onedrive_pending = False
    cust.holds_onedrive_failed = False
    if hasattr(cust, "holds_onedrive_released"):
        cust.holds_onedrive_released = False


def mark_mailbox_failed(cust: models.Custodian) -> None:
    cust.holds_email_pending = False
    cust.holds_email_failed = True
    if hasattr(cust, "holds_email_released"):
        cust.holds_email_released = False


def mark_site_failed(cust: models.Custodian) -> None:
    cust.holds_onedrive_pending = False
    cust.holds_onedrive_failed = True
    if hasattr(cust, "holds_onedrive_released"):
        cust.holds_onedrive_released = False


def is_item_not_found(exc: PurviewAPIError) -> bool:
    msg = str(exc or "").lower()
    return exc.status_code == 404 or "item not found" in msg


def is_site_source_retryable(exc: PurviewAPIError) -> bool:
    msg = str(exc or "").lower()
    if exc.status_code not in (400, 404, 405):
        return False
    retry_tokens = (
        "invalid site",
        "invalid sitesource",
        "could not find key property",
        "item not found",
        "specified http method is not allowed",
    )
    return any(token in msg for token in retry_tokens)


def apply_user_source_site_hold(
    email_norm: str,
    email: str,
    existing_flags: dict,
    *,
    requested_sources: set[str],
    purview_case_id: str,
    hold_id: str,
    hold_source_ids: dict[str, str],
    hold_sources_flags: dict[str, dict],
) -> Optional[str]:
    requested_mailbox = "mailbox" in requested_sources
    sources = {"site"}
    if existing_flags.get("mailbox") or requested_mailbox:
        sources.add("mailbox")
    included_sources = list(sources)
    try:
        user_source_id = hold_source_ids.get(email_norm)
        if user_source_id:
            purview_core.update_purview_hold_user_source(
                purview_case_id,
                hold_id,
                user_source_id,
                included_sources=included_sources,
            )
        else:
            created = purview_core.add_purview_hold_user_source(
                purview_case_id,
                hold_id,
                email=email,
                included_sources=included_sources,
            )
            if isinstance(created, dict):
                created_id = created.get("id")
                if isinstance(created_id, str) and created_id.strip():
                    hold_source_ids[email_norm] = created_id.strip()
        existing_flags["site"] = True
        if "mailbox" in sources:
            existing_flags["mailbox"] = True
        hold_sources_flags[email_norm] = existing_flags
        return None
    except PurviewAPIError as exc:
        return str(exc)


def build_hold_source_map(
    *,
    db: Session,
    case_id: int,
    purview_case_id: str,
    hold_id: str,
    updated: list[models.Custodian],
    site_key_candidates_by_email: dict[str, set[str]],
) -> dict[str, dict]:
    source_map: dict[str, dict] = {}
    site_id_to_emails: dict[str, set[str]] = {}
    personal_key_to_email: dict[str, str] = {}
    custodians = updated or []
    if not custodians:
        try:
            custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
        except Exception:
            custodians = []
    for cust in custodians or []:
        email = _purview_email_norm(getattr(cust, "email", None))
        if not email or email in {case_core.NO_EMAIL_PLACEHOLDER, case_core.UNMATCHED_EMAIL_PLACEHOLDER}:
            continue
        personal_key = _onedrive_personal_key(email)
        if personal_key:
            personal_key_to_email.setdefault(personal_key, email)
        keys: set[str] = set()
        raw_site = getattr(cust, "onedrive_site_id", None)
        if raw_site:
            key = _normalize_site_url(raw_site) if _looks_like_url(raw_site) else str(raw_site).strip().lower()
            if key:
                keys.add(key)
        for key in site_key_candidates_by_email.get(email, set()):
            if not key:
                continue
            keys.add(_normalize_site_url(key) if _looks_like_url(key) else str(key).strip().lower())
        for key in keys:
            site_id_to_emails.setdefault(key, set()).add(email)
    user_sources = purview_core.list_purview_hold_user_sources(purview_case_id, hold_id)
    for source in user_sources:
        email = _purview_email_norm(source.get("email"))
        if not email:
            continue
        flags = _purview_sources_flags(source.get("includedSources"))
        entry = source_map.get(email) or {"mailbox": False, "site": False}
        if not source.get("includedSources") or flags.get("mailbox"):
            entry["mailbox"] = True
        if flags.get("site"):
            entry["site"] = True
        source_map[email] = entry
    site_sources = purview_core.list_purview_hold_site_sources(purview_case_id, hold_id)
    for source in site_sources:
        keys: set[str] = set()
        site_id = _purview_site_key(source)
        if site_id:
            keys.add(_normalize_site_url(site_id) if _looks_like_url(site_id) else str(site_id).strip().lower())
        site_obj = source.get("site") if isinstance(source, dict) else None
        if isinstance(site_obj, dict):
            for key in _candidate_site_keys(site_obj):
                if not key:
                    continue
                keys.add(_normalize_site_url(key) if _looks_like_url(key) else str(key).strip().lower())
        for key in list(keys):
            for email in site_id_to_emails.get(key, set()):
                entry = source_map.get(email) or {"mailbox": False, "site": False}
                entry["site"] = True
                source_map[email] = entry
        web_url = None
        if isinstance(site_obj, dict):
            web_url = site_obj.get("webUrl")
        if not web_url and isinstance(source, dict):
            for candidate in ("siteWebUrl", "webUrl", "siteUrl"):
                value = source.get(candidate)
                if isinstance(value, str) and value.strip():
                    web_url = value.strip()
                    break
        if isinstance(web_url, str) and web_url.strip():
            personal_key = _personal_key_from_url(web_url)
            if personal_key and personal_key in personal_key_to_email:
                email = personal_key_to_email[personal_key]
                entry = source_map.get(email) or {"mailbox": False, "site": False}
                entry["site"] = True
                source_map[email] = entry
    return source_map


def should_verify_site(requested_sources: set[str]) -> bool:
    return "site" in requested_sources