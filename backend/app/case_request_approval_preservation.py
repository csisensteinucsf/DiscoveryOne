import time
from typing import Callable, Optional

from fastapi import HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from . import case_requests as case_request_core
from . import models, preservation_provider, schemas
from .case_holds import ensure_default_hold
from .hold_workflows import sync_legacy_custodian_to_default_hold


def run_approval_preservation_holds(
    *,
    db: Session,
    record: models.CaseRequest,
    actor: models.User,
    request: Optional[Request],
    preservation_hold_groups: dict[tuple[str, ...], list[int]],
    hold_notification_ids: list[int],
    rubrik_targets: list[models.Custodian],
    log_progress: Callable[[str, str, Optional[dict]], None],
) -> list[models.Custodian]:
    provider_label = preservation_provider.preservation_provider_label()
    automation_ready = preservation_provider.preservation_automation_ready()
    default_hold_id: Optional[int] = None
    if automation_ready and preservation_hold_groups and record.case_id:
        case = db.get(models.Case, int(record.case_id))
        if case is not None:
            default_hold = ensure_default_hold(db, case, assign_existing=True)
            db.flush()
            default_hold_id = int(default_hold.id)
    if record.request_type in {"new_case", "custodian"} and preservation_hold_groups and automation_ready:
        log_progress("preservation_case", f"Setting up {provider_label} case...")
    else:
        log_progress("finalizing", "Finalizing approval...")

    def _summarize_hold_results(result: Optional[dict]) -> dict:
        summary: dict[str, int] = {}
        if not isinstance(result, dict):
            return summary
        rows = result.get("results") if isinstance(result.get("results"), list) else []
        for item in rows:
            if not isinstance(item, dict):
                continue
            status = (item.get("status") or "").strip().lower()
            if not status:
                continue
            summary[status] = summary.get(status, 0) + 1
        return summary

    if record.request_type in {"new_case", "custodian"}:
        if preservation_hold_groups:
            group_summary = {
                ",".join(key): len(ids)
                for key, ids in preservation_hold_groups.items()
            }
            case_request_core.logger.info(
                "preservation_auto_hold_groups ts=%s record=%s case=%s groups=%s",
                case_request_core._now_ts(),
                record.id,
                record.case_id,
                group_summary,
            )
        else:
            case_request_core.logger.info(
                "preservation_auto_hold_groups_empty ts=%s record=%s case=%s",
                case_request_core._now_ts(),
                record.id,
                record.case_id,
            )

    # Apply configured provider automation for requests containing supported hold sources.
    try:
        if record.request_type in {"new_case", "custodian"} and preservation_hold_groups and automation_ready:
            case_id_val = record.case_id
            try:
                case_request_core.logger.info(
                    "preservation_case_auto_create_start ts=%s record=%s case=%s",
                    case_request_core._now_ts(),
                    record.id,
                    case_id_val,
                )
                result = preservation_provider.create_case(case_id=case_id_val, db=db, request=request, user=actor)
                case_request_core.logger.info(
                    "preservation_case_auto_create_complete ts=%s record=%s case=%s status=%s provider_case_id=%s",
                    case_request_core._now_ts(),
                    record.id,
                    case_id_val,
                    (result or {}).get("status"),
                    (result or {}).get("provider_case_id"),
                )
            except HTTPException as exc:
                log_progress(
                    "preservation_case_failed",
                    f"{provider_label} case setup failed. Continuing approval.",
                    {"error": str(getattr(exc, "detail", str(exc)))},
                )
                case_request_core.logger.warning(
                    "preservation_case_auto_create_failed ts=%s record=%s case=%s error=%s",
                    case_request_core._now_ts(), record.id, case_id_val, getattr(exc, "detail", str(exc)),
                )
            else:
                log_progress("preservation_holds", f"Applying {provider_label} holds...")
                for sources_key, custodian_ids in preservation_hold_groups.items():
                    custodian_ids_clean = [int(cid) for cid in (custodian_ids or []) if cid is not None]
                    if not custodian_ids_clean:
                        continue
                    try:
                        case_request_core.logger.info(
                            "preservation_hold_auto_apply_start ts=%s record=%s case=%s sources=%s custodian_ids=%s",
                            case_request_core._now_ts(),
                            record.id,
                            case_id_val,
                            sources_key,
                            custodian_ids_clean,
                        )
                        payload = schemas.PreservationHoldRequest(
                            custodian_ids=custodian_ids_clean,
                            included_sources=list(sources_key),
                            case_hold_id=default_hold_id,
                        )
                        hold_result = None
                        max_attempts = max(1, case_request_core.preservation_auto_apply_max_attempts())
                        for attempt in range(1, max_attempts + 1):
                            try:
                                hold_result = preservation_provider.apply_holds(
                                    case_id=case_id_val,
                                    payload=payload,
                                    db=db,
                                    request=request,
                                    user=actor,
                                )
                                # Provider adapters may mutate legacy custodian flags. Mirror those
                                # changes into the request case's default named hold before committing.
                                updated_custodians = (
                                    db.query(models.Custodian)
                                    .filter(models.Custodian.id.in_(custodian_ids_clean))
                                    .all()
                                )
                                for updated_custodian in updated_custodians:
                                    sync_legacy_custodian_to_default_hold(db, updated_custodian)
                                try:
                                    db.commit()
                                except Exception:
                                    db.rollback()
                                break
                            except HTTPException as exc:
                                detail = str(getattr(exc, "detail", str(exc)) or "")
                                retryable = exc.status_code == 409 and "does not exist" in detail.lower()
                                if retryable and attempt < max_attempts:
                                    delay = case_request_core.preservation_auto_apply_delay_seconds() * attempt
                                    case_request_core.logger.warning(
                                        "preservation_hold_auto_apply_retry ts=%s record=%s case=%s sources=%s attempt=%s delay=%.1fs error=%s",
                                        case_request_core._now_ts(),
                                        record.id,
                                        case_id_val,
                                        sources_key,
                                        attempt,
                                        delay,
                                        detail or exc,
                                    )
                                    try:
                                        case_request_core.log_event(
                                            db,
                                            action="preservation_hold_auto_apply_retry",
                                            actor_id=actor.id,
                                            target_type="case",
                                            target_id=case_id_val,
                                            details={
                                                "case_id": case_id_val,
                                                "case_name": record.case_name,
                                                "request_id": record.id,
                                                "sources": list(sources_key),
                                                "custodian_ids": custodian_ids,
                                                "attempt": attempt,
                                                "delay_seconds": delay,
                                                "error": detail or str(exc),
                                            },
                                            request=request,
                                        )
                                    except Exception as exc:
                                        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3385", exc)
                                    time.sleep(delay)
                                    continue
                                raise
                        status_counts = _summarize_hold_results(hold_result)
                        try:
                            case_request_core.log_event(
                                db,
                                action="preservation_hold_auto_apply",
                                actor_id=actor.id,
                                target_type="case",
                                target_id=case_id_val,
                                details={
                                    "case_id": case_id_val,
                                    "case_name": record.case_name,
                                    "request_id": record.id,
                                    "sources": list(sources_key),
                                    "custodian_ids": custodian_ids_clean,
                                    "attempts": max_attempts,
                                    "provider_case_id": (hold_result or {}).get("provider_case_id"),
                                    "provider_hold_id": (hold_result or {}).get("hold_id"),
                                    "status_counts": status_counts,
                                },
                                request=request,
                            )
                        except Exception as exc:
                            case_request_core._debug_suppressed("suppressed exception in case_requests.py:3411", exc)
                        case_request_core.logger.info(
                            "preservation_hold_auto_apply_complete ts=%s record=%s case=%s sources=%s attempts=%s hold_id=%s results=%s",
                            case_request_core._now_ts(),
                            record.id,
                            case_id_val,
                            sources_key,
                            max_attempts,
                            (hold_result or {}).get("hold_id"),
                            (hold_result or {}).get("results"),
                        )
                    except HTTPException as exc:
                        case_request_core.logger.warning(
                            "preservation_hold_auto_apply_failed ts=%s record=%s case=%s sources=%s custodian_ids=%s error=%s",
                            case_request_core._now_ts(),
                            record.id,
                            case_id_val,
                            sources_key,
                            custodian_ids_clean,
                            getattr(exc, "detail", str(exc)),
                        )
                        try:
                            case_request_core.log_event(
                                db,
                                action="preservation_hold_auto_apply_failed",
                                actor_id=actor.id,
                                target_type="case",
                                target_id=case_id_val,
                                details={
                                    "case_id": case_id_val,
                                    "case_name": record.case_name,
                                    "request_id": record.id,
                                    "sources": list(sources_key),
                                    "custodian_ids": custodian_ids_clean,
                                    "error": getattr(exc, "detail", str(exc)),
                                },
                                request=request,
                            )
                        except Exception as exc:
                            case_request_core._debug_suppressed("suppressed exception in case_requests.py:3450", exc)
                    except Exception as exc:
                        case_request_core.logger.warning(
                            "preservation_hold_auto_apply_failed ts=%s record=%s case=%s sources=%s custodian_ids=%s error=%s",
                            case_request_core._now_ts(),
                            record.id,
                            case_id_val,
                            sources_key,
                            custodian_ids_clean,
                            exc,
                        )
                        try:
                            case_request_core.log_event(
                                db,
                                action="preservation_hold_auto_apply_failed",
                                actor_id=actor.id,
                                target_type="case",
                                target_id=case_id_val,
                                details={
                                    "case_id": case_id_val,
                                    "case_name": record.case_name,
                                    "request_id": record.id,
                                    "sources": list(sources_key),
                                    "custodian_ids": custodian_ids_clean,
                                    "error": str(exc),
                                },
                                request=request,
                            )
                        except Exception as exc:
                            case_request_core._debug_suppressed("suppressed exception in case_requests.py:3479", exc)

                # External providers may take time to reflect accurate hold status.
                # Schedule a short retry poll so the Case Detail page shows correct hold flags sooner.
                try:
                    case_request_core._schedule_preservation_status_poll(case_id_val, "case_request_approve", delay_seconds=5, case_hold_id=default_hold_id)
                    case_request_core._schedule_preservation_status_poll(case_id_val, "case_request_approve", delay_seconds=20, case_hold_id=default_hold_id)
                    case_request_core._schedule_preservation_status_poll(case_id_val, "case_request_approve", delay_seconds=120, case_hold_id=default_hold_id)
                except Exception as exc:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:3488", exc)

                # Also do a short synchronous settle loop so the case is accurate on first analyst view.
                # This is best-effort and time-bounded to avoid blocking approvals indefinitely.
                try:
                    if hold_notification_ids and case_request_core.preservation_status_max_seconds() > 0:
                        log_progress(
                            "preservation_status",
                            f"Confirming {provider_label} hold status (may take up to a few minutes)...",
                        )
                        start_ts = time.time()
                        attempt = 0
                        while True:
                            elapsed = time.time() - start_ts
                            if elapsed >= case_request_core.preservation_status_max_seconds():
                                break
                            pending = (
                                db.query(models.Custodian)
                                .filter(models.Custodian.id.in_(hold_notification_ids))
                                .filter(
                                    or_(
                                        models.Custodian.holds_email_pending.is_(True),
                                        models.Custodian.holds_onedrive_pending.is_(True),
                                    )
                                )
                                .count()
                            )
                            if not pending:
                                break
                            attempt += 1
                            try:
                                preservation_provider.get_status(case_id=case_id_val, db=db, request=request, user=actor, case_hold_id=default_hold_id)
                            except Exception as exc:
                                case_request_core.logger.warning(
                                    "preservation_status_settle_failed ts=%s record=%s case=%s attempt=%s error=%s",
                                    case_request_core._now_ts(),
                                    record.id,
                                    case_id_val,
                                    attempt,
                                    exc,
                                )
                            pending_after = (
                                db.query(models.Custodian)
                                .filter(models.Custodian.id.in_(hold_notification_ids))
                                .filter(
                                    or_(
                                        models.Custodian.holds_email_pending.is_(True),
                                        models.Custodian.holds_onedrive_pending.is_(True),
                                    )
                                )
                                .count()
                            )
                            if not pending_after:
                                break
                            interval = max(1.0, float(case_request_core.preservation_status_interval_seconds() or 0))
                            time.sleep(interval)
                except Exception as exc:
                    case_request_core._debug_suppressed("suppressed exception in case_requests.py:3545", exc)
    except Exception:
        case_request_core.logger.exception(
            "preservation_hold_auto_apply_failed ts=%s record=%s case=%s",
            case_request_core._now_ts(), record.id, record.case_id,
        )

    # If the configured provider completed the email hold, skip redundant restore tickets.
    try:
        if record.request_type in {"new_case", "custodian"} and rubrik_targets and automation_ready:
            rubrik_targets = case_request_core._filter_rubrik_targets_after_preservation(db, rubrik_targets)
    except Exception as exc:
        case_request_core._debug_suppressed("suppressed exception in case_requests.py:3557", exc)


    return rubrik_targets
