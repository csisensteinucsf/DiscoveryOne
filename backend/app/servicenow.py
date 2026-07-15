import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple, List

import httpx

from .integration_settings import config_value, integration_active
from .ticket_workflow_catalog import servicenow_category_config

logger = logging.getLogger(__name__)


class ServiceNowError(Exception):
    """Raised when a ServiceNow call fails."""


@dataclass
class ServiceNowConfig:
    base_url: str
    table: str
    auth_type: str
    use_import_api: bool
    username: Optional[str]
    password: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    token_url: Optional[str]
    scope: Optional[str]
    customer_id: str
    source_system: str
    status_table: str


def servicenow_enabled() -> bool:
    return integration_active("servicenow", provider_key="ticket_provider", provider="servicenow")


def load_config() -> ServiceNowConfig:
    if not servicenow_enabled():
        raise ServiceNowError("ServiceNow integration is disabled. Enable ServiceNow in System > Integrations before creating or syncing tickets.")

    def _config_bool(key: str, env_name: str, default: bool = False) -> bool:
        raw = config_value("servicenow", key, env_name)
        if raw == "":
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}

    base_url = config_value("servicenow", "base_url", ["SNOW_BASE_URL", "SNOW_BASE"])
    username = config_value("servicenow", "username", ["SNOW_USERNAME", "SNOW_USER"])
    password = config_value("servicenow", "password", ["SNOW_PASSWORD", "SNOW_PASS"])
    auth_type = (config_value("servicenow", "auth_type", "SNOW_AUTH_TYPE", "basic") or "basic").lower()
    if auth_type not in {"basic", "oauth"}:
        raise ServiceNowError("ServiceNow auth type must be 'basic' or 'oauth'.")

    client_id = config_value("servicenow", "oauth_client_id", "SNOW_OAUTH_CLIENT_ID")
    client_secret = config_value("servicenow", "oauth_client_secret", "SNOW_OAUTH_CLIENT_SECRET")
    token_url = config_value("servicenow", "oauth_token_url", "SNOW_OAUTH_TOKEN_URL")
    scope = config_value("servicenow", "oauth_scope", "SNOW_OAUTH_SCOPE") or None
    table = config_value("servicenow", "table", "SNOW_TABLE", "incident") or "incident"
    # Default to import API when using an inbound integration table unless explicitly disabled.
    default_use_import_api = table.endswith("_inbound")
    use_import_api = _config_bool("use_import_api", "SNOW_USE_IMPORT_API", default=default_use_import_api)
    customer_id = config_value("servicenow", "customer_id", "SNOW_CUSTOMER_ID", "discoveryone")
    source_system = config_value("servicenow", "source_system", "SNOW_SOURCE_SYSTEM", "discoveryone")
    status_table = config_value("servicenow", "status_table", "SNOW_STATUS_TABLE", "incident")

    missing: Dict[str, str] = {"base URL": base_url}
    if auth_type == "oauth":
        token_url = token_url or (f"{base_url.rstrip('/')}/oauth_token.do" if base_url else "")
        missing.update({
            "OAuth client ID": client_id,
            "OAuth client secret": client_secret,
            "OAuth token URL": token_url,
        })
    else:
        missing.update({
            "username": username,
            "password": password,
        })

    missing_keys = [name for name, value in missing.items() if not value]
    if missing_keys:
        raise ServiceNowError(f"Missing ServiceNow configuration values: {', '.join(sorted(missing_keys))}")

    return ServiceNowConfig(
        base_url=base_url.rstrip("/"),
        table=table,
        username=username,
        password=password,
        auth_type=auth_type,
        use_import_api=use_import_api,
        client_id=client_id or None,
        client_secret=client_secret or None,
        token_url=token_url.rstrip("/") if token_url else None,
        scope=scope,
        customer_id=customer_id,
        source_system=source_system,
        status_table=status_table,
    )

def _category_config() -> Dict[str, Dict[str, str]]:
    """Return per-category ServiceNow routing from the stored ticket workflow catalog."""
    return servicenow_category_config()

def _extract_servicenow_error_message(result: Any, data: Any) -> str:
    candidates: list[dict] = []
    if isinstance(result, dict):
        candidates.append(result)
    elif isinstance(result, list):
        candidates.extend(item for item in result if isinstance(item, dict))
    if isinstance(data, dict):
        candidates.append(data)
        nested_error = data.get("error")
        if isinstance(nested_error, dict):
            candidates.append(nested_error)
    for item in candidates:
        message = str(item.get("error_message") or item.get("message") or item.get("detail") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        if message and (status == "error" or "unable to find incident keyword" in message.lower()):
            return message
    return ""


def _clean_context_value(value: Any) -> str:
    return str(value or "").strip()


def _append_access_log_context(lines: List[str], extra_context: Optional[Dict[str, Any]]) -> None:
    if not isinstance(extra_context, dict):
        return
    employee_id = _clean_context_value(
        extra_context.get("access_log_employee_id")
    )
    notes = _clean_context_value(
        extra_context.get("access_log_request_notes")
    )
    raw_windows = extra_context.get("access_log_time_windows") or []
    windows: List[str] = []
    if isinstance(raw_windows, list):
        for item in raw_windows:
            if not isinstance(item, dict):
                continue
            date_value = _clean_context_value(item.get("date"))
            start_time = _clean_context_value(item.get("start_time"))
            end_time = _clean_context_value(item.get("end_time"))
            if not any((date_value, start_time, end_time)):
                continue
            time_range = ""
            if start_time or end_time:
                time_range = f" {start_time or '?'}-{end_time or '?'}"
            windows.append(f"- {date_value or 'Date not specified'}{time_range}")
    if not any((employee_id, notes, windows)):
        return
    lines.append("")
    lines.append("Access log request details:")
    if employee_id:
        lines.append(f"Employee ID: {employee_id}")
    if windows:
        lines.append("Requested date/time windows:")
        lines.extend(windows)
    if notes:
        lines.append(f"Request notes: {notes}")


def _build_payload(
    category: str,
    config: ServiceNowConfig,
    case_name: Optional[str],
    case_link: Optional[str],
    custodian_name: Optional[str],
    custodian_email: Optional[str],
    customer_id_override: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    category_meta = _category_config().get(category)
    if not category_meta:
        raise ServiceNowError(f"Unsupported ServiceNow category: {category}")
    incident_keyword = category_meta.get("incident_keyword")
    if not incident_keyword:
        raise ServiceNowError(f"ServiceNow incident keyword missing for category: {category}")

    assignment_group = category_meta["assignment_group"]
    if not assignment_group:
        raise ServiceNowError(f"ServiceNow assignment group missing for category: {category}")

    lines = []
    request_type = category_meta.get("request_type") or category_meta.get("short_description") or category
    if request_type:
        lines.append(f"Request type: {request_type}")
    lines.append("Ticket customer will reach out over email with the details for this ticket.")
    lines.append("Feel free to reach out to ticket customer directly.")
    if case_name:
        lines.append(f"Case: {case_name}")
    if case_link:
        link_label = (category_meta.get("link_label") or "Case link").strip() or "Case link"
        lines.append(f"{link_label}: {case_link}")
    _append_access_log_context(lines, extra_context)
    long_description = "\n".join(lines)
    short_description = category_meta["short_description"]
    append_case_name = str(category_meta.get("append_case_name_to_short_description") or "").strip().lower() in {"1", "true", "yes", "on"}
    if case_name and append_case_name:
        short_description = f"{short_description} - {case_name}"

    payload = {
        "u_short_description": short_description,
        "u_long_description": long_description,
        "u_assignment_group": assignment_group,
        "u_customer_id": (customer_id_override or config.customer_id),
        "u_source_system": config.source_system,
        "u_source_number": case_name,
        "u_symptom": category_meta.get("symptom") or "Inquiry",
        "u_incident_keyword": incident_keyword,
    }
    return payload


_token_cache: Dict[str, Tuple[str, datetime]] = {}


def _cache_key(cfg: ServiceNowConfig) -> str:
    return f"{cfg.token_url}:{cfg.client_id}"


def _is_closed_state(state: Optional[str]) -> bool:
    if state is None:
        return False
    val = str(state).strip().lower()
    if not val:
        return False
    return val in {"6", "7", "8", "closed", "resolved", "canceled", "cancelled"}


def _get_oauth_token(cfg: ServiceNowConfig, force_refresh: bool = False) -> str:
    """
    Retrieve and cache a ServiceNow OAuth access token using client credentials.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cache_key = _cache_key(cfg)
    if not force_refresh:
        cached = _token_cache.get(cache_key)
        if cached:
            token, expires_at = cached
            if expires_at - now > timedelta(seconds=30):
                return token

    data = {"grant_type": "client_credentials"}
    if cfg.scope:
        data["scope"] = cfg.scope

    try:
        resp = httpx.post(
            cfg.token_url,
            data=data,
            headers={"Accept": "application/json"},
            auth=(cfg.client_id, cfg.client_secret),
            timeout=10.0,
        )
    except Exception as exc:  # pragma: no cover - network issues
        logger.exception("ServiceNow OAuth token request failed: %s", exc)
        raise ServiceNowError(f"Unable to reach ServiceNow for OAuth token: {exc}") from exc

    body = resp.text or ""
    if resp.status_code < 200 or resp.status_code >= 300:
        snippet = body[:400]
        logger.error("ServiceNow OAuth token HTTP failure status=%s snippet=%s", resp.status_code, snippet)
        raise ServiceNowError(f"ServiceNow OAuth token request failed with HTTP {resp.status_code}: {snippet}")

    try:
        payload = resp.json()
    except Exception as exc:
        logger.error("ServiceNow OAuth token response was not JSON: %s", exc)
        raise ServiceNowError("ServiceNow OAuth token response was not valid JSON.") from exc

    token = payload.get("access_token")
    expires_in = payload.get("expires_in") or 3600
    if not token:
        raise ServiceNowError("ServiceNow OAuth token response missing access_token.")

    expires_at = now + timedelta(seconds=int(expires_in))
    _token_cache[cache_key] = (token, expires_at)
    logger.info("ServiceNow OAuth token acquired expires_in=%s", expires_in)
    return token

def create_ticket(
    category: str,
    case_name: Optional[str] = None,
    case_link: Optional[str] = None,
    custodian_name: Optional[str] = None,
    custodian_email: Optional[str] = None,
    customer_id: Optional[str] = None,
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """
    Create a ServiceNow ticket for the given category and return the ticket number/sys_id.
    """
    cfg = load_config()
    log_full_response = (_read_env("SNOW_LOG_FULL_RESPONSE") or "").lower() in {"1", "true", "yes", "on"}
    payload = _build_payload(
        category,
        cfg,
        case_name,
        case_link,
        custodian_name,
        custodian_email,
        customer_id_override=customer_id,
        extra_context=extra_context,
    )
    url = (
        f"{cfg.base_url}/api/now/import/{cfg.table}"
        if cfg.use_import_api
        else f"{cfg.base_url}/api/now/table/{cfg.table}"
    )
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    logger.info(
        "ServiceNow create_ticket start category=%s case=%s custodian=%s email=%s",
        category,
        (case_name or "").strip() or None,
        (custodian_name or "").strip() or None,
        (custodian_email or "").strip() or None,
    )
    logger.info("ServiceNow create_ticket request url=%s table=%s", url, cfg.table)

    try:
        with httpx.Client(timeout=20.0) as client:
            if cfg.auth_type == "oauth":
                token = _get_oauth_token(cfg)
                resp = client.post(url, headers={**headers, "Authorization": f"Bearer {token}"}, json=payload)
                if resp.status_code == 401:
                    # Token may be expired even if cache thought it was valid; refresh once.
                    token = _get_oauth_token(cfg, force_refresh=True)
                    resp = client.post(url, headers={**headers, "Authorization": f"Bearer {token}"}, json=payload)
            else:
                resp = client.post(url, auth=(cfg.username, cfg.password), headers=headers, json=payload)
    except Exception as exc:  # pragma: no cover - network issues
        logger.exception("ServiceNow ticket creation failed: %s", exc)
        raise ServiceNowError(f"Unable to reach ServiceNow: {exc}") from exc

    body = resp.text or ""
    logger.info("ServiceNow create_ticket response status=%s length=%s", resp.status_code, len(body))
    logger.info("ServiceNow create_ticket full_response_logging=%s", log_full_response)
    if log_full_response:
        logger.info("ServiceNow create_ticket full response headers=%s", dict(resp.headers))
        logger.info("ServiceNow create_ticket full response body=%s", body)
    else:
        logger.info("ServiceNow create_ticket raw response body=%s", body[:5000])
        if len(body) > 5000:
            logger.info("ServiceNow create_ticket raw response truncated total_length=%s", len(body))

    if resp.status_code < 200 or resp.status_code >= 300:
        snippet = resp.text[:500]
        logger.error("ServiceNow ticket creation HTTP failure status=%s snippet=%s", resp.status_code, snippet)
        raise ServiceNowError(f"ServiceNow returned HTTP {resp.status_code}: {snippet}")

    try:
        data = resp.json()
    except Exception:
        data = {}
        logger.warning("ServiceNow create_ticket response was not valid JSON; falling back to raw parsing.")

    logger.info("ServiceNow parse start keys=%s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)

    result = data.get("result") if isinstance(data, dict) else None
    if result is None and isinstance(data, list):
        result = data
    ticket_number = None
    sys_id = None
    logger.info("ServiceNow ticket create succeeded; attempting to extract ticket number.")
    if isinstance(result, dict):
        ticket_number = (
            result.get("number")
            or result.get("u_number")
            or result.get("display_value")
            or result.get("u_display_value")
            or result.get("display_name")
        )
        sys_id = result.get("sys_id")
    elif isinstance(result, list) and result:
        first = result[0] if isinstance(result[0], dict) else {}
        ticket_number = (
            first.get("number")
            or first.get("u_number")
            or first.get("display_value")
            or first.get("u_display_value")
            or first.get("display_name")
        )
        sys_id = first.get("sys_id")
        record_link = first.get("record_link")
        if not sys_id and record_link and isinstance(record_link, str):
            sys_id = record_link.rstrip("/").split("/")[-1]
    if not ticket_number and isinstance(data, dict):
        ticket_number = (
            data.get("number")
            or data.get("u_number")
            or data.get("display_value")
        )
        sys_id = sys_id or data.get("sys_id")

    if not ticket_number:
        # Log full context to aid troubleshooting, regardless of SNOW_LOG_FULL_RESPONSE
        logger.error(
            "ServiceNow ticket number missing; response headers=%s body=%s",
            dict(resp.headers),
            body,
        )
        error_message = _extract_servicenow_error_message(result, data)
        if error_message:
            lower_message = error_message.lower()
            if "unable to find incident keyword" in lower_message:
                raise ServiceNowError(
                    f"ServiceNow rejected this ticket because the incident keyword is not configured there yet. {error_message}"
                )
            raise ServiceNowError(f"ServiceNow rejected the ticket. {error_message}")
        # include a small snippet of the response to aid debugging
        snippet = str(result or data or "")[:400]
        logger.warning("ServiceNow ticket created but ticket number missing; body snippet=%s", snippet)
        raise ServiceNowError(f"ServiceNow response did not include a ticket number. Body: {snippet}")

    logger.info("ServiceNow create_ticket success ticket=%s sys_id=%s", ticket_number, sys_id)

    return {"ticket_number": str(ticket_number), "sys_id": sys_id}


def get_ticket_statuses(ticket_numbers: list[str], table_override: Optional[str] = None) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Retrieve status for a set of ServiceNow ticket numbers. Returns a mapping of number -> info.
    """
    cfg = load_config()
    table = table_override or (cfg.status_table or "incident")
    numbers = [n.strip() for n in (ticket_numbers or []) if n and str(n).strip()]
    if not numbers:
        return {}

    headers = {"Accept": "application/json"}
    url = f"{cfg.base_url}/api/now/table/{table}"
    results: Dict[str, Dict[str, Optional[str]]] = {}

    def _assign(items: list[dict]) -> None:
        for item in items or []:
            number = (item.get("number") or item.get("u_number") or "").strip()
            if not number:
                continue
            sys_id = item.get("sys_id")
            state = item.get("state") or item.get("incident_state") or item.get("status")
            assigned_raw = item.get("assigned_to") or item.get("assigned_to.value") or item.get("assigned_to_sys_id")
            assigned_display = None
            assigned_email = item.get("assigned_to.email") or item.get("assigned_to_email")
            assigned_sys_id = None
            if isinstance(assigned_raw, dict):
                assigned_sys_id = assigned_raw.get("value") or assigned_raw.get("sys_id")
                assigned_display = assigned_raw.get("display_value") or assigned_raw.get("link") or assigned_raw.get("name")
                assigned_email = assigned_email or assigned_raw.get("email") or assigned_raw.get("u_email")
            elif assigned_raw:
                assigned_sys_id = assigned_raw
            assigned_display = assigned_display or item.get("assigned_to_display") or item.get("assigned_to")
            if isinstance(assigned_display, dict):
                assigned_display = assigned_display.get("display_value") or assigned_display.get("name")
            results[number] = {
                "sys_id": sys_id,
                "state": str(state) if state is not None else None,
                "status": str(state) if state is not None else None,
                "is_closed": _is_closed_state(state),
                "link": f"{cfg.base_url}/nav_to.do?uri={table}.do?sys_id={sys_id}" if sys_id else None,
                "table": table,
                "assigned_to_sys_id": assigned_sys_id,
                "assigned_to_display": assigned_display,
                "assigned_to_email": assigned_email,
            }

    try:
        with httpx.Client(timeout=20.0) as client:
            auth = None
            auth_headers: Dict[str, str] = {}
            if cfg.auth_type == "oauth":
                token = _get_oauth_token(cfg)
                auth_headers = {"Authorization": f"Bearer {token}"}
            else:
                auth = (cfg.username, cfg.password)

            chunk_size = 30
            for i in range(0, len(numbers), chunk_size):
                subset = numbers[i:i + chunk_size]
                params = {
                    "sysparm_query": f"numberIN{','.join(subset)}",
                    "sysparm_fields": "number,sys_id,state,incident_state,status,sys_class_name,assigned_to,assigned_to.email",
                    "sysparm_display_value": "true",
                    "sysparm_limit": len(subset),
                }
                resp = client.get(url, params=params, headers={**headers, **auth_headers}, auth=auth)
                if resp.status_code == 401 and cfg.auth_type == "oauth":
                    token = _get_oauth_token(cfg, force_refresh=True)
                    auth_headers = {"Authorization": f"Bearer {token}"}
                    resp = client.get(url, params=params, headers={**headers, **auth_headers}, auth=auth)
                body = resp.text or ""
                if resp.status_code < 200 or resp.status_code >= 300:
                    snippet = body[:400]
                    logger.error("ServiceNow status HTTP failure status=%s snippet=%s", resp.status_code, snippet)
                    raise ServiceNowError(f"ServiceNow status request failed with HTTP {resp.status_code}: {snippet}")
                try:
                    payload = resp.json()
                except Exception:
                    logger.error("ServiceNow status response not JSON body=%s", body[:400])
                    raise ServiceNowError("ServiceNow status response was not valid JSON.")
                data = payload.get("result") if isinstance(payload, dict) else payload
                if isinstance(data, list):
                    _assign(data)
                elif isinstance(data, dict):
                    _assign([data])
                else:
                    logger.warning("ServiceNow status response unexpected shape type=%s body_snippet=%s", type(payload).__name__, str(payload)[:400])
    except ServiceNowError:
        raise
    except Exception as exc:  # pragma: no cover - network issues
        logger.exception("ServiceNow status lookup failed: %s", exc)
        raise ServiceNowError(f"Unable to reach ServiceNow: {exc}") from exc

    return results
