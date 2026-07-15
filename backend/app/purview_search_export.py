from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from . import models
from .audit import log_event
from .purview import (
    PurviewAPIError,
    PurviewConfigError,
    add_purview_case_custodian,
    add_purview_custodian_user_source,
    build_purview_custodian_site_source_bind_url,
    build_purview_custodian_user_source_bind_url,
    build_purview_noncustodial_source_bind_url,
    create_purview_case,
    create_purview_case_search,
    find_purview_case_by_display_name,
    list_purview_case_custodians,
    list_purview_case_noncustodial_data_sources,
    list_purview_custodian_site_sources,
    list_purview_custodian_user_sources,
)
from .safe_log import debug_suppressed as _debug_suppressed
from .search_export_provider_registry import SearchExportOperationContext


_SEARCH_QUERY_SPLIT_RE = re.compile(
    r"(?:^|\n)\s*(?:Provider Query|Purview KQL):\s*",
    re.IGNORECASE,
)
_SMART_QUOTES_TRANSLATION = str.maketrans(
    {
        chr(0x2018): "'",
        chr(0x2019): "'",
        chr(0x201C): '"',
        chr(0x201D): '"',
    }
)
_KQL_EMAIL_DOMAIN_WILDCARD_RE = re.compile(
    r'(?i)\b(?P<prop>from|to|cc|bcc|participants|sender|senders|recipient|recipients)\s*:\s*(?P<quote>["\'])?\*\s*@(?P<domain>[a-z0-9.-]+\.[a-z]{2,})(?P=quote)?'
)
_KQL_DATE_COMPARISON_RE = re.compile(
    r'(?i)\b(?P<prop>received|sent|created|lastmodifiedtime)\s*(?P<op><=|>=|=|<|>)\s*(?P<quote>["\'])?(?P<date>\d{1,2}/\d{1,2}/\d{4})(?P=quote)?'
)


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_int_list(values: Any) -> list[int]:
    if not isinstance(values, list):
        return []
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        result.append(number)
    return result


def _split_search_additional(additional: Any) -> tuple[str, str]:
    raw = str(additional or "").strip()
    if not raw:
        return "", ""
    match = _SEARCH_QUERY_SPLIT_RE.search(raw)
    if not match:
        return raw, ""
    overview = raw[: match.start()].strip()
    query = raw[match.end() :].strip()
    return overview, query


def _mmddyyyy_to_iso(value: str) -> str:
    parts = str(value or "").strip().split("/")
    if len(parts) != 3:
        return value
    try:
        month, day, year = (int(part) for part in parts)
    except (TypeError, ValueError):
        return value
    if not 1900 <= year <= 2100:
        return value
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return value
    return f"{year:04d}-{month:02d}-{day:02d}"


def normalize_purview_kql(raw: Any) -> str:
    query = _coerce_text(raw) or ""
    if not query:
        return ""
    query = query.translate(_SMART_QUOTES_TRANSLATION)

    def rewrite_domain(match: re.Match[str]) -> str:
        prop = (match.group("prop") or "").strip().lower()
        domain = (match.group("domain") or "").strip().lower()
        if not prop or not domain:
            return match.group(0)
        return f"{prop}:{domain}"

    def rewrite_date(match: re.Match[str]) -> str:
        prop = (match.group("prop") or "").strip().lower()
        operator = (match.group("op") or "").strip()
        date = (match.group("date") or "").strip()
        if not prop or not operator or not date:
            return match.group(0)
        return f"{prop}{operator}{_mmddyyyy_to_iso(date)}"

    query = _KQL_EMAIL_DOMAIN_WILDCARD_RE.sub(rewrite_domain, query)
    query = _KQL_DATE_COMPARISON_RE.sub(rewrite_date, query)
    return re.sub(r"\s+", " ", query).strip()


def _purview_error_status(error: PurviewAPIError) -> int:
    status = error.status_code or 502
    return status if 400 <= status < 600 else 502


def push_search_to_purview(
    *,
    case: models.Case,
    search: models.Search,
    payload: dict[str, Any],
    context: SearchExportOperationContext,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    requested_query = _coerce_text(
        body.get("query") or body.get("purview_kql")
    )
    additional_override = _coerce_text(body.get("additional"))
    search_name_override = _coerce_text(body.get("display_name"))
    search_description_override = _coerce_text(body.get("description"))

    source_additional = (
        additional_override
        if additional_override is not None
        else search.additional
    )
    search_overview, extracted_query = _split_search_additional(
        source_additional
    )
    purview_kql = normalize_purview_kql(
        requested_query or extracted_query
    )
    if not purview_kql:
        raise HTTPException(
            status_code=400,
            detail="Purview KQL is required before exporting this search.",
        )

    case_name = (getattr(case, "name", "") or "").strip()
    if not case_name:
        raise HTTPException(
            status_code=400,
            detail="Case must have a name before exporting searches.",
        )

    search_name = (
        search_name_override
        or _coerce_text(getattr(search, "name", None))
        or f"{case_name}-Search {search.id}"
    )
    search_description = (
        search_description_override
        if search_description_override is not None
        else (_coerce_text(search_overview) or None)
    )

    try:
        raw_ids = search.custodian_ids
        if isinstance(raw_ids, (str, bytes)):
            raw_ids = json.loads(raw_ids or "[]")
    except Exception:
        raw_ids = []
    assigned_ids = _safe_int_list(raw_ids)

    assigned_custodians: list[models.Custodian] = []
    if assigned_ids:
        assigned_custodians = (
            context.db.query(models.Custodian)
            .filter(
                models.Custodian.case_id == case.id,
                models.Custodian.id.in_(assigned_ids),
            )
            .all()
        )

    assigned_by_email: dict[str, models.Custodian] = {}
    for custodian in assigned_custodians:
        email = _normalize_email(custodian.email)
        if email and email not in assigned_by_email:
            assigned_by_email[email] = custodian
    assigned_emails = set(assigned_by_email)

    matched_emails: set[str] = set()
    custodian_source_binds: list[str] = []
    noncustodial_source_binds: list[str] = []
    attach_counts = {
        "custodians_added": 0,
        "user_sources_added": 0,
    }
    warnings: list[str] = []

    try:
        provider_case = find_purview_case_by_display_name(case_name)
        provider_case_status = "exists"
        if not provider_case:
            provider_case = create_purview_case(
                display_name=case_name,
                description=_coerce_text(
                    getattr(case, "description", None)
                ),
            )
            provider_case_status = "created"

        provider_case_id = (provider_case or {}).get("id")
        if not isinstance(provider_case_id, str) or not provider_case_id.strip():
            raise HTTPException(
                status_code=502,
                detail="Purview case is missing an identifier.",
            )
        provider_case_id = provider_case_id.strip()

        def case_custodian_ids_by_email(
            rows: list[dict[str, Any]],
        ) -> dict[str, str]:
            mapping: dict[str, str] = {}
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                provider_custodian_id = str(row.get("id") or "").strip()
                email = _normalize_email(row.get("email"))
                if not provider_custodian_id or not email:
                    continue
                if assigned_emails and email not in assigned_emails:
                    continue
                mapping.setdefault(email, provider_custodian_id)
            return mapping

        provider_custodians = list_purview_case_custodians(
            provider_case_id
        )
        provider_ids_by_email = case_custodian_ids_by_email(
            provider_custodians
        )

        if assigned_emails:
            missing_emails = [
                email
                for email in assigned_emails
                if email not in provider_ids_by_email
            ]
            for email in missing_emails:
                local = assigned_by_email.get(email)
                try:
                    add_purview_case_custodian(
                        provider_case_id,
                        email=email,
                        display_name=_coerce_text(
                            getattr(local, "name", None)
                        ),
                    )
                    attach_counts["custodians_added"] += 1
                except PurviewAPIError as error:
                    warnings.append(f"custodian_add:{email}:{error}")

            if missing_emails:
                provider_ids_by_email = case_custodian_ids_by_email(
                    list_purview_case_custodians(provider_case_id)
                )

            for email, provider_custodian_id in provider_ids_by_email.items():
                matched_emails.add(email)
                try:
                    user_sources = list_purview_custodian_user_sources(
                        provider_case_id,
                        provider_custodian_id,
                    )
                except PurviewAPIError as error:
                    warnings.append(f"user_source_list:{email}:{error}")
                    user_sources = []

                has_user_source = any(
                    _normalize_email((source or {}).get("email")) == email
                    for source in user_sources
                )
                if not has_user_source:
                    try:
                        add_purview_custodian_user_source(
                            provider_case_id,
                            provider_custodian_id,
                            email=email,
                        )
                        attach_counts["user_sources_added"] += 1
                    except PurviewAPIError as error:
                        warnings.append(f"user_source_add:{email}:{error}")
                    try:
                        user_sources = list_purview_custodian_user_sources(
                            provider_case_id,
                            provider_custodian_id,
                        )
                    except PurviewAPIError:
                        user_sources = []

                for source in user_sources or []:
                    source_id = str(
                        (source or {}).get("id") or ""
                    ).strip()
                    if source_id:
                        custodian_source_binds.append(
                            build_purview_custodian_user_source_bind_url(
                                provider_case_id,
                                provider_custodian_id,
                                source_id,
                            )
                        )

                try:
                    site_sources = list_purview_custodian_site_sources(
                        provider_case_id,
                        provider_custodian_id,
                    )
                except PurviewAPIError as error:
                    warnings.append(f"site_source_list:{email}:{error}")
                    site_sources = []
                for source in site_sources or []:
                    source_id = str(
                        (source or {}).get("id") or ""
                    ).strip()
                    if source_id:
                        custodian_source_binds.append(
                            build_purview_custodian_site_source_bind_url(
                                provider_case_id,
                                provider_custodian_id,
                                source_id,
                            )
                        )

        if not custodian_source_binds:
            for source in (
                list_purview_case_noncustodial_data_sources(
                    provider_case_id
                )
                or []
            ):
                source_id = str(
                    (source or {}).get("id") or ""
                ).strip()
                if source_id:
                    noncustodial_source_binds.append(
                        build_purview_noncustodial_source_bind_url(
                            provider_case_id,
                            source_id,
                        )
                    )

        if not custodian_source_binds and not noncustodial_source_binds:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No Purview data sources are available for this search. "
                    f"Assigned custodians: {len(assigned_ids)}, "
                    f"matched in Purview: {len(matched_emails)}. "
                    "Run datasource sync/apply holds, then retry."
                ),
            )

        pushed = create_purview_case_search(
            provider_case_id,
            display_name=search_name,
            content_query=purview_kql,
            description=search_description,
            custodian_source_binds=custodian_source_binds,
            noncustodial_source_binds=noncustodial_source_binds,
        )
    except PurviewConfigError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except PurviewAPIError as error:
        raise HTTPException(
            status_code=_purview_error_status(error),
            detail=str(error),
        ) from error

    source_counts = {
        "custodian_sources": len(custodian_source_binds),
        "noncustodial_sources": len(noncustodial_source_binds),
        "assigned_custodians": len(assigned_ids),
        "matched_custodian_emails": len(matched_emails),
        **attach_counts,
    }
    provider_search_id = (
        pushed.get("id") if isinstance(pushed, dict) else None
    )
    provider_search_name = (
        pushed.get("displayName")
        if isinstance(pushed, dict)
        else None
    ) or search_name

    result = {
        "status": "created",
        "provider": "purview",
        "case_id": case.id,
        "search_id": search.id,
        "search_name": search_name,
        "provider_case_id": provider_case_id,
        "provider_case_status": provider_case_status,
        "provider_search_id": provider_search_id,
        "provider_search_name": provider_search_name,
        "data_source_counts": source_counts,
        "auto_attach_warnings": warnings[:20],
        # Compatibility fields for existing clients.
        "purview_case_id": provider_case_id,
        "purview_case_status": provider_case_status,
        "purview_search_id": provider_search_id,
        "purview_search_name": provider_search_name,
    }

    try:
        log_event(
            context.db,
            action="search_export_push",
            target_type="search",
            target_id=search.id,
            actor_id=getattr(context.user, "id", None),
            details={
                "provider": "purview",
                "case_id": case.id,
                "case_name": case_name,
                "search_id": search.id,
                "search_name": search_name,
                "provider_case_id": provider_case_id,
                "provider_search_id": provider_search_id,
                "query_length": len(purview_kql),
                "data_source_counts": source_counts,
                "auto_attach_warning_count": len(warnings),
            },
            request=context.request,
        )
    except Exception as error:
        _debug_suppressed(
            "suppressed exception in purview_search_export.py:audit",
            error,
        )

    return result