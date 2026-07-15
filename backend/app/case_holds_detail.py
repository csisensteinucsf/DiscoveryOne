import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import models
from .permissions import ensure_case_visible
from .preservation_catalog import configured_builtin_hold_fields, hold_field_for_source

NO_EMAIL_PLACEHOLDER = "NoEmail"
UNMATCHED_EMAIL_PLACEHOLDER = "UNMATCHED"
FALLBACK_HOLD_DETAIL_META = [
    {"key": "holds_email", "label": "Email"},
    {"key": "holds_onedrive", "label": "OneDrive"},
    {"key": "holds_gdrive", "label": "Google Drive"},
    {"key": "holds_box", "label": "Box"},
    {"key": "holds_slack", "label": "Slack"},
]


def _hold_detail_meta() -> list[dict[str, str]]:
    configured = [
        {"key": field, "label": label}
        for _source_key, field, label in configured_builtin_hold_fields(enabled_only=True)
    ]
    return configured or [dict(item) for item in FALLBACK_HOLD_DETAIL_META]


def _hold_detail_keys() -> set[str]:
    return {item["key"] for item in _hold_detail_meta()}


def _hold_detail_label_by_key() -> dict[str, str]:
    return {item["key"]: item["label"] for item in _hold_detail_meta()}


def _hold_detail_state(*, active: bool, pending: bool, failed: bool, released: bool) -> str:
    if failed:
        return "failed"
    if pending:
        return "pending"
    if active:
        return "active"
    if released:
        return "released"
    return "off"


def _hold_detail_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return bool(value)


def _hold_detail_key_from_field(field_name: Any) -> Optional[str]:
    field = str(field_name or "").strip()
    if not field.startswith("holds_"):
        return None
    if field in _hold_detail_keys():
        return field
    for suffix in ("_pending", "_failed", "_released"):
        if field.endswith(suffix):
            base = field[: -len(suffix)]
            if base in _hold_detail_keys():
                return base
    return None


def _hold_detail_keys_from_sources(raw_sources: Any) -> set[str]:
    keys: set[str] = set()
    allowed = _hold_detail_keys()
    values = raw_sources if isinstance(raw_sources, list) else [raw_sources]
    for raw in values:
        token = str(raw or "").strip()
        if not token:
            continue
        candidates = [token]
        candidates.extend(part for part in token.replace(",", " ").split() if part)
        for candidate in candidates:
            mapped = hold_field_for_source(candidate)
            if mapped and mapped in allowed:
                keys.add(mapped)
    return keys


def _hold_detail_event_state(action: str, status: str, *, enable: Optional[bool] = None) -> str:
    a = str(action or "").strip().lower()
    s = str(status or "").strip().lower()

    if a.startswith(("slack_hold_sync", "hold_source_sync")):
        if a.endswith("_failed"):
            return "failed"
        if a.endswith("_attempt"):
            return "pending"
        return "active" if bool(enable) else "released"

    if "failed" in a:
        return "failed"
    if "retry" in a or a.endswith("_attempt"):
        return "pending"

    if "release" in a:
        if s in {"error", "failed"}:
            return "failed"
        if s in {"released", "hold_deleted", "not_found", "no_hold", "no_case", "no_case_id", "no_custodians"}:
            return "released"
        return "released"

    if "apply" in a:
        if s in {"on_hold", "already_on_hold"}:
            return "active"
        if s in {"pending"}:
            return "pending"
        if s in {"partial_hold"}:
            return "active"
        if s in {"onedrive_missing"}:
            return "pending"
        if s in {"error", "missing_email", "not_found"}:
            return "failed"
        return "active"

    return "info"


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


def build_case_holds_detail(*, case_id: int, limit: int, db: Session, actor: models.User) -> dict[str, Any]:
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ensure_case_visible(case, actor, db)

    custodians = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id)
        .order_by(
            func.lower(func.coalesce(models.Custodian.name, "")),
            func.lower(func.coalesce(models.Custodian.email, "")),
            models.Custodian.id.asc(),
        )
        .all()
    )

    def _coerce_int(value: Any) -> Optional[int]:
        try:
            if value is None:
                return None
            text_value = str(value).strip()
            if not text_value:
                return None
            return int(text_value)
        except Exception:
            return None

    def _email_key(value: Any) -> str:
        return (str(value or "").strip().lower())

    custodian_id_by_email: dict[str, int] = {}
    rows_by_id: dict[int, dict[str, Any]] = {}
    for cust in custodians:
        cid = _coerce_int(getattr(cust, "id", None))
        if cid is None:
            continue
        email_norm = _email_key(getattr(cust, "email", None))
        if email_norm and email_norm not in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()} and email_norm not in custodian_id_by_email:
            custodian_id_by_email[email_norm] = cid

        current_holds: list[dict[str, Any]] = []
        for item in _hold_detail_meta():
            key = item["key"]
            active = bool(getattr(cust, key, False))
            pending = bool(getattr(cust, f"{key}_pending", False))
            failed = bool(getattr(cust, f"{key}_failed", False))
            released = bool(getattr(cust, f"{key}_released", False))
            current_holds.append(
                {
                    "key": key,
                    "label": item["label"],
                    "state": _hold_detail_state(active=active, pending=pending, failed=failed, released=released),
                    "active": active,
                    "pending": pending,
                    "failed": failed,
                    "released": released,
                    "last_event_at": None,
                    "last_event_action": None,
                    "last_event_actor": None,
                    "last_event_summary": None,
                }
            )

        row = {
            "id": cid,
            "name": (getattr(cust, "name", None) or "").strip(),
            "email": (getattr(cust, "email", None) or "").strip(),
            "current_holds": current_holds,
            "timeline": [],
            "event_count": 0,
            "last_activity_at": None,
        }
        rows_by_id[cid] = row

    if not rows_by_id:
        return {
            "case_id": case_id,
            "case_name": getattr(case, "name", None),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": {"custodians": 0, "events": 0},
            "custodians": [],
        }

    hold_actions = [
        "custodian_update",
        "purview_hold_apply_attempt",
        "purview_hold_apply",
        "purview_hold_apply_failed",
        "purview_hold_release",
        "purview_hold_release_failed",
        "purview_hold_auto_apply",
        "purview_hold_auto_apply_retry",
        "purview_hold_auto_apply_failed",
        "preservation_hold_auto_apply",
        "preservation_hold_auto_apply_retry",
        "preservation_hold_auto_apply_failed",
        "slack_hold_sync_attempt",
        "slack_hold_sync",
        "slack_hold_sync_failed",
        "hold_source_sync_attempt",
        "hold_source_sync",
        "hold_source_sync_failed",
    ]

    action_sql = ", ".join([f"'{action}'" for action in hold_actions])
    sql = text(
        f"""
        WITH cust AS (
            SELECT id FROM custodians WHERE case_id = :case_id
        )
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
         WHERE ev.action IN ({action_sql})
           AND (
                (ev.target_type = 'case' AND ev.target_id = :case_id)
             OR (ev.target_type = 'custodian' AND ev.target_id IN (SELECT id FROM cust))
             OR (
                    (ev.details->>'case_id') ~ '^[0-9]+$'
                AND (ev.details->>'case_id')::integer = :case_id
             )
           )
         ORDER BY ev.created_at DESC, ev.id DESC
         LIMIT :limit
        """
    )
    events = db.execute(sql, {"case_id": case_id, "limit": int(limit)}).mappings().all()

    latest_by_hold: dict[tuple[int, str], tuple[datetime, int, dict[str, Any]]] = {}

    def _record_event(
        *,
        custodian_id: int,
        hold_key: str,
        row: dict[str, Any],
        state: str,
        summary: str,
        message: Optional[str] = None,
        details_payload: Any = None,
    ) -> None:
        target = rows_by_id.get(int(custodian_id))
        if not target:
            return
        if hold_key not in _hold_detail_keys():
            return

        created_at = row.get("created_at")
        event_id = _coerce_int(row.get("id")) or 0
        action = str(row.get("action") or "").strip()
        actor_name = (str(row.get("username") or "").strip() or None)

        event = {
            "id": event_id,
            "created_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
            "action": action,
            "actor_id": _coerce_int(row.get("actor_id")),
            "actor": actor_name,
            "hold_key": hold_key,
            "hold_label": _hold_detail_label_by_key().get(hold_key) or hold_key,
            "state": state,
            "summary": (summary or "").strip() or action,
            "message": (message or "").strip() or None,
            "details": details_payload,
            "_sort_created": created_at if isinstance(created_at, datetime) else datetime.min.replace(tzinfo=timezone.utc),
            "_sort_id": event_id,
        }
        target["timeline"].append(event)

        sig = (int(custodian_id), hold_key)
        prior = latest_by_hold.get(sig)
        cur_key = (event["_sort_created"], event["_sort_id"])
        prev_key = (prior[0], prior[1]) if prior else None
        if prev_key is None or cur_key > prev_key:
            latest_by_hold[sig] = (event["_sort_created"], event["_sort_id"], event)

    for row in events or []:
        raw_details = _parse_details(row.get("details"))
        details = raw_details if isinstance(raw_details, dict) else {}
        action = str(row.get("action") or "").strip().lower()

        requested_keys = _hold_detail_keys_from_sources(details.get("requested_sources"))
        requested_keys.update(_hold_detail_keys_from_sources(details.get("sources")))
        if action.startswith("slack_hold_sync"):
            requested_keys.add("holds_slack")
        if action.startswith("hold_source_sync"):
            source_field = hold_field_for_source(details.get("source_key"))
            if source_field:
                requested_keys.add(source_field)
        if action.startswith(("purview_hold", "preservation_hold")) and not requested_keys:
            requested_keys.update({"holds_email", "holds_onedrive"})

        candidate_ids: set[int] = set()
        direct_id = _coerce_int(details.get("custodian_id"))
        if direct_id is not None and direct_id in rows_by_id:
            candidate_ids.add(direct_id)
        if str(row.get("target_type") or "").strip().lower() == "custodian":
            target_id = _coerce_int(row.get("target_id"))
            if target_id is not None and target_id in rows_by_id:
                candidate_ids.add(target_id)
        if isinstance(details.get("custodian_ids"), list):
            for cid_value in details.get("custodian_ids"):
                cid = _coerce_int(cid_value)
                if cid is not None and cid in rows_by_id:
                    candidate_ids.add(cid)

        if action == "custodian_update":
            changes = details.get("changes") if isinstance(details.get("changes"), dict) else {}
            if not changes:
                continue

            grouped_changes: dict[str, dict[str, Any]] = {}
            for field_name, diff in changes.items():
                hold_key = _hold_detail_key_from_field(field_name)
                if not hold_key:
                    continue

                field = str(field_name or "").strip()
                old_value = diff.get("old") if isinstance(diff, dict) else None
                new_value = diff.get("new") if isinstance(diff, dict) else None

                bucket = grouped_changes.get(hold_key)
                if bucket is None:
                    bucket = {
                        "changes": [],
                        "new_flags": {},
                    }
                    grouped_changes[hold_key] = bucket

                bucket["changes"].append({"field": field, "old": old_value, "new": new_value})

                if field == hold_key:
                    bucket["new_flags"]["active"] = _hold_detail_bool(new_value)
                elif field.endswith("_pending"):
                    bucket["new_flags"]["pending"] = _hold_detail_bool(new_value)
                elif field.endswith("_failed"):
                    bucket["new_flags"]["failed"] = _hold_detail_bool(new_value)
                elif field.endswith("_released"):
                    bucket["new_flags"]["released"] = _hold_detail_bool(new_value)

            if not grouped_changes:
                continue

            target_ids = list(candidate_ids)
            if not target_ids:
                inferred = _coerce_int(details.get("custodian_id"))
                if inferred is not None and inferred in rows_by_id:
                    target_ids = [inferred]
            if not target_ids:
                continue

            for hold_key, bucket in grouped_changes.items():
                new_flags = bucket.get("new_flags") or {}
                if new_flags.get("failed") is True:
                    state = "failed"
                elif new_flags.get("pending") is True:
                    state = "pending"
                elif new_flags.get("active") is True:
                    state = "active"
                elif new_flags.get("released") is True:
                    state = "released"
                elif new_flags.get("active") is False:
                    state = "off"
                else:
                    state = "info"

                changes = [
                    item
                    for item in (bucket.get("changes") or [])
                    if isinstance(item, dict) and str(item.get("field") or "").strip()
                ]
                # Suppress transitional "pending -> false" noise when the same update also sets the hold active.
                if new_flags.get("active") is True:
                    changes = [
                        item
                        for item in changes
                        if not (
                            str(item.get("field") or "").strip().endswith("_pending")
                            and _hold_detail_bool(item.get("new")) is False
                        )
                    ]
                if not changes:
                    continue

                parts = [
                    f"{str(item.get('field')).strip()}: {item.get('old')} -> {item.get('new')}"
                    for item in changes
                ]
                summary = " | ".join(parts[:4])
                if len(parts) > 4:
                    summary = f"{summary} | +{len(parts) - 4} more"

                payload = {
                    "changes": changes,
                    "raw_details": raw_details,
                }

                for cid in target_ids:
                    _record_event(
                        custodian_id=cid,
                        hold_key=hold_key,
                        row=row,
                        state=state,
                        summary=summary,
                        details_payload=payload,
                    )
            continue

        results = details.get("results") if isinstance(details.get("results"), list) else []
        if results:
            for item in results:
                if not isinstance(item, dict):
                    continue
                cid = _coerce_int(item.get("custodian_id"))
                if cid is None:
                    cid = _coerce_int(item.get("id"))
                if cid is None:
                    item_email = _email_key(item.get("email") or item.get("custodian_email"))
                    if item_email:
                        cid = custodian_id_by_email.get(item_email)
                if cid is None or cid not in rows_by_id:
                    continue

                item_keys = set(requested_keys)
                if _hold_detail_bool(item.get("mailbox")):
                    item_keys.add("holds_email")
                if _hold_detail_bool(item.get("site")):
                    item_keys.add("holds_onedrive")
                if not item_keys and action.startswith(("purview_hold", "preservation_hold")):
                    item_keys.update({"holds_email", "holds_onedrive"})
                if not item_keys and action.startswith("slack_hold"):
                    item_keys.add("holds_slack")
                if not item_keys:
                    continue

                status = str(item.get("status") or "").strip().lower()
                state = _hold_detail_event_state(action, status, enable=details.get("enable"))
                message = (str(item.get("message") or "").strip() or None)
                summary = (
                    status.replace("_", " ").strip().title()
                    if status
                    else str(row.get("action") or "").replace("_", " ").title()
                )
                payload = {
                    "result": item,
                    "requested_sources": sorted(requested_keys),
                    "release_mode": details.get("release_mode"),
                    "raw_details": raw_details,
                }
                for key in sorted(item_keys):
                    _record_event(
                        custodian_id=cid,
                        hold_key=key,
                        row=row,
                        state=state,
                        summary=summary,
                        message=message,
                        details_payload=payload,
                    )
            continue

        if not candidate_ids:
            continue

        status_text = str(details.get("status") or details.get("reason") or "").strip().lower()
        state = _hold_detail_event_state(action, status_text, enable=details.get("enable"))
        summary = str(row.get("action") or "").replace("_", " ").strip().title()
        message = (str(details.get("error") or "").strip() or None)
        payload = {
            "requested_sources": sorted(requested_keys),
            "release_mode": details.get("release_mode"),
            "status_counts": details.get("status_counts"),
            "raw_details": raw_details,
        }
        keys = set(requested_keys)
        if action.startswith(("purview_hold", "preservation_hold")) and not keys:
            keys.update({"holds_email", "holds_onedrive"})
        if action.startswith("slack_hold"):
            keys.add("holds_slack")
        if not keys:
            continue
        for cid in sorted(candidate_ids):
            for key in sorted(keys):
                _record_event(
                    custodian_id=cid,
                    hold_key=key,
                    row=row,
                    state=state,
                    summary=summary,
                    message=message,
                    details_payload=payload,
                )

    total_events = 0
    out_rows: list[dict[str, Any]] = []
    for cid, row in rows_by_id.items():
        timeline = row.get("timeline") or []
        timeline.sort(
            key=lambda item: (
                item.get("_sort_created") or datetime.min.replace(tzinfo=timezone.utc),
                item.get("_sort_id") or 0,
            ),
            reverse=True,
        )

        for hold in row.get("current_holds") or []:
            key = hold.get("key")
            latest = latest_by_hold.get((cid, key)) if key else None
            if not latest:
                continue
            event = latest[2]
            hold["last_event_at"] = event.get("created_at")
            hold["last_event_action"] = event.get("action")
            hold["last_event_actor"] = event.get("actor")
            hold["last_event_summary"] = event.get("summary")

        if timeline:
            row["last_activity_at"] = timeline[0].get("created_at")

        for item in timeline:
            item.pop("_sort_created", None)
            item.pop("_sort_id", None)

        row["event_count"] = len(timeline)
        total_events += len(timeline)
        out_rows.append(row)

    out_rows.sort(
        key=lambda item: (
            str(item.get("name") or item.get("email") or "").lower(),
            int(item.get("id") or 0),
        )
    )

    return {
        "case_id": case_id,
        "case_name": getattr(case, "name", None),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "custodians": len(out_rows),
            "events": total_events,
        },
        "custodians": out_rows,
    }