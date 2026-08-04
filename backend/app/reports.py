
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, or_, literal, case as sql_case, text
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import io, csv, json


def _csv_iter(headers, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    def _emit():
        data = buf.getvalue(); buf.seek(0); buf.truncate(0); return data
    writer.writerow(headers); yield _emit()
    for r in rows:
        row = []
        for k in headers:
            v = r.get(k, "")
            v = "" if v is None else str(v)
            if v and v[0] in ("=", "+", "-", "@"):  # neutralize Excel injection
                v = "'" + v
            row.append(v)
        writer.writerow(row)
        yield _emit()

router = APIRouter(prefix="/api", tags=["reports"])

# ---------------- Database session ----------------
from .database import SessionLocal
from . import models
from .preservation_catalog import configured_hold_catalog, custodian_configured_hold_flags, custodian_has_configured_hold
from .auth import current_user as get_current_user
from .permissions import (
    ensure_case_editable,
    get_visible_case_ids,
    is_requestor,
    get_requestor_allowed_emails,
    get_tech_visible_case_ids,
    is_tester,
    is_tech,
)

logger = logging.getLogger(__name__)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def _normalize_paging(page: int, per_page: int, *, max_per_page: int = 1000) -> tuple[int, int]:
    safe_page = max(1, int(page or 1))
    safe_per_page = max(1, min(int(per_page or 200), int(max_per_page)))
    return safe_page, safe_per_page


def _paginate_payload(items: list[dict], *, page: int, per_page: int) -> dict:
    safe_page, safe_per_page = _normalize_paging(page, per_page)
    total = len(items)
    start = (safe_page - 1) * safe_per_page
    end = start + safe_per_page
    return {
        "items": items[start:end],
        "total": total,
        "page": safe_page,
        "per_page": safe_per_page,
    }



def _visible_case_ids(db: Session, actor) -> Optional[set]:
    return get_visible_case_ids(actor, db)


def _filter_cases_query(query, case_ids: Optional[set]):
    if case_ids is None:
        return query
    if not case_ids:
        return query.filter(literal(False))
    return query.filter(models.Case.id.in_(case_ids))


def _filter_by_case_ids(query, column, case_ids: Optional[set]):
    if case_ids is None:
        return query
    if not case_ids:
        return query.filter(literal(False))
    return query.filter(column.in_(case_ids))


def _user_display_name(user):
    if not user:
        return ""
    first = (getattr(user, "first_name", "") or "").strip()
    last = (getattr(user, "last_name", "") or "").strip()
    combined = " ".join(part for part in (first, last) if part)
    if combined:
        return combined
    email = getattr(user, "email", None)
    if email:
        return email
    return getattr(user, "username", "") or ""

# ==================================================
#               REPORTING ENDPOINTS
# ==================================================

def _csv_response(rows: List[Dict[str, Any]], headers: List[str], filename: str):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow([r.get(k, "") for k in headers])
    buf.seek(0)
    return StreamingResponse(_csv_iter(headers, rows), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })

def _analyst_items(db: Session, case_ids: Optional[set]):
    q = _filter_cases_query(db.query(models.Case), case_ids)
    cases = q.all()
    items: Dict[str, Dict[str, Any]] = {}
    for c in cases:
        name = _user_display_name(getattr(c, "analyst", None)) or "â€”"
        row = items.setdefault(name, {"analyst": name, "open_cases": 0, "closed_cases": 0})
        if c.closed:
            row["closed_cases"] += 1
        else:
            row["open_cases"] += 1
    return list(items.values())


@router.get("/reports/analysts")
def rpt_analysts(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    items = _analyst_items(db, case_ids)
    return {"items": items}

@router.get("/reports/analysts/export")
def rpt_analysts_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    items = _analyst_items(db, case_ids)
    return _csv_response(items, ["analyst", "open_cases", "closed_cases"], "analysts.csv")

def _status_count(values: List[str], status: str):
    status = status.lower()
    return sum(1 for v in values if (v or "").lower() == status)


def _case_hold_memberships(db: Session, case_id: int, *, active_only: bool = False):
    query = (
        db.query(models.HoldCustodian)
        .join(models.CaseHold, models.HoldCustodian.hold_id == models.CaseHold.id)
        .options(
            selectinload(models.HoldCustodian.custodian),
            selectinload(models.HoldCustodian.preservation_sources),
            selectinload(models.HoldCustodian.hold),
        )
        .filter(models.CaseHold.case_id == int(case_id))
    )
    if active_only:
        query = query.filter(models.CaseHold.status == "active")
    return query.all()


def _case_hold_searches(db: Session, case_id: int, *, active_only: bool = False):
    query = (
        db.query(models.HoldSearch)
        .join(models.CaseHold, models.HoldSearch.hold_id == models.CaseHold.id)
        .options(selectinload(models.HoldSearch.search), selectinload(models.HoldSearch.hold))
        .filter(models.CaseHold.case_id == int(case_id))
    )
    if active_only:
        query = query.filter(models.CaseHold.status == "active")
    return query.all()


def _case_aging_items(db: Session, case_ids: Optional[set]):
    now = datetime.now(timezone.utc)
    q = _filter_cases_query(db.query(models.Case), case_ids)
    cases = q.order_by(models.Case.name.asc()).all()
    items = []
    for c in cases:
        created_at = getattr(c, "created_at", None) or now
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        else:
            created_at = created_at.astimezone(timezone.utc)
        anchor_date = c.start_date or created_at.date()
        days_open = max((now.date() - anchor_date).days, 0) if anchor_date else 0
        custodians = db.query(models.Custodian).filter(models.Custodian.case_id == c.id).all()
        holds = db.query(models.CaseHold).filter(models.CaseHold.case_id == c.id).all()
        memberships = _case_hold_memberships(db, c.id)
        hold_searches = _case_hold_searches(db, c.id)

        def count_status(field):
            return sum(1 for link in hold_searches if getattr(link, field, "") == "performed")

        items.append({
            "case": c.name,
            "case_id": c.id,
            "status": "Inactive" if c.closed else "Active",
            "created_at": created_at.isoformat(),
            "days_open": days_open,
            "custodians": len(custodians),
            "holds_total": len(holds),
            "active_holds": sum(1 for hold in holds if hold.status == "active"),
            "custodian_hold_links": len(memberships),
            "searches_total": len(hold_searches),
            "searches_done": count_status("status_search"),
            "exports_done": count_status("status_export"),
            "deliveries_done": count_status("status_delivery"),
            "analyst": getattr(getattr(c, "analyst", None), "username", None),
        })
    return items

def _ntp_consent_summary_items(db: Session, case_ids: Optional[set]):
    query = (
        db.query(models.HoldCustodian)
        .join(models.CaseHold, models.HoldCustodian.hold_id == models.CaseHold.id)
    )
    query = _filter_by_case_ids(query, models.CaseHold.case_id, case_ids)
    memberships = query.all()

    def gather(field, label):
        counts: Dict[str, int] = {}
        for membership in memberships:
            key = (getattr(membership, field, "") or "not sent").lower()
            counts[key] = counts.get(key, 0) + 1
        return [
            {"type": label, "status": status, "count": count}
            for status, count in sorted(counts.items())
        ]

    return gather("ntp_status", "NTP") + gather("consent_status", "Consent")

def _custodian_gaps_items(db: Session, case_ids: Optional[set]):
    q = _filter_cases_query(db.query(models.Case), case_ids)
    cases = q.order_by(models.Case.name.asc()).all()
    items = []
    for c in cases:
        custodians = db.query(models.Custodian).filter(models.Custodian.case_id == c.id).all()
        memberships = _case_hold_memberships(db, c.id, active_only=True)
        assigned_ids = {int(membership.custodian_id) for membership in memberships}
        without_hold = sum(1 for custodian in custodians if int(custodian.id) not in assigned_ids)
        without_preservation = sum(
            1
            for membership in memberships
            if not any(
                (source.status or "not_started").lower() in {"pending", "active"}
                for source in membership.preservation_sources or []
            )
        )
        ntp_not_sent = sum(
            1 for membership in memberships
            if (membership.ntp_status or "").lower() == "not sent"
        )
        consent_not_received = sum(
            1 for membership in memberships
            if (membership.consent_status or "").lower() not in {"received", "implied", "awoc", "na"}
        )
        items.append({
            "case": c.name,
            "custodians": len(custodians),
            "active_holds": len({membership.hold_id for membership in memberships}),
            "custodian_hold_links": len(memberships),
            "without_hold": without_hold,
            "without_preservation": without_preservation,
            "ntp_not_sent": ntp_not_sent,
            "consent_not_received": consent_not_received,
        })
    return items

def _parse_audit_details(val):
    if isinstance(val, (dict, list)) or val is None:
        return val
    s = str(val).strip()
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            return json.loads(s)
        except Exception:
            return s
    return s


def _case_timeline_items(db: Session, case_id: int, limit: int, actor) -> List[Dict[str, Any]]:
    ensure_case_editable(actor)
    allowed = _visible_case_ids(db, actor)
    if allowed is not None and case_id not in allowed:
        raise HTTPException(status_code=404, detail="Case not found")
    exists = db.query(models.Case.id).filter(models.Case.id == case_id)
    exists = _filter_by_case_ids(exists, models.Case.id, allowed)
    if not db.query(exists.exists()).scalar():
        raise HTTPException(status_code=404, detail="Case not found")
    limit = max(1, min(limit, 1000))
    sql = text(
        """
        WITH cust AS (SELECT id FROM custodians WHERE case_id = :case_id),
             srch AS (SELECT id FROM searches WHERE case_id = :case_id)
        SELECT ev.id,
               ev.created_at,
               ev.action,
               ev.target_type,
               ev.target_id,
               ev.details,
               ev.actor_id,
               u.username
          FROM audit_events ev
          LEFT JOIN users u ON u.id = ev.actor_id
         WHERE (ev.target_type = 'case' AND ev.target_id = :case_id)
            OR (ev.target_type = 'custodian' AND ev.target_id IN (SELECT id FROM cust))
            OR (ev.target_type = 'search' AND ev.target_id IN (SELECT id FROM srch))
         ORDER BY ev.created_at DESC, ev.id DESC
         LIMIT :limit
        """
    )
    rows = db.execute(sql, {"case_id": case_id, "limit": limit}).mappings().all()
    out = []
    for r in rows:
        rec = dict(r)
        rec["details"] = _parse_audit_details(rec.get("details"))
        out.append(rec)
    return out

def _consents_by_case_items(db: Session, case_ids: Optional[set]):
    q = db.query(models.Case).filter(models.Case.closed == False)
    q = _filter_cases_query(q, case_ids)
    cases = q.all()
    items = []
    for c in cases:
        memberships = _case_hold_memberships(db, c.id)
        statuses = [membership.consent_status or "not sent" for membership in memberships]
        items.append({
            "case_name": c.name,
            "holds": len({membership.hold_id for membership in memberships}),
            "custodian_hold_links": len(memberships),
            "not_sent": _status_count(statuses, "not sent"),
            "sent": _status_count(statuses, "sent"),
            "received": _status_count(statuses, "received"),
            "implied": _status_count(statuses, "implied") + _status_count(statuses, "na"),
            "awoc": _status_count(statuses, "awoc"),
        })
    return items

@router.get("/reports/consents_by_case")
def rpt_consents_by_case(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _consents_by_case_items(db, _visible_case_ids(db, actor))
    return {"items": items}

@router.get("/reports/consents_by_case/export")
def rpt_consents_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _consents_by_case_items(db, _visible_case_ids(db, actor))
    return _csv_response(items, ["case_name", "holds", "custodian_hold_links", "not_sent", "sent", "received", "implied", "awoc"], "consents_by_case.csv")


@router.get("/reports/case_timeline")
def rpt_case_timeline(
    case_id: int = Query(..., description="Case ID"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _case_timeline_items(db, case_id, limit, actor)
    return {"items": items, "limit": limit}


@router.get("/reports/case_timeline/export")
def rpt_case_timeline_export(
    case_id: int = Query(..., description="Case ID"),
    limit: int = Query(1000, ge=1, le=1000),
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _case_timeline_items(db, case_id, limit, actor)
    headers = ["created_at", "action", "target_type", "target_id", "actor_id", "username", "details"]
    rows = []
    for item in items:
        rows.append({
            "created_at": item.get("created_at"),
            "action": item.get("action"),
            "target_type": item.get("target_type"),
            "target_id": item.get("target_id"),
            "actor_id": item.get("actor_id"),
            "username": item.get("username"),
            "details": item.get("details"),
        })
    return _csv_response(rows, headers, f"case_{case_id}_timeline.csv")



def _holds_items(db: Session, case_ids: Optional[set]):
    q = _filter_cases_query(db.query(models.Case), case_ids)
    cases = q.all()
    buckets: Dict[str, Dict[str, Any]] = {}
    for case in cases:
        holds = db.query(models.CaseHold).filter(models.CaseHold.case_id == case.id).all()
        if not holds:
            holds = [None]
        for hold in holds:
            status = "no holds" if hold is None else str(hold.status or "active").lower()
            label = status.replace("_", " ").title()
            row = buckets.setdefault(label, {
                "hold_status": label,
                "hold_count": 0,
                "cases_open_ids": set(),
                "cases_closed_ids": set(),
                "custodian_case_links": 0,
            })
            if hold is not None:
                row["hold_count"] += 1
                row["custodian_case_links"] += db.query(models.HoldCustodian).filter(
                    models.HoldCustodian.hold_id == hold.id
                ).count()
            if case.closed:
                row["cases_closed_ids"].add(int(case.id))
            else:
                row["cases_open_ids"].add(int(case.id))

    items = []
    for row in buckets.values():
        items.append({
            "hold_status": row["hold_status"],
            "hold_count": row["hold_count"],
            "cases_open": len(row["cases_open_ids"]),
            "cases_closed": len(row["cases_closed_ids"]),
            "custodian_case_links": row["custodian_case_links"],
        })
    return sorted(items, key=lambda item: item["hold_status"])

@router.get("/reports/holds")
def rpt_holds(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _holds_items(db, _visible_case_ids(db, actor))
    return {"items": items}

@router.get("/reports/holds/export")
def rpt_holds_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _holds_items(db, _visible_case_ids(db, actor))
    return _csv_response(items, ["hold_status","hold_count","cases_open","cases_closed","custodian_case_links"], "holds.csv")

def _cases_by_year_items(db: Session, case_ids: Optional[set]):
    items: Dict[str, int] = {}
    q = _filter_cases_query(db.query(models.Case), case_ids)
    for c in q.all():
        y = (c.created_at.year if getattr(c, "created_at", None) else None)
        if not y: continue
        items[str(y)] = items.get(str(y), 0) + 1
    return [{"year": y, "cases": items[y]} for y in sorted(items.keys())]

@router.get("/reports/cases_by_year")
def rpt_cases_by_year(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    return {"items": _cases_by_year_items(db, case_ids)}

@router.get("/reports/cases_by_year/export")
def rpt_cases_by_year_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    items = _cases_by_year_items(db, case_ids)
    return _csv_response(items, ["year", "cases"], "cases_by_year.csv")

def _cases_summary_items(db: Session, case_ids: Optional[set], open_only: bool):
    q = db.query(models.Case)
    if open_only:
        q = q.filter(models.Case.closed == False)
    q = _filter_cases_query(q, case_ids)
    cases = q.order_by(models.Case.name.asc()).all()
    items = []
    for c in cases:
        custodians = db.query(models.Custodian).filter(models.Custodian.case_id == c.id).all()
        holds = db.query(models.CaseHold).filter(models.CaseHold.case_id == c.id).all()
        memberships = _case_hold_memberships(db, c.id)
        hold_searches = _case_hold_searches(db, c.id)

        def count_status(rows, field, value):
            return sum(1 for row in rows if getattr(row, field, "") == value)

        items.append({
            "name": c.name,
            "custodians": len(custodians),
            "holds_total": len(holds),
            "active_holds": sum(1 for hold in holds if hold.status == "active"),
            "custodian_hold_links": len(memberships),
            "search_total": len(hold_searches),
            "search_done": count_status(hold_searches, "status_search", "performed"),
            "export_done": count_status(hold_searches, "status_export", "performed"),
            "delivered": count_status(hold_searches, "status_delivery", "performed"),
            "ntp_sent": count_status(memberships, "ntp_status", "sent"),
            "ntp_acknowledged": count_status(memberships, "ntp_status", "acknowledged"),
            "consent_sent": count_status(memberships, "consent_status", "sent"),
            "consent_received": count_status(memberships, "consent_status", "received"),
        })
    return items

@router.get("/reports/cases_summary")
def rpt_cases_summary(
    open_only: bool = Query(False),
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _cases_summary_items(db, _visible_case_ids(db, actor), open_only)
    return {"items": items}

@router.get("/reports/cases_summary/export")
def rpt_cases_summary_export(
    open_only: bool = Query(False),
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _cases_summary_items(db, _visible_case_ids(db, actor), open_only)
    headers = ["name","custodians","holds_total","active_holds","custodian_hold_links","search_total","search_done","export_done","delivered","ntp_sent","ntp_acknowledged","consent_sent","consent_received"]
    return _csv_response(items, headers, "cases_summary.csv")

def _searches_by_status_items(db: Session, case_ids: Optional[set]) -> List[Dict[str, Any]]:
    q = (
        db.query(models.HoldSearch)
        .join(models.CaseHold, models.HoldSearch.hold_id == models.CaseHold.id)
    )
    q = _filter_by_case_ids(q, models.CaseHold.case_id, case_ids)
    total = q.count()
    performed = q.filter(models.HoldSearch.status_search == "performed").count()
    return [
        {"search": "performed", "export": None, "delivery": None, "rows": performed},
        {"search": "not performed", "export": None, "delivery": None, "rows": total - performed},
    ]

@router.get("/reports/searches_by_status")
def rpt_searches_by_status(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    return {"items": _searches_by_status_items(db, case_ids)}

@router.get("/reports/searches_by_status/export")
def rpt_searches_by_status_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    items = _searches_by_status_items(db, case_ids)
    return _csv_response(items, ["search", "export", "delivery", "rows"], "searches_by_status.csv")

# --- Additional advanced reports ---
@router.get("/reports/case_aging")
def rpt_case_aging(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _case_aging_items(db, _visible_case_ids(db, actor))
    return {"items": items}

@router.get("/reports/case_aging/export")
def rpt_case_aging_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _case_aging_items(db, _visible_case_ids(db, actor))
    headers = ["case","status","analyst","created_at","days_open","custodians","holds_total","active_holds","custodian_hold_links","searches_total","searches_done","exports_done","deliveries_done"]
    return _csv_response(items, headers, "case_aging.csv")


@router.get("/reports/ntp_consent_summary")
def rpt_ntp_consent_summary(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _ntp_consent_summary_items(db, _visible_case_ids(db, actor))
    return {"items": items}

@router.get("/reports/ntp_consent_summary/export")
def rpt_ntp_consent_summary_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _ntp_consent_summary_items(db, _visible_case_ids(db, actor))
    return _csv_response(items, ["type","status","count"], "ntp_consent_summary.csv")


@router.get("/reports/custodian_gaps")
def rpt_custodian_gaps(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _custodian_gaps_items(db, _visible_case_ids(db, actor))
    return {"items": items}

@router.get("/reports/custodian_gaps/export")
def rpt_custodian_gaps_export(
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    items = _custodian_gaps_items(db, _visible_case_ids(db, actor))
    headers = ["case","custodians","active_holds","custodian_hold_links","without_hold","without_preservation","ntp_not_sent","consent_not_received"]
    return _csv_response(items, headers, "custodian_gaps.csv")

# --- Custodian report (searchable) ---
def _custodian_hold_flags(cu: models.Custodian) -> Dict[str, bool]:
    memberships = list(getattr(cu, "hold_memberships", None) or [])
    if not memberships:
        holds = custodian_configured_hold_flags(cu)
        holds["any"] = any(holds.values())
        return holds
    holds = {key: False for key, _field, _label in configured_hold_catalog(enabled_only=True)}
    for membership in memberships:
        for source in getattr(membership, "preservation_sources", None) or []:
            key = str(getattr(source, "source_key", "") or "").strip().lower()
            status = str(getattr(source, "status", "") or "").strip().lower()
            if key and status in {"pending", "active"}:
                holds[key] = True
    holds["any"] = bool(memberships)
    return holds


def _custodian_named_holds(cu: models.Custodian) -> List[Dict[str, Any]]:
    result = []
    for membership in getattr(cu, "hold_memberships", None) or []:
        hold = getattr(membership, "hold", None)
        if hold is None:
            continue
        result.append({
            "id": int(hold.id),
            "name": hold.name,
            "status": hold.status,
            "ntp_status": membership.ntp_status,
            "consent_status": membership.consent_status,
        })
    return sorted(result, key=lambda item: (str(item.get("name") or "").lower(), int(item["id"])))


def _find_custodians(
    db: Session,
    q: Optional[str] = None,
    case_ids: Optional[set] = None,
    *,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
):
    q_norm = (q or "").strip().lower()
    query = (
        db.query(models.Custodian, models.Case)
        .join(models.Case, models.Custodian.case_id == models.Case.id)
        .options(
            selectinload(models.Custodian.custom_preservation),
            selectinload(models.Custodian.hold_memberships)
            .selectinload(models.HoldCustodian.preservation_sources),
            selectinload(models.Custodian.hold_memberships)
            .selectinload(models.HoldCustodian.hold),
        )
    )
    query = _filter_by_case_ids(query, models.Custodian.case_id, case_ids)
    if q_norm:
        q_like = f"%{q_norm}%"
        query = query.filter(
            or_(
                func.lower(models.Custodian.name).like(q_like),
                func.lower(models.Custodian.email).like(q_like),
            )
        )
    query = query.order_by(models.Case.name.asc(), models.Custodian.id.asc())

    total = None
    if page is not None and per_page is not None:
        safe_page, safe_per_page = _normalize_paging(page, per_page)
        total = int(query.order_by(None).count() or 0)
        offset = (safe_page - 1) * safe_per_page
        items = query.offset(offset).limit(safe_per_page).all()
    else:
        items = query.all()

    case_ids_in_page = sorted({int(case.id) for (_, case) in items if getattr(case, "id", None) is not None})
    search_map: dict[int, dict[str, int]] = {}
    if case_ids_in_page:
        rows = (
            db.query(
                models.CaseHold.case_id,
                func.count(models.HoldSearch.id).label("total"),
                func.sum(sql_case((models.HoldSearch.status_search == "performed", 1), else_=0)).label("search_done"),
                func.sum(sql_case((models.HoldSearch.status_export == "performed", 1), else_=0)).label("export_done"),
                func.sum(sql_case((models.HoldSearch.status_delivery == "performed", 1), else_=0)).label("delivered"),
            )
            .join(models.CaseHold, models.HoldSearch.hold_id == models.CaseHold.id)
            .filter(models.CaseHold.case_id.in_(case_ids_in_page))
            .group_by(models.CaseHold.case_id)
            .all()
        )
        for row in rows:
            cid = int(getattr(row, "case_id", 0) or 0)
            if cid <= 0:
                continue
            search_map[cid] = {
                "total": int(getattr(row, "total", 0) or 0),
                "search_done": int(getattr(row, "search_done", 0) or 0),
                "export_done": int(getattr(row, "export_done", 0) or 0),
                "delivered": int(getattr(row, "delivered", 0) or 0),
            }

    results = []
    for cu, case in items:
        cid = int(getattr(case, "id", 0) or 0)
        counts = search_map.get(cid, {"total": 0, "search_done": 0, "export_done": 0, "delivered": 0})
        results.append({
            "custodian": {
                "id": cu.id,
                "name": cu.name,
                "email": cu.email,
                "holds": _custodian_hold_flags(cu),
                "named_holds": _custodian_named_holds(cu),
            },
            "case": {"id": case.id, "name": case.name},
            "searches": counts,
        })
    return results, total

@router.get("/reports/custodian")
def rpt_custodian(
    q: Optional[str] = Query(None),
    paged: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    q_norm = (q or "").strip().lower()
    case_ids = _visible_case_ids(db, actor)
    matches = []
    if q_norm:
        q_like = f"%{q_norm}%"
        cust_query = db.query(models.Custodian.id, models.Custodian.name, models.Custodian.email)
        cust_query = _filter_by_case_ids(cust_query, models.Custodian.case_id, case_ids)
        cust_query = cust_query.filter(
            or_(
                func.lower(models.Custodian.name).like(q_like),
                func.lower(models.Custodian.email).like(q_like),
            )
        )
        for cid, name, email in cust_query.order_by(models.Custodian.name.asc(), models.Custodian.id.asc()).limit(100).all():
            matches.append({"id": cid, "name": name, "email": email})

    items, total = _find_custodians(
        db,
        q_norm if q_norm else None,
        case_ids,
        page=page if paged else None,
        per_page=per_page if paged else None,
    )
    if paged:
        safe_page, safe_per_page = _normalize_paging(page, per_page)
        return {
            "matches": matches,
            "items": items,
            "total": int(total if total is not None else len(items)),
            "page": safe_page,
            "per_page": safe_per_page,
        }
    return {"matches": matches, "items": items}


@router.get("/reports/custodian/export")
def rpt_custodian_export(
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    actor = Depends(get_current_user),
):
    q_norm = (q or "").strip().lower()
    rows, _ = _find_custodians(db, q_norm if q_norm else None, _visible_case_ids(db, actor))
    # Flatten for CSV
    flat = []
    for r in rows:
        holds = r["custodian"].get("holds", {})

        def flag(key):
            return "yes" if holds.get(key) else "no"

        row = {
            "custodian": r["custodian"]["name"] or r["custodian"]["email"],
            "email": r["custodian"]["email"] or "",
            "case": r["case"]["name"],
            "searches": r["searches"]["total"],
            "search_performed": r["searches"]["search_done"],
            "export_performed": r["searches"]["export_done"],
            "delivered": r["searches"]["delivered"],
        }
        for key, _field, _label in configured_hold_catalog(enabled_only=True):
            row[f"hold_{key}"] = flag(key)
        flat.append(row)
    hold_headers = [f"hold_{key}" for key, _field, _label in configured_hold_catalog(enabled_only=True)]
    headers = [
        "custodian", "email", "case", "searches", "search_performed", "export_performed", "delivered",
        *hold_headers,
    ]
    return _csv_response(flat, headers, "custodian_report.csv")

