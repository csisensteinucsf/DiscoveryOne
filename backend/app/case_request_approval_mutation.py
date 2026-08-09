from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from . import case_requests as case_request_core
from . import models
from . import ticket_workflow_catalog


@dataclass
class ApprovalMutationResult:
    rubrik_targets: list[models.Custodian] = field(default_factory=list)
    box_targets: list[models.Custodian] = field(default_factory=list)
    case_for_tickets: Optional[models.Case] = None
    case_analyst_user: Optional[models.User] = None
    preservation_hold_groups: dict[tuple[str, ...], list[int]] = field(default_factory=dict)
    hold_notification_ids: list[int] = field(default_factory=list)
    hold_notification_should_send: bool = False
    custodian_create_audit_payloads: list[dict[str, Any]] = field(default_factory=list)
    ticket_target_debug_rows: list[dict[str, Any]] = field(default_factory=list)


def _debug_log_custodian_holds(context: str, items: list[models.Custodian]) -> None:
    try:
        for cust in items:
            case_request_core.logger.info(
                "case_request_hold_debug ts=%s %s cust_id=%s email=%s box=%s box_pending=%s rubrik=%s rubrik_pending=%s email=%s email_pending=%s auto_rubrik=%s",
                case_request_core._now_ts(), context,
                getattr(cust, "id", None),
                getattr(cust, "email", None),
                getattr(cust, "holds_box", None),
                getattr(cust, "holds_box_pending", None),
                getattr(cust, "holds_rubrik_restore", None),
                getattr(cust, "holds_rubrik_restore_pending", None),
                getattr(cust, "holds_email", None),
                getattr(cust, "holds_email_pending", None),
                getattr(cust, "_auto_rubrik_flag", None),
            )
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:2955", exc)


def _has_hold(model: models.Custodian, attr: str) -> bool:
    return bool(getattr(model, attr, False) or getattr(model, f"{attr}_pending", False))


def _ticket_target_debug_row(
    model: models.Custodian,
    workflows: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    try:
        workflow_targets = ticket_workflow_catalog.approval_categories_for_custodian(
            model,
            workflows=workflows,
        )
    except Exception as exc:
        case_request_core._debug_suppressed(
            "suppressed exception resolving approval ticket workflows",
            exc,
        )
        workflow_targets = []

    return {
        "custodian_id": int(getattr(model, "id", 0) or 0),
        "email": getattr(model, "email", None),
        "person_lookup_overridden": bool(getattr(model, "person_lookup_overridden", False)),
        "employment_status": getattr(model, "employment_status", None),
        "employment_end_date": (
            str(getattr(model, "employment_end_date", None))
            if getattr(model, "employment_end_date", None) is not None
            else None
        ),
        "email_hold_requested": _has_hold(model, "holds_email"),
        "box_hold_requested": _has_hold(model, "holds_box"),
        "rubrik_hold_pending": bool(getattr(model, "holds_rubrik_restore_pending", False)),
        "rubrik_auto_targeted": bool(getattr(model, "_auto_rubrik_flag", False)),
        "ticket_workflow_targets": workflow_targets,
    }


def _has_usable_email(model: models.Custodian) -> bool:
    email = (getattr(model, "email", None) or "").strip()
    if not email:
        return False
    norm = email.lower()
    if norm in {case_request_core.NO_EMAIL_PLACEHOLDER.lower(), case_request_core.UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        return False
    return "@" in norm


def _any_requested_holds(models_list: list[models.Custodian]) -> bool:
    for item in models_list or []:
        if (
            _has_hold(item, "holds_email")
            or _has_hold(item, "holds_onedrive")
            or _has_hold(item, "holds_box")
            or _has_hold(item, "holds_rubrik_restore")
        ):
            return True
    return False


def apply_approval_request_mutation(
    *,
    db: Session,
    record: models.CaseRequest,
    payload: dict[str, Any],
    analyst_id: Optional[int],
    actor: models.User,
    request: Optional[Request],
) -> ApprovalMutationResult:
    rubrik_targets: list[models.Custodian] = []
    box_targets: list[models.Custodian] = []
    case_for_tickets: Optional[models.Case] = None
    case_analyst_user: Optional[models.User] = None
    preservation_hold_groups: dict[tuple[str, ...], list[int]] = {}
    hold_notification_ids: list[int] = []
    hold_notification_should_send = False
    custodian_create_audit_payloads: list[dict[str, Any]] = []
    ticket_target_debug_rows: list[dict[str, Any]] = []
    approval_workflows = ticket_workflow_catalog.approval_workflow_lookup()
    if record.request_type == "new_case":
        naming_mode = case_request_core._case_naming_mode()
        case_name = record.case_name
        case_color = record.color
        if naming_mode == "legal_case_name":
            legal_name = str(payload.get("legal_case_name") or record.case_name or "").strip()
            if not legal_name:
                raise HTTPException(status_code=422, detail="Legal case name is required when eDiscovery case naming uses Legal Case Name")
            case_name = case_request_core._unique_case_name(db, legal_name)
            case_color = None
        elif naming_mode == "created_date":
            case_name = case_request_core._next_created_date_case_name(db)
            case_color = None
        else:
            case_request_core._ensure_case_name_available(db, record.case_name, exclude_request_id=record.id)
        if analyst_id is None:
            raise HTTPException(status_code=400, detail="Analyst is required when approving a new case request")
        analyst = db.get(models.User, analyst_id)
        if not analyst:
            raise HTTPException(status_code=404, detail="Selected analyst not found")
        if case_request_core.get_role(analyst) not in {"analyst", "sys_admin"}:
            raise HTTPException(status_code=400, detail="Selected user is not an analyst")
        case = models.Case(
            name=case_name,
            legal_case_name=payload.get("legal_case_name"),
            claimant=payload.get("claimant"),
            internal_counsel=payload.get("internal_counsel"),
            outside_counsel=payload.get("outside_counsel"),
            matter_number=payload.get("matter_number"),
            description=payload.get("description"),
            requestor=record.requestor_email,
            is_private=bool(payload.get("is_private")),
            is_test_case=bool(payload.get("is_test_case")),
            color=case_color,
            analyst_id=analyst.id,
        )
        db.add(case)
        db.flush()
        trusted_email_intake = (
            db.query(models.EmailIntakeMessage.id)
            .filter(models.EmailIntakeMessage.case_request_id == record.id)
            .first()
            is not None
        )
        requestor_entries = case_request_core._normalize_requestor_entries(
            db,
            payload.get("requestors"),
            record.requestor_email,
            allow_external=trusted_email_intake,
        )
        if requestor_entries:
            case_request_core._apply_case_requestors(case, requestor_entries)
        else:
            try:
                case.requestors.append(
                    models.CaseRequestor(
                        email=record.requestor_email,
                        user_id=getattr(record, "requestor_id", None),
                        requestor_group=getattr(getattr(record, "requestor", None), "requestor_group", None),
                        is_primary=True,
                    )
                )
            except Exception as exc:
                case_request_core._debug_suppressed("suppressed exception in case_requests.py:3053", exc)
        record.case_id = case.id
        custodians = case_request_core._collect_custodians(record)
        case_request_core._ensure_unique_custodian_emails(custodians)
        claimant_value = payload.get("claimant")
        rubrik_targets: list[models.Custodian] = []
        built_custodians: list[models.Custodian] = []
        for cust in custodians:
            model = case_request_core._custodian_model(case.id, cust, record.ntp_all_sent)
            if case_request_core._custodian_matches_claimant(
                claimant=claimant_value,
                name=getattr(model, "name", None),
                email=getattr(model, "email", None),
            ):
                model.ntp_status = "silent"
                model.consent_status = "implied"
            case_request_core._apply_consent_not_required_defaults(case, model)
            db.add(model)
            db.flush()
            case_request_core._sync_custom_preservation(db, model, getattr(model, "_custom_preservation_payload", []) or [])
            if bool(getattr(model, "holds_slack", False)):
                case_request_core._sync_slack_hold_for_custodian_or_raise(
                    case,
                    model,
                    enable=True,
                    db=db,
                    actor_id=getattr(actor, "id", None),
                    request=request,
                    source="case_request_new_case",
                    continue_on_user_not_found=True,
                )
            built_custodians.append(model)
            box_requested = _has_hold(model, "holds_box")
            rubrik_auto = bool(getattr(model, "_auto_rubrik_flag", False))
            if rubrik_auto:
                rubrik_targets.append(model)
            if box_requested:
                box_targets.append(model)
            ticket_target_debug_rows.append(_ticket_target_debug_row(model, approval_workflows))
            sources: list[str] = []
            if _has_usable_email(model):
                if _has_hold(model, "holds_email"):
                    sources.append("mailbox")
                if _has_hold(model, "holds_onedrive"):
                    sources.append("site")
            if sources:
                key = tuple(src for src in ("mailbox", "site") if src in sources)
                if getattr(model, "id", None) is not None:
                    preservation_hold_groups.setdefault(key, []).append(int(model.id))
                else:
                    case_request_core.logger.warning(
                        "case_request_purview_hold_skip_missing_id ts=%s record=%s case=%s custodian_email=%s",
                        case_request_core._now_ts(),
                        record.id,
                        case.id,
                        getattr(model, "email", None),
                    )
        _debug_log_custodian_holds("new_case", built_custodians)
        hold_notification_ids = [int(c.id) for c in built_custodians if getattr(c, "id", None) is not None]
        hold_notification_should_send = _any_requested_holds(built_custodians)
        for c in built_custodians:
            cid = int(getattr(c, "id", 0) or 0)
            if cid <= 0:
                continue
            custodian_create_audit_payloads.append({
                "custodian_id": cid,
                "custodian_name": getattr(c, "name", None),
                "custodian_email": getattr(c, "email", None),
                "case_id": case.id,
                "case_name": getattr(case, "name", None),
            })
        for idx, search_payload in enumerate(case_request_core._extract_search_payloads(payload), start=1):
            data = dict(search_payload)
            data.setdefault("name", f"{case.name}-Search {idx}")
            db.add(case_request_core._search_model(case.id, data))

        requested_hold_name = str(payload.get("hold_name") or "").strip()
        if requested_hold_name:
            default_hold = (
                db.query(models.CaseHold)
                .filter(models.CaseHold.case_id == case.id, models.CaseHold.name.ilike(requested_hold_name))
                .first()
            )
            if default_hold is None:
                default_hold = models.CaseHold(
                    case_id=case.id,
                    name=requested_hold_name[:255],
                    status="active",
                    sort_order=0,
                )
                db.add(default_hold)
                db.flush()
            from .case_holds import assign_custodians_to_hold
            from .hold_workflows import set_search_holds

            built_ids = [int(item.id) for item in built_custodians if getattr(item, "id", None)]
            if built_ids:
                assign_custodians_to_hold(
                    db,
                    case_id=int(case.id),
                    hold_id=int(default_hold.id),
                    custodian_ids=built_ids,
                )
            for search in db.query(models.Search).filter(models.Search.case_id == case.id).all():
                set_search_holds(db, search=search, hold_ids=[int(default_hold.id)])
        db.flush()
        case_for_tickets = case
        case_analyst_user = analyst
    elif record.request_type == "custodian":
        if not record.case_id:
            raise HTTPException(status_code=400, detail="Request missing case reference")
        case_for_tickets = db.get(models.Case, record.case_id)
        custodians = case_request_core._collect_custodians(record)
        if not custodians:
            raise HTTPException(status_code=400, detail="No custodians provided")
        case_request_core._ensure_unique_custodian_emails(
            custodians,
            existing_lookup=case_request_core._custodian_lookup_for_case(db, int(record.case_id)),
        )
        claimant_value = getattr(case_for_tickets, "claimant", None) if case_for_tickets else None
        rubrik_targets: list[models.Custodian] = []
        built_custodians: list[models.Custodian] = []
        case_analyst_user = None
        for cust in custodians:
            model = case_request_core._custodian_model(record.case_id, cust, record.ntp_all_sent)
            if case_request_core._custodian_matches_claimant(
                claimant=claimant_value,
                name=getattr(model, "name", None),
                email=getattr(model, "email", None),
            ):
                model.ntp_status = "silent"
                model.consent_status = "implied"
            if case_for_tickets:
                case_request_core._apply_consent_not_required_defaults(case_for_tickets, model)
            db.add(model)
            db.flush()
            case_request_core._sync_custom_preservation(db, model, getattr(model, "_custom_preservation_payload", []) or [])
            if bool(getattr(model, "holds_slack", False)):
                case_request_core._sync_slack_hold_for_custodian_or_raise(
                    case_for_tickets,
                    model,
                    enable=True,
                    db=db,
                    actor_id=getattr(actor, "id", None),
                    request=request,
                    source="case_request_custodian",
                    continue_on_user_not_found=True,
                )
            built_custodians.append(model)
            box_requested = _has_hold(model, "holds_box")
            rubrik_auto = bool(getattr(model, "_auto_rubrik_flag", False))
            if rubrik_auto:
                rubrik_targets.append(model)
            if box_requested:
                box_targets.append(model)
            ticket_target_debug_rows.append(_ticket_target_debug_row(model, approval_workflows))
            sources: list[str] = []
            if _has_usable_email(model):
                if _has_hold(model, "holds_email"):
                    sources.append("mailbox")
                if _has_hold(model, "holds_onedrive"):
                    sources.append("site")
            if sources:
                key = tuple(src for src in ("mailbox", "site") if src in sources)
                if getattr(model, "id", None) is not None:
                    preservation_hold_groups.setdefault(key, []).append(int(model.id))
                else:
                    case_request_core.logger.warning(
                        "case_request_purview_hold_skip_missing_id ts=%s record=%s case=%s custodian_email=%s",
                        case_request_core._now_ts(),
                        record.id,
                        record.case_id,
                        getattr(model, "email", None),
                    )
        _debug_log_custodian_holds("custodian_update", built_custodians)
        hold_notification_ids = [int(c.id) for c in built_custodians if getattr(c, "id", None) is not None]
        hold_notification_should_send = _any_requested_holds(built_custodians)
        for c in built_custodians:
            cid = int(getattr(c, "id", 0) or 0)
            if cid <= 0:
                continue
            custodian_create_audit_payloads.append({
                "custodian_id": cid,
                "custodian_name": getattr(c, "name", None),
                "custodian_email": getattr(c, "email", None),
                "case_id": record.case_id,
                "case_name": getattr(case_for_tickets, "name", None) if case_for_tickets else None,
            })
        try:
            if case_for_tickets and getattr(case_for_tickets, "analyst_id", None):
                case_analyst_user = db.get(models.User, case_for_tickets.analyst_id)
        except Exception:
            case_analyst_user = None
    elif record.request_type == "search":
        if not record.case_id:
            raise HTTPException(status_code=400, detail="Request missing case reference")
        search_payloads = payload.get("searches")
        if isinstance(search_payloads, list):
            for item in search_payloads:
                if isinstance(item, dict) and case_request_core._search_has_details(item):
                    db.add(case_request_core._search_model(record.case_id, item))
        else:
            search_payload = payload.get("search") or payload
            if isinstance(search_payload, dict) and case_request_core._search_has_details(search_payload):
                db.add(case_request_core._search_model(record.case_id, search_payload))
    elif record.request_type == "close_case":
        if not record.case_id:
            raise HTTPException(status_code=400, detail="Request missing case reference")
        case = db.get(models.Case, record.case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Case not found")
        from .case_closure_readiness import case_closure_readiness

        readiness = case_closure_readiness(db, int(case.id))
        if not readiness["ready"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "case_closure_blocked",
                    "message": "This closure request cannot be approved until every active Hold is closed and every preservation item is released.",
                    **readiness,
                },
            )
        case.closed = True
        case.closed_at = datetime.now(timezone.utc)
    else:
        raise HTTPException(status_code=400, detail="Unsupported request type")

    explicit_hold = (
        case_request_core._explicit_request_hold(db, int(record.case_id), payload)
        if record.case_id
        else None
    )
    case_request_core._apply_consents(
        db,
        record.case_id,
        payload.get("consents"),
        case_hold_id=int(explicit_hold.id) if explicit_hold is not None else None,
    )
    case_request_core._assign_request_proofs_to_default_hold(db, record)


    record.status = "approved"
    record.reviewed_at = datetime.now(timezone.utc)
    record.reviewed_by_id = actor.id
    case_request_core._remove_attachment(record, remove_consent_proofs=False)
    db.commit()
    if record.case_id:
        case_request_core._sync_case_documentation_counters(db, int(record.case_id))

    return ApprovalMutationResult(
        rubrik_targets=rubrik_targets,
        box_targets=box_targets,
        case_for_tickets=case_for_tickets,
        case_analyst_user=case_analyst_user,
        preservation_hold_groups=preservation_hold_groups,
        hold_notification_ids=hold_notification_ids,
        hold_notification_should_send=hold_notification_should_send,
        custodian_create_audit_payloads=custodian_create_audit_payloads,
        ticket_target_debug_rows=ticket_target_debug_rows,
    )
