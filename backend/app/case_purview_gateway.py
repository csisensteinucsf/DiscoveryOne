from __future__ import annotations

from .integration_settings import config_value
from .purview import (
    PurviewAPIError,
    PurviewConfigError,
    add_purview_case_custodian,
    add_purview_case_member,
    add_purview_case_noncustodial_site_source,
    add_purview_case_noncustodial_user_source,
    add_purview_custodian_site_source,
    add_purview_custodian_user_source,
    add_purview_hold_site_source,
    add_purview_hold_user_source,
    create_purview_case,
    create_purview_case_legal_hold,
    delete_purview_case_custodian,
    delete_purview_case_legal_hold,
    delete_purview_custodian_site_source,
    delete_purview_custodian_user_source,
    delete_purview_hold_site_source,
    delete_purview_hold_user_source,
    find_purview_case_by_display_name,
    get_purview_custodian_last_index_operation,
    get_purview_noncustodial_last_index_operation,
    get_purview_onedrive_site,
    list_purview_case_custodians,
    list_purview_case_legal_holds,
    list_purview_case_members,
    list_purview_case_noncustodial_data_sources,
    list_purview_case_operations,
    list_purview_custodian_site_sources,
    list_purview_custodian_user_sources,
    list_purview_hold_site_sources,
    list_purview_hold_user_sources,
    probe_purview_portal_graph_endpoints,
    purview_enabled,
    release_purview_case_custodian,
    resolve_purview_user_emails,
    resolve_purview_user_id,
    retry_purview_hold_policy,
    update_purview_case_custodian_index,
    update_purview_case_noncustodial_index,
    update_purview_hold_user_source,
)


def _as_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _as_int(value: object, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(str(value or "").strip())
    except (TypeError, ValueError):
        return default


def hold_missing_email_mark_failed() -> bool:
    return _as_bool(
        config_value(
            "purview",
            "hold_missing_email_mark_failed",
            "PURVIEW_HOLD_MISSING_EMAIL_MARK_FAILED",
            "0",
        )
    )


def add_data_sources_enabled() -> bool:
    return _as_bool(
        config_value(
            "purview",
            "add_data_sources",
            "PURVIEW_ADD_DATA_SOURCES",
            "0",
        )
    )


def status_onedrive_lookup_limit() -> int:
    return max(
        0,
        _as_int(
            config_value(
                "purview",
                "status_onedrive_lookup_limit",
                "PURVIEW_STATUS_ONEDRIVE_LOOKUP_LIMIT",
                "25",
            ),
            25,
        ),
    )


def status_poll_delay_seconds() -> float:
    return max(
        0.0,
        _as_float(
            config_value(
                "purview",
                "status_poll_delay_seconds",
                "PURVIEW_STATUS_POLL_DELAY_SECONDS",
                "120",
            ),
            120.0,
        ),
    )
