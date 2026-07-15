from __future__ import annotations

import os
from typing import Any, Iterable
from urllib.parse import urlparse

from .integration_settings import config_value, integration_enabled


def _truthy(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _float_value(value: Any, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        parsed = float(str(value or "").strip())
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def ai_integration_enabled() -> bool:
    if integration_enabled("ai", default=False):
        return True
    try:
        from .system_settings import load_system_settings

        if load_system_settings().get("initial_setup_completed"):
            return False
    except Exception:
        pass
    # Backward compatibility for deployments that have not completed app setup.
    return bool((os.getenv("AI_URL") or "").strip() and (os.getenv("AI_MODEL") or "").strip())


def ai_value(key: str, env_names: str | Iterable[str], default: str = "") -> str:
    return config_value("ai", key, env_names, default)


def ai_feature_enabled(key: str, env_names: str | Iterable[str], default: bool = False) -> bool:
    raw = ai_value(key, env_names, "1" if default else "0")
    return _truthy(raw, default)


def ai_client_config(*, feature_prefix: str | None = None, timeout_minimum: float = 5.0) -> dict[str, Any]:
    prefix = (feature_prefix or "").strip().upper()
    prefix_names = lambda suffix: ([f"{prefix}_{suffix}", f"AI_{suffix}"] if prefix else [f"AI_{suffix}"])

    url = ai_value("url", prefix_names("URL"), "")
    model = ai_value("model", prefix_names("MODEL"), "")
    api_key = ai_value("api_key", prefix_names("API_KEY"), "")
    auth_header = ai_value("auth_header", prefix_names("AUTH_HEADER"), "Authorization") or "Authorization"
    timeout_seconds = _float_value(ai_value("timeout_seconds", prefix_names("TIMEOUT_SECONDS"), "25"), 25.0, minimum=timeout_minimum)
    temperature = _float_value(ai_value("temperature", prefix_names("TEMPERATURE"), "0.1"), 0.1, minimum=0.0, maximum=1.0)
    system_prompt = ai_value("system_prompt", prefix_names("SYSTEM_PROMPT"), "")

    try:
        endpoint_host = urlparse(url).netloc or ""
    except Exception:
        endpoint_host = ""

    return {
        "url": url,
        "model": model,
        "api_key": api_key,
        "auth_header": auth_header,
        "timeout_seconds": timeout_seconds,
        "temperature": temperature,
        "system_prompt": system_prompt,
        "endpoint_host": endpoint_host,
    }


def ai_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = str(config.get("api_key") or "").strip()
    if not api_key:
        return headers
    auth_header = str(config.get("auth_header") or "Authorization").strip() or "Authorization"
    if auth_header.lower() == "authorization" and not api_key.lower().startswith("bearer "):
        headers[auth_header] = f"Bearer {api_key}"
    else:
        headers[auth_header] = api_key
    return headers


def ai_configured(*, feature_prefix: str | None = None) -> bool:
    if not ai_integration_enabled():
        return False
    cfg = ai_client_config(feature_prefix=feature_prefix)
    return bool(cfg.get("url") and cfg.get("model"))


def ai_int_setting(key: str, env_names: str | Iterable[str], default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = ai_value(key, env_names, str(default))
    try:
        value = int(str(raw or "").strip())
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def search_builder_max_suggestions() -> int:
    return ai_int_setting("search_builder_max_suggestions", "SEARCH_BUILDER_AI_MAX_SPLIT", 4, minimum=1, maximum=8)
