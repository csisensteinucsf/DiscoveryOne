from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from . import schemas
from .case_purview_release import release_purview_holds_for_case
from .case_purview_utils import _purview_email_norm, _purview_name_norm
from .preservation_provider_registry import PreservationOperationContext
from .purview import (
    PurviewAPIError,
    delete_purview_case_custodian,
    delete_purview_custodian_site_source,
    delete_purview_custodian_user_source,
    delete_purview_hold_site_source,
    delete_purview_hold_user_source,
    list_purview_case_custodians,
    list_purview_case_legal_holds,
    list_purview_custodian_site_sources,
    list_purview_custodian_user_sources,
    release_purview_case_custodian,
    resolve_purview_user_emails,
)

logger = logging.getLogger(__name__)
_EMAIL_PLACEHOLDERS = {"noemail", "unmatched"}


def _compatibility_fields(
    *,
    hold_release: dict | None,
    deleted: list[dict],
    released: list[dict],
    deleted_hold_sources: list[dict],
    deleted_custodian_sources: list[dict],
) -> dict[str, Any]:
    return {
        "purview_hold_release": hold_release,
        "purview_case_custodian_deleted": {"deleted": deleted} if deleted else None,
        "purview_case_custodian_released": {"released": released} if released else None,
        "purview_hold_sources_deleted": {"deleted": deleted_hold_sources} if deleted_hold_sources else None,
        "purview_custodian_sources_deleted": {"deleted": deleted_custodian_sources} if deleted_custodian_sources else None,
    }


def remove_purview_custodian(
    *,
    case_id: int,
    custodian_id: int,
    custodian_name: str | None,
    custodian_email: str | None,
    context: PreservationOperationContext,
) -> dict[str, Any]:
    email = _purview_email_norm(custodian_email)
    if not email or email in _EMAIL_PLACEHOLDERS:
        hold_release = {
            "status": "skipped",
            "reason": "custodian_missing_email",
        }
        logger.info(
            "purview_custodian_release_skipped case_id=%s custodian_id=%s reason=missing_email",
            case_id,
            custodian_id,
        )
        return {
            "provider": "purview",
            "status": "skipped",
            "reason": "custodian_missing_email",
            "compatibility_fields": _compatibility_fields(
                hold_release=hold_release,
                deleted=[],
                released=[],
                deleted_hold_sources=[],
                deleted_custodian_sources=[],
            ),
        }

    payload = schemas.PurviewHoldRequest(
        custodian_ids=[custodian_id],
        included_sources=["mailbox", "site"],
        delete_hold_policy=False,
    )
    hold_release = release_purview_holds_for_case(
        case_id=case_id,
        payload=payload,
        db=context.db,
        request=context.request,
        _user=context.user,
    )
    if isinstance(hold_release, dict):
        logger.info(
            "purview_custodian_release case_id=%s custodian_id=%s status=%s status_counts=%s",
            case_id,
            custodian_id,
            hold_release.get("status"),
            hold_release.get("status_counts"),
        )
        results = hold_release.get("results") or []
        if isinstance(results, list):
            row = next(
                (
                    item
                    for item in results
                    if isinstance(item, dict)
                    and int(item.get("custodian_id") or 0) == int(custodian_id)
                ),
                None,
            )
            if row and (row.get("status") or "").strip().lower() == "error":
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Preservation hold release failed: "
                        + (row.get("message") or "unknown error")
                    ),
                )

    provider_case_id = (
        hold_release.get("purview_case_id")
        if isinstance(hold_release, dict)
        else None
    )
    deleted: list[dict] = []
    released: list[dict] = []
    deleted_hold_sources: list[dict] = []
    deleted_custodian_sources: list[dict] = []

    if isinstance(provider_case_id, str) and provider_case_id.strip():
        candidates = set(resolve_purview_user_emails(email) or [])
        candidates.add(email)
        target_name = _purview_name_norm(custodian_name)
        try:
            provider_custodians = list_purview_case_custodians(provider_case_id)
            matches_by_email: list[tuple[str, str | None]] = []
            matches_by_name: list[tuple[str, str | None]] = []
            for provider_custodian in provider_custodians:
                if not isinstance(provider_custodian, dict):
                    continue
                provider_custodian_id = (
                    provider_custodian.get("id") or ""
                ).strip()
                if not provider_custodian_id:
                    continue
                provider_email = _purview_email_norm(
                    provider_custodian.get("email")
                )
                provider_name = _purview_name_norm(
                    provider_custodian.get("displayName")
                )
                if provider_email and provider_email in candidates:
                    matches_by_email.append(
                        (provider_custodian_id, provider_email)
                    )
                elif target_name and provider_name == target_name:
                    matches_by_name.append(
                        (provider_custodian_id, provider_email or None)
                    )

            chosen = (
                matches_by_email
                or (matches_by_name if len(matches_by_name) == 1 else [])
            )
            for provider_custodian_id, provider_email in chosen:
                try:
                    release_purview_case_custodian(
                        provider_case_id,
                        provider_custodian_id,
                    )
                    released.append(
                        {
                            "id": provider_custodian_id,
                            "email": provider_email,
                        }
                    )
                except PurviewAPIError:
                    pass

                try:
                    holds = list_purview_case_legal_holds(provider_case_id)
                except PurviewAPIError:
                    holds = []
                hold_ids = [
                    (hold.get("id") or "").strip()
                    for hold in holds or []
                    if isinstance(hold, dict)
                    and isinstance(hold.get("id"), str)
                    and (hold.get("id") or "").strip()
                ]
                try:
                    user_sources = list_purview_custodian_user_sources(
                        provider_case_id,
                        provider_custodian_id,
                    )
                except PurviewAPIError:
                    user_sources = []
                try:
                    site_sources = list_purview_custodian_site_sources(
                        provider_case_id,
                        provider_custodian_id,
                    )
                except PurviewAPIError:
                    site_sources = []

                user_source_ids = [
                    (source.get("id") or "").strip()
                    for source in user_sources
                    if isinstance(source, dict)
                    and isinstance(source.get("id"), str)
                    and (source.get("id") or "").strip()
                ]
                site_source_ids = [
                    (source.get("id") or "").strip()
                    for source in site_sources
                    if isinstance(source, dict)
                    and isinstance(source.get("id"), str)
                    and (source.get("id") or "").strip()
                ]

                for source_id in user_source_ids:
                    try:
                        if delete_purview_custodian_user_source(
                            provider_case_id,
                            provider_custodian_id,
                            source_id,
                        ):
                            deleted_custodian_sources.append(
                                {
                                    "type": "user",
                                    "custodian_id": provider_custodian_id,
                                    "id": source_id,
                                }
                            )
                    except PurviewAPIError:
                        pass
                    for hold_id in hold_ids:
                        try:
                            if delete_purview_hold_user_source(
                                provider_case_id,
                                hold_id,
                                source_id,
                            ):
                                deleted_hold_sources.append(
                                    {
                                        "type": "user",
                                        "hold_id": hold_id,
                                        "id": source_id,
                                    }
                                )
                        except PurviewAPIError:
                            pass

                for source_id in site_source_ids:
                    try:
                        if delete_purview_custodian_site_source(
                            provider_case_id,
                            provider_custodian_id,
                            source_id,
                        ):
                            deleted_custodian_sources.append(
                                {
                                    "type": "site",
                                    "custodian_id": provider_custodian_id,
                                    "id": source_id,
                                }
                            )
                    except PurviewAPIError:
                        pass
                    for hold_id in hold_ids:
                        try:
                            if delete_purview_hold_site_source(
                                provider_case_id,
                                hold_id,
                                source_id,
                            ):
                                deleted_hold_sources.append(
                                    {
                                        "type": "site",
                                        "hold_id": hold_id,
                                        "id": source_id,
                                    }
                                )
                        except PurviewAPIError:
                            pass

                try:
                    if delete_purview_case_custodian(
                        provider_case_id,
                        provider_custodian_id,
                    ):
                        deleted.append(
                            {
                                "id": provider_custodian_id,
                                "email": provider_email,
                            }
                        )
                except PurviewAPIError:
                    pass
        except PurviewAPIError:
            deleted = []
            released = []
            deleted_hold_sources = []
            deleted_custodian_sources = []

    compatibility_fields = _compatibility_fields(
        hold_release=hold_release if isinstance(hold_release, dict) else None,
        deleted=deleted,
        released=released,
        deleted_hold_sources=deleted_hold_sources,
        deleted_custodian_sources=deleted_custodian_sources,
    )
    return {
        "provider": "purview",
        "status": (
            str(hold_release.get("status") or "completed")
            if isinstance(hold_release, dict)
            else "completed"
        ),
        "hold_release": hold_release,
        "custodians_released": released,
        "custodians_deleted": deleted,
        "hold_sources_deleted": deleted_hold_sources,
        "custodian_sources_deleted": deleted_custodian_sources,
        "compatibility_fields": compatibility_fields,
    }