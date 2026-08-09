from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import bindparam, func, text

from .database import SessionLocal, engine
from .models import Case, CaseConsent, CaseNote, CaseRequestConsentProof, Custodian, NTPTemplate
from .system_settings import load_system_settings, save_system_settings

STARTUP_BACKFILL_SETTINGS_KEY = "startup_backfills"
STARTUP_MAINTENANCE_SETTINGS_KEY = "startup_maintenance"
try:
    STARTUP_BACKFILL_VERSION = int(os.getenv("STARTUP_BACKFILL_VERSION", "1") or "1")
except Exception:
    STARTUP_BACKFILL_VERSION = 1
try:
    STARTUP_MAINTENANCE_VERSION = int(os.getenv("STARTUP_MAINTENANCE_VERSION", "1") or "1")
except Exception:
    STARTUP_MAINTENANCE_VERSION = 1

def _to_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    try:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except Exception:
        return None


def _backfill_case_note_counters() -> None:
    try:
        with SessionLocal() as _db:
            audience_expr = func.coalesce(CaseNote.audience, "internal")
            rows = (
                _db.query(
                    CaseNote.case_id,
                    audience_expr.label("audience"),
                    func.count(CaseNote.id).label("count"),
                )
                .group_by(CaseNote.case_id, audience_expr)
                .all()
            )
            counts_by_case: dict[int, dict[str, int]] = {}
            for case_id, audience, count in rows:
                try:
                    cid = int(case_id)
                except Exception:
                    continue
                bucket = counts_by_case.setdefault(cid, {"internal": 0, "requestor": 0, "ticket": 0})
                key = str(audience or "internal").strip().lower() or "internal"
                if key not in bucket:
                    continue
                try:
                    bucket[key] = int(count or 0)
                except Exception:
                    bucket[key] = 0

            updated = 0
            for case in _db.query(Case).all():
                expected = counts_by_case.get(
                    int(getattr(case, "id", 0) or 0),
                    {"internal": 0, "requestor": 0, "ticket": 0},
                )
                cur_internal = int(getattr(case, "notes_internal_count", 0) or 0)
                cur_requestor = int(getattr(case, "notes_requestor_count", 0) or 0)
                cur_ticket = int(getattr(case, "notes_ticket_count", 0) or 0)
                if (
                    cur_internal == expected["internal"]
                    and cur_requestor == expected["requestor"]
                    and cur_ticket == expected["ticket"]
                ):
                    continue
                case.notes_internal_count = expected["internal"]
                case.notes_requestor_count = expected["requestor"]
                case.notes_ticket_count = expected["ticket"]
                updated += 1

            if updated:
                _db.commit()
                print(f"[bootstrap] case note counters backfill updated={updated}")
    except Exception as _e:
        print(f"[bootstrap] case note counters backfill skipped: {_e}")




def _backfill_case_documentation_counters() -> None:
    try:
        with SessionLocal() as _db:
            consent_rows = (
                _db.query(CaseConsent.case_id, func.count(CaseConsent.id))
                .filter(CaseConsent.case_id.isnot(None))
                .group_by(CaseConsent.case_id)
                .all()
            )
            proof_rows = (
                _db.query(CaseRequestConsentProof.case_id, func.count(CaseRequestConsentProof.id))
                .filter(CaseRequestConsentProof.case_id.isnot(None))
                .group_by(CaseRequestConsentProof.case_id)
                .all()
            )
            consent_map = {}
            for case_id, count in consent_rows:
                try:
                    consent_map[int(case_id)] = int(count or 0)
                except Exception:
                    continue
            proof_map = {}
            for case_id, count in proof_rows:
                try:
                    proof_map[int(case_id)] = int(count or 0)
                except Exception:
                    continue

            updated = 0
            for case in _db.query(Case).all():
                cid = int(getattr(case, "id", 0) or 0)
                expected_consents = int(consent_map.get(cid, 0) or 0)
                expected_proofs = int(proof_map.get(cid, 0) or 0)
                current_consents = int(getattr(case, "consent_envelope_count", 0) or 0)
                current_proofs = int(getattr(case, "consent_proof_count", 0) or 0)
                if current_consents == expected_consents and current_proofs == expected_proofs:
                    continue
                case.consent_envelope_count = expected_consents
                case.consent_proof_count = expected_proofs
                updated += 1

            if updated:
                _db.commit()
                print(f"[bootstrap] case documentation counters backfill updated={updated}")
    except Exception as _e:
        print(f"[bootstrap] case documentation counters backfill skipped: {_e}")

def _backfill_custodian_added_at() -> None:
    try:
        with SessionLocal() as _db:
            missing = _db.query(Custodian).filter(Custodian.added_at.is_(None)).all()
            if not missing:
                return

            ids: list[int] = []
            for row in missing:
                try:
                    cid = int(getattr(row, "id", 0) or 0)
                except Exception:
                    cid = 0
                if cid > 0:
                    ids.append(cid)

            audit_map: dict[int, datetime] = {}
            if ids:
                stmt = text(
                    """
                    SELECT target_id AS custodian_id, MIN(created_at) AS added_at
                      FROM audit_events
                     WHERE target_type = 'custodian'
                       AND action = 'custodian_create'
                       AND target_id IN :custodian_ids
                     GROUP BY target_id
                    """
                ).bindparams(bindparam("custodian_ids", expanding=True))
                chunk_size = 1000
                for start in range(0, len(ids), chunk_size):
                    chunk = ids[start:start + chunk_size]
                    if not chunk:
                        continue
                    rows = _db.execute(stmt, {"custodian_ids": chunk}).mappings().all()
                    for item in rows or []:
                        try:
                            cid = int(item.get("custodian_id"))
                        except Exception:
                            continue
                        added_at = item.get("added_at")
                        if added_at is None:
                            continue
                        prior = audit_map.get(cid)
                        if prior is None or added_at < prior:
                            audit_map[cid] = added_at

            case_ids_set: set[int] = set()
            for row in missing:
                try:
                    case_id = int(getattr(row, "case_id", 0) or 0)
                except Exception:
                    case_id = 0
                if case_id > 0:
                    case_ids_set.add(case_id)
            case_ids = sorted(case_ids_set)
            case_created_map: dict[int, datetime] = {}
            if case_ids:
                rows = _db.query(Case.id, Case.created_at).filter(Case.id.in_(case_ids)).all()
                for case_id, created_at in rows:
                    try:
                        cid = int(case_id)
                    except Exception:
                        continue
                    created_utc = _to_utc_datetime(created_at)
                    if created_utc is not None:
                        case_created_map[cid] = created_utc

            window = timedelta(hours=48)
            updated = 0
            for row in missing:
                try:
                    cid = int(getattr(row, "id", 0) or 0)
                except Exception:
                    cid = 0
                added_at = audit_map.get(cid)
                if added_at is None:
                    try:
                        case_id = int(getattr(row, "case_id", 0) or 0)
                    except Exception:
                        case_id = 0
                    case_created = case_created_map.get(case_id)
                    created_at_utc = _to_utc_datetime(getattr(row, "created_at", None))
                    if case_created is not None and created_at_utc is not None:
                        if abs((created_at_utc - case_created).total_seconds()) <= window.total_seconds():
                            added_at = getattr(row, "created_at", None)
                if added_at is None:
                    continue
                setattr(row, "added_at", added_at)
                updated += 1

            if updated:
                _db.commit()
                print(f"[bootstrap] custodian added_at backfill updated={updated}")
    except Exception as _e:
        print(f"[bootstrap] custodian added_at backfill skipped: {_e}")


def _startup_backfills_state_current() -> bool:
    try:
        settings = load_system_settings()
        payload = settings.get(STARTUP_BACKFILL_SETTINGS_KEY) or {}
        return int(payload.get("version", 0) or 0) == int(STARTUP_BACKFILL_VERSION)
    except Exception:
        return False


def _mark_startup_backfills_state_current() -> None:
    try:
        settings = load_system_settings()
        settings[STARTUP_BACKFILL_SETTINGS_KEY] = {
            "version": int(STARTUP_BACKFILL_VERSION),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_system_settings(settings)
    except Exception as exc:
        print(f"[bootstrap] startup backfill state write skipped: {exc}")


def run_startup_backfills_once() -> None:
    if _startup_backfills_state_current():
        return
    _backfill_custodian_added_at()
    _backfill_case_note_counters()
    _backfill_case_documentation_counters()
    _mark_startup_backfills_state_current()


def _parse_email_csv(value: Optional[str]) -> list[str]:
    addresses: list[str] = []
    if not value:
        return addresses
    for part in value.split(","):
        addr = (part or "").strip()
        if addr:
            addresses.append(addr)
    return addresses


def _normalize_ntp_template_bcc_storage(existing: Optional[str]) -> str:
    try:
        settings = load_system_settings()
    except Exception:
        settings = {}
    ntp_settings = settings.get("ntp") if isinstance(settings.get("ntp"), dict) else {}
    reserved_value = str(ntp_settings.get("reserved_archive_bcc_addresses") or "").strip()
    if not settings.get("initial_setup_completed") and not reserved_value:
        reserved_value = os.getenv("NTP_TEMPLATE_BCC_RESERVED_ADDRESSES") or ""
    reserved = {addr.lower() for addr in _parse_email_csv(reserved_value)}
    merged: list[str] = []
    seen: set[str] = set()
    for addr in _parse_email_csv(existing):
        key = addr.lower()
        if key in reserved:
            continue
        if key in seen:
            continue
        seen.add(key)
        merged.append(addr)
    return ", ".join(merged)


def _startup_maintenance_state_current() -> bool:
    try:
        settings = load_system_settings()
        payload = settings.get(STARTUP_MAINTENANCE_SETTINGS_KEY) or {}
        return int(payload.get("version", 0) or 0) == int(STARTUP_MAINTENANCE_VERSION)
    except Exception:
        return False


def _mark_startup_maintenance_state_current() -> None:
    try:
        settings = load_system_settings()
        settings[STARTUP_MAINTENANCE_SETTINGS_KEY] = {
            "version": int(STARTUP_MAINTENANCE_VERSION),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        save_system_settings(settings)
    except Exception as exc:
        print(f"[bootstrap] startup maintenance state write skipped: {exc}")


def run_startup_maintenance_once() -> None:
    if _startup_maintenance_state_current():
        return

    try:
        with SessionLocal() as _db:
            _rows = _db.query(NTPTemplate).all()
            _updated = 0
            for _row in _rows:
                _normalized_bcc = _normalize_ntp_template_bcc_storage(getattr(_row, "bcc", None))
                if (getattr(_row, "bcc", "") or "").strip() != _normalized_bcc:
                    _row.bcc = _normalized_bcc
                    _updated += 1
            if _updated:
                _db.commit()
    except Exception as _e:
        print(f"[bootstrap] ntp template bcc normalize skipped: {_e}")

    try:
        with engine.begin() as _conn:
            _conn.exec_driver_sql("""
                UPDATE case_request_consent_proofs AS proof
                   SET case_id = req.case_id
                  FROM case_requests AS req
                 WHERE proof.case_request_id = req.id
                   AND proof.case_id IS NULL
                   AND req.case_id IS NOT NULL;
            """)
            _conn.exec_driver_sql("""
                UPDATE case_request_consent_proofs AS proof
                   SET uploaded_by_id = req.requestor_id
                  FROM case_requests AS req
                 WHERE proof.case_request_id = req.id
                   AND proof.uploaded_by_id IS NULL
                   AND req.requestor_id IS NOT NULL;
            """)
    except Exception as _e:
        print(f"[bootstrap] consent proof backfill skipped: {_e}")

    try:
        with engine.begin() as _conn:
            _conn.exec_driver_sql("""
                ALTER TABLE users
                  ADD COLUMN IF NOT EXISTS user_theme VARCHAR(16);
                UPDATE users SET user_theme = COALESCE(NULLIF(user_theme, ''), 'light') WHERE user_theme IS NULL;
            """)
    except Exception as _e:
        print(f"[bootstrap] user_theme column ensure skipped: {_e}")

    try:
        with engine.begin() as _conn:
            _conn.exec_driver_sql("""
                ALTER TABLE session_tokens
                  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;
                UPDATE session_tokens SET last_seen_at = COALESCE(last_seen_at, NOW()) WHERE last_seen_at IS NULL;
            """)
    except Exception as _e:
        print(f"[bootstrap] session_tokens column ensure skipped: {_e}")

    try:
        with engine.begin() as _conn:
            _conn.exec_driver_sql("""
                ALTER TABLE cases
                  ADD COLUMN IF NOT EXISTS is_private BOOLEAN NOT NULL DEFAULT FALSE,
                  ADD COLUMN IF NOT EXISTS is_test_case BOOLEAN NOT NULL DEFAULT FALSE;
            """)
            _conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS requestor_groups (
                  id SERIAL PRIMARY KEY,
                  name VARCHAR(255) NOT NULL UNIQUE,
                  label VARCHAR(255) NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            _conn.exec_driver_sql("""
                CREATE INDEX IF NOT EXISTS ix_requestor_groups_name
                  ON requestor_groups (lower(name));
            """)
            _conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS requestor_group_access (
                  id SERIAL PRIMARY KEY,
                  source_group VARCHAR(255) NOT NULL,
                  target_group VARCHAR(255) NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """)
            _conn.exec_driver_sql("""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_requestor_group_access_source_target
                  ON requestor_group_access (lower(source_group), lower(target_group));
            """)
            _conn.exec_driver_sql("""
                CREATE INDEX IF NOT EXISTS ix_requestor_group_access_source
                  ON requestor_group_access (lower(source_group));
            """)
            _conn.exec_driver_sql("""
                CREATE INDEX IF NOT EXISTS ix_requestor_group_access_target
                  ON requestor_group_access (lower(target_group));
            """)
    except Exception as _e:
        print(f"[bootstrap] case privacy/group access ensure skipped: {_e}")

    _mark_startup_maintenance_state_current()