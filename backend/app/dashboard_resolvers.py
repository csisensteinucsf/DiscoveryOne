"""Dashboard widget resolver functions."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, ticket_provider
from .dashboard_access import _filter_case_ids, _visible_case_ids
from .permissions import filter_ticket_entries_for_user, is_requestor, is_tech
from .preservation_catalog import configured_builtin_hold_fields


def _resolve_case_counts(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    q = db.query(models.Case.closed, func.count(models.Case.id)).group_by(models.Case.closed)
    q = _filter_case_ids(q, models.Case.id, case_ids)
    rows = q.all()
    counts = {bool(closed): int(n) for closed, n in rows}
    total = sum(counts.values())
    open_count = counts.get(False, 0)
    closed_count = counts.get(True, 0)
    last_days = int(config.get("created_last_days") or 7)
    since = datetime.now(timezone.utc) - timedelta(days=max(1, min(365, last_days)))
    q2 = db.query(func.count(models.Case.id)).filter(models.Case.created_at >= since)
    q2 = _filter_case_ids(q2, models.Case.id, case_ids)
    created_recent = int(q2.scalar() or 0)
    return {
        "total": total,
        "open": open_count,
        "closed": closed_count,
        "created_last_days": last_days,
        "created_recent": created_recent,
    }


def _resolve_consent_status(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    status_col = func.lower(func.coalesce(models.CaseConsent.status, "")).label("status")
    q = (
        db.query(status_col, func.count(models.CaseConsent.id))
        .join(models.Case, models.Case.id == models.CaseConsent.case_id)
        .filter(models.CaseConsent.case_id.isnot(None))
    )
    if config.get("open_only", True):
        q = q.filter(models.Case.closed.is_(False))
    q = _filter_case_ids(q, models.Case.id, case_ids)
    q = q.group_by(status_col)
    rows = q.all()
    by_status: dict[str, int] = {}
    for status, n in rows:
        s = (status or "").strip() or "unknown"
        by_status[s] = int(n or 0)
    pending = by_status.get("sent", 0) + by_status.get("delivered", 0)
    return {"by_status": by_status, "pending": pending}


def _resolve_ntp_status(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    open_only = bool(config.get("open_only", True))
    status_col = func.lower(func.coalesce(models.Custodian.ntp_status, "not sent")).label("status")
    q = (
        db.query(status_col, func.count(models.Custodian.id))
        .join(models.Case, models.Case.id == models.Custodian.case_id)
    )
    if open_only:
        q = q.filter(models.Case.closed.is_(False))
    q = _filter_case_ids(q, models.Case.id, case_ids)
    q = q.group_by(status_col)
    rows = q.all()
    by_status: dict[str, int] = {}
    for status, n in rows:
        key = (status or "").strip() or "unknown"
        by_status[key] = int(n or 0)
    total = sum(by_status.values())
    pending = by_status.get("not sent", 0) + by_status.get("sent", 0)
    return {"by_status": by_status, "total": total, "pending": pending, "open_only": open_only}


def _resolve_ntp_reminders(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    open_only = bool(config.get("open_only", True))
    try:
        days_ahead = int(config.get("days_ahead") or 7)
    except Exception:
        days_ahead = 7
    days_ahead = max(1, min(90, days_ahead))

    now = datetime.now(timezone.utc)
    base = (
        db.query(models.NTPReminder)
        .join(models.Case, models.Case.id == models.NTPReminder.case_id)
    )
    if open_only:
        base = base.filter(models.Case.closed.is_(False))
    base = _filter_case_ids(base, models.Case.id, case_ids)

    status_col = func.lower(func.coalesce(models.NTPReminder.status, "active"))
    status_rows = base.with_entities(status_col, func.count(models.NTPReminder.id)).group_by(status_col).all()
    by_status: dict[str, int] = {}
    for status, n in status_rows:
        key = (status or "").strip() or "unknown"
        by_status[key] = int(n or 0)

    active_q = base.filter(models.NTPReminder.status == "active")
    active = int(active_q.count() or 0)
    due_now = int(active_q.filter(models.NTPReminder.next_send_at <= now).count() or 0)
    due_soon = int(
        active_q.filter(models.NTPReminder.next_send_at <= (now + timedelta(days=days_ahead))).count() or 0
    )
    next_due = (
        active_q.with_entities(models.NTPReminder.next_send_at)
        .order_by(models.NTPReminder.next_send_at.asc().nulls_last(), models.NTPReminder.id.asc())
        .first()
    )
    next_due_at = next_due[0].isoformat() if next_due and next_due[0] else None

    return {
        "by_status": by_status,
        "active": active,
        "due_now": due_now,
        "due_soon": due_soon,
        "days_ahead": days_ahead,
        "next_due_at": next_due_at,
        "open_only": open_only,
    }


def _resolve_hold_status(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    configured_fields = configured_builtin_hold_fields(enabled_only=True)
    active_fields = [field for _key, field, _label in configured_fields if hasattr(models.Custodian, field)]
    pending_fields = [f"{field}_pending" for field in active_fields if hasattr(models.Custodian, f"{field}_pending")]
    keys = [key for key, field, _label in configured_fields if field in active_fields]

    q = db.query(models.Custodian).join(models.Case, models.Case.id == models.Custodian.case_id)
    if config.get("open_only", True):
        q = q.filter(models.Case.closed.is_(False))
    q = _filter_case_ids(q, models.Case.id, case_ids)
    columns = [getattr(models.Custodian, field) for field in active_fields] + [getattr(models.Custodian, field) for field in pending_fields]
    rows = q.with_entities(*columns).all() if columns else q.with_entities(models.Custodian.id).all()
    total = len(rows)
    active_any = 0
    pending_any = 0
    active_by_type = {key: 0 for key in keys}
    pending_by_type = {key: 0 for key in keys}
    active_count = len(active_fields)
    for r in rows:
        active = [bool(r[idx]) for idx in range(active_count)]
        pending = [bool(r[active_count + idx]) for idx in range(len(pending_fields))]
        if any(active):
            active_any += 1
        if any(pending):
            pending_any += 1
        for idx, k in enumerate(keys):
            if idx < len(active) and active[idx]:
                active_by_type[k] += 1
            if idx < len(pending) and pending[idx]:
                pending_by_type[k] += 1
    return {
        "custodians": total,
        "active_any": active_any,
        "pending_any": pending_any,
        "active_by_type": active_by_type,
        "pending_by_type": pending_by_type,
    }


def _resolve_search_status(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    open_only = bool(config.get("open_only", True))

    q = db.query(models.Search).join(models.Case, models.Case.id == models.Search.case_id)
    if open_only:
        q = q.filter(models.Case.closed.is_(False))
    q = _filter_case_ids(q, models.Case.id, case_ids)

    rows = q.with_entities(
        models.Search.status_search,
        models.Search.status_export,
        models.Search.status_delivery,
        models.Search.export_without_consent,
    ).all()

    by_search: dict[str, int] = {}
    by_export: dict[str, int] = {}
    by_delivery: dict[str, int] = {}
    delivery_pending = 0
    exported_without_consent = 0

    for search_status, export_status, delivery_status, without_consent in rows:
        s_key = (search_status or "").strip().lower() or "unknown"
        e_key = (export_status or "").strip().lower() or "unknown"
        d_key = (delivery_status or "").strip().lower() or "unknown"

        by_search[s_key] = by_search.get(s_key, 0) + 1
        by_export[e_key] = by_export.get(e_key, 0) + 1
        by_delivery[d_key] = by_delivery.get(d_key, 0) + 1

        if e_key == "performed" and d_key not in {"performed", "not required"}:
            delivery_pending += 1
        if bool(without_consent):
            exported_without_consent += 1

    return {
        "total": len(rows),
        "by_search": by_search,
        "by_export": by_export,
        "by_delivery": by_delivery,
        "search_performed": by_search.get("performed", 0),
        "search_not_performed": max(0, len(rows) - by_search.get("performed", 0)),
        "export_performed": by_export.get("performed", 0),
        "export_not_performed": max(0, len(rows) - by_export.get("performed", 0)),
        "delivery_performed": by_delivery.get("performed", 0),
        "delivery_not_required": by_delivery.get("not required", 0),
        "delivery_pending": delivery_pending,
        "exported_without_consent": exported_without_consent,
        "open_only": open_only,
    }

def _resolve_requests_sla(db: Session, actor: models.User, *, config: dict) -> dict:
    now = datetime.now(timezone.utc)
    q = db.query(models.CaseRequest).filter(models.CaseRequest.status == "pending")
    if is_requestor(actor):
        q = q.filter(models.CaseRequest.requestor_id == actor.id)
    rows = q.with_entities(
        models.CaseRequest.id,
        models.CaseRequest.request_type,
        models.CaseRequest.case_id,
        models.CaseRequest.case_name,
        models.CaseRequest.created_at,
    ).all()
    by_type: dict[str, int] = {}
    buckets = {"lt_24h": 0, "d1_3": 0, "gt_3d": 0}
    for rid, rtype, case_id, case_name, created_at in rows:
        key = (rtype or "unknown").strip() or "unknown"
        by_type[key] = by_type.get(key, 0) + 1
        created = created_at or now
        if getattr(created, "tzinfo", None) is None:
            created = created.replace(tzinfo=timezone.utc)
        age = now - created
        if age < timedelta(hours=24):
            buckets["lt_24h"] += 1
        elif age <= timedelta(days=3):
            buckets["d1_3"] += 1
        else:
            buckets["gt_3d"] += 1
    oldest = (
        q.order_by(models.CaseRequest.created_at.asc().nullsfirst(), models.CaseRequest.id.asc())
        .limit(int(config.get("oldest_limit") or 5))
        .all()
    )
    oldest_out = []
    for row in oldest:
        oldest_out.append(
            {
                "id": row.id,
                "request_type": row.request_type,
                "case_id": row.case_id,
                "case_name": row.case_name,
                "created_at": str(row.created_at or ""),
            }
        )
    return {"pending": len(rows), "by_type": by_type, "age_buckets": buckets, "oldest": oldest_out}


def _status_is_closed(value: Optional[str]) -> bool:
    return ticket_provider.is_closed_status(value)

def _resolve_open_tickets(db: Session, actor: models.User, *, config: dict) -> dict:
    case_ids = _visible_case_ids(db, actor)
    open_only = bool(config.get("open_only", True))
    refresh_live = bool(config.get("refresh_live", True))
    try:
        max_tickets = int(config.get("max_tickets") or 200)
    except Exception:
        max_tickets = 200
    max_tickets = max(1, min(500, max_tickets))

    q = db.query(models.Case)
    if open_only:
        q = q.filter(models.Case.closed.is_(False))
    q = _filter_case_ids(q, models.Case.id, case_ids)
    cases = q.all()

    rows: list[dict] = []
    tickets: list[str] = []
    for case in cases:
        entries = getattr(case, "request_ticket_entries", []) or []
        if is_tech(actor):
            entries = filter_ticket_entries_for_user(entries, actor)
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            ticket = (entry.get("ticket") or "").strip()
            if not ticket:
                continue
            tickets.append(ticket)
            rows.append({"case": case, "entry": entry, "ticket": ticket})

    unique_tickets: list[str] = []
    seen = set()
    for t in tickets:
        key = t.strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_tickets.append(t)

    truncated = len(unique_tickets) > max_tickets
    status_lookup: dict[str, dict] = {}
    if refresh_live and unique_tickets:
        subset = unique_tickets[:max_tickets]
        try:
            status_lookup = ticket_provider.get_ticket_statuses(subset)
        except Exception:
            status_lookup = {}

    open_count = 0
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    unknown_status = 0
    for row in rows:
        entry = row["entry"]
        ticket = row["ticket"]
        info = status_lookup.get(ticket) or status_lookup.get(ticket.strip().upper()) or {}
        status = info.get("status") or entry.get("status") or ""
        is_closed = bool(info.get("is_closed")) if "is_closed" in info else _status_is_closed(status)
        if not status:
            unknown_status += 1
        if is_closed:
            continue
        open_count += 1
        category = (entry.get("category") or "unknown").strip().lower() or "unknown"
        by_category[category] = by_category.get(category, 0) + 1
        status_key = (str(status or "")).strip().lower() or "unknown"
        by_status[status_key] = by_status.get(status_key, 0) + 1

    return {
        "open": open_count,
        "total": len(rows),
        "by_category": by_category,
        "by_status": by_status,
        "unknown_status": unknown_status,
        "open_only": open_only,
        "refresh_live": refresh_live,
        "truncated": truncated,
        "max_tickets": max_tickets,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


_RESOLVERS = {
    "case_counts": _resolve_case_counts,
    "consent_status": _resolve_consent_status,
    "search_status": _resolve_search_status,
    "ntp_status": _resolve_ntp_status,
    "ntp_reminders": _resolve_ntp_reminders,
    "hold_status": _resolve_hold_status,
    "open_tickets": _resolve_open_tickets,
    "requests_sla": _resolve_requests_sla,
}


