from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import HTTPException

from . import models, preservation_provider, schemas, ticket_provider
from .audit import log_event
from .cases import (
    _apply_request_holds,
    _configured_ticket_default_customer_id,
    _normalize_request_ticket_entries,
    _require_employee_id,
    _schedule_preservation_status_poll,
    _sync_legacy_request_tickets,
)
from .notifications import _app_base_url as app_base_url
from .permissions import get_role
from .safe_log import debug_suppressed
from . import case_request_hold_automation as hold_automation
from .case_request_settings import auto_rubrik_restore_for_separated_email_holds

logger = logging.getLogger(__name__)


def now_ts() -> str:
    try:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def payload_dict(record: models.CaseRequest) -> Dict[str, Any]:
    if not record.payload:
        return {}
    try:
        return json.loads(record.payload)
    except Exception:
        return {}

def auto_apply_case_request_holds(
    request_id: int,
    *,
    session_factory,
    auto_hold_threads: dict[int, object],
    auto_hold_lock,
    schedule_hold_status_email,
) -> None:
    """
    Best-effort background worker for requestor auto-approved custodian requests.
    Runs configured preservation and ticket automation without blocking the submitter.
    """
    db = session_factory()
    try:
        record = db.get(models.CaseRequest, int(request_id))
        if not record or record.request_type != "custodian" or not record.case_id:
            return
        payload = payload_dict(record)
        custodian_ids = payload.get("approved_custodian_ids") or payload.get("approved_custodian_id_list") or []
        try:
            custodian_ids = [int(x) for x in (custodian_ids or []) if int(x) > 0]
        except Exception:
            custodian_ids = []
        if not custodian_ids:
            return
        case_for_tickets = db.get(models.Case, int(record.case_id))
        if not case_for_tickets:
            return
        actor = None
        try:
            actor = db.get(models.User, int(getattr(record, "reviewed_by_id", 0) or 0))
        except Exception:
            actor = None
        if not actor or get_role(actor) not in {"analyst", "sys_admin"}:
            actor = hold_automation.pick_auto_approver(db, case_for_tickets)
        if not actor:
            return

        custodians = (
            db.query(models.Custodian)
            .filter(models.Custodian.id.in_(custodian_ids))
            .all()
        )
        if not custodians:
            return

        automation_ready = preservation_provider.preservation_automation_ready()
        preservation_hold_groups: dict[tuple[str, ...], list[int]] = {}
        box_targets: list[models.Custodian] = []
        rubrik_targets: list[models.Custodian] = []
        auto_rubrik_enabled = auto_rubrik_restore_for_separated_email_holds()
        for cust in custodians:
            if hold_automation.has_hold(cust, "holds_box"):
                box_targets.append(cust)
            # Reconstruct the "auto rubrik" intent from persisted fields.
            status = (getattr(cust, "employment_status", None) or "").strip().lower()
            if auto_rubrik_enabled and status in {"separated_90", "separated_365"} and bool(getattr(cust, "holds_email", False)) and bool(getattr(cust, "holds_rubrik_restore_pending", False)):
                rubrik_targets.append(cust)

            sources: list[str] = []
            if hold_automation.has_usable_email(cust):
                if hold_automation.has_hold(cust, "holds_email"):
                    sources.append("mailbox")
                if hold_automation.has_hold(cust, "holds_onedrive"):
                    sources.append("site")
            if sources and getattr(cust, "id", None) is not None:
                key = tuple(src for src in ("mailbox", "site") if src in sources)
                preservation_hold_groups.setdefault(key, []).append(int(cust.id))

        # Configured preservation provider (best-effort): create case and apply grouped holds.
        try:
            if preservation_hold_groups and automation_ready:
                case_id_val = int(record.case_id)
                try:
                    preservation_provider.create_case(case_id=case_id_val, db=db, request=None, user=actor)
                except HTTPException as exc:
                    logger.warning(
                        "auto_case_request_preservation_case_failed ts=%s request_id=%s case=%s error=%s",
                        now_ts(),
                        record.id,
                        case_id_val,
                        getattr(exc, "detail", str(exc)),
                    )
                except Exception as exc:
                    logger.warning(
                        "auto_case_request_preservation_case_failed ts=%s request_id=%s case=%s error=%s",
                        now_ts(),
                        record.id,
                        case_id_val,
                        exc,
                    )
                for sources_key, ids in preservation_hold_groups.items():
                    if not ids:
                        continue
                    try:
                        preservation_provider.apply_holds(
                            case_id=case_id_val,
                            payload=schemas.PreservationHoldRequest(
                                custodian_ids=[int(i) for i in ids],
                                included_sources=list(sources_key),
                            ),
                            db=db,
                            request=None,
                            user=actor,
                        )
                        try:
                            db.commit()
                        except Exception:
                            db.rollback()
                    except Exception as exc:
                        logger.warning(
                            "auto_case_request_preservation_holds_failed ts=%s request_id=%s case=%s sources=%s error=%s",
                            now_ts(),
                            record.id,
                            case_id_val,
                            sources_key,
                            exc,
                        )
                try:
                    _schedule_preservation_status_poll(case_id_val, "auto_case_request", delay_seconds=10)
                except Exception as exc:
                    debug_suppressed("suppressed exception in case_requests.py:354", exc)
        except Exception as exc:
            debug_suppressed("suppressed exception in case_requests.py:356", exc)

        # If provider email preservation is complete, skip redundant restore tickets.
        try:
            if automation_ready:
                rubrik_targets = hold_automation.filter_rubrik_targets_after_preservation(db, rubrik_targets)
        except Exception as exc:
            debug_suppressed("suppressed exception in case_requests.py:362", exc)

        # External tickets (best-effort): mirror approval logic for configured ticket workflows.
        try:
            if rubrik_targets or box_targets:
                if case_for_tickets:
                    entries = getattr(case_for_tickets, "request_ticket_entries", []) or []
                    customer_id_override = None
                    customer_owner = None
                    try:
                        if getattr(case_for_tickets, "analyst_id", None):
                            customer_owner = db.get(models.User, case_for_tickets.analyst_id)
                    except Exception:
                        customer_owner = None
                    customer_owner = customer_owner or actor
                    try:
                        customer_id_override = _require_employee_id(customer_owner)
                    except Exception:
                        customer_id_override = None
                    if not customer_id_override:
                        customer_id_override = _configured_ticket_default_customer_id()

                    case_link = None
                    try:
                        base = app_base_url(None)
                        case_link = f"{base}/cases/{int(case_for_tickets.id)}"
                    except Exception:
                        case_link = None

                    def _create_ticket_group(category: str, custs: list[models.Custodian]) -> None:
                        if not custs:
                            return
                        primary = custs[0]
                        seen = set()
                        bulk: list[dict] = []
                        for c in custs:
                            cid = getattr(c, "id", None)
                            email = (getattr(c, "email", None) or "").strip().lower()
                            key = (cid, email)
                            if key in seen:
                                continue
                            seen.add(key)
                            bulk.append({"id": cid, "name": getattr(c, "name", None), "email": getattr(c, "email", None)})
                        result = ticket_provider.create_ticket(
                            category=category,
                            case_name=getattr(case_for_tickets, "name", None),
                            case_link=case_link,
                            custodian_name=getattr(primary, "name", None),
                            custodian_email=getattr(primary, "email", None),
                            customer_id=customer_id_override,
                        )
                        ticket_number = (result or {}).get("ticket_number") or (result or {}).get("ticket")
                        sys_id = (result or {}).get("sys_id")
                        entries.append({
                            "id": str(uuid.uuid4()),
                            "category": category,
                            "ticket": ticket_number,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "custodian_id": getattr(primary, "id", None),
                            "custodian_name": getattr(primary, "name", None),
                            "custodian_email": getattr(primary, "email", None),
                            "sys_id": sys_id,
                            "bulk_custodians": bulk or None,
                        })
                        try:
                            log_event(
                                db,
                                action="case_request_ticket",
                                actor_id=getattr(actor, "id", None),
                                target_type="case",
                                target_id=getattr(case_for_tickets, "id", None),
                                details={
                                    "case_id": getattr(case_for_tickets, "id", None),
                                    "case_name": getattr(case_for_tickets, "name", None),
                                    "category": category,
                                    "ticket": ticket_number,
                                    "sys_id": sys_id,
                                    "custodian_id": getattr(primary, "id", None),
                                    "custodian_name": getattr(primary, "name", None),
                                    "custodian_email": getattr(primary, "email", None),
                                    "bulk_custodians": bulk or None,
                                    "source": "auto_case_request",
                                    "request_id": record.id,
                                },
                            )
                        except Exception as exc:
                            debug_suppressed("suppressed exception in case_requests.py:452", exc)

                    try:
                        if rubrik_targets:
                            _create_ticket_group("rubrik_restore", rubrik_targets)
                    except Exception as exc:
                        logger.warning("auto_case_request_rubrik_ticket_failed ts=%s request_id=%s error=%s", now_ts(), record.id, exc)
                    try:
                        if box_targets:
                            _create_ticket_group("box_hold", box_targets)
                    except Exception as exc:
                        logger.warning("auto_case_request_box_ticket_failed ts=%s request_id=%s error=%s", now_ts(), record.id, exc)

                    try:
                        normalized_entries = _normalize_request_ticket_entries(entries, case_for_tickets) or []
                        case_for_tickets.request_ticket_entries = normalized_entries
                        _sync_legacy_request_tickets(case_for_tickets, normalized_entries)
                        _apply_request_holds(case_for_tickets, normalized_entries)
                        db.add(case_for_tickets)
                        db.commit()
                    except Exception:
                        try:
                            db.rollback()
                        except Exception as exc:
                            debug_suppressed("suppressed exception in case_requests.py:476", exc)
        except Exception as exc:
            debug_suppressed("suppressed exception in case_requests.py:478", exc)

        # Notify requestor (email) about hold status a few minutes later (best-effort).
        try:
            base_url = None
            try:
                base_url = app_base_url(None)
            except Exception:
                base_url = None
            schedule_hold_status_email(record.id, custodian_ids, base_url=base_url)
        except Exception as exc:
            debug_suppressed("suppressed exception in case_requests.py:489", exc)
    finally:
        try:
            db.close()
        except Exception as exc:
            debug_suppressed("suppressed exception in case_requests.py:494", exc)
        with auto_hold_lock:
            auto_hold_threads.pop(int(request_id), None)

