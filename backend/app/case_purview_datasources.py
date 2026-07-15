import logging
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from . import cases as case_core
from . import case_purview_gateway as purview_core, models
from .purview import PurviewAPIError
from .case_purview_utils import (
    _candidate_site_keys,
    _canonical_site_key,
    _looks_like_url,
    _normalize_site_url,
    _purview_email_norm,
    _purview_site_key,
)

logger = logging.getLogger(__name__)


def _purview_sync_case_datasources(
    *,
    db: Session,
    case_id: int,
    purview_case_id: str,
    custodian_ids: Optional[list[int]] = None,
    requested_sources: Optional[set[str]] = None,
    actor_id: Optional[int] = None,
    request: Optional[Request] = None,
    context: Optional[str] = None,
) -> dict:
    """
    Best-effort sync of case custodians + custodian/noncustodial sources in Purview.

    This is intentionally non-fatal so hold application can proceed even if datasource sync fails.
    """
    sources = {s for s in (requested_sources or {"mailbox", "site"}) if s in {"mailbox", "site"}}
    source_list = sorted(sources)
    result: dict[str, Any] = {
        "enabled": True,
        "case_id": case_id,
        "purview_case_id": purview_case_id,
        "requested_sources": source_list,
        "context": context,
        "counts": {
            "selected": 0,
            "eligible": 0,
            "skipped_missing_email": 0,
            "case_custodian_add_attempted": 0,
            "case_custodian_add_failed": 0,
            "noncustodial_source_attempted": 0,
            "noncustodial_source_failed": 0,
            "noncustodial_site_source_attempted": 0,
            "noncustodial_site_source_failed": 0,
            "noncustodial_index_update_attempted": 0,
            "noncustodial_index_update_failed": 0,
            "noncustodial_total": 0,
            "noncustodial_user_present": 0,
            "noncustodial_site_present": 0,
            "missing_case_custodian_id": 0,
            "mailbox_source_attempted": 0,
            "mailbox_source_failed": 0,
            "site_source_attempted": 0,
            "site_source_failed": 0,
            "custodian_site_source_attempted": 0,
            "custodian_site_source_failed": 0,
        },
        "results": [],
    }

    def _emit_sync_event() -> None:
        rows = result.get("results") if isinstance(result.get("results"), list) else []
        status_counts: dict[str, int] = {}
        failed_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = (row.get("status") or "").strip().lower() or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            row_errors = row.get("errors") if isinstance(row.get("errors"), list) else []
            if row_errors or status in {"partial_error", "missing_case_custodian_id"}:
                failed_rows.append(
                    {
                        "custodian_id": row.get("custodian_id"),
                        "email": row.get("email"),
                        "status": row.get("status"),
                        "errors": row_errors[:3],
                    }
                )
        details = {
            "case_id": case_id,
            "purview_case_id": purview_case_id,
            "requested_sources": source_list,
            "context": context,
            "status": result.get("status"),
            "error": result.get("error"),
            "counts": result.get("counts"),
            "status_counts": status_counts,
            "failed_rows": failed_rows[:50],
            "verify_mismatch": bool(result.get("verify_mismatch")),
            "noncustodial_verify_error": result.get("noncustodial_verify_error"),
            "noncustodial_preview": (result.get("noncustodial_preview") or [])[:25],
        }
        try:
            logger.info(
                "purview_datasource_sync case_id=%s purview_case_id=%s status=%s error=%s verify_mismatch=%s counts=%s status_counts=%s",
                case_id,
                purview_case_id,
                details.get("status"),
                details.get("error"),
                details.get("verify_mismatch"),
                details.get("counts"),
                status_counts,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:2796", exc)
        try:
            case_core.log_event(
                db,
                action="purview_datasource_sync",
                actor_id=actor_id,
                target_type="case",
                target_id=case_id,
                details=details,
                request=request,
            )
        except Exception as exc:
            case_core._debug_suppressed("suppressed exception in cases.py:2808", exc)

    if not isinstance(purview_case_id, str) or not purview_case_id.strip():
        result["error"] = "missing_purview_case_id"
        result["status"] = "error"
        _emit_sync_event()
        return result
    if not sources:
        result["status"] = "no_requested_sources"
        _emit_sync_event()
        return result

    try:
        query = db.query(models.Custodian).filter(models.Custodian.case_id == case_id)
        if custodian_ids:
            ids = sorted({int(cid) for cid in custodian_ids if cid is not None})
            query = query.filter(models.Custodian.id.in_(ids))
        custodians = query.all()
    except Exception:
        result["error"] = "load_custodians_failed"
        result["status"] = "error"
        _emit_sync_event()
        return result

    result["counts"]["selected"] = len(custodians or [])
    if not custodians:
        result["status"] = "no_custodians"
        _emit_sync_event()
        return result

    try:
        case_custodians = purview_core.list_purview_case_custodians(purview_case_id)
    except PurviewAPIError as exc:
        result["error"] = str(exc)
        result["status"] = "error"
        _emit_sync_event()
        return result

    case_custodian_by_email: dict[str, dict] = {}
    for item in case_custodians or []:
        if not isinstance(item, dict):
            continue
        key = _purview_email_norm(item.get("email"))
        if key:
            case_custodian_by_email[key] = item

    valid_rows: list[dict] = []
    for cust in custodians:
        email = (getattr(cust, "email", None) or "").strip()
        email_norm = _purview_email_norm(email)
        row = {
            "custodian_id": getattr(cust, "id", None),
            "email": email_norm or None,
            "email_raw": email,
            "display_name": (getattr(cust, "name", None) or "").strip() or None,
            "status": "pending",
            "errors": [],
            "noncustodial_user_source_id": None,
            "noncustodial_site_source_id": None,
            "onedrive_site_web_url": None,
            "onedrive_site_key": None,
            "noncustodial_user_present": None,
            "noncustodial_site_present": None,
        }
        if not email_norm or email_norm in {case_core.NO_EMAIL_PLACEHOLDER.lower(), case_core.UNMATCHED_EMAIL_PLACEHOLDER.lower()}:
            row["status"] = "skipped_missing_email"
            result["counts"]["skipped_missing_email"] += 1
            result["results"].append(row)
            continue
        valid_rows.append(row)

    result["counts"]["eligible"] = len(valid_rows)

    added_noncustodial_ids: set[str] = set()
    any_added = False
    for row in valid_rows:
        email_norm = row.get("email")
        if not isinstance(email_norm, str):
            continue

        result["counts"]["noncustodial_source_attempted"] += 1
        try:
            noncustodial_resp = purview_core.add_purview_case_noncustodial_user_source(
                purview_case_id,
                email=(row.get("email_raw") or email_norm),
                included_sources=source_list,
            )
            if isinstance(noncustodial_resp, dict):
                noncustodial_id = noncustodial_resp.get("id")
                if isinstance(noncustodial_id, str) and noncustodial_id.strip():
                    row["noncustodial_user_source_id"] = noncustodial_id.strip()
                    added_noncustodial_ids.add(noncustodial_id.strip())
        except PurviewAPIError as exc:
            row["errors"].append(f"add_noncustodial_source: {exc}")
            result["counts"]["noncustodial_source_failed"] += 1

        if "site" in sources:
            result["counts"]["noncustodial_site_source_attempted"] += 1
            try:
                site_resource = purview_core.get_purview_onedrive_site(row.get("email_raw") or email_norm)
                site_key = _canonical_site_key(site_resource if isinstance(site_resource, dict) else None)
                if isinstance(site_key, str) and site_key.strip():
                    row["onedrive_site_key"] = site_key.strip().lower()
                site_web_url = None
                if isinstance(site_resource, dict):
                    for key in ("webUrl", "sharepointSiteUrl"):
                        value = site_resource.get(key)
                        if isinstance(value, str) and value.strip():
                            site_web_url = value.strip()
                            break
                if not site_web_url:
                    row["errors"].append("add_noncustodial_site_source: missing_onedrive_web_url")
                    result["counts"]["noncustodial_site_source_failed"] += 1
                else:
                    row["onedrive_site_web_url"] = site_web_url
                    noncustodial_site_resp = purview_core.add_purview_case_noncustodial_site_source(
                        purview_case_id,
                        site_web_url=site_web_url,
                    )
                    if isinstance(noncustodial_site_resp, dict):
                        noncustodial_site_id = noncustodial_site_resp.get("id")
                        if isinstance(noncustodial_site_id, str) and noncustodial_site_id.strip():
                            row["noncustodial_site_source_id"] = noncustodial_site_id.strip()
                            added_noncustodial_ids.add(noncustodial_site_id.strip())
            except PurviewAPIError as exc:
                row["errors"].append(f"add_noncustodial_site_source: {exc}")
                result["counts"]["noncustodial_site_source_failed"] += 1
            except Exception:
                row["errors"].append("add_noncustodial_site_source: unexpected_exception")
                result["counts"]["noncustodial_site_source_failed"] += 1

        if email_norm in case_custodian_by_email:
            continue
        result["counts"]["case_custodian_add_attempted"] += 1
        try:
            purview_core.add_purview_case_custodian(
                purview_case_id,
                email=(row.get("email_raw") or email_norm),
                display_name=row.get("display_name") or None,
            )
            any_added = True
        except PurviewAPIError as exc:
            row["errors"].append(f"add_case_custodian: {exc}")
            result["counts"]["case_custodian_add_failed"] += 1

    if any_added:
        try:
            case_custodians = purview_core.list_purview_case_custodians(purview_case_id)
            case_custodian_by_email = {}
            for item in case_custodians or []:
                if not isinstance(item, dict):
                    continue
                key = _purview_email_norm(item.get("email"))
                if key:
                    case_custodian_by_email[key] = item
        except PurviewAPIError as exc:
            result["error"] = str(exc)
            result["status"] = "error"
            _emit_sync_event()
            return result

    for noncustodial_id in sorted(added_noncustodial_ids):
        if not isinstance(noncustodial_id, str) or not noncustodial_id.strip():
            continue
        result["counts"]["noncustodial_index_update_attempted"] += 1
        try:
            purview_core.update_purview_case_noncustodial_index(purview_case_id, noncustodial_id.strip())
        except PurviewAPIError as exc:
            result["counts"]["noncustodial_index_update_failed"] += 1
            preview_errors = result.get("noncustodial_index_update_errors")
            if not isinstance(preview_errors, list):
                preview_errors = []
                result["noncustodial_index_update_errors"] = preview_errors
            if len(preview_errors) < 30:
                preview_errors.append({"id": noncustodial_id.strip(), "error": str(exc)})
        except Exception:
            result["counts"]["noncustodial_index_update_failed"] += 1

    try:
        noncustodial = purview_core.list_purview_case_noncustodial_data_sources(purview_case_id)
        result["counts"]["noncustodial_total"] = len(noncustodial or [])
        noncustodial_user_emails: set[str] = set()
        noncustodial_site_keys: set[str] = set()
        noncustodial_preview: list[dict[str, Any]] = []
        for item in noncustodial or []:
            if not isinstance(item, dict):
                continue
            ds = item.get("dataSource") if isinstance(item.get("dataSource"), dict) else {}
            email_key = _purview_email_norm(ds.get("email") if isinstance(ds, dict) else None)
            if email_key:
                noncustodial_user_emails.add(email_key)
            for candidate in _candidate_site_keys(ds if isinstance(ds, dict) else None):
                if candidate:
                    key = _normalize_site_url(candidate) if _looks_like_url(candidate) else candidate.strip().lower()
                    if key:
                        noncustodial_site_keys.add(key)
            site_obj = ds.get("site") if isinstance(ds, dict) and isinstance(ds.get("site"), dict) else None
            for candidate in _candidate_site_keys(site_obj if isinstance(site_obj, dict) else None):
                if candidate:
                    key = _normalize_site_url(candidate) if _looks_like_url(candidate) else candidate.strip().lower()
                    if key:
                        noncustodial_site_keys.add(key)
            source_level_key = _purview_site_key(ds if isinstance(ds, dict) else None)
            if source_level_key:
                key = _normalize_site_url(source_level_key) if _looks_like_url(source_level_key) else source_level_key.strip().lower()
                if key:
                    noncustodial_site_keys.add(key)
            source_level_key = _purview_site_key(item)
            if source_level_key:
                key = _normalize_site_url(source_level_key) if _looks_like_url(source_level_key) else source_level_key.strip().lower()
                if key:
                    noncustodial_site_keys.add(key)
            if len(noncustodial_preview) < 25:
                noncustodial_preview.append(
                    {
                        "id": item.get("id"),
                        "type": (ds.get("@odata.type") if isinstance(ds, dict) else None),
                        "email": (ds.get("email") if isinstance(ds, dict) else None),
                        "site": (ds.get("site") if isinstance(ds, dict) else None),
                    }
                )
        result["noncustodial_preview"] = noncustodial_preview

        for row in valid_rows:
            email_norm = row.get("email")
            if isinstance(email_norm, str) and email_norm:
                row["noncustodial_user_present"] = email_norm in noncustodial_user_emails
                if row["noncustodial_user_present"]:
                    result["counts"]["noncustodial_user_present"] += 1
            if "site" in sources:
                site_present = False
                site_key = row.get("onedrive_site_key")
                if isinstance(site_key, str) and site_key.strip():
                    site_present = site_key.strip().lower() in noncustodial_site_keys
                elif isinstance(row.get("onedrive_site_web_url"), str) and row.get("onedrive_site_web_url").strip():
                    site_present = _normalize_site_url(row.get("onedrive_site_web_url").strip()) in noncustodial_site_keys
                row["noncustodial_site_present"] = site_present
                if site_present:
                    result["counts"]["noncustodial_site_present"] += 1

        expected = int(result["counts"].get("eligible", 0) or 0)
        user_ok = int(result["counts"].get("noncustodial_user_present", 0) or 0) >= expected
        site_ok = ("site" not in sources) or (int(result["counts"].get("noncustodial_site_present", 0) or 0) >= expected)
        if expected > 0 and (not user_ok or not site_ok):
            result["verify_mismatch"] = True
    except PurviewAPIError as exc:
        result["noncustodial_verify_error"] = str(exc)
    except Exception:
        result["noncustodial_verify_error"] = "unexpected_exception"

    for row in valid_rows:
        email_norm = row.get("email")
        if not isinstance(email_norm, str):
            continue
        purview_custodian = case_custodian_by_email.get(email_norm) or {}
        purview_custodian_id = purview_custodian.get("id")
        if not isinstance(purview_custodian_id, str) or not purview_custodian_id.strip():
            row["status"] = "missing_case_custodian_id"
            result["counts"]["missing_case_custodian_id"] += 1
            result["results"].append(row)
            continue
        pcid = purview_custodian_id.strip()
        row["purview_custodian_id"] = pcid

        if "mailbox" in sources:
            result["counts"]["mailbox_source_attempted"] += 1
            try:
                purview_core.add_purview_custodian_user_source(
                    purview_case_id,
                    pcid,
                    email=email_norm,
                    included_sources=["mailbox"],
                )
            except PurviewAPIError as exc:
                row["errors"].append(f"add_mailbox_source: {exc}")
                result["counts"]["mailbox_source_failed"] += 1

        if "site" in sources:
            result["counts"]["site_source_attempted"] += 1
            try:
                purview_core.add_purview_custodian_user_source(
                    purview_case_id,
                    pcid,
                    email=email_norm,
                    included_sources=["site"],
                )
            except PurviewAPIError as exc:
                row["errors"].append(f"add_site_source: {exc}")
                result["counts"]["site_source_failed"] += 1
            site_web_url = row.get("onedrive_site_web_url")
            if isinstance(site_web_url, str) and site_web_url.strip():
                result["counts"]["custodian_site_source_attempted"] += 1
                try:
                    purview_core.add_purview_custodian_site_source(
                        purview_case_id,
                        pcid,
                        site_web_url=site_web_url.strip(),
                    )
                except PurviewAPIError as exc:
                    row["errors"].append(f"add_custodian_site_source: {exc}")
                    result["counts"]["custodian_site_source_failed"] += 1

        row["status"] = "synced" if not row["errors"] else "partial_error"
        result["results"].append(row)

    if result.get("error"):
        result["status"] = "error"
    elif result["counts"]["eligible"] == 0:
        result["status"] = "no_eligible_custodians"
    elif (
        result["counts"]["case_custodian_add_failed"]
        or result["counts"]["noncustodial_source_failed"]
        or result["counts"]["noncustodial_site_source_failed"]
        or result["counts"]["noncustodial_index_update_failed"]
        or result["counts"]["mailbox_source_failed"]
        or result["counts"]["site_source_failed"]
        or result["counts"]["custodian_site_source_failed"]
        or result["counts"]["missing_case_custodian_id"]
        or result.get("verify_mismatch")
        or result.get("noncustodial_verify_error")
    ):
        result["status"] = "partial_error"
    else:
        result["status"] = "ok"
    _emit_sync_event()
    return result
