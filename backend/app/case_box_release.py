from __future__ import annotations

import logging
from typing import Optional
from uuid import uuid4

from fastapi import Request
from sqlalchemy.orm import Session

from . import models, ticket_provider
from .audit import log_event

logger = logging.getLogger(__name__)


def custodian_needs_box_hold_release(cust: models.Custodian) -> bool:
    try:
        # Only request release when a Box hold is currently in effect (active or pending).
        # Failed/unknown states should be resolved manually before requesting release.
        return bool(getattr(cust, "holds_box", False) or getattr(cust, "holds_box_pending", False))
    except Exception:
        return False


def case_has_box_hold_request(case: models.Case, entries: list[dict]) -> bool:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("category") != "box_hold":
            continue
        ticket = (entry.get("ticket") or "").strip()
        if ticket:
            return True
        # Draft entries still imply a Box hold request exists.
        return True
    legacy = (getattr(case, "box_hold_ticket", None) or "").strip()
    return bool(legacy)


def has_box_hold_release_ticket(entries: list[dict]) -> bool:
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("category") != "box_hold_release":
            continue
        ticket = (entry.get("ticket") or "").strip()
        if ticket:
            return True
    return False


def maybe_create_box_hold_release_ticket(
    db: Session,
    *,
    case: models.Case,
    actor: models.User,
    request: Request | None,
    source: str,
    require_customer_id,
    case_link,
    normalize_request_ticket_entries,
    sync_legacy_request_tickets,
    apply_request_holds,
    debug_suppressed,
) -> Optional[dict]:
    """
    Best-effort: if the case has any Box holds, create an external ticket requesting Box hold release.
    Never raises.
    """
    try:
        case_id = getattr(case, "id", None)
        if not case_id:
            return None

        custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
        existing_entries = getattr(case, "request_ticket_entries", []) or []
        targets = [c for c in custodians if custodian_needs_box_hold_release(c)]
        if not targets and case_has_box_hold_request(case, existing_entries):
            targets = list(custodians or [])
        if not targets:
            return None

        if has_box_hold_release_ticket(existing_entries):
            return {"status": "skipped_existing"}

        primary = targets[0]
        seen = set()
        bulk: list[dict] = []
        for c in targets:
            cid = getattr(c, "id", None)
            email_norm = (getattr(c, "email", None) or "").strip().lower()
            key = (cid, email_norm)
            if key in seen:
                continue
            seen.add(key)
            bulk.append({"id": cid, "name": getattr(c, "name", None), "email": getattr(c, "email", None)})

        customer_id_override = require_customer_id(actor)
        link = case_link(request, int(case_id))
        result = ticket_provider.create_ticket(
            category="box_hold_release",
            case_name=getattr(case, "name", None),
            case_link=link,
            custodian_name=getattr(primary, "name", None),
            custodian_email=getattr(primary, "email", None),
            customer_id=customer_id_override,
        )
        ticket_number = (result.get("ticket_number") or result.get("ticket") or result.get("number") or "").strip()
        sys_id = result.get("sys_id") or None
        if not ticket_number:
            return {"status": "error", "error": "External ticket provider did not return a ticket number."}

        new_entry = {
            "id": str(uuid4()),
            "category": "box_hold_release",
            "ticket": ticket_number,
            "sys_id": sys_id,
            "custodian_id": getattr(primary, "id", None),
            "custodian_name": getattr(primary, "name", None),
            "custodian_email": getattr(primary, "email", None),
            "bulk_custodians": bulk or None,
            "purpose": "release",
            "source": source,
        }
        entries = (existing_entries or []) + [new_entry]
        normalized_entries = normalize_request_ticket_entries(entries, case) or []
        case.request_ticket_entries = normalized_entries
        sync_legacy_request_tickets(case, normalized_entries)
        apply_request_holds(case, normalized_entries)
        db.add(case)
        db.commit()
        db.refresh(case)

        try:
            log_event(
                db,
                action="case_request_ticket",
                actor_id=getattr(actor, "id", None),
                target_type="case",
                target_id=int(case_id),
                details={
                    "case_id": int(case_id),
                    "case_name": getattr(case, "name", None),
                    "category": "box_hold_release",
                    "ticket": ticket_number,
                    "sys_id": sys_id,
                    "custodian_id": getattr(primary, "id", None),
                    "custodian_name": getattr(primary, "name", None),
                    "custodian_email": getattr(primary, "email", None),
                    "bulk_custodians": bulk or None,
                    "source": source,
                },
                request=request,
            )
        except Exception as exc:
            debug_suppressed("suppressed exception in case_box_release.py:147", exc)

        return {"status": "created", "ticket": ticket_number, "sys_id": sys_id}
    except ticket_provider.TicketProviderError as exc:
        logger.warning("External box_hold_release ticket creation failed case=%s error=%s", getattr(case, "id", None), exc)
        return {"status": "error", "error": str(exc)}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unexpected error creating box_hold_release ticket case=%s error=%s", getattr(case, "id", None), exc)
        try:
            db.rollback()
        except Exception as rollback_exc:
            debug_suppressed("suppressed exception in case_box_release.py:157", rollback_exc)
        return {"status": "error", "error": str(exc)}
