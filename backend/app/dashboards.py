from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import func, or_, and_, literal
from sqlalchemy.orm import Session

from . import models
from . import ticket_provider
from .audit import log_event
from .auth import current_user as get_current_user
from .database import get_db
from .permissions import (
    get_requestor_allowed_emails,
    get_tech_visible_case_ids,
    filter_ticket_entries_for_user,
    is_requestor,
    is_tester,
    is_tech,
)
from .safe_log import debug_suppressed as _debug_suppressed

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])

_CONFIG_VERSION = 1
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_DRILLDOWN_ITEMS = 1000


def _ntp_dashboard() -> dict:
    return {
        "id": "ntp",
        "name": "NTPs",
        "widgets": [
            {"id": "ntp-status", "type": "ntp_status", "title": "NTP Status", "config": {"open_only": True}},
            {"id": "ntp-reminders", "type": "ntp_reminders", "title": "NTP Reminders", "config": {"open_only": True, "days_ahead": 7}},
        ],
    }


def _default_config() -> dict:
    return {
        "version": _CONFIG_VERSION,
        "active_dashboard_id": "default",
        "dashboards": [
            {
                "id": "default",
                "name": "My Dashboard",
                "widgets": [
                    {"id": "cases", "type": "case_counts", "title": "Cases", "config": {}},
                    {"id": "consents", "type": "consent_status", "title": "Consents", "config": {"open_only": True}},
                    {"id": "searches", "type": "search_status", "title": "Searches", "config": {"open_only": True}},
                    {"id": "holds", "type": "hold_status", "title": "Holds", "config": {"open_only": True}},
                    {"id": "tickets", "type": "open_tickets", "title": "Open Tickets", "config": {"open_only": True}},
                    {"id": "requests", "type": "requests_sla", "title": "Requests", "config": {}},
                ],
            },
            _ntp_dashboard(),
        ],
    }


def _coerce_config(raw: Any) -> dict:
    if raw is None:
        return _default_config()
    if isinstance(raw, dict):
        cfg = raw
    elif isinstance(raw, (bytes, str)):
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}
    else:
        cfg = {}

    if not isinstance(cfg, dict):
        return _default_config()
    if int(cfg.get("version") or 0) != _CONFIG_VERSION:
        # best-effort migration hook for future versions
        return _default_config()
    if not isinstance(cfg.get("dashboards"), list) or not cfg["dashboards"]:
        return _default_config()
    return _ensure_ntp_dashboard(cfg)


def _ensure_ntp_dashboard(cfg: dict) -> dict:
    dashboards = cfg.get("dashboards")
    if not isinstance(dashboards, list):
        return cfg
    for dash in dashboards:
        if isinstance(dash, dict) and dash.get("id") == "ntp":
            return cfg
    updated = list(dashboards)
    updated.append(_ntp_dashboard())
    return {**cfg, "dashboards": updated}


def _validate_and_dump_config(cfg: Any) -> str:
    if not isinstance(cfg, dict):
        raise HTTPException(status_code=422, detail="dashboard config must be an object")
    if int(cfg.get("version") or 0) != _CONFIG_VERSION:
        raise HTTPException(status_code=422, detail="unsupported dashboard config version")
    dashboards = cfg.get("dashboards")
    if not isinstance(dashboards, list) or not dashboards:
        raise HTTPException(status_code=422, detail="dashboards must be a non-empty list")
    for dash in dashboards:
        if not isinstance(dash, dict):
            raise HTTPException(status_code=422, detail="dashboard entries must be objects")
        if not (dash.get("id") and dash.get("name")):
            raise HTTPException(status_code=422, detail="dashboard requires id and name")
        widgets = dash.get("widgets") or []
        if not isinstance(widgets, list):
            raise HTTPException(status_code=422, detail="dashboard widgets must be a list")
        for w in widgets:
            if not isinstance(w, dict):
                raise HTTPException(status_code=422, detail="widgets must be objects")
            if not (w.get("id") and w.get("type")):
                raise HTTPException(status_code=422, detail="widget requires id and type")
            if "config" in w and not isinstance(w.get("config"), dict):
                raise HTTPException(status_code=422, detail="widget config must be an object")

    dumped = json.dumps(cfg, ensure_ascii=False)
    if len(dumped.encode("utf-8")) > _MAX_CONFIG_BYTES:
        raise HTTPException(status_code=413, detail="dashboard config too large")
    return dumped


from .dashboard_access import _filter_case_ids, _visible_case_ids


@router.get("")
def get_dashboard_config(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cfg = _coerce_config(getattr(user, "dashboards_raw", None))
    return cfg


@router.put("")
def set_dashboard_config(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    dumped = _validate_and_dump_config(payload)
    user.dashboards_raw = dumped
    db.add(user)
    db.commit()
    try:
        log_event(
            db,
            action="dashboard_update",
            actor_id=user.id,
            target_type="user",
            target_id=user.id,
            details={
                "dashboard_count": len(payload.get("dashboards") or []),
                "active_dashboard_id": payload.get("active_dashboard_id"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in dashboards.py:198", exc)
    return {"ok": True}


from .dashboard_resolvers import _RESOLVERS


@router.post("/resolve")
def resolve_widgets(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    widgets = payload.get("widgets") or []
    if not isinstance(widgets, list):
        raise HTTPException(status_code=422, detail="widgets must be a list")
    out: Dict[str, Any] = {}
    for item in widgets:
        if not isinstance(item, dict):
            continue
        wid = item.get("id") or str(uuid.uuid4())
        wtype = (item.get("type") or "").strip()
        cfg = item.get("config") if isinstance(item.get("config"), dict) else {}
        resolver = _RESOLVERS.get(wtype)
        if not resolver:
            out[str(wid)] = {"error": "unknown_widget"}
            continue
        try:
            out[str(wid)] = resolver(db, actor, config=cfg)
        except Exception as exc:
            out[str(wid)] = {"error": str(exc)}
    return {"results": out}


@router.post("/drilldown")
def drilldown(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    kind = (payload.get("kind") or "").strip().lower()
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    limit = payload.get("limit")
    try:
        limit_n = int(limit) if limit is not None else _MAX_DRILLDOWN_ITEMS
    except Exception:
        limit_n = _MAX_DRILLDOWN_ITEMS
    limit_n = max(1, min(_MAX_DRILLDOWN_ITEMS, limit_n))

    case_ids = _visible_case_ids(db, actor)

    if kind == "cases_list":
        closed_raw = config.get("closed")
        closed: Optional[bool] = None
        if closed_raw in (True, False):
            closed = bool(closed_raw)
        elif isinstance(closed_raw, str):
            s = closed_raw.strip().lower()
            if s in {"open", "false", "0"}:
                closed = False
            elif s in {"closed", "true", "1"}:
                closed = True
        created_last_days = config.get("created_last_days")
        try:
            days = int(created_last_days) if created_last_days is not None else None
        except Exception:
            days = None
        if days is not None:
            days = max(1, min(365, days))
        since = datetime.now(timezone.utc) - timedelta(days=days) if days else None

        q = (
            db.query(models.Case, models.User)
            .outerjoin(models.User, models.User.id == models.Case.analyst_id)
        )
        if closed is not None:
            q = q.filter(models.Case.closed.is_(closed))
        if since is not None:
            q = q.filter(models.Case.created_at >= since)
        q = _filter_case_ids(q, models.Case.id, case_ids)
        q = q.order_by(models.Case.created_at.desc().nullslast(), models.Case.id.desc())
        q = q.limit(limit_n)
        rows = q.all()
        items = []
        for case, analyst in rows:
            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "created_at": str(getattr(case, "created_at", "") or ""),
                    "legal_case_name": getattr(case, "legal_case_name", None),
                    "requestor": getattr(case, "requestor", None),
                    "analyst_id": getattr(analyst, "id", None) if analyst else None,
                    "analyst_username": getattr(analyst, "username", None) if analyst else None,
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n}

    if kind == "consent_pending":
        open_only = bool(config.get("open_only", True))
        status_filter = (config.get("status_filter") or "").strip().lower()
        allowed = {"sent", "delivered"}
        statuses = ("sent", "delivered")
        if status_filter in allowed:
            statuses = (status_filter,)
        status_col = func.lower(func.coalesce(models.CaseConsent.status, ""))
        q = (
            db.query(models.CaseConsent, models.Case)
            .join(models.Case, models.Case.id == models.CaseConsent.case_id)
            .filter(models.CaseConsent.case_id.isnot(None))
            .filter(status_col.in_(statuses))
        )
        if open_only:
            q = q.filter(models.Case.closed.is_(False))
        q = _filter_case_ids(q, models.Case.id, case_ids)
        q = q.order_by(models.Case.id.asc(), models.CaseConsent.sent_at.asc().nulls_last(), models.CaseConsent.id.asc())
        q = q.limit(limit_n)
        rows = q.all()
        items = []
        for consent, case in rows:
            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "consent_id": getattr(consent, "id", None),
                    "status": getattr(consent, "status", None),
                    "sent_at": str(getattr(consent, "sent_at", "") or ""),
                    "updated_at": str(getattr(consent, "updated_at", "") or ""),
                    "envelope_id": getattr(consent, "envelope_id", None),
                    "custodian_id": getattr(consent, "custodian_id", None),
                    "custodian_name": getattr(consent, "custodian_name", None),
                    "custodian_email": getattr(consent, "custodian_email", None),
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n}

    if kind == "ntp_status_list":
        open_only = bool(config.get("open_only", True))
        status_filter = (config.get("status_filter") or "").strip().lower()
        allowed = {"not sent", "sent", "acknowledged", "na"}
        if status_filter and status_filter not in allowed:
            raise HTTPException(status_code=422, detail="invalid ntp status")
        status_col = func.lower(func.coalesce(models.Custodian.ntp_status, "not sent"))

        q = db.query(models.Custodian, models.Case).join(models.Case, models.Case.id == models.Custodian.case_id)
        if open_only:
            q = q.filter(models.Case.closed.is_(False))
        q = _filter_case_ids(q, models.Case.id, case_ids)
        if status_filter:
            q = q.filter(status_col == status_filter)
        q = q.order_by(models.Case.id.asc(), models.Custodian.id.asc())
        q = q.limit(limit_n)
        rows = q.all()
        items = []
        for cust, case in rows:
            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "custodian_id": getattr(cust, "id", None),
                    "custodian_name": getattr(cust, "name", None),
                    "custodian_email": getattr(cust, "email", None),
                    "ntp_status": getattr(cust, "ntp_status", None),
                    "ntp_sent_at": str(getattr(cust, "ntp_sent_at", "") or ""),
                    "ntp_acknowledged_at": str(getattr(cust, "ntp_acknowledged_at", "") or ""),
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n}

    if kind == "ntp_reminders_list":
        open_only = bool(config.get("open_only", True))
        mode = (config.get("mode") or "active").strip().lower()
        status_filter = (config.get("status_filter") or "").strip().lower()
        try:
            days_ahead = int(config.get("days_ahead") or 7)
        except Exception:
            days_ahead = 7
        days_ahead = max(1, min(90, days_ahead))
        now = datetime.now(timezone.utc)

        q = (
            db.query(models.NTPReminder, models.Case, models.Custodian, models.NTPTemplate)
            .join(models.Case, models.Case.id == models.NTPReminder.case_id)
            .outerjoin(models.Custodian, models.Custodian.id == models.NTPReminder.custodian_id)
            .outerjoin(models.NTPTemplate, models.NTPTemplate.id == models.NTPReminder.template_id)
        )
        if open_only:
            q = q.filter(models.Case.closed.is_(False))
        q = _filter_case_ids(q, models.Case.id, case_ids)

        if status_filter:
            if status_filter not in {"active", "completed", "cancelled"}:
                raise HTTPException(status_code=422, detail="invalid reminder status")
            q = q.filter(func.lower(models.NTPReminder.status) == status_filter)

        if mode == "active":
            q = q.filter(models.NTPReminder.status == "active")
        elif mode == "due_now":
            q = q.filter(models.NTPReminder.status == "active")
            q = q.filter(models.NTPReminder.next_send_at <= now)
        elif mode == "due_soon":
            q = q.filter(models.NTPReminder.status == "active")
            q = q.filter(models.NTPReminder.next_send_at <= (now + timedelta(days=days_ahead)))
        elif mode == "all":
            pass
        elif mode in {"completed", "cancelled"}:
            q = q.filter(models.NTPReminder.status == mode)
        else:
            raise HTTPException(status_code=422, detail="invalid mode")

        q = q.order_by(models.NTPReminder.next_send_at.asc().nulls_last(), models.NTPReminder.id.asc())
        q = q.limit(limit_n)
        rows = q.all()
        items = []
        for reminder, case, custodian, template in rows:
            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "custodian_id": getattr(custodian, "id", None) if custodian else None,
                    "custodian_name": getattr(custodian, "name", None) if custodian else None,
                    "custodian_email": getattr(custodian, "email", None) if custodian else None,
                    "reminder_id": getattr(reminder, "id", None),
                    "template_id": getattr(reminder, "template_id", None),
                    "template_name": getattr(template, "name", None) if template else None,
                    "interval_days": getattr(reminder, "interval_days", None),
                    "next_send_at": str(getattr(reminder, "next_send_at", "") or ""),
                    "stop_after": str(getattr(reminder, "stop_after", "") or ""),
                    "last_sent_at": str(getattr(reminder, "last_sent_at", "") or ""),
                    "send_count": getattr(reminder, "send_count", None),
                    "reminder_status": getattr(reminder, "status", None),
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n, "days_ahead": days_ahead}

    if kind == "holds_list":
        open_only = bool(config.get("open_only", True))
        mode = (config.get("mode") or "pending").strip().lower()
        hold_type = (config.get("hold_type") or "").strip().lower()
        keys = ["email", "onedrive", "box", "slack", "rubrik_restore"]
        if hold_type and hold_type not in keys:
            raise HTTPException(status_code=422, detail="invalid hold_type")
        pending = mode != "active"

        q = db.query(models.Custodian, models.Case).join(models.Case, models.Case.id == models.Custodian.case_id)
        if open_only:
            q = q.filter(models.Case.closed.is_(False))
        q = _filter_case_ids(q, models.Case.id, case_ids)

        def _col(key: str):
            if pending:
                return getattr(models.Custodian, f"holds_{key}_pending")
            return getattr(models.Custodian, f"holds_{key}")

        if hold_type:
            q = q.filter(_col(hold_type).is_(True))
        else:
            q = q.filter(or_(*[_col(k).is_(True) for k in keys]))

        q = q.order_by(models.Case.id.asc(), models.Custodian.id.asc())
        q = q.limit(limit_n)
        rows = q.all()
        items = []
        for cust, case in rows:
            active_map = {k: bool(getattr(cust, f"holds_{k}", False)) for k in keys}
            pending_map = {k: bool(getattr(cust, f"holds_{k}_pending", False)) for k in keys}
            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "custodian_id": getattr(cust, "id", None),
                    "custodian_name": getattr(cust, "name", None),
                    "custodian_email": getattr(cust, "email", None),
                    "holds_active": active_map,
                    "holds_pending": pending_map,
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n}

    if kind == "searches_list":
        open_only = bool(config.get("open_only", True))
        metric = (config.get("metric") or "all").strip().lower()
        allowed = {
            "all",
            "search_performed",
            "search_not_performed",
            "export_performed",
            "export_not_performed",
            "delivery_performed",
            "delivery_not_required",
            "delivery_pending",
            "export_without_consent",
        }
        if metric not in allowed:
            raise HTTPException(status_code=422, detail="invalid search metric")

        search_col = func.lower(func.coalesce(models.Search.status_search, "not performed"))
        export_col = func.lower(func.coalesce(models.Search.status_export, "not performed"))
        delivery_col = func.lower(func.coalesce(models.Search.status_delivery, "not performed"))

        q = db.query(models.Search, models.Case).join(models.Case, models.Case.id == models.Search.case_id)
        if open_only:
            q = q.filter(models.Case.closed.is_(False))
        q = _filter_case_ids(q, models.Case.id, case_ids)

        if metric == "search_performed":
            q = q.filter(search_col == "performed")
        elif metric == "search_not_performed":
            q = q.filter(search_col != "performed")
        elif metric == "export_performed":
            q = q.filter(export_col == "performed")
        elif metric == "export_not_performed":
            q = q.filter(export_col != "performed")
        elif metric == "delivery_performed":
            q = q.filter(delivery_col == "performed")
        elif metric == "delivery_not_required":
            q = q.filter(delivery_col == "not required")
        elif metric == "delivery_pending":
            q = q.filter(export_col == "performed")
            q = q.filter(delivery_col.notin_(("performed", "not required")))
        elif metric == "export_without_consent":
            q = q.filter(models.Search.export_without_consent.is_(True))

        q = q.order_by(models.Case.id.asc(), models.Search.id.asc())
        q = q.limit(limit_n)
        rows = q.all()

        items = []
        for search, case in rows:
            custodian_count = 0
            try:
                raw_ids = json.loads(getattr(search, "custodian_ids", "[]") or "[]")
                if isinstance(raw_ids, list):
                    custodian_count = len([x for x in raw_ids if str(x or "").strip()])
            except Exception:
                custodian_count = 0

            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "search_id": getattr(search, "id", None),
                    "search_name": getattr(search, "name", None),
                    "status_search": getattr(search, "status_search", None),
                    "status_export": getattr(search, "status_export", None),
                    "status_delivery": getattr(search, "status_delivery", None),
                    "export_without_consent": bool(getattr(search, "export_without_consent", False)),
                    "custodian_count": custodian_count,
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n}
    if kind == "requests_list":
        status = (config.get("status") or "pending").strip().lower()
        if status != "pending":
            raise HTTPException(status_code=422, detail="only pending requests supported")
        age_bucket = (config.get("age_bucket") or "").strip().lower()
        request_type = (config.get("request_type") or "").strip().lower()
        now = datetime.now(timezone.utc)

        q = db.query(models.CaseRequest).filter(models.CaseRequest.status == "pending")
        if is_requestor(actor):
            q = q.filter(models.CaseRequest.requestor_id == actor.id)
        if case_ids is not None:
            if is_requestor(actor):
                # allow case_id NULL only for self-submitted requests
                q = q.filter(
                    or_(
                        models.CaseRequest.case_id.in_(list(case_ids)),
                        and_(models.CaseRequest.case_id.is_(None), models.CaseRequest.requestor_id == actor.id),
                    )
                )
            else:
                q = q.filter(models.CaseRequest.case_id.in_(list(case_ids)))
        if request_type:
            q = q.filter(func.lower(models.CaseRequest.request_type) == request_type)

        if age_bucket:
            if age_bucket == "lt_24h":
                q = q.filter(models.CaseRequest.created_at >= (now - timedelta(hours=24)))
            elif age_bucket == "d1_3":
                q = q.filter(models.CaseRequest.created_at < (now - timedelta(hours=24)))
                q = q.filter(models.CaseRequest.created_at >= (now - timedelta(days=3)))
            elif age_bucket == "gt_3d":
                q = q.filter(models.CaseRequest.created_at < (now - timedelta(days=3)))
            else:
                raise HTTPException(status_code=422, detail="invalid age_bucket")

        q = q.order_by(models.CaseRequest.created_at.asc().nullsfirst(), models.CaseRequest.id.asc())
        q = q.limit(limit_n)
        rows = q.all()
        items = []
        for row in rows:
            created = getattr(row, "created_at", None)
            created_str = str(created or "")
            items.append(
                {
                    "request_id": getattr(row, "id", None),
                    "request_type": getattr(row, "request_type", None),
                    "case_id": getattr(row, "case_id", None),
                    "case_name": getattr(row, "case_name", None),
                    "requestor_email": getattr(row, "requestor_email", None),
                    "created_at": created_str,
                }
            )
        return {"items": items, "count": len(items), "limit": limit_n}

    if kind == "tickets_list":
        open_only = bool(config.get("open_only", True))
        refresh_live = bool(config.get("refresh_live", True))
        category_filter = (config.get("category") or "").strip().lower()
        status_filter = (config.get("status") or "").strip().lower()

        q = db.query(models.Case)
        if open_only:
            q = q.filter(models.Case.closed.is_(False))
        q = _filter_case_ids(q, models.Case.id, case_ids)
        cases = q.all()

        raw_rows: list[dict] = []
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
                category = (entry.get("category") or "").strip().lower()
                if category_filter and category != category_filter:
                    continue
                tickets.append(ticket)
                raw_rows.append({"case": case, "entry": entry, "ticket": ticket})

        status_lookup: dict[str, dict] = {}
        if refresh_live and tickets:
            unique = []
            seen = set()
            for t in tickets:
                key = t.strip().upper()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(t)
                if len(unique) >= 500:
                    break
            try:
                status_lookup = ticket_provider.get_ticket_statuses(unique)
            except Exception:
                status_lookup = {}

        items = []
        for row in raw_rows:
            case = row["case"]
            entry = row["entry"]
            ticket = row["ticket"]
            info = status_lookup.get(ticket) or status_lookup.get(ticket.strip().upper()) or {}
            status = info.get("status") or entry.get("status") or None
            is_closed = bool(info.get("is_closed")) if "is_closed" in info else ticket_provider.is_closed_status(status)
            if is_closed:
                continue
            status_key = (str(status or "")).strip().lower() or "unknown"
            if status_filter and status_key != status_filter:
                continue
            items.append(
                {
                    "case_id": getattr(case, "id", None),
                    "case_name": getattr(case, "name", None),
                    "case_closed": bool(getattr(case, "closed", False)),
                    "entry_id": str(entry.get("id") or ""),
                    "category": (entry.get("category") or "").strip(),
                    "ticket": ticket,
                    "status": status,
                    "is_closed": bool(is_closed),
                    "link": info.get("link") or entry.get("link") or entry.get("url"),
                    "assigned_to_display": info.get("assigned_to_display") or entry.get("assigned_to_display"),
                    "assigned_to_email": info.get("assigned_to_email") or entry.get("assigned_to_email"),
                    "custodian_name": entry.get("custodian_name"),
                    "custodian_email": entry.get("custodian_email"),
                }
            )
            if len(items) >= limit_n:
                break
        return {"items": items, "count": len(items), "limit": limit_n}

    raise HTTPException(status_code=422, detail="unknown drilldown kind")
