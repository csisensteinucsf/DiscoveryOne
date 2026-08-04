# backend/app/logs.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, List, Tuple
import json

from .database import get_db
from .auth import current_user as get_current_user
from .permissions import is_sys_admin, is_requestor, get_requestor_allowed_emails
from .audit import sync_audit_file_to_db

router = APIRouter(prefix="/api/logs", tags=["logs"])

_REQUESTOR_FETCH_SQL = """
SELECT ev.id, ev.created_at, ev.actor_id, ev.action, ev.target_type, ev.target_id, ev.details,
       ev.request_ip, ev.user_agent, u.username
  FROM audit_events ev
  LEFT JOIN users u ON u.id = ev.actor_id
  LEFT JOIN custodians cu ON (ev.target_type = 'custodian' AND cu.id = ev.target_id)
  LEFT JOIN searches se ON (ev.target_type = 'search' AND se.id = ev.target_id)
  LEFT JOIN case_requests rq ON (ev.target_type = 'case_request' AND rq.id = ev.target_id)
 __WHERE_FINAL__
 ORDER BY ev.created_at DESC, ev.id DESC
 LIMIT :limit OFFSET :offset
"""

_ADMIN_FETCH_SQL = """
SELECT ev.id, ev.created_at, ev.actor_id, ev.action, ev.target_type, ev.target_id, ev.details,
       ev.request_ip, ev.user_agent, u.username
  FROM audit_events ev
  LEFT JOIN users u ON u.id = ev.actor_id
 __WHERE__
 ORDER BY ev.created_at DESC, ev.id DESC
 LIMIT :limit OFFSET :offset
"""

_REQUESTOR_COUNT_SQL = """
SELECT COUNT(*)
  FROM audit_events ev
  LEFT JOIN users u ON u.id = ev.actor_id
  LEFT JOIN custodians cu ON (ev.target_type = 'custodian' AND cu.id = ev.target_id)
  LEFT JOIN searches se ON (ev.target_type = 'search' AND se.id = ev.target_id)
  LEFT JOIN case_requests rq ON (ev.target_type = 'case_request' AND rq.id = ev.target_id)
 __WHERE_FINAL__
"""

_ADMIN_COUNT_SQL = "SELECT COUNT(*) FROM audit_events ev LEFT JOIN users u ON u.id = ev.actor_id __WHERE__"

_LOG_CATEGORY_ACTION_PATTERNS: Dict[str, List[str]] = {
    "ntp": ["ntp_%", "system_ntp_%"],
    "email": ["%email_sent%", "%_email_%", "email_test"],
    "delete_remove": ["%delete%", "%remove%"],
    "hold": ["%hold%"],
    "login_auth": ["login%", "auth_login_%", "password_reset_%", "password_help_request"],
    "case": ["case_%"],
    "custodian": ["custodian_%"],
    "search": ["search_%"],
    "consent": ["consent_%", "case_consent_%"],
    "system": [
        "system_%",
        "backup_%",
        "logo_%",
        "dashboard_%",
        "tool_%",
        "tls_%",
        "log_ship_%",
        "deprecated_%",
        "registration_%",
        "user_%",
    ],
}


def _csv_safe_cell(value: Any) -> str:
    text_value = "" if value is None else str(value)
    if text_value and text_value[0] in ("=", "+", "-", "@"):
        return "'" + text_value
    return text_value


def _parse_details(val):
    if isinstance(val, (dict, list)) or val is None:
        return val
    s = str(val).strip()
    if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
        try:
            return json.loads(s)
        except Exception:
            return s
    return s


def _category_clause(category: str | None) -> Tuple[str, Dict[str, Any]]:
    norm = (category or "").strip().lower()
    if not norm:
        return "", {}
    patterns = _LOG_CATEGORY_ACTION_PATTERNS.get(norm) or []
    if not patterns:
        return "", {}
    clauses: List[str] = []
    params: Dict[str, Any] = {}
    for idx, pattern in enumerate(patterns):
        key = f"category_action_{idx}"
        clauses.append(f"ev.action ILIKE :{key}")
        params[key] = pattern
    return "(" + " OR ".join(clauses) + ")", params


def _build_filters(
    *,
    action: str | None,
    actor_id: int | None,
    ip: str | None,
    contains: str | None,
    category: str | None,
) -> Tuple[str, Dict[str, Any]]:
    clauses = []
    params: Dict[str, Any] = {}
    category_sql, category_params = _category_clause(category)
    if category_sql:
        clauses.append(category_sql)
        params.update(category_params)
    if action:
        clauses.append("ev.action ILIKE :action")
        params["action"] = f"%{action}%"
    if actor_id:
        clauses.append("ev.actor_id = :actor_id")
        params["actor_id"] = actor_id
    if ip:
        clauses.append("ev.request_ip ILIKE :ip")
        params["ip"] = f"%{ip}%"
    if contains:
        clauses.append("(CAST(ev.details AS TEXT) ILIKE :contains OR COALESCE(u.username,'') ILIKE :contains)")
        params["contains"] = f"%{contains}%"
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _fetch(
    db: Session,
    limit: int,
    offset: int,
    *,
    scope: dict,
    action: str | None = None,
    actor_id: int | None = None,
    ip: str | None = None,
    contains: str | None = None,
    category: str | None = None,
) -> List[Dict[str, Any]]:
    mode = (scope or {}).get("mode")
    if mode == "requestor":
        case_ids = [int(x) for x in (scope.get("case_ids") or []) if int(x) > 0]
        if not case_ids:
            return []
        where, params = _build_filters(action=action, actor_id=actor_id, ip=ip, contains=contains, category=category)
        where2 = where.replace("WHERE ", "") if where.startswith("WHERE ") else where
        case_scope = """
        COALESCE(
            CASE WHEN ev.target_type = 'case' THEN ev.target_id END,
            cu.case_id,
            se.case_id,
            rq.case_id,
            CASE WHEN (ev.details->>'case_id') ~ '^\\d+$' THEN (ev.details->>'case_id')::int END
        ) = ANY(:case_ids)
        """
        clauses = [case_scope]
        if where2.strip():
            clauses.append(where2.strip())
        where_final = "WHERE " + " AND ".join(clauses)
        sql = text(_REQUESTOR_FETCH_SQL.replace("__WHERE_FINAL__", where_final))
        params.update({"limit": limit, "offset": offset, "case_ids": case_ids})
        rows = db.execute(sql, params).mappings().all()
    else:
        where, params = _build_filters(action=action, actor_id=actor_id, ip=ip, contains=contains, category=category)
        sql = text(_ADMIN_FETCH_SQL.replace("__WHERE__", where))
        params.update({"limit": limit, "offset": offset})
        rows = db.execute(sql, params).mappings().all()
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["details"] = _parse_details(d.get("details"))
        out.append(d)
    return out


def _count(
    db: Session,
    *,
    scope: dict,
    action: str | None = None,
    actor_id: int | None = None,
    ip: str | None = None,
    contains: str | None = None,
    category: str | None = None,
) -> int:
    mode = (scope or {}).get("mode")
    if mode == "requestor":
        case_ids = [int(x) for x in (scope.get("case_ids") or []) if int(x) > 0]
        if not case_ids:
            return 0
        where, params = _build_filters(action=action, actor_id=actor_id, ip=ip, contains=contains, category=category)
        where2 = where.replace("WHERE ", "") if where.startswith("WHERE ") else where
        case_scope = """
        COALESCE(
            CASE WHEN ev.target_type = 'case' THEN ev.target_id END,
            cu.case_id,
            se.case_id,
            rq.case_id,
            CASE WHEN (ev.details->>'case_id') ~ '^\\d+$' THEN (ev.details->>'case_id')::int END
        ) = ANY(:case_ids)
        """
        clauses = [case_scope]
        if where2.strip():
            clauses.append(where2.strip())
        where_final = "WHERE " + " AND ".join(clauses)
        sql = text(_REQUESTOR_COUNT_SQL.replace("__WHERE_FINAL__", where_final))
        params.update({"case_ids": case_ids})
        return int(db.execute(sql, params).scalar() or 0)
    where, params = _build_filters(action=action, actor_id=actor_id, ip=ip, contains=contains, category=category)
    sql = text(_ADMIN_COUNT_SQL.replace("__WHERE__", where))
    return int(db.execute(sql, params).scalar() or 0)


def _require_admin(user):
    if not user or not is_sys_admin(user):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def _direct_requestor_emails(user) -> List[str]:
    out: List[str] = []
    for value in (getattr(user, "email", None), getattr(user, "username", None)):
        text_value = str(value or "").strip().lower()
        if text_value and "@" in text_value and " " not in text_value and text_value not in out:
            out.append(text_value)
    return out


def _requestor_visible_case_ids(db: Session, user) -> List[int]:
    allowed = list(get_requestor_allowed_emails(user, db) or [])
    direct_emails = _direct_requestor_emails(user)
    if not allowed and not direct_emails and getattr(user, "id", None) is None:
        return []
    # Private cases must not inherit group/delegated requestor visibility.
    sql = text(
        """
        SELECT DISTINCT c.id AS case_id
          FROM cases c
          LEFT JOIN case_requestors cr ON cr.case_id = c.id
         WHERE (
                (
                    c.is_private IS TRUE
                    AND (
                           (c.requestor IS NOT NULL AND lower(trim(c.requestor)) = ANY(:direct_emails))
                        OR (cr.email IS NOT NULL AND lower(trim(cr.email)) = ANY(:direct_emails))
                        OR (cr.user_id IS NOT NULL AND cr.user_id = :user_id)
                    )
                )
             OR (
                    c.is_private IS NOT TRUE
                    AND (
                           (c.requestor IS NOT NULL AND lower(trim(c.requestor)) = ANY(:allowed_emails))
                        OR (cr.email IS NOT NULL AND lower(trim(cr.email)) = ANY(:allowed_emails))
                        OR (cr.user_id IS NOT NULL AND cr.user_id = :user_id)
                    )
                )
         )
        """
    )
    params = {
        "allowed_emails": [str(x).strip().lower() for x in allowed if str(x).strip()],
        "direct_emails": direct_emails,
        "user_id": int(getattr(user, "id", 0) or 0),
    }
    rows = db.execute(sql, params).mappings().all()
    out: List[int] = []
    for row in rows:
        try:
            cid = int(row.get("case_id") or 0)
        except Exception:
            cid = 0
        if cid and cid not in out:
            out.append(cid)
    return out


def _log_scope(db: Session, user) -> dict:
    """
    Returns a scope descriptor used to enforce access.
    Sys admins: full access.
    Requestors use the dedicated, redacted NTP history endpoints. The global
    audit stream contains internal workflow, identity, network, and ticket data.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if is_sys_admin(user):
        return {"mode": "admin"}
    raise HTTPException(status_code=403, detail="Access denied")


@router.get("")
def get_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    action: str | None = Query(None, description="Filter actions (ILIKE match)"),
    category: str | None = Query(None, description="Filter by log category"),
    actor_id: int | None = Query(None, description="Exact actor_id"),
    ip: str | None = Query(None, description="Match request_ip (ILIKE)"),
    contains: str | None = Query(None, description="Search username or details (ILIKE)"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    scope = _log_scope(db, user)
    total = _count(db, scope=scope, action=action, actor_id=actor_id, ip=ip, contains=contains, category=category)
    offset = (page - 1) * per_page
    items = _fetch(db, per_page, offset, scope=scope, action=action, actor_id=actor_id, ip=ip, contains=contains, category=category)
    return {"items": items, "total": total, "page": page, "per_page": per_page}


@router.post("/sync_audit")
def sync_audit_logs(
    max_files: int | None = Query(None, ge=1, le=500),
    max_lines: int | None = Query(None, ge=1, le=5000000),
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
):
    _require_admin(user)
    return sync_audit_file_to_db(db, max_files=max_files, max_lines=max_lines)

