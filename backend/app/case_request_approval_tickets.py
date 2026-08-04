from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session, selectinload

from . import models
from .database import SessionLocal
from . import case_requests as case_request_core
from . import ticket_provider
from . import ticket_workflow_catalog


def _approval_ticket_targets(
    *,
    db: Session,
    provider: str,
    rubrik_targets: list[models.Custodian],
    box_targets: list[models.Custodian],
    ticket_target_debug_rows: list[dict[str, Any]],
) -> tuple[dict[str, list[models.Custodian]], dict[str, dict[str, Any]]]:
    workflows = ticket_workflow_catalog.approval_workflow_lookup(provider=provider)
    if not workflows:
        return {}, {}

    custodians: list[models.Custodian] = []
    seen: set[tuple[str, Any]] = set()

    def _add(custodian: models.Custodian | None) -> None:
        if custodian is None:
            return
        custodian_id = getattr(custodian, "id", None)
        identity = (
            ("id", int(custodian_id))
            if custodian_id is not None
            else ("object", id(custodian))
        )
        if identity in seen:
            return
        seen.add(identity)
        custodians.append(custodian)

    # The legacy lists keep direct callers compatible. Debug rows identify all
    # custodians created by this approval without including pre-existing case members.
    for custodian in list(rubrik_targets or []) + list(box_targets or []):
        _add(custodian)
    for row in ticket_target_debug_rows or []:
        try:
            custodian_id = int(row.get("custodian_id") or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if custodian_id <= 0 or ("id", custodian_id) in seen:
            continue
        try:
            _add(db.get(models.Custodian, custodian_id))
        except Exception as exc:
            case_request_core._debug_suppressed(
                "suppressed exception loading approval ticket custodian",
                exc,
            )

    targets: dict[str, list[models.Custodian]] = {
        category: [] for category in workflows
    }
    for custodian in custodians:
        try:
            categories = ticket_workflow_catalog.approval_categories_for_custodian(
                custodian,
                provider=provider,
                workflows=workflows,
            )
        except Exception as exc:
            case_request_core._debug_suppressed(
                "suppressed exception resolving approval ticket targets",
                exc,
            )
            continue
        for category in categories:
            if category in targets:
                targets[category].append(custodian)

    return {
        category: custodians_for_category
        for category, custodians_for_category in targets.items()
        if custodians_for_category
    }, workflows


def create_approval_tickets(
    *,
    db: Session,
    record: models.CaseRequest,
    actor: models.User,
    request: Optional[Request],
    case_for_tickets: Optional[models.Case],
    case_analyst_user: Optional[models.User],
    rubrik_targets: list[models.Custodian],
    box_targets: list[models.Custodian],
    ticket_target_debug_rows: list[dict[str, Any]],
    ticket_errors: list[str],
    log_progress,
    session_factory=SessionLocal,
) -> None:
    if record.request_type not in {"new_case", "custodian"}:
        return

    provider = str(ticket_provider.current_ticket_provider() or "none").strip().lower()
    target_groups, approval_workflows = _approval_ticket_targets(
        db=db,
        provider=provider,
        rubrik_targets=rubrik_targets,
        box_targets=box_targets,
        ticket_target_debug_rows=ticket_target_debug_rows,
    )
    workflow_counts = {
        category: len(custodians)
        for category, custodians in target_groups.items()
    }

    log_progress("finalizing", "Finalizing approval...")
    log_progress(
        "ticket_targets",
        "Preparing external ticket targets...",
        {
            "ticket_provider": provider,
            "workflow_counts": workflow_counts,
            "workflow_target_ids": {
                category: [
                    int(getattr(custodian, "id", 0) or 0)
                    for custodian in custodians
                    if getattr(custodian, "id", None) is not None
                ]
                for category, custodians in target_groups.items()
            },
            # Preserve legacy diagnostics while consumers migrate to workflow_counts.
            "box_count": len(box_targets or []),
            "rubrik_count": len(rubrik_targets or []),
            "box_target_ids": [
                int(getattr(custodian, "id", 0) or 0)
                for custodian in (box_targets or [])
                if getattr(custodian, "id", None) is not None
            ],
            "rubrik_target_ids": [
                int(getattr(custodian, "id", 0) or 0)
                for custodian in (rubrik_targets or [])
                if getattr(custodian, "id", None) is not None
            ],
            "custodian_debug": ticket_target_debug_rows,
        },
    )

    if not case_for_tickets:
        if target_groups:
            log_progress(
                "ticket_skipped",
                "External ticket auto-create skipped.",
                {"ticket_provider": provider, "case_id": None},
            )
            case_request_core.logger.warning(
                "case_request_ticket_auto_create skipped ticket_provider=%s case=%s",
                provider,
                None,
            )
        return

    if not target_groups:
        case_request_core.logger.info(
            "case_request_ticket_targets_empty ts=%s record=%s case=%s ticket_provider=%s approval_workflows=%s",
            case_request_core._now_ts(),
            record.id,
            getattr(case_for_tickets, "id", None),
            provider,
            sorted(approval_workflows),
        )
        return

    case_request_core.logger.info(
        "case_request_ticket_auto_create ts=%s record=%s case=%s ticket_provider=%s workflow_counts=%s",
        case_request_core._now_ts(),
        record.id,
        getattr(case_for_tickets, "id", None),
        provider,
        workflow_counts,
    )

    entries = list(getattr(case_for_tickets, "request_ticket_entries", []) or [])
    customer_id_override = None
    customer_owner = case_analyst_user or actor
    try:
        customer_id_override = case_request_core._require_employee_id(customer_owner)
    except HTTPException as exc:
        case_request_core.logger.warning(
            "External ticket creation Employee ID lookup failed ts=%s user=%s error=%s",
            case_request_core._now_ts(),
            getattr(customer_owner, "id", None),
            exc.detail,
        )
    except Exception as exc:
        case_request_core.logger.warning(
            "External ticket creation Employee ID lookup unexpected error ts=%s user=%s error=%s",
            case_request_core._now_ts(),
            getattr(customer_owner, "id", None),
            exc,
        )
    if not customer_id_override:
        customer_id_override = case_request_core._configured_ticket_default_customer_id()

    case_link = None
    try:
        base = case_request_core._app_base_url(request)
        case_id = getattr(case_for_tickets, "id", None)
        if case_id:
            case_link = f"{base}/cases/{case_id}"
    except Exception:
        case_link = None

    def _create_ticket_group(
        category: str,
        custodians: list[models.Custodian],
    ) -> None:
        primary = custodians[0]
        seen_custodians: set[tuple[Any, str]] = set()
        bulk: list[dict[str, Any]] = []
        for custodian in custodians:
            custodian_id = getattr(custodian, "id", None)
            email = (getattr(custodian, "email", None) or "").strip().lower()
            identity = (custodian_id, email)
            if identity in seen_custodians:
                continue
            seen_custodians.add(identity)
            bulk.append(
                {
                    "id": custodian_id,
                    "name": getattr(custodian, "name", None),
                    "email": getattr(custodian, "email", None),
                }
            )

        result = ticket_provider.create_ticket(
            category=category,
            case_name=getattr(case_for_tickets, "name", None),
            case_link=case_link,
            custodian_name=getattr(primary, "name", None),
            custodian_email=getattr(primary, "email", None),
            customer_id=customer_id_override,
        )
        ticket_number = (
            (result or {}).get("ticket_number")
            or (result or {}).get("ticket")
            or (result or {}).get("number")
        )
        sys_id = (result or {}).get("sys_id")
        entries.append(
            {
                "id": str(uuid.uuid4()),
                "category": category,
                "ticket": ticket_number,
                "provider_managed": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "custodian_id": getattr(primary, "id", None),
                "custodian_name": getattr(primary, "name", None),
                "custodian_email": getattr(primary, "email", None),
                "sys_id": sys_id,
                "bulk_custodians": bulk or None,
            }
        )
        try:
            case_request_core.log_event(
                db,
                action="case_request_ticket",
                actor_id=actor.id,
                target_type="case",
                target_id=getattr(case_for_tickets, "id", None),
                details={
                    "case_id": getattr(case_for_tickets, "id", None),
                    "case_name": getattr(case_for_tickets, "name", None),
                    "category": category,
                    "ticket_provider": provider,
                    "ticket": ticket_number,
                    "provider_managed": True,
                    "sys_id": sys_id,
                    "custodian_id": getattr(primary, "id", None),
                    "custodian_name": getattr(primary, "name", None),
                    "custodian_email": getattr(primary, "email", None),
                    "bulk_custodians": bulk or None,
                    "source": "auto_case_request",
                },
                request=request,
            )
        except Exception as exc:
            case_request_core._debug_suppressed(
                "suppressed exception logging approval ticket creation",
                exc,
            )

    created_any = False
    for category, custodians in target_groups.items():
        label = ticket_workflow_catalog.category_label(category) or category
        try:
            _create_ticket_group(category, custodians)
            created_any = True
        except ticket_provider.TicketProviderError as exc:
            ticket_errors.append(
                f"{category}:{getattr(custodians[0], 'id', None)}:{exc}"
            )
            log_progress(
                f"ticket_{category}_failed",
                f"{label} ticket creation failed.",
                {"category": category, "ticket_provider": provider, "error": str(exc)},
            )
            case_request_core.logger.exception(
                "Approval ticket creation failed ts=%s category=%s ticket_provider=%s",
                case_request_core._now_ts(),
                category,
                provider,
            )
        except Exception as exc:
            log_progress(
                f"ticket_{category}_failed",
                f"{label} ticket creation failed.",
                {"category": category, "ticket_provider": provider, "error": str(exc)},
            )
            case_request_core.logger.exception(
                "Approval ticket creation failed (unexpected) ts=%s category=%s ticket_provider=%s",
                case_request_core._now_ts(),
                category,
                provider,
            )

    if not created_any:
        return

    try:
        normalized_entries = (
            case_request_core._normalize_request_ticket_entries(
                entries,
                case_for_tickets,
                trusted_provider=True,
            )
            or []
        )
        case_for_tickets.request_ticket_entries = normalized_entries
        case_request_core._sync_legacy_request_tickets(
            case_for_tickets,
            normalized_entries,
        )
        case_request_core._apply_request_holds(
            case_for_tickets,
            normalized_entries,
        )
        db.add(case_for_tickets)
        db.commit()
    except Exception:
        db.rollback()
        try:
            case_id = getattr(case_for_tickets, "id", None)
            if case_id:
                db2 = session_factory()
                try:
                    case2 = (
                        db2.query(models.Case)
                        .options(selectinload(models.Case.custodians))
                        .filter(models.Case.id == int(case_id))
                        .first()
                    )
                    if case2:
                        normalized_entries = (
                            case_request_core._normalize_request_ticket_entries(
                                entries,
                                case2,
                                trusted_provider=True,
                            )
                            or []
                        )
                        case2.request_ticket_entries = normalized_entries
                        case_request_core._sync_legacy_request_tickets(
                            case2,
                            normalized_entries,
                        )
                        case_request_core._apply_request_holds(
                            case2,
                            normalized_entries,
                        )
                        db2.add(case2)
                        db2.commit()
                finally:
                    try:
                        db2.close()
                    except Exception as exc:
                        case_request_core._debug_suppressed(
                            "suppressed exception closing approval ticket fallback session",
                            exc,
                        )
        except Exception as exc:
            case_request_core._debug_suppressed(
                "suppressed exception persisting approval tickets in fallback session",
                exc,
            )
        try:
            case_request_core.log_event(
                db,
                action="case_request_ticket_persist_failed",
                actor_id=actor.id,
                target_type="case",
                target_id=getattr(case_for_tickets, "id", None),
                details={
                    "case_id": getattr(case_for_tickets, "id", None),
                    "case_name": getattr(case_for_tickets, "name", None),
                    "request_id": record.id,
                    "entries_count": len(entries),
                },
                request=request,
            )
        except Exception as exc:
            case_request_core._debug_suppressed(
                "suppressed exception logging approval ticket persistence failure",
                exc,
            )
