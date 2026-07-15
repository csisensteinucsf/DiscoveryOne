import secrets
import time
from typing import Any, Dict, Optional

import httpx

from .integration_settings import config_value


def http_timeout_seconds() -> float:
    raw = config_value(
        "purview",
        "http_timeout_seconds",
        ["PURVIEW_HTTP_TIMEOUT_SECONDS", "PURVIEW_HTTP_TIMEOUT"],
        "60",
    )
    try:
        value = float(raw)
    except Exception:
        value = 60.0
    return max(5.0, min(300.0, value))


def http_retry_count() -> int:
    raw = config_value("purview", "http_retry_count", "PURVIEW_HTTP_RETRY_COUNT", "3")
    try:
        value = int(raw)
    except Exception:
        value = 3
    return max(0, min(10, value))


def http_should_retry_status(status_code: int) -> bool:
    return status_code in {429, 500, 502, 503, 504}


def parse_retry_after_seconds(resp: httpx.Response) -> Optional[float]:
    if not resp:
        return None
    raw = resp.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw.strip())
    except Exception:
        return None


def http_request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    allow_statuses: Optional[set[int]] = None,
    idempotent: bool = True,
) -> httpx.Response:
    timeout = http_timeout_seconds()
    retries = http_retry_count() if idempotent else 0
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            resp = httpx.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
                data=data,
                timeout=timeout,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_exc = exc
            if attempt >= retries:
                raise
            backoff = min(10.0, 0.75 * (2 ** attempt) + (secrets.randbelow(2500) / 10000.0))
            time.sleep(backoff)
            continue

        if allow_statuses and resp.status_code in allow_statuses:
            return resp
        if resp.status_code >= 400 and idempotent and http_should_retry_status(resp.status_code) and attempt < retries:
            delay = parse_retry_after_seconds(resp)
            if delay is None:
                delay = min(10.0, 0.75 * (2 ** attempt) + (secrets.randbelow(2500) / 10000.0))
            time.sleep(max(0.5, min(30.0, delay)))
            continue
        return resp

    if last_exc:
        raise last_exc
    raise httpx.RequestError("Request failed")