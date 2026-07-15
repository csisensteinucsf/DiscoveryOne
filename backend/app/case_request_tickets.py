import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from . import models, ticket_provider
from .audit import log_event
from .safe_log import debug_suppressed as _debug_suppressed
from .ticket_workflow_catalog import (
    category_legacy_fields,
    completion_satisfies_hold_key,
    ticket_workflows_raw,
    workflow_lookup,
)


def _ticket_workflows_raw():
    return ticket_workflows_raw()


def _request_ticket_category_lookup() -> dict[str, dict]:
    return workflow_lookup(include_disabled=True)


def _request_ticket_categories() -> set[str]:
    return set(_request_ticket_category_lookup().keys())


def _request_ticket_category_fields() -> dict[str, str]:
    return category_legacy_fields()


MAX_TICKET_LENGTH = 64
MAX_TICKET_METADATA_LENGTH = 512

def _clean_str(val) -> str:
    if val is None:
        return ""
    try:
        text = str(val)
    except Exception:
        return ""
    return text.strip()


def _normalize_request_ticket_entries(entries, case: models.Case | None = None):
    if entries is None:
        return None
    normalized = []
    custodian_lookup = {}
    existing_ids: set[str] = set()
    existing_created_at_by_id: dict[str, str] = {}
    if case is not None:
        try:
            attached = getattr(case, "custodians", []) or []
        except Exception:
            attached = []
        for cust in attached:
            if cust and getattr(cust, "id", None) is not None:
                custodian_lookup[int(cust.id)] = cust
        try:
            existing_entries = getattr(case, "request_ticket_entries", []) or []
        except Exception:
            existing_entries = []
        for entry in existing_entries:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("id") or "").strip()
            if not entry_id:
                continue
            existing_ids.add(entry_id)
            created_val = entry.get("created_at")
            if isinstance(created_val, datetime):
                try:
                    existing_created_at_by_id[entry_id] = created_val.astimezone(timezone.utc).isoformat()
                except (ValueError, OSError):
                    continue
            elif isinstance(created_val, str) and created_val.strip():
                existing_created_at_by_id[entry_id] = created_val.strip()
    for raw in entries or []:
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        elif hasattr(raw, "dict"):
            raw = raw.dict()
        elif not isinstance(raw, dict):
            continue
        category = raw.get("category")
        if category not in _request_ticket_categories():
            continue
        ticket = _clean_str(raw.get("ticket"))
        entry_id = str(raw.get("id") or uuid4())
        created_raw = raw.get("created_at")
        created_at = None
        if isinstance(created_raw, datetime):
            try:
                created_at = created_raw.astimezone(timezone.utc).isoformat()
            except Exception:
                created_at = None
        elif isinstance(created_raw, str) and created_raw.strip():
            created_at = created_raw.strip()
        if created_at is None and ticket:
            if case is not None and entry_id in existing_ids:
                created_at = existing_created_at_by_id.get(entry_id)
            elif case is not None:
                created_at = datetime.now(timezone.utc).isoformat()
        record = {
            "id": entry_id,
            "category": category,
            "ticket": ticket[:MAX_TICKET_LENGTH],
            "created_at": created_at,
            "custodian_id": None,
            "custodian_name": None,
            "custodian_email": None,
            "sys_id": _clean_str(raw.get("sys_id")) or None,
            "status": _clean_str(raw.get("status") or raw.get("sn_status")) or None,
            "assigned_to_sys_id": _clean_str(raw.get("assigned_to_sys_id")) or None,
            "assigned_to_display": _clean_str(raw.get("assigned_to_display")) or None,
            "assigned_to_email": _clean_str(raw.get("assigned_to_email")) or None,
        }
        custodian_id = raw.get("custodian_id")
        cid = None
        if custodian_id is not None:
            try:
                cid = int(custodian_id)
            except (TypeError, ValueError):
                cid = None
        if cid:
            record["custodian_id"] = cid
            match = custodian_lookup.get(cid)
            if match is not None:
                record["custodian_name"] = getattr(match, "name", None)
                record["custodian_email"] = getattr(match, "email", None)
        if record["custodian_name"] is None:
            name = _clean_str(raw.get("custodian_name")) or None
            record["custodian_name"] = name
        if record["custodian_email"] is None:
            email = _clean_str(raw.get("custodian_email")) or None
            record["custodian_email"] = email
        # Preserve any supplemental metadata (e.g., ServiceNow status/assignee) without letting it grow unchecked
        for key, value in raw.items():
            if key in {"id", "category", "ticket", "created_at", "custodian_id", "custodian_name", "custodian_email"}:
                continue
            if value is None:
                continue
            if key == "bulk_custodians":
                bulk: list[dict] = []
                if isinstance(value, list):
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        bulk.append(
                            {
                                "id": item.get("id"),
                                "name": (item.get("name") or "").strip() or None,
                                "email": (item.get("email") or "").strip() or None,
                            }
                        )
                record[key] = bulk
                continue
            if key == "access_log_time_windows":
                windows: list[dict] = []
                if isinstance(value, list):
                    for item in value:
                        if not isinstance(item, dict):
                            continue
                        date_value = _clean_str(item.get("date")) or None
                        start_time = _clean_str(item.get("start_time")) or None
                        end_time = _clean_str(item.get("end_time")) or None
                        if not any((date_value, start_time, end_time)):
                            continue
                        windows.append(
                            {
                                "date": date_value,
                                "start_time": start_time,
                                "end_time": end_time,
                            }
                        )
                record[key] = windows
                continue
            if key == "assignment_email_sent":
                record[key] = bool(value)
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
                value = value[:MAX_TICKET_METADATA_LENGTH]
            elif not isinstance(value, (int, float, bool)):
                # Avoid persisting nested structures; keep scalars only
                continue
            record[key] = value
        normalized.append(record)
    return normalized


def _recover_request_ticket_entries_from_audit(
    db: Session,
    *,
    case: models.Case,
    request: Request | None,
    actor: models.User | None,
    force: bool = False,
) -> bool:
    """
    Best-effort repair for cases that have ServiceNow tickets recorded in audit_events but no longer
    have any ticket fields populated on the case record (so tickets disappear from the UI).
    """
    try:
        case_id = getattr(case, "id", None)
        if not case_id:
            return False

        existing = getattr(case, "request_ticket_entries", []) or []
        existing_keys: set[tuple[str, str]] = set()
        existing_categories: set[str] = set()
        for entry in existing:
            if not isinstance(entry, dict):
                continue
            cat = (entry.get("category") or "").strip()
            tkt = (entry.get("ticket") or "").strip()
            if cat and tkt:
                existing_keys.add((cat, tkt))
                existing_categories.add(cat)

        if not force:
            # If the missing category isn't relevant to the case, skip recovery work.
            try:
                holds_present = (
                    db.query(models.Custodian.id)
                    .filter(models.Custodian.case_id == int(case_id))
                    .filter(
                        or_(
                            models.Custodian.holds_rubrik_restore.is_(True),
                            models.Custodian.holds_rubrik_restore_pending.is_(True),
                            models.Custodian.holds_rubrik_restore_failed.is_(True),
                            models.Custodian.holds_box.is_(True),
                            models.Custodian.holds_box_pending.is_(True),
                            models.Custodian.holds_box_failed.is_(True),
                        )
                    )
                    .limit(1)
                    .first()
                )
            except Exception:
                holds_present = True
            if not holds_present:
                return False

        def _recover_from_audit_events() -> list[dict]:
            try:
                rows = (
                    db.execute(
                        text(
                            """
                            SELECT created_at, details
                            FROM audit_events
                            WHERE action = 'case_request_ticket'
                              AND target_type = 'case'
                              AND target_id = :case_id
                            ORDER BY created_at DESC, id DESC
                            LIMIT 200
                            """
                        ),
                        {"case_id": int(case_id)},
                    )
                    .mappings()
                    .all()
                )
            except Exception:
                rows = []
            if not rows:
                return []
            seen: set[tuple[str, str]] = set()
            recovered: list[dict] = []
            for row in reversed(rows):
                created_at = row.get("created_at") if isinstance(row, dict) else None
                created_iso = None
                if isinstance(created_at, datetime):
                    try:
                        created_iso = created_at.astimezone(timezone.utc).isoformat()
                    except Exception:
                        created_iso = None
                elif isinstance(created_at, str) and created_at.strip():
                    created_iso = created_at.strip()
                details = row.get("details") if isinstance(row, dict) else None
                if not isinstance(details, dict):
                    continue
                category = (details.get("category") or "").strip()
                ticket = (details.get("ticket") or "").strip()
                if not category or not ticket:
                    continue
                if category not in _request_ticket_categories():
                    continue
                key = (category, ticket)
                if key in seen:
                    continue
                seen.add(key)
                recovered.append(
                    {
                        "id": str(details.get("entry_id") or uuid4()),
                        "category": category,
                        "ticket": ticket,
                        "created_at": created_iso,
                        "sys_id": details.get("sys_id"),
                        "custodian_id": details.get("custodian_id"),
                        "custodian_name": details.get("custodian_name"),
                        "custodian_email": details.get("custodian_email"),
                        "bulk_custodians": details.get("bulk_custodians"),
                        "source": details.get("source"),
                        "purpose": details.get("purpose"),
                    }
                )
            return recovered

        def _recover_from_audit_logfile() -> list[dict]:
            import glob
            import gzip
            import os

            log_dir = os.getenv("AUDIT_LOG_DIR") or os.getenv("LOG_DIR") or "/app/logs"
            log_name = os.getenv("AUDIT_LOG_FILE_NAME") or "audit.log"
            base_path = os.path.join(log_dir, log_name)
            candidates = glob.glob(base_path + "*")
            if not candidates:
                candidates = [base_path]
            try:
                candidates = sorted(
                    [p for p in candidates if os.path.isfile(p)],
                    key=lambda p: os.path.getmtime(p),
                    reverse=True,
                )
            except Exception as exc:
                _debug_suppressed("suppressed exception in cases.py:1031", exc)

            seen: set[tuple[str, str]] = set()
            recovered: list[dict] = []
            max_files = 6
            max_lines_total = 200_000
            lines_scanned = 0

            def _process_lines(lines_iter):
                nonlocal lines_scanned
                for line in lines_iter:
                    if lines_scanned >= max_lines_total:
                        return
                    lines_scanned += 1
                    if not line:
                        continue
                    # Fast prefilter (avoid json.loads unless likely relevant)
                    if '"action": "case_request_ticket"' not in line:
                        continue
                    if '"case_id": ' not in line and '"target_id": ' not in line:
                        continue
                    if str(case_id) not in line:
                        continue
                    idx = line.find("{")
                    if idx < 0:
                        continue
                    payload = line[idx:]
                    try:
                        record = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if not isinstance(record, dict):
                        continue
                    if record.get("action") != "case_request_ticket":
                        continue
                    if record.get("target_type") != "case":
                        continue
                    if int(record.get("target_id") or 0) != int(case_id):
                        details = record.get("details")
                        if not (isinstance(details, dict) and int(details.get("case_id") or 0) == int(case_id)):
                            continue
                    details = record.get("details")
                    if not isinstance(details, dict):
                        continue
                    created_iso = record.get("created_at") if isinstance(record.get("created_at"), str) else None
                    if created_iso:
                        created_iso = created_iso.strip() or None
                    category = (details.get("category") or "").strip()
                    ticket = (details.get("ticket") or "").strip()
                    if not category or not ticket:
                        continue
                    if category not in _request_ticket_categories():
                        continue
                    key = (category, ticket)
                    if key in seen:
                        continue
                    seen.add(key)
                    recovered.append(
                        {
                            "id": str(details.get("entry_id") or uuid4()),
                            "category": category,
                            "ticket": ticket,
                            "created_at": created_iso,
                            "sys_id": details.get("sys_id"),
                            "custodian_id": details.get("custodian_id"),
                            "custodian_name": details.get("custodian_name"),
                            "custodian_email": details.get("custodian_email"),
                            "bulk_custodians": details.get("bulk_custodians"),
                            "source": details.get("source"),
                            "purpose": details.get("purpose"),
                        }
                    )

            for path in candidates[:max_files]:
                try:
                    if path.endswith(".gz"):
                        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as f:
                            _process_lines(f)
                    else:
                        with open(path, "rb") as f:
                            try:
                                f.seek(0, 2)
                                size = f.tell()
                                read_size = min(size, 5 * 1024 * 1024)
                                f.seek(max(0, size - read_size))
                            except Exception as exc:
                                _debug_suppressed("suppressed exception in cases.py:1117", exc)
                            data = f.read().decode("utf-8", errors="ignore")
                        _process_lines(reversed([ln for ln in data.splitlines() if ln.strip()]))
                except (OSError, UnicodeDecodeError, ValueError):
                    continue
                # If we already found something for a missing category, no need to keep scanning.
                if recovered:
                    break

            return list(reversed(recovered))

        recovered = _recover_from_audit_events()
        if not recovered:
            recovered = _recover_from_audit_logfile()

        if not recovered:
            return False

        # Merge: keep existing entries and add any missing tickets recovered from audit.
        merged = []
        if existing:
            merged.extend(existing)
        for item in recovered:
            if not isinstance(item, dict):
                continue
            cat = (item.get("category") or "").strip()
            tkt = (item.get("ticket") or "").strip()
            if cat and tkt and (cat, tkt) in existing_keys:
                continue
            merged.append(item)

        normalized = _normalize_request_ticket_entries(merged, case) or []
        if not normalized:
            return False

        if existing and len(normalized) == len(existing):
            # Nothing new to persist.
            return False

        case.request_ticket_entries = normalized
        _sync_legacy_request_tickets(case, normalized)
        _apply_request_holds(case, normalized)
        db.add(case)
        db.commit()
        db.refresh(case)

        try:
            log_event(
                db,
                action="case_request_ticket_repaired",
                actor_id=getattr(actor, "id", None) if actor else None,
                target_type="case",
                target_id=int(case_id),
                details={
                    "case_id": int(case_id),
                    "case_name": getattr(case, "name", None),
                    "recovered_count": len(normalized),
                    "prior_count": len(existing or []),
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in cases.py:1179", exc)
        return True
    except Exception:
        try:
            db.rollback()
        except Exception as exc:
            _debug_suppressed("suppressed exception in cases.py:1185", exc)
        return False


def _apply_request_holds(case: models.Case, entries):
    """
    Apply configured workflow status transitions to matching custodians.
    """
    if not case or not entries:
        return

    workflows = _request_ticket_category_lookup()
    cust_by_id = {}
    cust_by_email = {}
    try:
        for custodian in getattr(case, "custodians", []) or []:
            if getattr(custodian, "id", None) is not None:
                cust_by_id[int(custodian.id)] = custodian
            email = (getattr(custodian, "email", None) or "").strip().lower()
            if email:
                cust_by_email[email] = custodian
    except Exception:
        return

    def _match(id_value, email_value):
        if id_value is not None and int(id_value) in cust_by_id:
            return cust_by_id[int(id_value)]
        normalized_email = (email_value or "").strip().lower()
        if normalized_email and normalized_email in cust_by_email:
            return cust_by_email[normalized_email]
        return None

    def _ticket_is_closed(entry: dict) -> bool:
        if bool(entry.get("is_closed")):
            return True
        status_value = entry.get("status") or entry.get("ticket_status")
        try:
            return ticket_provider.is_closed_status(status_value)
        except Exception:
            return False

    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        category = entry.get("category")
        workflow = workflows.get(category) or {}
        hold_field = str(workflow.get("hold_key") or "").strip()
        if not hold_field:
            continue

        pending_field = f"{hold_field}_pending"
        failed_field = f"{hold_field}_failed"
        released_field = f"{hold_field}_released"
        manual_status_tracking = bool(workflow.get("manual_status_tracking"))
        hold_operation = str(workflow.get("hold_operation") or "hold").strip().lower()
        completion_hold_field = completion_satisfies_hold_key(workflow)

        targets = [(entry.get("custodian_id"), entry.get("custodian_email"))]
        if isinstance(entry.get("bulk_custodians"), list):
            targets.extend(
                (item.get("id"), item.get("email"))
                for item in entry["bulk_custodians"]
                if isinstance(item, dict)
            )

        for custodian_id, custodian_email in targets:
            custodian = _match(custodian_id, custodian_email)
            if custodian is None:
                continue
            try:
                if manual_status_tracking:
                    if getattr(custodian, released_field, False):
                        continue
                    if hold_operation == "release":
                        setattr(custodian, hold_field, True)
                        setattr(custodian, pending_field, True)
                        setattr(custodian, failed_field, False)
                        if hasattr(custodian, released_field):
                            setattr(custodian, released_field, False)
                    elif not (
                        getattr(custodian, hold_field, False)
                        or getattr(custodian, pending_field, False)
                        or getattr(custodian, failed_field, False)
                    ):
                        setattr(custodian, hold_field, True)
                        setattr(custodian, pending_field, True)
                        setattr(custodian, failed_field, False)
                    continue

                if getattr(custodian, failed_field, False):
                    continue

                is_closed = _ticket_is_closed(entry)
                prior_pending = bool(getattr(custodian, pending_field, False))
                if hold_operation == "release":
                    setattr(custodian, pending_field, not is_closed)
                    setattr(custodian, hold_field, not is_closed)
                    if hasattr(custodian, released_field):
                        setattr(custodian, released_field, is_closed)
                else:
                    setattr(custodian, pending_field, not is_closed)
                    if not is_closed or prior_pending:
                        setattr(custodian, hold_field, True)
                    if hasattr(custodian, released_field) and (
                        getattr(custodian, hold_field, False)
                        or getattr(custodian, pending_field, False)
                    ):
                        setattr(custodian, released_field, False)

                if is_closed and completion_hold_field:
                    completion_pending_field = f"{completion_hold_field}_pending"
                    completion_released_field = f"{completion_hold_field}_released"
                    if getattr(custodian, completion_pending_field, False):
                        setattr(custodian, completion_pending_field, False)
                    setattr(custodian, completion_hold_field, True)
                    if hasattr(custodian, completion_released_field):
                        setattr(custodian, completion_released_field, False)
            except (AttributeError, KeyError, TypeError, ValueError):
                continue


def _first_ticket(entries, category):
    if not entries:
        return None
    for item in entries:
        if not isinstance(item, dict):
            continue
        if item.get("category") != category:
            continue
        ticket = (item.get("ticket") or "").strip()
        if ticket:
            return ticket[:MAX_TICKET_LENGTH]
    return None


def _sync_legacy_request_tickets(case: models.Case, entries):
    for category, field in _request_ticket_category_fields().items():
        value = _first_ticket(entries, category)
        setattr(case, field, value)


