from __future__ import annotations

from typing import Optional, Dict, Any, Union

import ast
import gzip
import hashlib
import json
import logging
import os
import re
import shutil
from pathlib import Path
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum
from logging.handlers import RotatingFileHandler

from fastapi import Request
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from . import models

# Actions we actually persist to the audit_events table
BIG_ACTIONS = {
    "login",
    "login_failed",
    "login_success",
    "auth_login_success",
    "case_create",
    "case_consent_proof_upload",
    "case_consent_proof_download",
    "case_consent_proof_delete",
    "case_request_attachment_download",
    "case_request_consent_attachment_download",
    "case_request_consent_proof_download",
    "user_create",
    "user_update",
    "user_password_change",
    "user_admin_change",
    "user_delete",
    "case_close",
    "case_reopen",
    "case_delete",
    "consent_request_docusign",
    "consent_status_update_docusign",
    "consent_completed_email_sent",
    "consent_weekly_pending_email_sent",
    "account_review_email_sent",
    "search_delivery_reminder_email_sent",
    "purview_case_create",
    "purview_case_create_failed",
    "purview_hold_apply",
    "purview_hold_auto_apply",
    "purview_hold_auto_apply_failed",
    "purview_hold_auto_apply_retry",
    "purview_hold_release",
    "purview_hold_release_failed",
    "case_rename",
    "custodian_create",
    "custodian_create_failed",
    "custodian_update",
    "custodian_delete",
    "custodian_remove",
    "custodian_directory_create",
    "search_create",
    "search_update",
    "search_delete",
    "search_ai_suggest",
    "search_ai_suggest_failed",
    "note_update",
    "note_attachment_upload",
    "note_attachment_delete",
    "note_attachment_download",
    "note_delete",
    "case_update",
    "case_summary_view",
    "case_summary_email",
    "slack_hold_sync_attempt",
    "slack_hold_sync",
    "slack_hold_sync_failed",
    "case_request_submit",
    "case_request_approve",
    "case_request_approve_progress",
    "case_request_decline",
    "case_request_ticket",
    "case_request_ticket_persist_failed",
    "case_request_ticket_repaired",
    "case_request_cleanup",
    "logo_upload",
    "logo_select",
    "logo_delete",
    "backup_run",
    "backup_delete",
    "backup_download",
    "backup_restore",
    "case_import",
    "email_test",
    "system_notifications_update",
    "system_smtp_update",
    "system_ntp_update",
    "tool_email_convert",
    "ntp_reminder_email_sent",
    "ntp_template_create",
    "ntp_template_update",
    "ntp_template_delete",
    "ntp_email_sent",
    "ntp_acknowledged",
    "password_reset_link_request",
    "password_reset_link_complete",
    "password_reset_totp",
    "password_help_request",
    "registration_request_submit",
    "registration_request_approve",
    "registration_request_decline",
    "registration_request_complete",
    "upload_scan",
    "malware_upload_detected",
    "dashboard_update",
    "help_video_create",
    # Generic email sends (see app.emailer.send_email)
    "email_sent",
    # Case requestor notifications
    "requestor_hold_status_email",
    "log_ship_run",
    "log_ship_failed",
}


# ---- Audit file logger (size-based rotation, gzip) ----
_AUDIT_LOGGER_READY = False

def _debug_suppressed(context: str, exc: Exception) -> None:
    try:
        logging.getLogger(__name__).debug("%s: %s", context, exc, exc_info=True)
    except Exception:
        return



def _audit_log_dir() -> Path:
    # Prefer explicit AUDIT_LOG_DIR; otherwise follow LOG_DIR so operators don't have to configure both.
    return Path(os.getenv("AUDIT_LOG_DIR") or os.getenv("LOG_DIR") or "/app/logs")


def _audit_log_name() -> str:
    return os.getenv("AUDIT_LOG_FILE_NAME", "audit.log")


def _audit_max_mb() -> int:
    try:
        return int(os.getenv("AUDIT_LOG_MAX_MB", "100"))
    except Exception:
        return 100


def _audit_backups() -> int:
    try:
        return int(os.getenv("AUDIT_LOG_BACKUP_COUNT", "20"))
    except Exception:
        return 20


def _audit_level() -> int:
    try:
        lvl = os.getenv("AUDIT_LOG_LEVEL", "INFO").upper()
        return getattr(logging, lvl, logging.INFO)
    except Exception:
        return logging.INFO


def _ensure_audit_logger() -> logging.Logger:
    """Idempotently configure the 'audit' rotating file logger."""
    global _AUDIT_LOGGER_READY
    lg = logging.getLogger("audit")
    # Ensure audit events do not duplicate into root/app log handlers.
    lg.propagate = False
    if _AUDIT_LOGGER_READY:
        return lg

    try:
        log_dir = _audit_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / _audit_log_name()

        handler = RotatingFileHandler(
            log_path,
            maxBytes=_audit_max_mb() * 1024 * 1024,
            backupCount=_audit_backups(),
            encoding="utf-8",
        )

        def namer(name: str) -> str:
            # "audit.log.1" -> "audit.log.1.gz"
            return name + ".gz"

        def rotator(source: str, dest: str) -> None:
            # Gzip old log file
            try:
                with open(source, "rb") as sf, gzip.open(dest, "wb") as df:
                    shutil.copyfileobj(sf, df)
            finally:
                try:
                    os.remove(source)
                except FileNotFoundError:
                    pass

        handler.namer = namer
        handler.rotator = rotator
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        handler.setLevel(_audit_level())

        if not any(isinstance(h, RotatingFileHandler) for h in lg.handlers):
            lg.addHandler(handler)

        lg.setLevel(_audit_level())
        _AUDIT_LOGGER_READY = True
    except Exception as exc:
        # If logger setup fails, surface it so operators notice degraded auditing
        try:
            logging.getLogger(__name__).error("audit logger setup failed: %s", exc, exc_info=True)
        except Exception as exc:
            _debug_suppressed("suppressed audit exception", exc)

    return lg


def _extract_client_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        client = getattr(request, "client", None)
        if client and getattr(client, "host", None):
            return client.host
    except Exception as exc:
        _debug_suppressed("suppressed audit exception", exc)
    return None


def _extract_user_agent(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    try:
        return request.headers.get("user-agent")
    except Exception:
        return None


def _json_safe(value: Any, *, _depth: int = 0, _max_depth: int = 8) -> Any:
    """Convert arbitrary values into JSON-safe primitives/containers."""
    if _depth >= _max_depth:
        try:
            return str(value)
        except Exception:
            return repr(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date, time)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, timedelta):
        try:
            return value.total_seconds()
        except Exception:
            return str(value)

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, Enum):
        return _json_safe(value.value, _depth=_depth + 1, _max_depth=_max_depth)

    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return str(value)

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            try:
                key = str(k)
            except Exception:
                key = repr(k)
            out[key] = _json_safe(v, _depth=_depth + 1, _max_depth=_max_depth)
        return out

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v, _depth=_depth + 1, _max_depth=_max_depth) for v in value]

    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump", None)):
        try:
            return _json_safe(value.model_dump(), _depth=_depth + 1, _max_depth=_max_depth)
        except Exception:
            pass

    if hasattr(value, "dict") and callable(getattr(value, "dict", None)):
        try:
            return _json_safe(value.dict(), _depth=_depth + 1, _max_depth=_max_depth)
        except Exception:
            pass

    if isinstance(value, BaseException):
        return str(value)

    try:
        json.dumps(value)
        return value
    except Exception:
        try:
            return str(value)
        except Exception:
            return repr(value)


def _normalise_details_for_db(
    details: Optional[Union[Dict[str, Any], str, Any]]
) -> Optional[str]:
    """
    Convert the supplied details into a JSON string suitable for insertion
    into a Postgres JSON/JSONB column.
    """
    if details is None:
        return None

    safe = _json_safe(details)
    if isinstance(safe, (dict, list)):
        payload = safe
    elif isinstance(safe, str):
        payload = {"message": safe}
    else:
        payload = {"value": safe}

    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        try:
            return json.dumps({"value": str(payload)}, ensure_ascii=False)
        except Exception:
            return None


def _coerce_details_to_object(details: Optional[Union[Dict[str, Any], str, Any]]) -> Dict[str, Any]:
    if details is None:
        return {}
    safe = _json_safe(details)
    if isinstance(safe, dict):
        return safe
    if isinstance(safe, list):
        return {"items": safe}
    if isinstance(safe, str):
        return {"message": safe}
    return {"value": safe}

def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        s = str(value).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _enrich_details(
    db: Optional[Session],
    *,
    details: Optional[Union[Dict[str, Any], str, Any]],
    target_type: Optional[str],
    target_id: Optional[int],
) -> Optional[Union[Dict[str, Any], str, Any]]:
    """
    Ensure all audit rows include case/custodian context when available.

    This must never raise and should avoid heavy queries; it uses best-effort
    lookups only when a DB session is available.
    """
    d: Dict[str, Any] = _coerce_details_to_object(details)

    case_id = _as_int(d.get("case_id") or d.get("caseId"))
    custodian_id = _as_int(d.get("custodian_id") or d.get("custodianId"))

    # Infer IDs from the primary target when possible.
    target_type_norm = (target_type or "").strip().lower()
    if case_id is None and target_type_norm == "case":
        case_id = _as_int(target_id)
    if custodian_id is None and target_type_norm == "custodian":
        custodian_id = _as_int(target_id)

    # Best-effort target-based enrichment for common entity types.
    if db is not None and target_id is not None:
        try:
            if target_type_norm in {"consent", "case_consent", "caseconsent"}:
                consent = db.get(models.CaseConsent, target_id)
                if consent is not None:
                    if case_id is None:
                        case_id = _as_int(getattr(consent, "case_id", None))
                    if custodian_id is None:
                        custodian_id = _as_int(getattr(consent, "custodian_id", None))
                    if not d.get("custodian_name"):
                        d["custodian_name"] = getattr(consent, "custodian_name", None)
                    if not d.get("custodian_email"):
                        d["custodian_email"] = getattr(consent, "custodian_email", None)
            elif target_type_norm in {"case_request", "caserequest"}:
                req = db.get(models.CaseRequest, target_id)
                if req is not None and case_id is None:
                    case_id = _as_int(getattr(req, "case_id", None))
            elif target_type_norm in {"note", "case_note", "casenote"}:
                note = db.get(models.CaseNote, target_id)
                if note is not None and case_id is None:
                    case_id = _as_int(getattr(note, "case_id", None))
            elif target_type_norm in {"note_attachment", "case_note_attachment", "casenoteattachment"}:
                att = db.get(models.CaseNoteAttachment, target_id)
                if att is not None:
                    note_id = _as_int(getattr(att, "note_id", None))
                    d.setdefault("note_id", note_id)
                    if note_id is not None and case_id is None:
                        note = db.get(models.CaseNote, note_id)
                        if note is not None:
                            case_id = _as_int(getattr(note, "case_id", None))
        except Exception as exc:
            _debug_suppressed("suppressed audit exception", exc)

    custodian_row = None
    if db is not None and custodian_id is not None:
        try:
            custodian_row = db.get(models.Custodian, custodian_id)
        except Exception:
            custodian_row = None

    if custodian_row is not None:
        d.setdefault("custodian_id", custodian_id)
        if not d.get("custodian_name"):
            d["custodian_name"] = getattr(custodian_row, "name", None)
        if not d.get("custodian_email"):
            d["custodian_email"] = getattr(custodian_row, "email", None)
        if case_id is None:
            case_id = _as_int(getattr(custodian_row, "case_id", None))

    if case_id is not None:
        d.setdefault("case_id", case_id)

    if case_id is not None and not d.get("case_name") and db is not None:
        try:
            case_row = db.get(models.Case, case_id)
            if case_row is not None and getattr(case_row, "name", None):
                d["case_name"] = getattr(case_row, "name", None)
        except Exception as exc:
            _debug_suppressed("suppressed audit exception", exc)

    # If we have a case and an email but no custodian name, try a cheap lookup.
    if (
        db is not None
        and case_id is not None
        and not d.get("custodian_name")
        and custodian_id is None
        and isinstance(d.get("custodian_email"), str)
    ):
        email = (d.get("custodian_email") or "").strip().lower()
        if email and email not in {"no-email@unknown"}:
            try:
                cust = (
                    db.query(models.Custodian)
                    .filter(models.Custodian.case_id == case_id)
                    .filter(func.lower(models.Custodian.email) == email)
                    .first()
                )
                if cust is not None:
                    d.setdefault("custodian_id", getattr(cust, "id", None))
                    d.setdefault("custodian_name", getattr(cust, "name", None))
            except Exception as exc:
                _debug_suppressed("suppressed audit exception", exc)

    # Enrich bulk custodian lists (best-effort by id).
    if db is not None and isinstance(d.get("bulk_custodians"), list):
        bulk = d.get("bulk_custodians") or []
        ids: list[int] = []
        for item in bulk:
            if not isinstance(item, dict):
                continue
            if item.get("name"):
                continue
            cid = _as_int(item.get("id") or item.get("custodian_id"))
            if cid is not None:
                ids.append(cid)
        if ids:
            try:
                rows = db.query(models.Custodian).filter(models.Custodian.id.in_(list(set(ids)))).all()
                by_id = {getattr(r, "id", None): r for r in rows if getattr(r, "id", None) is not None}
                updated = []
                for item in bulk:
                    if not isinstance(item, dict):
                        updated.append(item)
                        continue
                    cid = _as_int(item.get("id") or item.get("custodian_id"))
                    if cid is not None and not item.get("name") and cid in by_id:
                        new_item = dict(item)
                        new_item["name"] = getattr(by_id[cid], "name", None)
                        if not new_item.get("email"):
                            new_item["email"] = getattr(by_id[cid], "email", None)
                        updated.append(new_item)
                    else:
                        updated.append(item)
                d["bulk_custodians"] = updated
            except Exception as exc:
                _debug_suppressed("suppressed audit exception", exc)

    return d



def _details_payload(details: Optional[Union[Dict[str, Any], str, Any]]) -> Optional[Any]:
    if details is None:
        return None
    safe = _json_safe(details)
    if isinstance(safe, (dict, list)):
        return safe
    if isinstance(safe, str):
        return {"message": safe}
    return {"value": safe}


def _coerce_event_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            s = str(value).strip()
        except Exception:
            return None
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if re.match(r".*[+-]\d{4}$", s):
            s = s[:-2] + ":" + s[-2:]
        candidates = [s]
        if "T" not in s and " " in s:
            first, rest = s.split(" ", 1)
            candidates.append(f"{first}T{rest}")
        dt = None
        for candidate in candidates:
            try:
                dt = datetime.fromisoformat(candidate)
                break
            except Exception:
                dt = None
        if dt is None:
            legacy_formats = (
                "%Y-%m-%d %H:%M:%S,%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S,%f",
                "%Y-%m-%dT%H:%M:%S",
            )
            for fmt in legacy_formats:
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except Exception:
                    dt = None
        if dt is None:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _timestamp_from_audit_prefix(prefix: str) -> Optional[datetime]:
    try:
        raw = str(prefix or "").strip()
    except Exception:
        return None
    if not raw:
        return None
    pieces = [p for p in raw.split() if p]
    candidates: list[str] = [raw]
    if len(pieces) >= 2:
        candidates.append(f"{pieces[0]} {pieces[1]}")
        candidates.append(f"{pieces[0]}T{pieces[1]}")
    if pieces:
        candidates.append(pieces[0])
    for candidate in candidates:
        dt = _coerce_event_time(candidate)
        if dt is not None:
            return dt
    return None


def _audit_event_hash(
    *,
    created_at: datetime,
    action: str,
    actor_id: Optional[int],
    target_type: Optional[str],
    target_id: Optional[int],
    details: Optional[Any],
    request_ip: Optional[str],
    user_agent: Optional[str],
) -> str:
    payload = {
        "created_at": created_at.astimezone(timezone.utc).isoformat(),
        "action": action,
        "actor_id": actor_id,
        "target_type": target_type,
        "target_id": target_id,
        "details": _details_payload(details),
        "request_ip": request_ip,
        "user_agent": user_agent,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _insert_audit_event(
    db: Session,
    *,
    created_at: datetime,
    action: str,
    actor_id: Optional[int],
    target_type: Optional[str],
    target_id: Optional[int],
    details: Optional[Any],
    request_ip: Optional[str],
    user_agent: Optional[str],
    event_hash: Optional[str] = None,
) -> bool:
    if db is None:
        return False
    details_for_db = _normalise_details_for_db(details)
    effective_hash = event_hash or _audit_event_hash(
        created_at=created_at,
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        details=details,
        request_ip=request_ip,
        user_agent=user_agent,
    )
    db.execute(
        text(
            """
            INSERT INTO audit_events (
                actor_id,
                action,
                target_type,
                target_id,
                details,
                request_ip,
                user_agent,
                created_at,
                event_hash
            )
            VALUES (
                :actor_id,
                :action,
                :target_type,
                :target_id,
                :details,
                :request_ip,
                :user_agent,
                :created_at,
                :event_hash
            )
            ON CONFLICT (event_hash) DO NOTHING
            """
        ),
        {
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "details": details_for_db,
            "request_ip": request_ip,
            "user_agent": user_agent,
            "created_at": created_at,
            "event_hash": effective_hash,
        },
    )
    db.commit()
    return True


def _iter_audit_log_paths(max_files: Optional[int] = None) -> list[Path]:
    log_dir = _audit_log_dir()
    name = _audit_log_name()
    if not log_dir.exists():
        return []
    current = log_dir / name
    candidates = [p for p in log_dir.glob(f"{name}*") if p.is_file()]
    ordered: list[Path] = []
    if current in candidates:
        ordered.append(current)
        candidates = [p for p in candidates if p != current]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    ordered.extend(candidates)
    if max_files is not None and max_files > 0:
        ordered = ordered[:max_files]
    return ordered


def _read_audit_lines(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            yield line


def _parse_audit_line(line: str) -> Optional[Dict[str, Any]]:
    try:
        raw = (line or "").strip()
    except Exception:
        return None
    if not raw:
        return None
    json_start = raw.find("{")
    if json_start < 0:
        return None
    prefix = raw[:json_start].strip()
    payload_text = raw[json_start:].strip()
    if not payload_text.startswith("{"):
        return None
    try:
        payload = json.loads(payload_text)
    except Exception:
        try:
            payload = ast.literal_eval(payload_text)
        except Exception:
            return None
    if not isinstance(payload, dict) or not payload.get("action"):
        return None
    created_at = _coerce_event_time(payload.get("created_at")) or _timestamp_from_audit_prefix(prefix)
    if created_at is None:
        return None
    actor_id = _as_int(payload.get("actor_id"))
    target_id = _as_int(payload.get("target_id"))
    target_type = payload.get("target_type")
    request_ip = payload.get("request_ip") or payload.get("ip")
    user_agent = payload.get("user_agent")
    details = payload.get("details")
    event_hash = payload.get("event_hash")
    if not event_hash:
        event_hash = _audit_event_hash(
            created_at=created_at,
            action=str(payload.get("action") or ""),
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            details=details,
            request_ip=request_ip,
            user_agent=user_agent,
        )
    return {
        "created_at": created_at,
        "action": str(payload.get("action") or ""),
        "actor_id": actor_id,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "request_ip": request_ip,
        "user_agent": user_agent,
        "event_hash": event_hash,
    }


def _audit_event_exists(
    db: Session,
    *,
    created_at: datetime,
    action: str,
    actor_id: Optional[int],
    target_type: Optional[str],
    target_id: Optional[int],
    details: Optional[Any],
    request_ip: Optional[str],
    user_agent: Optional[str],
) -> bool:
    details_for_db = _normalise_details_for_db(details)
    row = db.execute(
        text(
            """
            SELECT 1
              FROM audit_events
             WHERE action = :action
               AND COALESCE(actor_id, -1) = COALESCE(:actor_id, -1)
               AND COALESCE(target_type, '') = COALESCE(:target_type, '')
               AND COALESCE(target_id, -1) = COALESCE(:target_id, -1)
               AND COALESCE(request_ip, '') = COALESCE(:request_ip, '')
               AND COALESCE(user_agent, '') = COALESCE(:user_agent, '')
               AND created_at BETWEEN :created_from AND :created_to
               AND ((:details_is_null = TRUE AND details IS NULL) OR details = CAST(:details AS JSONB))
             LIMIT 1
            """
        ),
        {
            "action": action,
            "actor_id": actor_id,
            "target_type": target_type,
            "target_id": target_id,
            "request_ip": request_ip,
            "user_agent": user_agent,
            "created_from": created_at - timedelta(seconds=1),
            "created_to": created_at + timedelta(seconds=1),
            "details": details_for_db,
            "details_is_null": details_for_db is None,
        },
    ).scalar()
    return bool(row)


def sync_audit_file_to_db(
    db: Session,
    *,
    max_files: Optional[int] = None,
    max_lines: Optional[int] = None,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "paths": [],
        "scanned": 0,
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
    }
    if db is None:
        return summary
    seen_hashes: set[str] = set()
    for path in _iter_audit_log_paths(max_files=max_files):
        summary["paths"].append(str(path))
        try:
            iterator = _read_audit_lines(path)
        except Exception as exc:
            summary["failed"] += 1
            _debug_suppressed("audit sync open failed", exc)
            continue
        for line in iterator:
            if max_lines is not None and summary["scanned"] >= max_lines:
                return summary
            summary["scanned"] += 1
            parsed = _parse_audit_line(line)
            if not parsed:
                summary["skipped"] += 1
                continue
            event_hash = parsed.get("event_hash")
            if event_hash and event_hash in seen_hashes:
                summary["skipped"] += 1
                continue
            if event_hash:
                seen_hashes.add(event_hash)
            try:
                exists = False
                if event_hash:
                    exists = bool(
                        db.execute(
                            text("SELECT 1 FROM audit_events WHERE event_hash = :event_hash LIMIT 1"),
                            {"event_hash": event_hash},
                        ).scalar()
                    )
                if not exists:
                    exists = _audit_event_exists(
                        db,
                        created_at=parsed["created_at"],
                        action=parsed["action"],
                        actor_id=parsed["actor_id"],
                        target_type=parsed["target_type"],
                        target_id=parsed["target_id"],
                        details=parsed["details"],
                        request_ip=parsed["request_ip"],
                        user_agent=parsed["user_agent"],
                    )
                if exists:
                    summary["skipped"] += 1
                    continue
                _insert_audit_event(
                    db,
                    created_at=parsed["created_at"],
                    action=parsed["action"],
                    actor_id=parsed["actor_id"],
                    target_type=parsed["target_type"],
                    target_id=parsed["target_id"],
                    details=parsed["details"],
                    request_ip=parsed["request_ip"],
                    user_agent=parsed["user_agent"],
                    event_hash=event_hash,
                )
                summary["inserted"] += 1
            except Exception as exc:
                summary["failed"] += 1
                try:
                    db.rollback()
                except Exception as rollback_exc:
                    _debug_suppressed("audit sync rollback skipped", rollback_exc)
                _debug_suppressed("audit sync insert failed", exc)
    return summary


def log_event(
    db: Session,
    *,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    user_id: Optional[int] = None,
    actor_id: Optional[int] = None,
    target: Optional[int] = None,
    details: Optional[Union[Dict[str, Any], str, Any]] = None,
    request: Optional[Request] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Core audit helper.

    Always tries to:
      1. Write a JSON line to the rotating audit logfile.
      2. Insert the same event into audit_events for the Logs page.

    It must never raise; callers should treat it as fire-and-forget.
    """
    actor = actor_id or user_id
    if target_id is None and target is not None:
        target_id = target

    ip = ip or _extract_client_ip(request)
    user_agent = user_agent or _extract_user_agent(request)

    try:
        details = _enrich_details(db, details=details, target_type=target_type, target_id=target_id)
    except Exception as exc:
        _debug_suppressed("suppressed audit exception", exc)

    created_at = datetime.now(timezone.utc)
    details_payload = _details_payload(details)
    event_hash = _audit_event_hash(
        created_at=created_at,
        action=action,
        actor_id=actor,
        target_type=target_type,
        target_id=target_id,
        details=details_payload,
        request_ip=ip,
        user_agent=user_agent,
    )
    log_record: Dict[str, Any] = {
        "created_at": created_at.isoformat(),
        "event_hash": event_hash,
        "action": action,
        "actor_id": actor,
        "target_type": target_type,
        "target_id": target_id,
        "details": details_payload,
    }
    if ip:
        log_record["ip"] = ip
        log_record["request_ip"] = ip
    if user_agent:
        log_record["user_agent"] = user_agent

    try:
        lg = _ensure_audit_logger()
        lg.info(json.dumps(log_record, ensure_ascii=False))
    except Exception as exc:
        _debug_suppressed("audit file logging skipped", exc)

    if db is None:
        return

    try:
        _insert_audit_event(
            db,
            created_at=created_at,
            action=action,
            actor_id=actor,
            target_type=target_type,
            target_id=target_id,
            details=details_payload,
            request_ip=ip,
            user_agent=user_agent,
            event_hash=event_hash,
        )
    except Exception as exc:
        try:
            db.rollback()
        except Exception as rollback_exc:
            _debug_suppressed("audit rollback skipped", rollback_exc)
        try:
            logging.getLogger("audit").warning(
                "audit_event DB insert failed",
                exc_info=True,
            )
        except Exception as log_exc:
            _debug_suppressed("audit failure warning log skipped", log_exc)
        _debug_suppressed("audit DB insert failed", exc)
        return

