from __future__ import annotations

import os


def app_display_name(*, fallback_env_names: tuple[str, ...] | None = None) -> str:
    try:
        from .system_settings import load_system_settings

        settings = load_system_settings()
        branding = settings.get("branding") or {}
        stored = str(branding.get("app_name") or "").strip()
        if stored:
            return stored
        if settings.get("initial_setup_completed"):
            return "DiscoveryOne"
    except Exception:
        pass
    env_names = fallback_env_names or ("APP_DISPLAY_NAME", "APP_NAME")
    for name in env_names:
        raw = os.getenv(name)
        if raw and raw.strip():
            return raw.strip()
    return "DiscoveryOne"


def branded_subject(text: str) -> str:
    return f"[{app_display_name()}] {str(text or '').strip()}"


def app_team_name() -> str:
    return f"{app_display_name()} Team"


def app_administrators_label() -> str:
    return f"{app_display_name()} administrators"
