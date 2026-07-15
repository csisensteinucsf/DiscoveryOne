from __future__ import annotations

from typing import Any

from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings


def _case_request_settings() -> dict[str, Any]:
    try:
        settings = load_system_settings().get("case_requests") or {}
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_request_settings.py:load", exc)
        settings = {}
    return settings if isinstance(settings, dict) else {}


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def requestor_stats_show_global() -> bool:
    return bool(_case_request_settings().get("requestor_stats_show_global", False))


def hold_automation_allow_override() -> bool:
    return bool(_case_request_settings().get("hold_automation_allow_override", False))


def auto_rubrik_restore_for_separated_email_holds() -> bool:
    return bool(_case_request_settings().get("auto_rubrik_restore_for_separated_email_holds", False))


def pending_cleanup_days() -> float:
    return _bounded_float(_case_request_settings().get("pending_cleanup_days"), 30.0, minimum=1.0, maximum=3650.0)


def pending_cleanup_interval_hours() -> float:
    return _bounded_float(_case_request_settings().get("pending_cleanup_interval_hours"), 12.0, minimum=1.0, maximum=168.0)


def hold_status_email_delay_seconds() -> float:
    return _bounded_float(_case_request_settings().get("hold_status_email_delay_seconds"), 300.0, minimum=0.0, maximum=86400.0)


def preservation_auto_apply_max_attempts() -> int:
    settings = _case_request_settings()
    value = settings.get(
        "preservation_auto_apply_max_attempts",
        settings.get("purview_auto_apply_max_attempts"),
    )
    return _bounded_int(value, 3, minimum=1, maximum=20)


def preservation_auto_apply_delay_seconds() -> float:
    settings = _case_request_settings()
    value = settings.get(
        "preservation_auto_apply_delay_seconds",
        settings.get("purview_auto_apply_delay_seconds"),
    )
    return _bounded_float(value, 2.0, minimum=0.0, maximum=3600.0)


def preservation_status_max_seconds() -> float:
    settings = _case_request_settings()
    value = settings.get(
        "preservation_status_max_seconds",
        settings.get("purview_approval_status_max_seconds"),
    )
    return _bounded_float(value, 90.0, minimum=0.0, maximum=86400.0)


def preservation_status_interval_seconds() -> float:
    settings = _case_request_settings()
    value = settings.get(
        "preservation_status_interval_seconds",
        settings.get("purview_approval_status_interval_seconds"),
    )
    return _bounded_float(value, 5.0, minimum=1.0, maximum=3600.0)


# Compatibility functions for extensions using the former provider-specific names.
def purview_auto_apply_max_attempts() -> int:
    return preservation_auto_apply_max_attempts()


def purview_auto_apply_delay_seconds() -> float:
    return preservation_auto_apply_delay_seconds()


def purview_approval_status_max_seconds() -> float:
    return preservation_status_max_seconds()


def purview_approval_status_interval_seconds() -> float:
    return preservation_status_interval_seconds()
