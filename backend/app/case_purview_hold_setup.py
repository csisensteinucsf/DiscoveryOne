import logging

from fastapi import HTTPException

from . import cases as case_core
from . import case_purview_gateway as purview_core
from .case_purview_utils import (
    _purview_email_norm,
    _purview_hold_display_name,
    _purview_hold_name_match,
    _purview_site_key,
    _purview_sources_flags,
)

logger = logging.getLogger(__name__)


def build_purview_hold_apply_context(*, case, case_id: int, display_name: str) -> dict:
    purview_case = purview_core.find_purview_case_by_display_name(display_name)
    if not purview_case:
        logger.warning(
            "purview_hold_apply_case_missing case_id=%s display_name=%s",
            case_id,
            display_name,
        )
        raise HTTPException(status_code=409, detail="Purview case does not exist yet.")
    purview_case_id = purview_case.get("id")
    if not purview_case_id:
        logger.warning(
            "purview_hold_apply_case_missing_id case_id=%s display_name=%s",
            case_id,
            display_name,
        )
        raise HTTPException(status_code=502, detail="Purview case lookup returned no id.")
    holds = purview_core.list_purview_case_legal_holds(purview_case_id)
    target_hold_name = _purview_hold_display_name(display_name)
    hold = next((h for h in holds if _purview_hold_name_match(h, target_hold_name)), None)
    created_hold = False
    if not hold:
        logger.info(
            "purview_hold_create_request case_id=%s purview_case_id=%s hold_name=%s",
            case.id,
            purview_case_id,
            target_hold_name,
        )
        hold = purview_core.create_purview_case_legal_hold(
            purview_case_id,
            display_name=target_hold_name,
            description=f"DiscoveryOne hold for {display_name}",
        )
        created_hold = True
    hold_id = hold.get("id")
    if not hold_id:
        logger.warning(
            "purview_hold_create_missing_id case_id=%s purview_case_id=%s hold_name=%s",
            case.id,
            purview_case_id,
            target_hold_name,
        )
        raise HTTPException(status_code=502, detail="Purview hold creation returned no id.")
    if hold not in holds:
        holds.append(hold)
    logger.info(
        "purview_hold_ready case_id=%s purview_case_id=%s hold_id=%s hold_name=%s created=%s",
        case.id,
        purview_case_id,
        hold_id,
        target_hold_name,
        created_hold,
    )
    hold_sources_flags: dict[str, dict] = {}
    hold_source_ids: dict[str, str] = {}
    site_ids_in_holds: set[str] = set()
    for item in holds:
        hold_item_id = item.get("id")
        if not hold_item_id:
            continue
        hold_sources = purview_core.list_purview_hold_user_sources(purview_case_id, hold_item_id)
        for source in hold_sources:
            email = _purview_email_norm(source.get("email"))
            if not email:
                continue
            if hold_item_id == hold_id:
                source_id = source.get("id")
                if isinstance(source_id, str) and source_id.strip():
                    hold_source_ids[email] = source_id.strip()
            flags = _purview_sources_flags(source.get("includedSources"))
            agg = hold_sources_flags.get(email) or {"mailbox": False, "site": False}
            if not source.get("includedSources") or flags.get("mailbox"):
                agg["mailbox"] = True
            if flags.get("site"):
                agg["site"] = True
            hold_sources_flags[email] = agg
        site_sources = purview_core.list_purview_hold_site_sources(purview_case_id, hold_item_id)
        for source in site_sources:
            site_id = _purview_site_key(source)
            if not site_id:
                continue
            site_ids_in_holds.add(site_id)
    case_custodians = purview_core.list_purview_case_custodians(purview_case_id)
    case_custodian_by_email: dict[str, dict] = {}
    for item in case_custodians or []:
        if not isinstance(item, dict):
            continue
        key = _purview_email_norm(item.get("email"))
        if key:
            case_custodian_by_email[key] = item
    return {
        "purview_case": purview_case,
        "purview_case_id": purview_case_id,
        "holds": holds,
        "hold": hold,
        "hold_id": hold_id,
        "hold_sources_flags": hold_sources_flags,
        "hold_source_ids": hold_source_ids,
        "site_ids_in_holds": site_ids_in_holds,
        "case_custodians": case_custodians,
        "case_custodian_by_email": case_custodian_by_email,
        "case_emails": set(case_custodian_by_email.keys()),
    }
