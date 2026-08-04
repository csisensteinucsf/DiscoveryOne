from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .cases import (
    NO_EMAIL_PLACEHOLDER,
    UNMATCHED_EMAIL_PLACEHOLDER,
    _derive_employment_status_from_end_date,
)
from .person_lookup_matching import (
    _build_lookup_display_name,
    _coerce_lookup_bool,
    _coerce_lookup_text,
    _normalize_lookup_email,
    _normalize_person_label,
    _rank_lookup_matches,
    _run_configured_person_lookup,
)
from .database import SessionLocal
from .identity_review import apply_custodian_name_email_review
from .person_lookup import (
    person_lookup_batch_session,
    person_lookup_enabled,
    person_lookup_provider_readiness_error,
)
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings, save_system_settings


logger = logging.getLogger(__name__)
_custodian_lookup_refresh_lock = threading.Lock()
_custodian_lookup_bootstrap_started = False


def lookup_matches_for_identity(
    name: str,
    *,
    cursor=None,
) -> tuple[list[dict], Optional[str]]:
    if not person_lookup_enabled():
        return ([], "Person lookup is not enabled.")

    matches, error = _run_configured_person_lookup(name, session=cursor)
    return (_rank_lookup_matches(name, matches or []), error)


def lookup_matches_for_query(
    query: str,
    *,
    email: Optional[str] = None,
    cursor=None,
) -> tuple[list[dict], Optional[str]]:
    if not person_lookup_enabled():
        return ([], "Person lookup is not enabled.")

    raw = (query or "").strip()
    explicit_email = _normalize_lookup_email(email)
    if not raw and not explicit_email:
        return ([], "Enter full name, email address or Employee ID for lookup.")

    matches, error = _run_configured_person_lookup(
        raw or explicit_email or "",
        email=explicit_email,
        session=cursor,
    )
    return (_rank_lookup_matches(explicit_email or raw, matches or []), error)

def apply_person_lookup_match_to_custodian(
    custodian: models.Custodian,
    match: dict,
    *,
    overwrite_name: bool = True,
    clear_override: bool = False,
    lookup_at: Optional[datetime] = None,
    use_ai_review: bool = False,
) -> None:
    if not custodian or not match:
        return
    display_name = _build_lookup_display_name(match)
    if overwrite_name and display_name:
        custodian.name = display_name

    matched_email = _coerce_lookup_text(match.get("email"))
    if matched_email:
        existing_email = (getattr(custodian, "email", None) or "").strip().lower()
        if (not existing_email) or existing_email in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
            custodian.email = matched_email

    custodian.employee_id = _coerce_lookup_text(match.get("external_id") or match.get("employee_id"))
    custodian.person_first_name = _coerce_lookup_text(match.get("first_name"))
    custodian.person_last_name = _coerce_lookup_text(match.get("last_name"))
    custodian.person_department_id = _coerce_lookup_text(match.get("department_id"))
    custodian.person_department = _coerce_lookup_text(match.get("department") or match.get("department_name"))
    custodian.person_title = _coerce_lookup_text(match.get("title") or match.get("job_title_official"))
    custodian.person_current_employee = _coerce_lookup_bool(match.get("current_employee"))

    end_date = _coerce_lookup_text(match.get("separation_date") or match.get("employee_end_date"))
    custodian.employment_end_date = end_date
    custodian.employment_status = _derive_employment_status_from_end_date(end_date)

    custodian.person_lookup_last_at = lookup_at or datetime.now(timezone.utc)
    apply_custodian_name_email_review(custodian, use_ai=use_ai_review)
    if clear_override:
        custodian.person_lookup_overridden = False


def custodian_lookup_identity_key(custodian: models.Custodian) -> Optional[tuple[str, str]]:
    email = (getattr(custodian, "email", None) or "").strip().lower()
    if email and email not in {NO_EMAIL_PLACEHOLDER.lower(), UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
        return ("email", email)
    name_key = _normalize_person_label(getattr(custodian, "name", None))
    if name_key:
        return ("name", name_key)
    return None


def custodian_lookup_snapshot(custodian: models.Custodian) -> tuple:
    return (
        getattr(custodian, "name", None),
        getattr(custodian, "email", None),
        getattr(custodian, "employment_end_date", None),
        getattr(custodian, "employment_status", None),
        getattr(custodian, "person_lookup_overridden", None),
        getattr(custodian, "name_email_review_required", None),
        getattr(custodian, "name_email_review_reason", None),
        getattr(custodian, "name_email_review_last_checked_at", None),
        getattr(custodian, "employee_id", None),
        getattr(custodian, "person_first_name", None),
        getattr(custodian, "person_last_name", None),
        getattr(custodian, "person_department_id", None),
        getattr(custodian, "person_department", None),
        getattr(custodian, "person_title", None),
        getattr(custodian, "person_current_employee", None),
    )


def persist_custodian_lookup_settings(summary: Dict[str, Any], *, mark_bootstrap_complete: bool = False) -> None:
    try:
        settings = load_system_settings()
        settings["custodian_lookup_last_run_at"] = summary.get("finished_at")
        if mark_bootstrap_complete and summary.get("status") == "completed":
            settings["custodian_lookup_bootstrap_completed"] = True
        save_system_settings(settings)
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_lookup_refresh.py:persist_settings", exc)


def run_full_custodian_lookup_update(
    db: Session,
    *,
    actor_id: Optional[int] = None,
    source: str = "manual",
    mark_bootstrap_complete: bool = False,
    request: Request = None,
    lookup_matches_for_identity_func: Callable[..., tuple[list[dict], Optional[str]]],
    pick_lookup_match: Callable[..., Optional[dict]],
    apply_match_to_custodian: Callable[..., None],
    apply_consent_defaults: Callable[..., None],
) -> Dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    summary: Dict[str, Any] = {
        "status": "pending",
        "source": source,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "records_total": 0,
        "identity_groups": 0,
        "lookups_attempted": 0,
        "lookups_matched": 0,
        "groups_updated": 0,
        "records_updated": 0,
        "groups_skipped_no_name": 0,
        "groups_skipped_ambiguous": 0,
        "errors": [],
    }

    with _custodian_lookup_refresh_lock:
        provider_error = person_lookup_provider_readiness_error()
        if not person_lookup_enabled():
            summary["status"] = "skipped"
            summary["message"] = "Person lookup is disabled."
        elif provider_error:
            summary["status"] = "skipped"
            summary["message"] = provider_error
        else:
            custodians = db.query(models.Custodian).all()
            summary["records_total"] = len(custodians)
            grouped: Dict[tuple[str, str], list[models.Custodian]] = {}
            for cust in custodians:
                key = custodian_lookup_identity_key(cust)
                if not key:
                    continue
                grouped.setdefault(key, []).append(cust)
            summary["identity_groups"] = len(grouped)

            case_ids = {int(c.case_id) for c in custodians if getattr(c, "case_id", None)}
            case_map: Dict[int, models.Case] = {}
            if case_ids:
                for case in db.query(models.Case).filter(models.Case.id.in_(list(case_ids))).all():
                    case_map[int(case.id)] = case

            try:
                with person_lookup_batch_session() as cursor:
                    for _, members in grouped.items():
                        if not members:
                            continue
                        representative = members[0]
                        for candidate in members:
                            if getattr(candidate, "person_lookup_last_at", None) and not getattr(representative, "person_lookup_last_at", None):
                                representative = candidate
                        display_name = (getattr(representative, "name", None) or "").strip()
                        if not display_name:
                            summary["groups_skipped_no_name"] += 1
                            continue

                        summary["lookups_attempted"] += 1
                        matches, err = lookup_matches_for_identity_func(display_name, cursor=cursor)
                        if err and not matches:
                            if len(summary["errors"]) < 50:
                                summary["errors"].append(f"{display_name}: {err}")
                            continue

                        match = pick_lookup_match(
                            matches=matches,
                            current_name=getattr(representative, "name", None),
                            current_email=getattr(representative, "email", None),
                        )
                        if not match:
                            if matches:
                                summary["groups_skipped_ambiguous"] += 1
                            continue

                        summary["lookups_matched"] += 1
                        group_changed = False
                        lookup_at = datetime.now(timezone.utc)
                        for cust in members:
                            before = custodian_lookup_snapshot(cust)
                            apply_match_to_custodian(
                                cust,
                                match,
                                overwrite_name=True,
                                clear_override=True,
                                lookup_at=lookup_at,
                            )
                            case_obj = case_map.get(int(getattr(cust, "case_id", 0) or 0))
                            if case_obj:
                                apply_consent_defaults(case_obj, cust)
                                from .hold_workflows import sync_custodian_not_required_policy_to_memberships

                                sync_custodian_not_required_policy_to_memberships(db, cust)
                            after = custodian_lookup_snapshot(cust)
                            if before != after:
                                group_changed = True
                                summary["records_updated"] += 1
                            db.add(cust)
                        if group_changed:
                            summary["groups_updated"] += 1

                db.commit()
                summary["status"] = "completed"
            except Exception as exc:
                db.rollback()
                summary["status"] = "failed"
                summary["message"] = str(exc)
                if len(summary["errors"]) < 50:
                    summary["errors"].append(str(exc))
                logger.exception("full_custodian_lookup_update_failed")

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    persist_custodian_lookup_settings(summary, mark_bootstrap_complete=mark_bootstrap_complete)
    try:
        log_event(
            db,
            action="custodian_full_lookup_update",
            actor_id=actor_id,
            target_type="system",
            target_id=None,
            details={
                "source": source,
                "status": summary.get("status"),
                "identity_groups": summary.get("identity_groups"),
                "lookups_attempted": summary.get("lookups_attempted"),
                "lookups_matched": summary.get("lookups_matched"),
                "groups_updated": summary.get("groups_updated"),
                "records_updated": summary.get("records_updated"),
                "groups_skipped_ambiguous": summary.get("groups_skipped_ambiguous"),
                "errors": summary.get("errors"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_lookup_refresh.py:log_event", exc)
    return summary


def run_custodian_lookup_bootstrap_once(runner: Callable[..., Dict[str, Any]]) -> None:
    db = SessionLocal()
    try:
        runner(
            db,
            actor_id=None,
            source="startup",
            mark_bootstrap_complete=True,
            request=None,
        )
    except Exception:
        logger.exception("custodian_lookup_bootstrap_failed")
    finally:
        try:
            db.close()
        except Exception as exc:
            _debug_suppressed("suppressed exception in case_request_lookup_refresh.py:bootstrap_db_close", exc)


def start_custodian_lookup_bootstrap(runner: Callable[..., Dict[str, Any]]) -> None:
    global _custodian_lookup_bootstrap_started
    if _custodian_lookup_bootstrap_started:
        return
    try:
        settings = load_system_settings()
        if bool(settings.get("custodian_lookup_bootstrap_completed")):
            _custodian_lookup_bootstrap_started = True
            return
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_lookup_refresh.py:start_bootstrap", exc)
    _custodian_lookup_bootstrap_started = True
    thread = threading.Thread(target=lambda: run_custodian_lookup_bootstrap_once(runner), daemon=True)
    thread.start()