from __future__ import annotations

import json
import logging
import re
import threading
import time
from difflib import SequenceMatcher
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from .app_branding import app_display_name, branded_subject
from .integration_settings import config_value
from .safe_log import debug_suppressed as _debug_suppressed
from .hold_workflows import sync_search_hold_statuses

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from . import models
from .audit import log_event
from .auth import current_user as get_current_user
from .database import SessionLocal, get_db
from .emailer import mail_provider_ready, send_email
from .notifications import _app_base_url
from .permissions import ensure_case_editable, ensure_case_visible
from .purview import (
    PurviewAPIError,
    PurviewConfigError,
    find_purview_case_by_display_name,
    get_purview_case_operation,
    list_purview_case_operations,
    purview_enabled,
)

router = APIRouter(prefix="/api/cases", tags=["purview_exports"])
logger = logging.getLogger(__name__)

NO_EMAIL_PLACEHOLDER = "noemail"
UNMATCHED_EMAIL_PLACEHOLDER = "unmatched"

def _config_bool(value: str | None, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _config_int(value: str | None, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return default


def purview_export_poll_enabled() -> bool:
    return _config_bool(config_value("purview", "export_poll_enabled", "PURVIEW_EXPORT_POLL_ENABLED", "1"), True)


def purview_export_poll_hours() -> str:
    return config_value("purview", "export_poll_hours", "PURVIEW_EXPORT_POLL_HOURS", "7,18")


def purview_export_poll_minute() -> int:
    return min(59, max(0, _config_int(config_value("purview", "export_poll_minute", "PURVIEW_EXPORT_POLL_MINUTE", "0"), 0)))


def purview_export_poll_timezone() -> str:
    return config_value("purview", "export_poll_timezone", "PURVIEW_EXPORT_POLL_TIMEZONE", "")


def purview_export_poll_requestor_groups() -> str:
    return config_value("purview", "export_poll_requestor_groups", "PURVIEW_EXPORT_POLL_REQUESTOR_GROUPS", "pra")


_EXPORT_SCHEDULER_STARTED = False


def _parse_poll_hours(raw: str) -> list[int]:
    values: list[int] = []
    for part in (raw or "").replace(";", ",").split(","):
        token = (part or "").strip()
        if not token:
            continue
        try:
            hour = int(token)
        except ValueError:
            continue
        if 0 <= hour <= 23 and hour not in values:
            values.append(hour)
    if not values:
        values = [7, 18]
    return sorted(values)

def _parse_group_values(raw: str) -> set[str]:
    values: set[str] = set()
    for part in (raw or "").replace(";", ",").split(","):
        token = (part or "").strip().lower()
        if token:
            values.add(token)
    return values


def _scheduler_timezone():
    configured_timezone = purview_export_poll_timezone()
    if configured_timezone and ZoneInfo is not None:
        try:
            return ZoneInfo(configured_timezone)
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview_exports.py:87", exc)
    try:
        tz = datetime.now().astimezone().tzinfo
        if tz is not None:
            return tz
    except Exception as exc:
        _debug_suppressed("suppressed exception in purview_exports.py:93", exc)
    return timezone.utc


def _next_poll_run(now_utc: datetime) -> datetime:
    tzinfo = _scheduler_timezone()
    local_now = now_utc.astimezone(tzinfo)
    minute = purview_export_poll_minute()
    candidates: list[datetime] = []
    for hour in _parse_poll_hours(purview_export_poll_hours()):
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate = candidate + timedelta(days=1)
        candidates.append(candidate)
    if not candidates:
        fallback = local_now + timedelta(hours=12)
        return fallback.astimezone(timezone.utc)
    return min(candidates).astimezone(timezone.utc)


MATCH_NAME_SIMILARITY_THRESHOLD = 0.88
_NAME_ALPHA_STOP_WORDS = {"search", "searches", "export", "exports"}


def _normalize_export_name(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    # Normalize inline operation/index patterns: Export1 -> Export 1, Search2 -> Search 2
    text = re.sub(r"\b(export(?:s)?|search(?:es)?)(?=\d)", r"\1 ", text)
    tokens = [
        token
        for token in re.sub(r"[^a-z0-9]+", " ", text).split()
        if token not in {"export", "exports", "search", "searches"}
    ]
    if not tokens:
        return ""
    deduped: list[str] = []
    for token in tokens:
        if deduped and deduped[-1] == token:
            continue
        deduped.append(token)
    return " ".join(deduped)

def _name_match_parts(value: str) -> dict[str, Any]:
    normalized = _normalize_export_name(value)
    tokens = [token for token in normalized.split(" ") if token]
    numbers = [token for token in tokens if token.isdigit()]
    alpha_tokens = [
        token
        for token in tokens
        if not token.isdigit() and token not in _NAME_ALPHA_STOP_WORDS
    ]
    year = next((token for token in numbers if len(token) == 4), None)
    index = numbers[-1] if numbers else None
    return {
        "normalized": normalized,
        "numbers": numbers,
        "year": year,
        "index": index,
        "alpha": " ".join(alpha_tokens),
    }


def _name_match_similarity(export_name: str, search_name: str) -> float:
    export_parts = _name_match_parts(export_name)
    search_parts = _name_match_parts(search_name)

    export_norm = export_parts["normalized"]
    search_norm = search_parts["normalized"]
    if not export_norm or not search_norm:
        return 0.0
    if export_norm == search_norm:
        return 1.0

    export_index = export_parts["index"]
    search_index = search_parts["index"]
    if export_index and search_index and export_index != search_index:
        return 0.0

    export_year = export_parts["year"]
    search_year = search_parts["year"]
    if export_year and search_year and export_year != search_year:
        return 0.0

    export_numbers = export_parts["numbers"]
    search_numbers = search_parts["numbers"]
    if export_numbers and search_numbers and set(export_numbers).isdisjoint(set(search_numbers)):
        return 0.0

    export_alpha = export_parts["alpha"]
    search_alpha = search_parts["alpha"]
    left = export_alpha or export_norm
    right = search_alpha or search_norm
    if not left or not right:
        return 0.0

    ratio = SequenceMatcher(None, left, right).ratio()
    if left in right or right in left:
        ratio = max(ratio, 0.9)
    return ratio

def _is_export_operation(operation: dict[str, Any]) -> bool:
    if not isinstance(operation, dict):
        return False
    probe_fields = [
        operation.get("action"),
        operation.get("@odata.type"),
        operation.get("operationType"),
        operation.get("type"),
        operation.get("description"),
    ]
    for value in probe_fields:
        text = str(value or "").strip().lower()
        if "export" in text:
            return True
    return False


def _extract_export_name(operation: dict[str, Any]) -> str:
    direct_fields = [
        operation.get("outputName"),
        operation.get("displayName"),
        operation.get("name"),
        operation.get("exportName"),
        operation.get("searchName"),
        operation.get("description"),
    ]
    for value in direct_fields:
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested_fields = ["search", "reviewSet", "resultSet", "additionalData", "additionalProperties"]
    for key in nested_fields:
        payload = operation.get(key)
        if not isinstance(payload, dict):
            continue
        for nested_key in ("outputName", "displayName", "name", "exportName", "searchName"):
            nested_value = payload.get(nested_key)
            if isinstance(nested_value, str) and nested_value.strip():
                return nested_value.strip()

    operation_id = (operation.get("id") or "").strip() if isinstance(operation.get("id"), str) else ""
    if operation_id:
        return f"Export operation {operation_id}"
    return "Unnamed export"


def _has_generic_export_name(name: str) -> bool:
    value = (name or "").strip().lower()
    return not value or value == "unnamed export" or value.startswith("export operation ")


def _collect_export_operations(case_id: str, operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exports: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for op in operations or []:
        if not isinstance(op, dict):
            continue
        if not _is_export_operation(op):
            continue
        op_id = (op.get("id") or "").strip() if isinstance(op.get("id"), str) else ""
        if op_id and op_id in seen_ids:
            continue
        if op_id:
            seen_ids.add(op_id)

        export_name = _extract_export_name(op)
        # Graph list-operations often omits export names; query operation detail when needed.
        if op_id and _has_generic_export_name(export_name):
            try:
                detail = get_purview_case_operation(case_id, op_id)
                if isinstance(detail, dict):
                    op = {**op, **detail}
                    detail_name = _extract_export_name(op)
                    if not _has_generic_export_name(detail_name):
                        export_name = detail_name
            except Exception as exc:
                _debug_suppressed("suppressed exception in purview_exports.py:271", exc)

        exports.append(
            {
                "id": op_id or None,
                "name": export_name,
                "action": op.get("action"),
                "status": op.get("status"),
                "createdDateTime": op.get("createdDateTime"),
                "completedDateTime": op.get("completedDateTime"),
            }
        )
    return exports

def _parse_custodian_ids(value: Any) -> list[int]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        try:
            decoded = json.loads(value)
            raw = decoded if isinstance(decoded, list) else []
        except Exception:
            raw = []
    else:
        raw = []
    out: list[int] = []
    for item in raw:
        try:
            cid = int(item)
        except (TypeError, ValueError):
            continue
        if cid not in out:
            out.append(cid)
    return out


def _search_missing_consent(search: models.Search, custodian_by_id: dict[int, models.Custodian]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for cid in _parse_custodian_ids(getattr(search, "custodian_ids", None)):
        cust = custodian_by_id.get(cid)
        if not cust:
            continue
        status = ((getattr(cust, "consent_status", None) or "not sent").strip().lower())
        if status in {"received", "implied", "awoc", "na"}:
            continue
        missing.append(
            {
                "id": getattr(cust, "id", None),
                "name": getattr(cust, "name", None),
                "email": getattr(cust, "email", None),
                "consent": status,
            }
        )
    return missing


def _match_exports_to_searches(
    exports: list[dict[str, Any]],
    searches: list[models.Search],
) -> tuple[list[tuple[dict[str, Any], models.Search]], list[dict[str, Any]]]:
    by_key: dict[str, list[models.Search]] = {}
    remaining_searches = sorted(searches or [], key=lambda s: getattr(s, "id", 0))

    for search in remaining_searches:
        key = _normalize_export_name(getattr(search, "name", "") or "")
        if not key:
            continue
        by_key.setdefault(key, []).append(search)

    matched: list[tuple[dict[str, Any], models.Search]] = []
    unmatched_exact: list[dict[str, Any]] = []

    for export in exports or []:
        key = _normalize_export_name(export.get("name") or "")
        if key and key in by_key and by_key[key]:
            search = by_key[key].pop(0)
            matched.append((export, search))
            if search in remaining_searches:
                remaining_searches.remove(search)
            continue
        unmatched_exact.append(export)

    if not unmatched_exact or not remaining_searches:
        return matched, unmatched_exact

    unmatched: list[dict[str, Any]] = []
    for export in unmatched_exact:
        export_name = export.get("name") or ""
        best_idx: Optional[int] = None
        best_score = 0.0

        for idx, search in enumerate(remaining_searches):
            search_name = getattr(search, "name", "") or ""
            score = _name_match_similarity(export_name, search_name)
            if score < MATCH_NAME_SIMILARITY_THRESHOLD:
                continue
            if best_idx is None:
                best_idx = idx
                best_score = score
                continue
            prev = remaining_searches[best_idx]
            prev_id = getattr(prev, "id", 0)
            curr_id = getattr(search, "id", 0)
            if score > best_score or (score == best_score and curr_id < prev_id):
                best_idx = idx
                best_score = score

        if best_idx is None:
            unmatched.append(export)
            continue

        search = remaining_searches.pop(best_idx)
        matched.append((export, search))

    return matched, unmatched

def _analyst_admin_recipients(db: Session) -> list[str]:
    rows = (
        db.query(models.User.email)
        .filter(models.User.email.isnot(None))
        .filter(
            or_(
                func.lower(func.coalesce(models.User.role, "")).in_(("analyst", "sys_admin")),
                models.User.is_admin.is_(True),
            )
        )
        .all()
    )
    unique: list[str] = []
    seen: set[str] = set()
    for (email,) in rows:
        text = (email or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _send_export_findings_email(
    db: Session,
    *,
    case: models.Case,
    purview_case_id: Optional[str],
    export_names: list[str],
    search_names: list[str],
    unmatched_exports: list[dict[str, Any]],
    matched_without_consent: list[dict[str, Any]],
    request: Optional[Request],
) -> bool:
    recipients = _analyst_admin_recipients(db)
    if not recipients:
        return False

    if not mail_provider_ready():
        return False

    case_name = (getattr(case, "name", None) or f"Case #{getattr(case, 'id', '?')}").strip()
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = branded_subject(f"Purview export findings for {case_name}")

    link = None
    try:
        base = _app_base_url(request)
        link = f"{base}/cases/{getattr(case, 'id', None)}"
    except Exception:
        link = None

    lines: list[str] = [
        f"{app_display_name()} detected Purview export activity that needs review.",
        "",
        f"Case: {case_name} (ID: {getattr(case, 'id', None)})",
        f"Checked: {now_utc}",
    ]
    if purview_case_id:
        lines.append(f"Purview case id: {purview_case_id}")
    if link:
        lines.append(f"Case link: {link}")

    lines.extend(["", "Purview export names:"])
    if export_names:
        for name in export_names:
            lines.append(f"- {name}")
    else:
        lines.append("- (none)")

    lines.extend(["", f"{app_display_name()} search names:"])
    if search_names:
        for name in search_names:
            lines.append(f"- {name}")
    else:
        lines.append("- (none)")

    lines.extend(["", f"Unmatched exports (no matching {app_display_name()} search):"])
    if unmatched_exports:
        for row in unmatched_exports:
            name = row.get("name") or "Unnamed export"
            status = row.get("status") or "unknown"
            lines.append(f"- {name} (status: {status})")
    else:
        lines.append("- (none)")

    lines.extend(["", "Matched exports with missing consent:"])
    if matched_without_consent:
        for row in matched_without_consent:
            search_name = row.get("search_name") or "Unnamed search"
            export_name = row.get("export_name") or "Unnamed export"
            lines.append(f"- Search '{search_name}' matched export '{export_name}'")
            for person in row.get("missing_consent") or []:
                pname = person.get("name") or person.get("email") or "Unnamed custodian"
                pemail = person.get("email") or ""
                pstatus = person.get("consent") or "not sent"
                label = f"{pname} ({pemail})" if pemail else pname
                lines.append(f"  - {label}: consent={pstatus}")
    else:
        lines.append("- (none)")

    lines.extend(["", app_display_name()])

    send_email(
        recipients=recipients,
        subject=subject,
        body="\n".join(lines),
    )
    return True


def sync_case_purview_exports(
    db: Session,
    *,
    case_id: int,
    actor_id: Optional[int],
    request: Optional[Request],
    source: str,
    send_notifications: bool,
) -> dict[str, Any]:
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    summary: dict[str, Any] = {
        "ok": True,
        "case_id": case_id,
        "case_name": getattr(case, "name", None),
        "source": source,
        "purview_enabled": bool(purview_enabled()),
        "purview_case_id": None,
        "exports_count": 0,
        "export_names": [],
        "searches_count": 0,
        "search_names": [],
        "matched_searches_count": 0,
        "matched_search_ids": [],
        "matched_without_consent_count": 0,
        "matched_without_consent": [],
        "unmatched_exports_count": 0,
        "unmatched_exports": [],
        "updated_searches_count": 0,
        "updated_search_ids": [],
        "notification_sent": False,
        "notification_reason": None,
    }

    if not purview_enabled():
        summary["ok"] = False
        summary["detail"] = "Purview integration is not configured"
        return summary

    display_name = (getattr(case, "name", None) or "").strip()
    if not display_name:
        summary["ok"] = False
        summary["detail"] = "Case does not have a valid name"
        return summary

    try:
        purview_case = find_purview_case_by_display_name(display_name)
        if not purview_case:
            summary["ok"] = False
            summary["detail"] = "Purview case not found"
            return summary

        purview_case_id = (purview_case.get("id") or "").strip() if isinstance(purview_case, dict) else ""
        summary["purview_case_id"] = purview_case_id or None
        if not purview_case_id:
            summary["ok"] = False
            summary["detail"] = "Purview case id missing"
            return summary

        operations = list_purview_case_operations(purview_case_id)
        exports = _collect_export_operations(purview_case_id, operations)
        export_names = [row.get("name") for row in exports if isinstance(row.get("name"), str)]
        summary["exports_count"] = len(exports)
        summary["export_names"] = export_names

        searches = (
            db.query(models.Search)
            .filter(models.Search.case_id == case_id)
            .order_by(models.Search.id.asc())
            .all()
        )
        search_names = [getattr(s, "name", None) or f"Search #{getattr(s, 'id', '?')}" for s in searches]
        summary["searches_count"] = len(searches)
        summary["search_names"] = search_names

        matched, unmatched = _match_exports_to_searches(exports, searches)
        summary["matched_searches_count"] = len(matched)
        summary["matched_search_ids"] = [getattr(search, "id", None) for (_, search) in matched]
        summary["unmatched_exports_count"] = len(unmatched)
        summary["unmatched_exports"] = unmatched

        custodians = (
            db.query(models.Custodian)
            .filter(models.Custodian.case_id == case_id)
            .all()
        )
        custodian_by_id = {int(getattr(c, "id")): c for c in custodians if getattr(c, "id", None) is not None}

        matched_without_consent: list[dict[str, Any]] = []
        updated_search_ids: list[int] = []
        for export_row, search in matched:
            changed = False
            if (getattr(search, "status_search", "") or "").strip().lower() != "performed":
                search.status_search = "performed"
                changed = True
            if (getattr(search, "status_export", "") or "").strip().lower() != "performed":
                search.status_export = "performed"
                changed = True

            missing = _search_missing_consent(search, custodian_by_id)
            if missing:
                if not bool(getattr(search, "export_without_consent", False)):
                    search.export_without_consent = True
                    changed = True
                matched_without_consent.append(
                    {
                        "search_id": getattr(search, "id", None),
                        "search_name": getattr(search, "name", None),
                        "export_name": export_row.get("name"),
                        "missing_consent": missing,
                    }
                )
            elif bool(getattr(search, "export_without_consent", False)):
                # Clear stale warning when consent is now complete for matched custodians.
                search.export_without_consent = False
                changed = True

            if changed:
                sync_search_hold_statuses(db, search)
                db.add(search)
                sid = getattr(search, "id", None)
                if isinstance(sid, int) and sid not in updated_search_ids:
                    updated_search_ids.append(sid)

        if updated_search_ids:
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise

        summary["matched_without_consent"] = matched_without_consent
        summary["matched_without_consent_count"] = len(matched_without_consent)
        summary["updated_search_ids"] = updated_search_ids
        summary["updated_searches_count"] = len(updated_search_ids)

        should_notify = bool(exports) and (len(searches) == 0 or len(unmatched) > 0)
        if should_notify and send_notifications:
            summary["notification_reason"] = "no_searches" if len(searches) == 0 else "name_mismatch"
            try:
                summary["notification_sent"] = _send_export_findings_email(
                    db,
                    case=case,
                    purview_case_id=purview_case_id,
                    export_names=export_names,
                    search_names=search_names,
                    unmatched_exports=unmatched,
                    matched_without_consent=matched_without_consent,
                    request=request,
                )
            except Exception as exc:
                logger.warning("purview_export_notification_failed case_id=%s error=%s", case_id, exc)
                summary["notification_sent"] = False

        return summary
    except PurviewConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PurviewAPIError as exc:
        status = exc.status_code or 502
        if status < 400 or status >= 600:
            status = 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


def _case_ids_with_active_purview_holds(db: Session) -> list[int]:
    rows = (
        db.query(models.Case.id)
        .join(models.Custodian, models.Custodian.case_id == models.Case.id)
        .filter(models.Case.closed.is_(False))
        .filter(
            or_(
                models.Custodian.holds_email.is_(True),
                models.Custodian.holds_onedrive.is_(True),
                models.Custodian.holds_email_pending.is_(True),
                models.Custodian.holds_onedrive_pending.is_(True),
            )
        )
        .distinct()
        .all()
    )
    out: list[int] = []
    for (case_id,) in rows:
        try:
            cid = int(case_id)
        except (TypeError, ValueError):
            continue
        out.append(cid)
    return out



def _case_ids_for_requestor_groups(db: Session, groups: set[str]) -> list[int]:
    if not groups:
        return []

    out: set[int] = set()

    # Case-level requestor group captured on case_requestors rows.
    rows_case_requestor_group = (
        db.query(models.Case.id)
        .join(models.CaseRequestor, models.CaseRequestor.case_id == models.Case.id)
        .filter(models.Case.closed.is_(False))
        .filter(func.lower(func.coalesce(models.CaseRequestor.requestor_group, "")).in_(groups))
        .distinct()
        .all()
    )
    for (case_id,) in rows_case_requestor_group:
        try:
            out.add(int(case_id))
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview_exports.py:739", exc)

    # Requestor user linked to case_requestors rows.
    rows_case_requestor_user_group = (
        db.query(models.Case.id)
        .join(models.CaseRequestor, models.CaseRequestor.case_id == models.Case.id)
        .join(models.User, models.User.id == models.CaseRequestor.user_id)
        .filter(models.Case.closed.is_(False))
        .filter(func.lower(func.coalesce(models.User.role, "")) == "requestor")
        .filter(func.lower(func.coalesce(models.User.requestor_group, "")).in_(groups))
        .distinct()
        .all()
    )
    for (case_id,) in rows_case_requestor_user_group:
        try:
            out.add(int(case_id))
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview_exports.py:756", exc)

    # Requestor user matched by case_requestors email.
    rows_case_requestor_email_group = (
        db.query(models.Case.id)
        .join(models.CaseRequestor, models.CaseRequestor.case_id == models.Case.id)
        .join(
            models.User,
            func.lower(func.coalesce(models.User.email, ""))
            == func.lower(func.coalesce(models.CaseRequestor.email, "")),
        )
        .filter(models.Case.closed.is_(False))
        .filter(func.lower(func.coalesce(models.User.role, "")) == "requestor")
        .filter(func.lower(func.coalesce(models.User.requestor_group, "")).in_(groups))
        .distinct()
        .all()
    )
    for (case_id,) in rows_case_requestor_email_group:
        try:
            out.add(int(case_id))
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview_exports.py:777", exc)

    # Legacy fallback: primary case.requestor email mapped to a requestor account.
    rows_primary_requestor_group = (
        db.query(models.Case.id)
        .join(
            models.User,
            func.lower(func.coalesce(models.User.email, ""))
            == func.lower(func.coalesce(models.Case.requestor, "")),
        )
        .filter(models.Case.closed.is_(False))
        .filter(func.lower(func.coalesce(models.User.role, "")) == "requestor")
        .filter(func.lower(func.coalesce(models.User.requestor_group, "")).in_(groups))
        .distinct()
        .all()
    )
    for (case_id,) in rows_primary_requestor_group:
        try:
            out.add(int(case_id))
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview_exports.py:797", exc)

    return sorted(out)


def _case_ids_for_scheduled_export_sync(db: Session) -> list[int]:
    out: set[int] = set(_case_ids_with_active_purview_holds(db))
    requestor_groups = _parse_group_values(purview_export_poll_requestor_groups())
    if requestor_groups:
        out.update(_case_ids_for_requestor_groups(db, requestor_groups))
    return sorted(out)

def _run_scheduled_export_sync() -> None:
    db = SessionLocal()
    try:
        case_ids = _case_ids_for_scheduled_export_sync(db)
        if not case_ids:
            return
        for case_id in case_ids:
            try:
                sync_case_purview_exports(
                    db,
                    case_id=case_id,
                    actor_id=None,
                    request=None,
                    source="scheduled",
                    send_notifications=True,
                )
            except Exception as exc:
                logger.warning("purview_export_sync_case_failed case_id=%s error=%s", case_id, exc)
    finally:
        try:
            db.close()
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview_exports.py:831", exc)


def start_purview_export_scheduler() -> None:
    global _EXPORT_SCHEDULER_STARTED
    if _EXPORT_SCHEDULER_STARTED:
        return
    if not purview_export_poll_enabled():
        return
    _EXPORT_SCHEDULER_STARTED = True

    def _worker() -> None:
        while True:
            try:
                now_utc = datetime.now(timezone.utc)
                next_run = _next_poll_run(now_utc)
                sleep_for = max(1.0, (next_run - now_utc).total_seconds())
                time.sleep(sleep_for)
                _run_scheduled_export_sync()
            except Exception as exc:  # pragma: no cover - background guard
                logger.warning("purview_export_scheduler_failure error=%s", exc)
                time.sleep(60)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


@router.post("/{case_id}/purview_exports/check")
def check_purview_exports(
    case_id: int,
    db: Session = Depends(get_db),
    request: Request = None,
    _user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, _user, db)
    ensure_case_editable(_user)
    return sync_case_purview_exports(
        db,
        case_id=case_id,
        actor_id=getattr(_user, "id", None),
        request=request,
        source="manual",
        send_notifications=True,
    )














