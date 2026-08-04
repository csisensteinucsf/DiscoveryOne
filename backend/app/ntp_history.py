import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session, selectinload

from . import models
from .auth import current_user as get_current_user
from .database import get_db
from . import ntp as ntp_core

router = APIRouter(prefix="/api", tags=["ntp"])


def _history_hold_context(
    db: Session,
    *,
    case_id: int,
    case_hold_id: Optional[int],
) -> tuple[Optional[models.CaseHold], List[models.HoldCustodian]]:
    if case_hold_id is None:
        return None, []
    hold = ntp_core.case_hold_or_404(db, case_id, case_hold_id)
    memberships = (
        db.query(models.HoldCustodian)
        .options(selectinload(models.HoldCustodian.custodian))
        .filter(models.HoldCustodian.hold_id == hold.id)
        .all()
    )
    return hold, memberships


@router.get("/cases/{case_id}/ntp/last_send")
def get_last_ntp_send(
    case_id: int,
    case_hold_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ntp_core.ensure_case_visible(case, user, db)
    hold, memberships = _history_hold_context(
        db,
        case_id=case_id,
        case_hold_id=case_hold_id,
    )
    membership_ids = [int(membership.id) for membership in memberships]

    row = db.execute(
        text(
            """
            SELECT ev.created_at, ev.details
              FROM audit_events ev
             WHERE ev.action = 'ntp_email_sent'
               AND ev.target_type = 'case'
               AND ev.target_id = :case_id
               AND (
                    :case_hold_id IS NULL
                    OR ev.details->>'hold_id' = CAST(:case_hold_id AS TEXT)
               )
             ORDER BY ev.created_at DESC, ev.id DESC
             LIMIT 1
            """
        ),
        {"case_id": int(case_id), "case_hold_id": int(case_hold_id) if case_hold_id is not None else None},
    ).mappings().first()
    details_raw = row.get("details") if row else None
    details: dict = {}
    if isinstance(details_raw, dict):
        details = details_raw
    elif isinstance(details_raw, (bytes, str)):
        try:
            details = json.loads(details_raw) if details_raw else {}
        except Exception:
            details = {}

    reminder_query = db.query(models.NTPReminder).filter(models.NTPReminder.case_id == int(case_id))
    if hold is not None:
        reminder_query = reminder_query.filter(models.NTPReminder.hold_custodian_id.in_(membership_ids))
    reminder = (
        reminder_query
        .order_by(models.NTPReminder.created_at.desc(), models.NTPReminder.id.desc())
        .first()
    )
    variables: dict = {}
    try:
        variables_raw = getattr(reminder, "variables", None) if reminder else None
        if isinstance(variables_raw, dict):
            variables = variables_raw
        else:
            variables = json.loads(variables_raw or "{}") if variables_raw is not None else {}
        if not isinstance(variables, dict):
            variables = {}
    except Exception:
        variables = {}

    return {
        "exists": bool(row),
        "hold_id": hold.id if hold is not None else None,
        "hold_name": hold.name if hold is not None else None,
        "sent_at": row.get("created_at").isoformat() if (row and row.get("created_at")) else None,
        "template_id": details.get("template_id"),
        "template_name": details.get("template_name"),
        "reminder_template_id": details.get("reminder_template_id"),
        "reminder_template_name": details.get("reminder_template_name"),
        "variables": variables,
    }



def _load_case_ntp_history_payload(
    case_id: int,
    db: Session,
    user: models.User,
    case_hold_id: Optional[int] = None,
) -> Dict[str, object]:
    case = db.get(models.Case, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    ntp_core.ensure_case_visible(case, user, db)
    hold, memberships = _history_hold_context(
        db,
        case_id=case_id,
        case_hold_id=case_hold_id,
    )
    membership_by_custodian = {
        int(membership.custodian_id): membership
        for membership in memberships
    }
    membership_ids = [int(membership.id) for membership in memberships]

    if hold is not None:
        custodian_rows = [membership.custodian for membership in memberships if membership.custodian is not None]
    else:
        custodian_rows = (
            db.query(models.Custodian)
            .filter(models.Custodian.case_id == int(case_id))
            .all()
        )
    custodian_by_id = {
        int(c.id): c
        for c in (custodian_rows or [])
        if getattr(c, "id", None) is not None
    }

    reminder_query = (
        db.query(models.NTPReminder)
        .options(selectinload(models.NTPReminder.template))
        .filter(models.NTPReminder.case_id == int(case_id))
    )
    if hold is not None:
        reminder_query = reminder_query.filter(models.NTPReminder.hold_custodian_id.in_(membership_ids))
    reminders = reminder_query.all()
    reminder_buckets: Dict[int, List[models.NTPReminder]] = {}
    for reminder in reminders or []:
        custodian_id = int(getattr(reminder, "custodian_id", 0) or 0)
        if custodian_id <= 0:
            continue
        reminder_buckets.setdefault(custodian_id, []).append(reminder)

    rows = db.execute(
        text(
            """
            SELECT ev.id, ev.action, ev.target_type, ev.target_id, ev.created_at, ev.details
              FROM audit_events ev
             WHERE ev.action IN ('ntp_email_sent', 'ntp_reminder_email_sent', 'ntp_acknowledged')
               AND (
                    (ev.target_type = 'case' AND ev.target_id = :case_id)
                 OR (
                        (ev.details->>'case_id') ~ '^[0-9]+$'
                    AND (ev.details->>'case_id')::integer = :case_id
                 )
               )
               AND (
                    :case_hold_id IS NULL
                    OR ev.details->>'hold_id' = CAST(:case_hold_id AS TEXT)
               )
             ORDER BY ev.created_at DESC, ev.id DESC
             LIMIT 2000
            """
        ),
        {"case_id": int(case_id), "case_hold_id": int(case_hold_id) if case_hold_id is not None else None},
    ).mappings().all()

    def _as_details(raw_value: object) -> dict:
        if isinstance(raw_value, dict):
            return raw_value
        if isinstance(raw_value, (bytes, str)):
            try:
                parsed = json.loads(raw_value) if raw_value else {}
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def _as_int(value: object) -> Optional[int]:
        try:
            if value is None:
                return None
            text_value = str(value).strip()
            if not text_value:
                return None
            return int(text_value)
        except Exception:
            return None

    def _coerce_dt(value: object) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                return None
        return None

    action_label = {
        "ntp_email_sent": "Initial NTP sent",
        "ntp_reminder_email_sent": "NTP reminder sent",
        "ntp_acknowledged": "NTP acknowledged",
    }

    events: List[Dict[str, object]] = []
    for row in rows or []:
        details = _as_details(row.get("details"))
        custodian_id = _as_int(details.get("custodian_id"))
        if custodian_id is None and (row.get("target_type") or "") == "custodian":
            custodian_id = _as_int(row.get("target_id"))
        custodian = custodian_by_id.get(int(custodian_id)) if custodian_id is not None else None

        custodian_name = (details.get("custodian_name") or "").strip() if isinstance(details.get("custodian_name"), str) else ""
        custodian_email = (details.get("custodian_email") or "").strip() if isinstance(details.get("custodian_email"), str) else ""
        if custodian is not None:
            if not custodian_name:
                custodian_name = getattr(custodian, "name", None) or ""
            if not custodian_email:
                custodian_email = getattr(custodian, "email", None) or ""

        action = (row.get("action") or "").strip()
        events.append({
            "id": row.get("id"),
            "action": action,
            "event_type": action_label.get(action) or action,
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
            "custodian_id": custodian_id,
            "custodian_name": custodian_name or None,
            "custodian_email": custodian_email or None,
            "template_id": _as_int(details.get("template_id")),
            "template_name": (details.get("template_name") or "").strip() if isinstance(details.get("template_name"), str) else None,
            "reminder_id": _as_int(details.get("reminder_id")),
            "token_id": _as_int(details.get("token_id")),
            "hold_id": _as_int(details.get("hold_id")) or (hold.id if hold is not None else None),
            "hold_name": (details.get("hold_name") or "").strip() if isinstance(details.get("hold_name"), str) else (hold.name if hold is not None else None),
        })

    custodian_summary: List[Dict[str, object]] = []
    for custodian in custodian_rows or []:
        custodian_id = int(getattr(custodian, "id", 0) or 0)
        if custodian_id <= 0:
            continue
        membership = membership_by_custodian.get(custodian_id)
        workflow = membership if membership is not None else custodian
        linked_reminders = list(reminder_buckets.get(custodian_id, []) or [])
        sorted_by_next = sorted(
            linked_reminders,
            key=lambda r: _coerce_dt(getattr(r, "next_send_at", None)) or datetime.max,
        )
        next_reminder = next(
            (r for r in sorted_by_next if str(getattr(r, "status", "") or "").strip().lower() == "active"),
            None,
        )
        sorted_by_last = sorted(
            linked_reminders,
            key=lambda r: _coerce_dt(getattr(r, "last_sent_at", None)) or datetime.min,
            reverse=True,
        )
        last_reminder = sorted_by_last[0] if sorted_by_last else None

        status_counts: Dict[str, int] = {}
        template_names = set()
        ntp_template_name = (getattr(workflow, "ntp_template_name", None) or "").strip()
        if ntp_template_name:
            template_names.add(ntp_template_name)
        for reminder in linked_reminders:
            status_key = str(getattr(reminder, "status", "active") or "active").strip().lower() or "active"
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
            reminder_template_name = (getattr(reminder, "template_name", None) or "").strip()
            if not reminder_template_name:
                template_row = getattr(reminder, "template", None)
                reminder_template_name = (getattr(template_row, "name", None) or "").strip() if template_row is not None else ""
            if reminder_template_name:
                template_names.add(reminder_template_name)

        has_activity = bool(
            getattr(workflow, "ntp_sent_at", None)
            or getattr(workflow, "ntp_acknowledged_at", None)
            or template_names
            or linked_reminders
            or str(getattr(workflow, "ntp_status", "") or "").strip().lower() in {"sent", "acknowledged"}
        )
        if not has_activity:
            continue

        reminder_summary = " | ".join(
            f"{status}: {count}" for status, count in sorted(status_counts.items())
        )

        custodian_summary.append({
            "id": custodian_id,
            "name": (getattr(custodian, "name", None) or "").strip(),
            "email": (getattr(custodian, "email", None) or "").strip(),
            "ntp_status": (getattr(workflow, "ntp_status", None) or "not sent").strip(),
            "ntp_template_name": ", ".join(sorted(template_names)),
            "ntp_sent_at": getattr(workflow, "ntp_sent_at", None).isoformat() if getattr(workflow, "ntp_sent_at", None) else None,
            "ntp_acknowledged_at": getattr(workflow, "ntp_acknowledged_at", None).isoformat() if getattr(workflow, "ntp_acknowledged_at", None) else None,
            "reminders_total": len(linked_reminders),
            "reminders_summary": reminder_summary,
            "next_reminder_at": getattr(next_reminder, "next_send_at", None).isoformat() if next_reminder and getattr(next_reminder, "next_send_at", None) else None,
            "last_reminder_sent_at": getattr(last_reminder, "last_sent_at", None).isoformat() if last_reminder and getattr(last_reminder, "last_sent_at", None) else None,
        })

    custodian_summary.sort(key=lambda row: (str(row.get("name") or row.get("email") or "").lower()))

    return {
        "case_id": int(case_id),
        "case_name": getattr(case, "name", None),
        "hold_id": hold.id if hold is not None else None,
        "hold_name": hold.name if hold is not None else None,
        "events": events,
        "custodian_summary": custodian_summary,
        "count": len(events),
    }


@router.get("/cases/{case_id}/ntp/history")
def get_case_ntp_history(
    case_id: int,
    case_hold_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return _load_case_ntp_history_payload(
        case_id=case_id,
        db=db,
        user=user,
        case_hold_id=case_hold_id,
    )



def _ntp_history_csv_response(filename: str, headers: List[str], rows: List[List[object]]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if value is None else str(value) for value in row])
    payload = buf.getvalue().encode("utf-8")
    stream = io.BytesIO(payload)
    return StreamingResponse(
        stream,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cases/{case_id}/ntp/history/export")
def export_case_ntp_history_csv(
    case_id: int,
    case_hold_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    payload = _load_case_ntp_history_payload(
        case_id=case_id,
        db=db,
        user=user,
        case_hold_id=case_hold_id,
    )
    case_name = str(payload.get("case_name") or f"case_{case_id}").strip() or f"case_{case_id}"
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    summary = payload.get("custodian_summary") if isinstance(payload.get("custodian_summary"), list) else []

    headers = [
        "record_type",
        "case_name",
        "custodian_name",
        "custodian_email",
        "ntp_status",
        "template_names",
        "ntp_sent_at",
        "ntp_acknowledged_at",
        "reminders_total",
        "reminders_summary",
        "next_reminder_at",
        "last_reminder_sent_at",
        "event_created_at",
        "event_type",
        "event_template_name",
        "event_details",
    ]
    csv_rows: List[List[object]] = []

    for row in summary:
        if not isinstance(row, dict):
            continue
        csv_rows.append([
            "summary",
            case_name,
            row.get("name") or "",
            row.get("email") or "",
            row.get("ntp_status") or "",
            row.get("ntp_template_name") or "",
            row.get("ntp_sent_at") or "",
            row.get("ntp_acknowledged_at") or "",
            row.get("reminders_total") or 0,
            row.get("reminders_summary") or "",
            row.get("next_reminder_at") or "",
            row.get("last_reminder_sent_at") or "",
            "",
            "",
            "",
            "",
        ])

    for event in events:
        if not isinstance(event, dict):
            continue
        detail_bits: List[str] = []
        if event.get("reminder_id"):
            detail_bits.append(f"Reminder #{event.get('reminder_id')}")
        if event.get("token_id"):
            detail_bits.append(f"Token #{event.get('token_id')}")
        csv_rows.append([
            "event",
            case_name,
            event.get("custodian_name") or "",
            event.get("custodian_email") or "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            event.get("created_at") or "",
            event.get("event_type") or event.get("action") or "",
            event.get("template_name") or "",
            " | ".join(detail_bits),
        ])

    name_parts = [case_name]
    if payload.get("hold_name"):
        name_parts.append(str(payload.get("hold_name")))
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", "_".join(name_parts)).strip("_") or f"case_{case_id}"
    filename = f"{safe_name}_ntp_history.csv"
    return _ntp_history_csv_response(filename=filename, headers=headers, rows=csv_rows)



def _resolve_actor_email_for_ntp_history_report(user: models.User) -> Optional[str]:
    direct = (getattr(user, "email", None) or "").strip()
    if direct and "@" in direct:
        return ntp_core._pretty_email_address(direct)
    fallback = (getattr(user, "username", None) or "").strip()
    if fallback and "@" in fallback:
        return ntp_core._pretty_email_address(fallback)
    return None



def _compose_ntp_history_report(payload: Dict[str, object]) -> str:
    case_name = str(payload.get("case_name") or payload.get("case_id") or "Case").strip() or "Case"
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    summary = payload.get("custodian_summary") if isinstance(payload.get("custodian_summary"), list) else []

    lines: List[str] = []
    hold_name = str(payload.get("hold_name") or "").strip()
    title = f"NTP History Report - {case_name}" + (f" - {hold_name}" if hold_name else "")
    lines.append(title)
    lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append(f"Custodian summary rows: {len(summary)}")
    lines.append(f"Timeline events: {len(events)}")
    lines.append("")
    lines.append("Custodian NTP summary:")
    if summary:
        for row in summary:
            if not isinstance(row, dict):
                continue
            custodian_name = str(row.get("name") or row.get("email") or "Custodian").strip()
            lines.append(
                "- "
                + custodian_name
                + f" | status={row.get('ntp_status') or 'not sent'}"
                + f" | sent={row.get('ntp_sent_at') or '-'}"
                + f" | ack={row.get('ntp_acknowledged_at') or '-'}"
                + f" | reminders={row.get('reminders_summary') or row.get('reminders_total') or 0}"
            )
    else:
        lines.append("- No custodian NTP activity found.")

    lines.append("")
    lines.append("NTP event timeline:")
    if events:
        for event in events:
            if not isinstance(event, dict):
                continue
            details: List[str] = []
            if event.get("reminder_id"):
                details.append(f"Reminder #{event.get('reminder_id')}")
            if event.get("token_id"):
                details.append(f"Token #{event.get('token_id')}")
            detail_text = f" | details={' | '.join(details)}" if details else ""
            lines.append(
                "- "
                + f"{event.get('created_at') or '-'}"
                + f" | {event.get('event_type') or event.get('action') or '-'}"
                + f" | {event.get('custodian_name') or event.get('custodian_email') or 'Custodian'}"
                + f" | template={event.get('template_name') or '-'}"
                + detail_text
            )
    else:
        lines.append("- No NTP events found.")

    return "\n".join(lines)


@router.post("/cases/{case_id}/ntp/history/email")
def email_case_ntp_history_report(
    case_id: int,
    case_hold_id: Optional[int] = None,
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(get_current_user),
):
    payload = _load_case_ntp_history_payload(case_id=case_id, db=db, user=user, case_hold_id=case_hold_id)
    recipient = _resolve_actor_email_for_ntp_history_report(user)
    if not recipient:
        raise HTTPException(status_code=400, detail="Your account does not have an email address configured")

    case_name = str(payload.get("case_name") or f"Case {case_id}").strip() or f"Case {case_id}"
    hold_name = str(payload.get("hold_name") or "").strip()
    subject = f"[{ntp_core.app_display_name()}] NTP History Report - {case_name}" + (f" - {hold_name}" if hold_name else "")
    body = _compose_ntp_history_report(payload)
    try:
        ntp_core.send_email(recipients=[recipient], subject=subject, body=body)
    except Exception as exc:
        ntp_core.logger.exception("Failed to send NTP history email report")
        raise HTTPException(status_code=503, detail="Unable to send NTP history email report") from exc

    try:
        ntp_core.log_event(
            db,
            action="ntp_history_report_email",
            actor_id=getattr(user, "id", None),
            target_type="case",
            target_id=case_id,
            details={
                "case_id": int(case_id),
                "case_name": case_name,
                "hold_id": payload.get("hold_id"),
                "hold_name": payload.get("hold_name"),
                "recipient": recipient,
                "summary_rows": len(payload.get("custodian_summary") or []),
                "timeline_rows": len(payload.get("events") or []),
            },
            request=request,
        )
    except Exception as exc:
        ntp_core._debug_suppressed("suppressed exception in ntp.py:ntp_history_report_email", exc)

    return {"ok": True, "recipient": recipient}
