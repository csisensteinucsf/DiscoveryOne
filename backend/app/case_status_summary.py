from collections import Counter
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case as sql_case, func, literal, or_, text
from sqlalchemy.orm import Session

from .app_branding import branded_subject
from . import models, schemas
from .audit import log_event
from .auth import current_user as get_current_user
from .database import get_db
from .emailer import send_email
from .permissions import ensure_case_visible
from .case_holds_detail import build_case_holds_detail
from .preservation_catalog import configured_builtin_hold_fields
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])


def _bounded_int(value: Any, default: int, *, minimum: int = 1, maximum: int = 3650) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _case_status_settings() -> dict:
    try:
        settings = load_system_settings().get("case_status") or {}
    except Exception:
        settings = {}
    return settings if isinstance(settings, dict) else {}


def sla_ntp_ack_days() -> int:
    return _bounded_int(_case_status_settings().get("ntp_ack_days"), 7)


def sla_consent_received_days() -> int:
    return _bounded_int(_case_status_settings().get("consent_received_days"), 7)


def _compute_case_status_map(db: Session, case_ids: list[int]) -> dict[int, schemas.CaseStatus]:
    normalized_ids: list[int] = []
    for raw in case_ids or []:
        try:
            value = int(raw)
        except Exception:
            continue
        if value > 0:
            normalized_ids.append(value)
    if not normalized_ids:
        return {}
    unique_ids = sorted(set(normalized_ids))

    hold_terms = [
        getattr(models.Custodian, field).is_(True)
        for _key, field, _label in configured_builtin_hold_fields(enabled_only=True)
        if hasattr(models.Custodian, field)
    ]
    hold_expr = or_(*hold_terms) if hold_terms else literal(False)

    rows = (
        db.query(
            models.Custodian.case_id,
            func.max(sql_case((hold_expr, 1), else_=0)).label("hold"),
            func.max(sql_case((func.lower(func.coalesce(models.Custodian.ntp_status, "")) == "sent", 1), else_=0)).label("ntp_partial"),
            func.max(sql_case((func.lower(func.coalesce(models.Custodian.ntp_status, "")) == "acknowledged", 1), else_=0)).label("ntp_full"),
            func.max(sql_case((func.lower(func.coalesce(models.Custodian.consent_status, "")) == "sent", 1), else_=0)).label("consent_partial"),
            func.max(sql_case((func.lower(func.coalesce(models.Custodian.consent_status, "")).in_(("received", "implied", "awoc")), 1), else_=0)).label("consent_full"),
            func.max(sql_case((models.Custodian.search_done.is_(True), 1), else_=0)).label("search"),
            func.max(sql_case((models.Custodian.export_done.is_(True), 1), else_=0)).label("export"),
            func.max(sql_case((models.Custodian.delivered_done.is_(True), 1), else_=0)).label("delivered"),
        )
        .filter(models.Custodian.case_id.in_(unique_ids))
        .group_by(models.Custodian.case_id)
        .all()
    )

    status_map: dict[int, schemas.CaseStatus] = {}
    for row in rows:
        try:
            cid = int(getattr(row, "case_id", row[0]))
        except Exception:
            continue
        ntp_full = int(getattr(row, "ntp_full", 0) or 0) > 0
        ntp_partial = int(getattr(row, "ntp_partial", 0) or 0) > 0
        consent_full = int(getattr(row, "consent_full", 0) or 0) > 0
        consent_partial = int(getattr(row, "consent_partial", 0) or 0) > 0
        status_map[cid] = schemas.CaseStatus(
            hold=int(getattr(row, "hold", 0) or 0) > 0,
            ntp=("full" if ntp_full else ("partial" if ntp_partial else "none")),
            consent=("full" if consent_full else ("partial" if consent_partial else "none")),
            search=int(getattr(row, "search", 0) or 0) > 0,
            export=int(getattr(row, "export", 0) or 0) > 0,
            delivered=int(getattr(row, "delivered", 0) or 0) > 0,
        )

    for cid in unique_ids:
        status_map.setdefault(cid, schemas.CaseStatus())
    return status_map


def _compute_case_status(db: Session, case_id: int) -> schemas.CaseStatus:
    try:
        cid = int(case_id)
    except Exception:
        return schemas.CaseStatus()
    if cid <= 0:
        return schemas.CaseStatus()
    return _compute_case_status_map(db, [cid]).get(cid, schemas.CaseStatus())


def _sla_overview(db: Session, case_id: int) -> dict:
    now = datetime.now(timezone.utc)
    ntp_ack_days = sla_ntp_ack_days()
    consent_received_days = sla_consent_received_days()
    ntp_overdue = []
    consent_overdue = []

    custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
    for cust in custodians:
        sent_at = getattr(cust, "ntp_sent_at", None)
        status = (getattr(cust, "ntp_status", "") or "").lower()
        if sent_at and status not in {"acknowledged", "silent", "na", "n/a", "not applicable", "not required"}:
            due_at = sent_at + timedelta(days=ntp_ack_days)
            if due_at < now:
                ntp_overdue.append({
                    "custodian_id": cust.id,
                    "custodian_name": cust.name,
                    "custodian_email": cust.email,
                    "sent_at": sent_at,
                    "due_at": due_at,
                    "days_overdue": max(0, (now - due_at).days),
                })

    consents = (
        db.query(models.CaseConsent)
        .filter(models.CaseConsent.case_id == case_id)
        .filter(models.CaseConsent.status.isnot(None))
        .all()
    )
    for consent in consents:
        status = (consent.status or "").lower()
        if status in {"completed", "received"}:
            continue
        if not consent.sent_at:
            continue
        due_at = consent.sent_at + timedelta(days=consent_received_days)
        if due_at < now:
            consent_overdue.append({
                "consent_id": consent.id,
                "custodian_id": consent.custodian_id,
                "custodian_name": consent.custodian_name,
                "custodian_email": consent.custodian_email,
                "sent_at": consent.sent_at,
                "due_at": due_at,
                "days_overdue": max(0, (now - due_at).days),
                "status": consent.status,
            })

    return {
        "config": {
            "ntp_ack_days": ntp_ack_days,
            "consent_received_days": consent_received_days,
        },
        "ntp_overdue": sorted(ntp_overdue, key=lambda i: i["due_at"]),
        "consent_overdue": sorted(consent_overdue, key=lambda i: i["due_at"]),
    }


@router.get("/{case_id}/sla_status")
def get_case_sla_status(
    case_id: int,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    return _sla_overview(db, case_id)



def _safe_parse_custodian_ids(raw: Any) -> list[int]:
    if isinstance(raw, list):
        vals = raw
    elif isinstance(raw, (str, bytes)):
        try:
            vals = json.loads(raw or "[]")
        except Exception:
            vals = []
    else:
        vals = []
    out: list[int] = []
    for value in vals:
        try:
            out.append(int(value))
        except Exception:
            continue
    return out


def _counter_for_status(values: list[str], *, expected: list[str]) -> dict[str, int]:
    counter = Counter((str(v or "").strip().lower() or "unknown") for v in values)
    out: dict[str, int] = {key: int(counter.get(key, 0)) for key in expected}
    for key, value in counter.items():
        if key not in out:
            out[key] = int(value)
    return out


def _format_dt(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        try:
            return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _resolve_actor_email(actor: models.User) -> str | None:
    direct = (getattr(actor, "email", None) or "").strip()
    if direct:
        return direct
    username = (getattr(actor, "username", None) or "").strip()
    if username and "@" in username:
        return username
    return None



def _env_flag(*args, **kwargs):
    from .case_summary_ai import _env_flag as impl
    return impl(*args, **kwargs)


def _is_case_summary_ai_configured(*args, **kwargs):
    from .case_summary_ai import _is_case_summary_ai_configured as impl
    return impl(*args, **kwargs)


def _extract_json_obj(*args, **kwargs):
    from .case_summary_ai import _extract_json_obj as impl
    return impl(*args, **kwargs)


def _as_str_list(*args, **kwargs):
    from .case_summary_ai import _as_str_list as impl
    return impl(*args, **kwargs)


def _parse_case_summary_ai(*args, **kwargs):
    from .case_summary_ai import _parse_case_summary_ai as impl
    return impl(*args, **kwargs)


def _compose_case_summary_ai_report_text(*args, **kwargs):
    from .case_summary_ai import _compose_case_summary_ai_report_text as impl
    return impl(*args, **kwargs)


def _build_case_summary_ai(*args, **kwargs):
    from .case_summary_ai import _build_case_summary_ai as impl
    return impl(*args, **kwargs)


def _build_case_summary_payload(db: Session, case: models.Case) -> dict[str, Any]:
    case_id = int(case.id)
    custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).all()
    searches = db.query(models.Search).filter(models.Search.case_id == case_id).all()
    consents = db.query(models.CaseConsent).filter(models.CaseConsent.case_id == case_id).all()
    tickets = [e for e in (getattr(case, "request_ticket_entries", []) or []) if isinstance(e, dict)]
    sla = _sla_overview(db, case_id)

    hold_fields = [
        (key, field)
        for key, field, _label in configured_builtin_hold_fields(enabled_only=True)
        if hasattr(models.Custodian, field)
    ]

    holds_summary: dict[str, dict[str, int]] = {}
    for label, field in hold_fields:
        pending_field = f"{field}_pending"
        failed_field = f"{field}_failed"
        released_field = f"{field}_released"
        active = sum(1 for c in custodians if bool(getattr(c, field, False)))
        pending = sum(1 for c in custodians if bool(getattr(c, pending_field, False)))
        failed = sum(1 for c in custodians if bool(getattr(c, failed_field, False)))
        released = sum(1 for c in custodians if bool(getattr(c, released_field, False)))
        requested = sum(
            1
            for c in custodians
            if any(
                bool(getattr(c, f, False))
                for f in (field, pending_field, failed_field, released_field)
            )
        )
        holds_summary[label] = {
            "requested": requested,
            "active": active,
            "pending": pending,
            "failed": failed,
            "released": released,
        }

    ntp_statuses = [(getattr(c, "ntp_status", None) or "not sent") for c in custodians]
    ntp_counts = _counter_for_status(
        ntp_statuses,
        expected=["not sent", "sent", "acknowledged", "silent"],
    )

    consent_statuses = [(getattr(c, "consent_status", None) or "not sent") for c in custodians]
    consent_counts = _counter_for_status(
        consent_statuses,
        expected=["not sent", "sent", "received", "implied", "awoc"],
    )

    search_counts = _counter_for_status(
        [getattr(s, "status_search", None) or "not performed" for s in searches],
        expected=["not performed", "performed"],
    )
    export_counts = _counter_for_status(
        [getattr(s, "status_export", None) or "not performed" for s in searches],
        expected=["not performed", "performed"],
    )
    delivery_counts = _counter_for_status(
        [getattr(s, "status_delivery", None) or "not performed" for s in searches],
        expected=["not performed", "performed", "not required"],
    )

    searches_needing_export = sum(
        1
        for s in searches
        if str(getattr(s, "status_search", "") or "").strip().lower() == "performed"
        and str(getattr(s, "status_export", "") or "").strip().lower() != "performed"
    )
    searches_needing_delivery = sum(
        1
        for s in searches
        if str(getattr(s, "status_export", "") or "").strip().lower() == "performed"
        and str(getattr(s, "status_delivery", "") or "").strip().lower() not in {"performed", "not required"}
    )
    exported_without_consent = sum(1 for s in searches if bool(getattr(s, "export_without_consent", False)))
    searches_without_custodians = sum(1 for s in searches if len(_safe_parse_custodian_ids(getattr(s, "custodian_ids", []))) == 0)

    envelope_status_counts = _counter_for_status(
        [getattr(c, "status", None) or "unknown" for c in consents],
        expected=["sent", "delivered", "completed", "voided", "declined", "received"],
    )

    ticket_closed_states = {"closed", "complete", "completed", "resolved", "done"}
    open_tickets = 0
    for t in tickets:
        status = str(t.get("status") or t.get("ticket_status") or "").strip().lower()
        if status and status in ticket_closed_states:
            continue
        open_tickets += 1

    missing_email = sum(1 for c in custodians if not (getattr(c, "email", None) or "").strip())
    ntp_needing_action = sum(
        1
        for c in custodians
        if str(getattr(c, "ntp_status", "") or "not sent").strip().lower() not in {"acknowledged", "silent", "na", "n/a", "not applicable", "not required"}
    )
    consent_needing_action = sum(
        1
        for c in custodians
        if str(getattr(c, "consent_status", "") or "not sent").strip().lower() not in {"received", "implied", "awoc", "na", "n/a", "not applicable", "not required"}
    )
    total_hold_failed = sum(int(v.get("failed", 0)) for v in holds_summary.values())
    total_hold_pending = sum(int(v.get("pending", 0)) for v in holds_summary.values())
    ntp_overdue_count = len(sla.get("ntp_overdue") or [])
    consent_overdue_count = len(sla.get("consent_overdue") or [])

    needs_attention: list[dict[str, Any]] = []
    if missing_email > 0:
        needs_attention.append({
            "severity": "warning",
            "code": "custodian_missing_email",
            "message": f"{missing_email} custodian(s) are missing an email address.",
        })
    if total_hold_failed > 0:
        needs_attention.append({
            "severity": "high",
            "code": "hold_failures",
            "message": f"{total_hold_failed} hold assignment(s) are marked failed.",
        })
    if total_hold_pending > 0:
        needs_attention.append({
            "severity": "warning",
            "code": "hold_pending",
            "message": f"{total_hold_pending} hold assignment(s) are still pending.",
        })
    if ntp_needing_action > 0:
        needs_attention.append({
            "severity": "warning",
            "code": "ntp_outstanding",
            "message": f"{ntp_needing_action} custodian(s) still need NTP completion.",
        })
    if consent_needing_action > 0:
        needs_attention.append({
            "severity": "warning",
            "code": "consent_outstanding",
            "message": f"{consent_needing_action} custodian(s) still need consent completion.",
        })
    if ntp_overdue_count > 0:
        needs_attention.append({
            "severity": "high",
            "code": "ntp_overdue",
            "message": f"{ntp_overdue_count} NTP acknowledgement SLA item(s) are overdue.",
        })
    if consent_overdue_count > 0:
        needs_attention.append({
            "severity": "high",
            "code": "consent_overdue",
            "message": f"{consent_overdue_count} consent SLA item(s) are overdue.",
        })
    if searches_needing_export > 0:
        needs_attention.append({
            "severity": "warning",
            "code": "search_export_gap",
            "message": f"{searches_needing_export} search(es) were performed but not exported.",
        })
    if searches_needing_delivery > 0:
        needs_attention.append({
            "severity": "warning",
            "code": "search_delivery_gap",
            "message": f"{searches_needing_delivery} search export(s) still need delivery.",
        })
    if exported_without_consent > 0:
        needs_attention.append({
            "severity": "high",
            "code": "export_without_consent",
            "message": f"{exported_without_consent} search export(s) were marked exported without consent.",
        })
    if open_tickets > 0:
        needs_attention.append({
            "severity": "info",
            "code": "tickets_open",
            "message": f"{open_tickets} request ticket(s) are still open or unclassified.",
        })

    generated_at = datetime.now(timezone.utc)
    analyst_name = ""
    analyst = getattr(case, "analyst", None)
    if analyst is not None:
        analyst_name = (
            " ".join(
                [
                    (getattr(analyst, "first_name", "") or "").strip(),
                    (getattr(analyst, "last_name", "") or "").strip(),
                ]
            ).strip()
            or (getattr(analyst, "email", "") or "").strip()
            or (getattr(analyst, "username", "") or "").strip()
        )
    requestors = [
        (getattr(r, "email", None) or "").strip()
        for r in (getattr(case, "requestors", None) or [])
        if (getattr(r, "email", None) or "").strip()
    ]
    if not requestors and (getattr(case, "requestor", None) or "").strip():
        requestors = [(getattr(case, "requestor", "") or "").strip()]

    case_status = _compute_case_status(db, case_id)
    status_line = (
        f"Holds: {'Yes' if case_status.hold else 'No'} | "
        f"NTP: {case_status.ntp} | "
        f"Consent: {case_status.consent} | "
        f"Search: {'Yes' if case_status.search else 'No'} | "
        f"Export: {'Yes' if case_status.export else 'No'} | "
        f"Delivered: {'Yes' if case_status.delivered else 'No'}"
    )

    lines: list[str] = []
    lines.append("DiscoveryOne Case Summary")
    lines.append(f"Generated: {_format_dt(generated_at)}")
    lines.append("")
    lines.append(f"Case: {(getattr(case, 'name', None) or '').strip() or '-'}")
    lines.append(f"Legal case: {(getattr(case, 'legal_case_name', None) or '').strip() or '-'}")
    lines.append(f"Claimant: {(getattr(case, 'claimant', None) or '').strip() or '-'}")
    lines.append(f"Analyst: {analyst_name or '-'}")
    lines.append(f"Requestors: {', '.join(requestors) if requestors else '-'}")
    lines.append(f"Closed: {'Yes' if bool(getattr(case, 'closed', False)) else 'No'}")
    lines.append(f"Case status: {status_line}")
    lines.append("")
    lines.append("Custodians")
    lines.append(f"- Total: {len(custodians)}")
    lines.append(f"- With email: {len(custodians) - missing_email}")
    lines.append(f"- Missing email: {missing_email}")
    lines.append("")
    lines.append("Holds")
    for label, _field in hold_fields:
        row = holds_summary.get(label, {})
        lines.append(
            f"- {label}: requested={row.get('requested', 0)}, active={row.get('active', 0)}, "
            f"pending={row.get('pending', 0)}, failed={row.get('failed', 0)}, released={row.get('released', 0)}"
        )
    lines.append("")
    lines.append(
        "NTP status: "
        + ", ".join(f"{k}={ntp_counts.get(k, 0)}" for k in ("not sent", "sent", "acknowledged", "silent"))
    )
    lines.append(
        "Consent status: "
        + ", ".join(f"{k}={consent_counts.get(k, 0)}" for k in ("not sent", "sent", "received", "implied", "awoc"))
    )
    lines.append("")
    lines.append(f"Searches: total={len(searches)}, without custodians={searches_without_custodians}")
    lines.append(
        "Search status: "
        + ", ".join(f"{k}={search_counts.get(k, 0)}" for k in ("not performed", "performed"))
    )
    lines.append(
        "Export status: "
        + ", ".join(f"{k}={export_counts.get(k, 0)}" for k in ("not performed", "performed"))
        + f", export_without_consent={exported_without_consent}"
    )
    lines.append(
        "Delivery status: "
        + ", ".join(f"{k}={delivery_counts.get(k, 0)}" for k in ("not performed", "performed", "not required"))
    )
    lines.append(f"Searches needing export: {searches_needing_export}")
    lines.append(f"Searches needing delivery: {searches_needing_delivery}")
    lines.append("")
    lines.append(f"Consent envelopes: total={len(consents)}")
    if consents:
        lines.append(
            "Envelope statuses: "
            + ", ".join(f"{k}={v}" for k, v in envelope_status_counts.items() if int(v or 0) > 0)
        )
    lines.append("")
    lines.append(
        f"SLA overdue: ntp={ntp_overdue_count}, consent={consent_overdue_count}"
    )
    lines.append(f"Request tickets: total={len(tickets)}, open_or_unclassified={open_tickets}")
    lines.append("")
    lines.append("Needs attention")
    if needs_attention:
        for item in needs_attention:
            lines.append(f"- [{item.get('severity', 'info')}] {item.get('message')}")
    else:
        lines.append("- None")

    summary_payload: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "case": {
            "id": case_id,
            "name": getattr(case, "name", None),
            "legal_case_name": getattr(case, "legal_case_name", None),
            "claimant": getattr(case, "claimant", None),
            "requestors": requestors,
            "analyst_name": analyst_name or None,
            "closed": bool(getattr(case, "closed", False)),
            "slack_hold_policy_id": getattr(case, "slack_hold_policy_id", None),
            "created_at": getattr(case, "created_at", None).isoformat() if getattr(case, "created_at", None) else None,
            "status": {
                "hold": bool(case_status.hold),
                "ntp": case_status.ntp,
                "consent": case_status.consent,
                "search": bool(case_status.search),
                "export": bool(case_status.export),
                "delivered": bool(case_status.delivered),
            },
        },
        "sections": {
            "custodians": {
                "total": len(custodians),
                "with_email": len(custodians) - missing_email,
                "missing_email": missing_email,
            },
            "holds": holds_summary,
            "ntp": {
                "statuses": ntp_counts,
                "needing_action": ntp_needing_action,
            },
            "consent": {
                "statuses": consent_counts,
                "needing_action": consent_needing_action,
                "envelopes_total": len(consents),
                "envelope_statuses": envelope_status_counts,
            },
            "searches": {
                "total": len(searches),
                "status_search": search_counts,
                "status_export": export_counts,
                "status_delivery": delivery_counts,
                "without_custodians": searches_without_custodians,
                "needing_export": searches_needing_export,
                "needing_delivery": searches_needing_delivery,
                "export_without_consent": exported_without_consent,
            },
            "sla": sla,
            "tickets": {
                "total": len(tickets),
                "open_or_unclassified": open_tickets,
            },
        },
        "needs_attention": needs_attention,
        "report_text": "\n".join(lines).strip(),
    }
    return summary_payload



@router.get("/{case_id}/holds_detail")
def get_case_holds_detail(
    case_id: int,
    limit: int = Query(5000, ge=100, le=20000),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    return build_case_holds_detail(case_id=case_id, limit=int(limit), db=db, actor=actor)



@router.get("/{case_id}/summary")
def case_summary(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)

    payload = _build_case_summary_payload(db, case)
    ai_result = _build_case_summary_ai(case=case, facts=payload)
    if ai_result.get("status") != "ok":
        detail = ai_result.get("error") or "Case summary AI is unavailable"
        raise HTTPException(status_code=503, detail=detail)

    payload["ai"] = ai_result
    payload["report_text"] = _compose_case_summary_ai_report_text(
        case=case,
        ai=ai_result,
        fallback_text=payload.get("report_text") or "",
        generated_at=_format_dt(datetime.now(timezone.utc)),
    )
    payload["needs_attention"] = [
        {
            "severity": "warning" if str(item).strip() else "info",
            "code": "ai_attention",
            "message": str(item),
        }
        for item in (ai_result.get("attention_items") or [])
        if str(item or "").strip()
    ]

    try:
        log_event(
            db,
            action="case_summary_view",
            actor_id=getattr(actor, "id", None),
            target_type="case",
            target_id=case_id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "needs_attention_count": len(payload.get("needs_attention") or []),
                "ai_model": ai_result.get("model"),
                "ai_status": ai_result.get("status"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_status_summary.py:case_summary_view", exc)
    return payload


@router.post("/{case_id}/summary/email")
def email_case_summary_to_self(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    actor: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)
    recipient = _resolve_actor_email(actor)
    if not recipient:
        raise HTTPException(status_code=400, detail="Your account does not have an email address configured")

    payload = _build_case_summary_payload(db, case)
    ai_result = _build_case_summary_ai(case=case, facts=payload)
    if ai_result.get("status") != "ok":
        detail = ai_result.get("error") or "Case summary AI is unavailable"
        raise HTTPException(status_code=503, detail=detail)

    report_text = _compose_case_summary_ai_report_text(
        case=case,
        ai=ai_result,
        fallback_text=payload.get("report_text") or "",
        generated_at=_format_dt(datetime.now(timezone.utc)),
    )

    subject = branded_subject(f"AI Case Summary - {(getattr(case, 'name', None) or 'Unnamed Case').strip()}")
    send_email(
        recipients=[recipient],
        subject=subject,
        body=report_text,
    )
    try:
        log_event(
            db,
            action="case_summary_email",
            actor_id=getattr(actor, "id", None),
            target_type="case",
            target_id=case_id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "recipient": recipient,
                "needs_attention_count": len(ai_result.get("attention_items") or []),
                "ai_model": ai_result.get("model"),
                "ai_status": ai_result.get("status"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_status_summary.py:case_summary_email", exc)
    return {"ok": True, "recipient": recipient}


