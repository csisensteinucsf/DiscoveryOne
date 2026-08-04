import logging
import time
from urllib.parse import urlparse, quote
from typing import Any, Dict, Optional, List

import httpx
from .integration_settings import config_value, integration_active
from .safe_log import debug_suppressed as _debug_suppressed
from .purview_http import http_request as _http_request
from .purview_hold_sources import (
    PURVIEW_HOLD_SOURCES,
    normalize_included_sources as _normalize_included_sources,
    serialize_included_sources as _serialize_included_sources,
)

logger = logging.getLogger(__name__)


def purview_tenant_id() -> str:
    return config_value("purview", "tenant_id", ["PURVIEW_TENANT_ID", "O365_TENANT_ID"]).strip()


def purview_client_id() -> str:
    return config_value("purview", "client_id", ["PURVIEW_CLIENT_ID", "O365_CLIENT_ID"]).strip()


def purview_client_secret() -> str:
    return config_value("purview", "client_secret", ["PURVIEW_CLIENT_SECRET", "O365_CLIENT_SECRET"]).strip()


def purview_scope() -> str:
    return config_value("purview", "scope", "PURVIEW_SCOPE", "https://graph.microsoft.com/.default").strip() or "https://graph.microsoft.com/.default"


def purview_graph_base() -> str:
    return config_value("purview", "graph_base", "PURVIEW_GRAPH_BASE", "https://graph.microsoft.com/beta").rstrip("/")


def purview_graph_base_v1() -> str:
    return config_value("purview", "graph_base_v1", "PURVIEW_GRAPH_BASE_V1", "https://graph.microsoft.com/v1.0").rstrip("/")


def purview_security_base() -> str:
    return config_value("purview", "security_base", "PURVIEW_SECURITY_BASE", purview_graph_base_v1()).rstrip("/")


def purview_onedrive_host() -> str:
    return config_value("purview", "onedrive_host", "PURVIEW_ONEDRIVE_HOST").strip().lower()


def _auth_signature() -> tuple[str, str, str, str]:
    return (purview_tenant_id(), purview_client_id(), purview_client_secret(), purview_scope())


_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0, "signature": None}
_sharepoint_personal_host: Optional[str] = None






class PurviewConfigError(RuntimeError):
    """Raised when the integration is not configured."""


class PurviewAPIError(RuntimeError):
    """Raised when Microsoft Graph returns an error."""

    def __init__(self, message: str, *, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def purview_enabled() -> bool:
    tenant_id, client_id, client_secret, _scope = _auth_signature()
    return (
        integration_active("purview", provider_key="preservation_provider", provider="purview")
        and bool(tenant_id and client_id and client_secret)
    )


def _get_access_token() -> str:
    signature = _auth_signature()
    tenant_id, client_id, client_secret, scope = signature
    if not integration_active("purview", provider_key="preservation_provider", provider="purview") or not (tenant_id and client_id and client_secret):
        raise PurviewConfigError("Purview integration is disabled or not configured. Enable Purview in System > Integrations and configure tenant ID, client ID, and client secret.")
    now = time.time()
    cached = _token_cache.get("token")
    if cached and _token_cache.get("signature") == signature and _token_cache.get("expires_at", 0) > now + 30:
        return cached
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
        "grant_type": "client_credentials",
    }
    try:
        resp = _http_request("POST", token_url, data=data, idempotent=True)
    except httpx.RequestError as exc:
        raise PurviewAPIError(f"Unable to reach Microsoft identity platform: {exc}") from exc
    if resp.status_code != 200:
        detail = _extract_error_message(resp)
        raise PurviewAPIError(f"Authentication failed: {detail}", status_code=resp.status_code)
    payload = resp.json()
    token = payload.get("access_token")
    expires_in = int(payload.get("expires_in", 3599))
    if not token:
        raise PurviewAPIError("Authentication response did not include an access token")
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(30, expires_in - 30)
    _token_cache["signature"] = signature
    return token


def create_purview_case(*, display_name: str, description: Optional[str] = None) -> Dict[str, Any]:
    token = _get_access_token()
    url = f"{purview_security_base()}/security/cases/ediscoveryCases"
    body: Dict[str, Any] = {"displayName": display_name}
    if description:
        body["description"] = description
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        # Not strictly idempotent. If we time out, we might have created the case anyway; try to locate it.
        resp = _http_request("POST", url, headers=headers, json=body, idempotent=False)
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        try:
            existing = find_purview_case_by_display_name(display_name)
            if existing:
                logger.info("purview_case_create_timeout_recovered display_name=%s", display_name)
                return existing
        except Exception as exc:
            _debug_suppressed("suppressed exception in purview.py:207", exc)
        raise PurviewAPIError(f"Unable to reach Microsoft Graph: {exc}") from exc
    if resp.status_code == 409:
        existing = find_purview_case_by_display_name(display_name)
        if existing:
            return existing
    if resp.status_code not in (200, 201):
        detail = _extract_error_message(resp)
        raise PurviewAPIError(f"Purview case creation failed: {detail}", status_code=resp.status_code)
    return resp.json()


def _escape_odata_string(value: str) -> str:
    return (value or "").replace("'", "''")


def _graph_request(
    method: str,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    allow_statuses: Optional[set[int]] = None,
) -> Any:
    token = _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = _http_request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
            allow_statuses=allow_statuses,
            idempotent=(method.upper() in {"GET", "DELETE", "PUT", "PATCH"}),
        )
    except httpx.RequestError as exc:
        raise PurviewAPIError(f"Unable to reach Microsoft Graph: {exc}") from exc
    if allow_statuses and resp.status_code in allow_statuses:
        try:
            return resp.json()
        except Exception:
            return resp.text or None
    if resp.status_code >= 400:
        detail = _extract_error_message(resp)
        raise PurviewAPIError(f"Purview API request failed: {detail}", status_code=resp.status_code)
    if resp.status_code == 204:
        return None
    try:
        return resp.json()
    except Exception:
        return resp.text or None


def _graph_delete(url: str, *, allow_not_found: bool = False) -> bool:
    """
    Perform a DELETE request and return True if a resource was deleted.

    - Returns True on 2xx/204.
    - Returns False on 404 when allow_not_found=True.
    - Raises PurviewAPIError for other 4xx/5xx responses.
    """
    token = _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = _http_request("DELETE", url, headers=headers, idempotent=True)
    except httpx.RequestError as exc:
        raise PurviewAPIError(f"Unable to reach Microsoft Graph: {exc}") from exc
    if allow_not_found and resp.status_code == 404:
        return False
    if resp.status_code >= 400:
        detail = _extract_error_message(resp)
        raise PurviewAPIError(f"Purview API request failed: {detail}", status_code=resp.status_code)
    return True


def _graph_list(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    max_pages: int = 10,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    next_url = url
    next_params = params
    for _ in range(max_pages):
        payload = _graph_request("GET", next_url, params=next_params)
        if not isinstance(payload, dict):
            break
        items.extend(payload.get("value") or [])
        next_url = payload.get("@odata.nextLink")
        next_params = None
        if not next_url:
            break
    return items


def find_purview_case_by_display_name(display_name: str) -> Optional[Dict[str, Any]]:
    name = (display_name or "").strip()
    if not name:
        return None
    url = f"{purview_security_base()}/security/cases/ediscoveryCases"
    filter_expr = f"displayName eq '{_escape_odata_string(name)}'"
    cases: Optional[List[Dict[str, Any]]] = None
    try:
        payload = _graph_request("GET", url, params={"$filter": filter_expr, "$top": 20})
        if isinstance(payload, dict):
            cases = payload.get("value") or []
    except PurviewAPIError as exc:
        if exc.status_code == 400:
            cases = _graph_list(url, params={"$top": 50}, max_pages=4)
        else:
            raise
    if not cases:
        return None
    name_key = name.lower()
    for item in cases:
        if not isinstance(item, dict):
            continue
        if (item.get("displayName") or "").strip().lower() == name_key:
            return item
    return cases[0] if cases else None


def list_purview_case_custodians(case_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians"
    return _graph_list(url, params={"$top": 200}, max_pages=5)


def add_purview_case_custodian(
    case_id: str,
    *,
    email: str,
    display_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians"
    body: Dict[str, Any] = {"email": email}
    if display_name:
        body["displayName"] = display_name
    return _graph_request("POST", url, json=body, allow_statuses={409})


def delete_purview_case_custodian(case_id: str, custodian_id: str) -> bool:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}"
    return _graph_delete(url, allow_not_found=True)


def release_purview_case_custodian(case_id: str, custodian_id: str) -> Any:
    """
    Releases a Purview eDiscovery custodian from active holds for the case.

    See: POST /security/cases/ediscoveryCases/{caseId}/custodians/{custodianId}/release
    """
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/release"
    # Endpoint commonly returns 204; be tolerant of 200/202 as well.
    return _graph_request("POST", url, allow_statuses={200, 202, 204})


def list_purview_custodian_user_sources(case_id: str, custodian_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/userSources"
    return _graph_list(url, params={"$top": 200}, max_pages=5)


def list_purview_custodian_site_sources(case_id: str, custodian_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/siteSources"
    params = {"$top": 200, "$expand": "site($select=id,webUrl)"}
    return _graph_list(url, params=params, max_pages=5)


def add_purview_custodian_user_source(
    case_id: str,
    custodian_id: str,
    *,
    email: str,
    included_sources: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/userSources"
    body: Dict[str, Any] = {
        "@odata.type": "#microsoft.graph.security.userSource",
        "email": email,
    }
    if included_sources is not None:
        serialized = _serialize_included_sources(included_sources)
        if serialized:
            body["includedSources"] = serialized
    return _graph_request("POST", url, json=body, allow_statuses={409})


def add_purview_custodian_site_source(
    case_id: str,
    custodian_id: str,
    *,
    site_id: Optional[str] = None,
    site_web_url: Optional[str] = None,
    site_bind_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/siteSources"
    if not site_id and not site_web_url and not site_bind_url:
        raise ValueError("site_id or site_web_url is required")
    body: Dict[str, Any] = {"@odata.type": "#microsoft.graph.security.siteSource"}
    if site_bind_url:
        body["site@odata.bind"] = site_bind_url
    else:
        site_payload = {"id": site_id} if site_id else {"webUrl": site_web_url}
        body["site"] = site_payload
    return _graph_request("POST", url, json=body, allow_statuses={409})


def list_purview_case_noncustodial_data_sources(case_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/noncustodialDataSources"
    params = {"$top": 200, "$expand": "dataSource"}
    return _graph_list(url, params=params, max_pages=5)



def list_purview_case_searches(case_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/searches"
    return _graph_list(url, params={"$top": 200}, max_pages=5)


def build_purview_custodian_user_source_bind_url(case_id: str, custodian_id: str, user_source_id: str) -> str:
    return (
        f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/"
        f"custodians/{custodian_id}/userSources/{user_source_id}"
    )


def build_purview_custodian_site_source_bind_url(case_id: str, custodian_id: str, site_source_id: str) -> str:
    return (
        f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/"
        f"custodians/{custodian_id}/siteSources/{site_source_id}"
    )


def build_purview_noncustodial_source_bind_url(case_id: str, noncustodial_id: str) -> str:
    return (
        f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/"
        f"noncustodialSources/{noncustodial_id}"
    )


def _dedupe_str_list(values: Optional[List[str]]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in values or []:
        value = (str(item or "")).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def create_purview_case_search(
    case_id: str,
    *,
    display_name: str,
    content_query: str,
    description: Optional[str] = None,
    custodian_source_binds: Optional[List[str]] = None,
    noncustodial_source_binds: Optional[List[str]] = None,
    data_source_scopes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/searches"
    body: Dict[str, Any] = {
        "displayName": (display_name or "").strip(),
        "contentQuery": (content_query or "").strip(),
    }
    if description:
        body["description"] = description

    custodian_binds = _dedupe_str_list(custodian_source_binds)
    if custodian_binds:
        body["custodianSources@odata.bind"] = custodian_binds

    noncustodial_binds = _dedupe_str_list(noncustodial_source_binds)
    if noncustodial_binds:
        body["noncustodialSources@odata.bind"] = noncustodial_binds

    scopes = _dedupe_str_list(data_source_scopes)
    if scopes:
        body["dataSourceScopes"] = scopes

    return _graph_request("POST", url, json=body)


def list_purview_case_operations(case_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/operations"
    return _graph_list(url, params={"$top": 200}, max_pages=5)


def get_purview_case_operation(case_id: str, operation_id: str) -> Any:
    op = (operation_id or "").strip()
    if not op:
        return None
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/operations/{op}"
    return _graph_request("GET", url, allow_statuses={200, 404})

def update_purview_case_custodian_index(case_id: str, custodian_id: str) -> Any:
    """
    Triggers Purview to (re)index a custodian's data sources.

    See: POST /security/cases/ediscoveryCases/{caseId}/custodians/{custodianId}/updateIndex
    """
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/updateIndex"
    return _graph_request("POST", url, allow_statuses={200, 202, 204})


def update_purview_case_noncustodial_index(case_id: str, noncustodial_id: str) -> Any:
    """
    Triggers Purview to (re)index a noncustodial data source.

    See: POST /security/cases/ediscoveryCases/{caseId}/noncustodialDataSources/{id}/updateIndex
    """
    url = (
        f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/"
        f"noncustodialDataSources/{noncustodial_id}/updateIndex"
    )
    return _graph_request("POST", url, allow_statuses={200, 202, 204})


def get_purview_custodian_last_index_operation(case_id: str, custodian_id: str) -> Any:
    url = (
        f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/"
        f"custodians/{custodian_id}/lastIndexOperation"
    )
    return _graph_request("GET", url, allow_statuses={200, 404})


def get_purview_noncustodial_last_index_operation(case_id: str, noncustodial_id: str) -> Any:
    # Note: Graph docs currently expose this under `noncustodialSources` rather than `noncustodialDataSources`.
    url = (
        f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/"
        f"noncustodialSources/{noncustodial_id}/lastIndexOperation"
    )
    return _graph_request("GET", url, allow_statuses={200, 404})


def list_purview_case_members(case_id: str) -> List[Dict[str, Any]]:
    # Note: caseMembers APIs are currently documented under beta.
    url = f"{purview_graph_base()}/security/cases/ediscoveryCases/{case_id}/caseMembers"
    return _graph_list(url, params={"$top": 200}, max_pages=5)


def add_purview_case_member(case_id: str, *, smtp_address: str) -> Optional[Dict[str, Any]]:
    addr = (smtp_address or "").strip()
    if not addr:
        raise ValueError("smtp_address is required")
    url = f"{purview_graph_base()}/security/cases/ediscoveryCases/{case_id}/caseMembers"
    body: Dict[str, Any] = {
        "recipientType": "user",
        "smtpAddress": addr,
    }
    return _graph_request("POST", url, json=body, allow_statuses={409})


def add_purview_case_noncustodial_user_source(
    case_id: str,
    *,
    email: str,
    included_sources: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/noncustodialDataSources"
    data_source: Dict[str, Any] = {
        "@odata.type": "microsoft.graph.security.userSource",
        "email": email,
    }
    if included_sources is not None:
        serialized = _serialize_included_sources(included_sources)
        if serialized:
            data_source["includedSources"] = serialized
    body: Dict[str, Any] = {"dataSource": data_source}
    return _graph_request("POST", url, json=body, allow_statuses={409})


def add_purview_case_noncustodial_site_source(
    case_id: str,
    *,
    site_web_url: str,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/noncustodialDataSources"
    body: Dict[str, Any] = {
        "dataSource": {
            "@odata.type": "microsoft.graph.security.siteSource",
            "site": {"webUrl": site_web_url},
        }
    }
    return _graph_request("POST", url, json=body, allow_statuses={409})


def retry_purview_hold_policy(case_id: str, hold_id: str) -> Any:
    """
    Triggers a retry/sync for a hold policy.

    See (beta): POST /security/cases/ediscoveryCases/{caseId}/legalHolds/{holdId}/retryPolicy
    """
    url = f"{purview_graph_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/retryPolicy"
    return _graph_request("POST", url, allow_statuses={200, 202, 204})


def probe_purview_portal_graph_endpoints(case_id: str) -> Dict[str, Any]:
    """
    Best-effort probing for Graph endpoints that may correspond to the Purview portal's case-level
    "Data sources" experience.

    The Purview portal UI uses an internal `/apiproxy/.../ediscovery/v1/locations` API that uses
    cookie/XSRF authentication. The Microsoft Graph eDiscovery (Premium) API exposes custodians,
    userSources, and noncustodialDataSources, but does not expose a case-level `dataSources`
    collection for app-only auth. This probe logs what we can see via Graph and confirms the portal
    endpoint requires an interactive session.
    """
    candidates = [
        # eDiscovery (Premium) APIs we already use (for comparison).
        ("security.v1.custodians", f"{purview_graph_base_v1()}/security/cases/ediscoveryCases/{case_id}/custodians"),
        ("security.v1.noncustodialDataSources", f"{purview_graph_base_v1()}/security/cases/ediscoveryCases/{case_id}/noncustodialDataSources"),
        ("security.beta.custodians", f"{purview_graph_base()}/security/cases/ediscoveryCases/{case_id}/custodians"),
        ("security.beta.noncustodialDataSources", f"{purview_graph_base()}/security/cases/ediscoveryCases/{case_id}/noncustodialDataSources"),
    ]

    results: Dict[str, Any] = {}
    try:
        results["_token_claims"] = _jwt_claims_summary(_get_access_token())
    except Exception:
        results["_token_claims"] = {"error": "claims_parse_failed"}
    for key, url in candidates:
        try:
            payload = _graph_request("GET", url, params={"$top": 5})
            if isinstance(payload, dict) and "value" in payload:
                val = payload.get("value") or []
                results[key] = {"ok": True, "count": len(val)}
            else:
                results[key] = {"ok": True, "count": None}
        except PurviewAPIError as exc:
            results[key] = {"ok": False, "status_code": exc.status_code, "error": str(exc)}
        except Exception as exc:
            results[key] = {"ok": False, "status_code": None, "error": f"unexpected_exception: {exc}"}

    # Probe the Purview portal's internal endpoint (no auth); it should consistently return 440.
    try:
        resp = _http_request(
            "POST",
            "https://purview.microsoft.com/apiproxy/aedmcc/ediscovery/v1/locations",
            json={"caseId": case_id, "probe": True},
            idempotent=True,
            allow_statuses={200, 206, 400, 401, 403, 404, 429, 440, 500, 502, 503, 504},
        )
        results["portal.locations_api"] = {
            "ok": resp.status_code in (200, 206),
            "status_code": resp.status_code,
            "requires_session_cookie": resp.status_code == 440,
        }
    except Exception as exc:
        results["portal.locations_api"] = {"ok": False, "status_code": None, "error": f"unexpected_exception: {exc}"}
    return results


def delete_purview_custodian_user_source(case_id: str, custodian_id: str, user_source_id: str) -> bool:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/userSources/{user_source_id}"
    return _graph_delete(url, allow_not_found=True)


def delete_purview_custodian_site_source(case_id: str, custodian_id: str, site_source_id: str) -> bool:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/custodians/{custodian_id}/siteSources/{site_source_id}"
    return _graph_delete(url, allow_not_found=True)


def list_purview_case_legal_holds(case_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds"
    return _graph_list(url, params={"$top": 200}, max_pages=5)


def create_purview_case_legal_hold(
    case_id: str,
    *,
    display_name: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds"
    body: Dict[str, Any] = {"displayName": display_name, "contentQuery": ""}
    if description:
        body["description"] = description
    return _graph_request("POST", url, json=body)


def list_purview_hold_user_sources(case_id: str, hold_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/userSources"
    params = {"$top": 200, "$select": "id,email,includedSources"}
    try:
        return _graph_list(url, params=params, max_pages=5)
    except PurviewAPIError as exc:
        # Some tenants/Graph versions may reject $select on this collection.
        if exc.status_code == 400:
            return _graph_list(url, params={"$top": 200}, max_pages=5)
        raise


def resolve_purview_user_emails(email: str) -> List[str]:
    """
    Best-effort resolution of alternate mailbox identifiers for a user.

    Purview hold userSources sometimes store a different identifier than the case custodian's email
    (for example UPN vs primary SMTP). This helper expands a single input into a small set of likely
    equivalents (mail, userPrincipalName, proxyAddresses).
    """
    addr = (email or "").strip()
    if not addr:
        return []

    candidates: set[str] = set()
    candidates.add(addr.lower())

    def _add(val: Optional[str]) -> None:
        if not isinstance(val, str):
            return
        v = val.strip().lower()
        if v:
            candidates.add(v)

    def _add_proxy(values: Any) -> None:
        if not isinstance(values, list):
            return
        for item in values:
            if not isinstance(item, str):
                continue
            raw = item.strip()
            if ":" in raw:
                _, rhs = raw.split(":", 1)
                _add(rhs)
            else:
                _add(raw)

    try:
        payload = _graph_request(
            "GET",
            f"{purview_graph_base()}/users/{addr}",
            params={"$select": "mail,userPrincipalName,proxyAddresses"},
            allow_statuses={404},
        )
        if isinstance(payload, dict) and "error" not in payload:
            _add(payload.get("mail"))
            _add(payload.get("userPrincipalName"))
            _add_proxy(payload.get("proxyAddresses"))
    except PurviewAPIError:
        payload = None

    if len(candidates) <= 1:
        filter_expr = f"mail eq '{_escape_odata_string(addr)}' or userPrincipalName eq '{_escape_odata_string(addr)}'"
        try:
            payload = _graph_request(
                "GET",
                f"{purview_graph_base()}/users",
                params={"$filter": filter_expr, "$select": "mail,userPrincipalName,proxyAddresses", "$top": 1},
                allow_statuses={404},
            )
            if isinstance(payload, dict) and "error" not in payload:
                users = payload.get("value") or []
                entry = users[0] if isinstance(users, list) and users and isinstance(users[0], dict) else None
                if isinstance(entry, dict):
                    _add(entry.get("mail"))
                    _add(entry.get("userPrincipalName"))
                    _add_proxy(entry.get("proxyAddresses"))
        except PurviewAPIError:
            pass

    return sorted(candidates)


def resolve_purview_user_id(email: str) -> Optional[str]:
    """
    Best-effort lookup of the Azure AD user object id for a mailbox identifier.

    This is used as an additional matching key when Purview hold userSources do not expose a usable email.
    """
    addr = (email or "").strip()
    if not addr:
        return None

    def _extract_id(payload: Any) -> Optional[str]:
        if isinstance(payload, dict) and "error" not in payload:
            candidate = payload.get("id")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        if isinstance(payload, dict):
            users = payload.get("value") or []
            if isinstance(users, list) and users:
                entry = users[0] if isinstance(users[0], dict) else {}
                candidate = entry.get("id")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return None

    try:
        payload = _graph_request(
            "GET",
            f"{purview_graph_base()}/users/{addr}",
            params={"$select": "id"},
            allow_statuses={404},
        )
        direct_id = _extract_id(payload)
        if direct_id:
            return direct_id
    except PurviewAPIError:
        pass

    filter_expr = f"mail eq '{_escape_odata_string(addr)}' or userPrincipalName eq '{_escape_odata_string(addr)}'"
    try:
        payload = _graph_request(
            "GET",
            f"{purview_graph_base()}/users",
            params={"$filter": filter_expr, "$select": "id", "$top": 1},
        )
        listed_id = _extract_id(payload)
        if listed_id:
            return listed_id
    except PurviewAPIError:
        pass

    proxy_filter = (
        f"proxyAddresses/any(p:p eq 'SMTP:{_escape_odata_string(addr)}' or p eq 'smtp:{_escape_odata_string(addr)}')"
    )
    try:
        payload = _graph_request(
            "GET",
            f"{purview_graph_base()}/users",
            params={"$filter": proxy_filter, "$select": "id", "$top": 1},
        )
        return _extract_id(payload)
    except PurviewAPIError:
        return None


def add_purview_hold_user_source(
    case_id: str,
    hold_id: str,
    *,
    email: str,
    included_sources: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/userSources"
    body: Dict[str, Any] = {
        "@odata.type": "#microsoft.graph.security.userSource",
        "email": email,
    }
    if included_sources is not None:
        serialized = _serialize_included_sources(included_sources)
        if serialized:
            body["includedSources"] = serialized
    return _graph_request("POST", url, json=body, allow_statuses={409})


def list_purview_hold_site_sources(case_id: str, hold_id: str) -> List[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/siteSources"
    params = {"$top": 200, "$expand": "site($select=id,webUrl)"}
    return _graph_list(url, params=params, max_pages=5)


def add_purview_hold_site_source(
    case_id: str,
    hold_id: str,
    *,
    site_id: Optional[str] = None,
    site_web_url: Optional[str] = None,
    site_bind_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/siteSources"
    if not site_id and not site_web_url and not site_bind_url:
        raise ValueError("site_id or site_web_url is required")
    body: Dict[str, Any] = {"@odata.type": "#microsoft.graph.security.siteSource"}
    if site_bind_url:
        body["site@odata.bind"] = site_bind_url
    else:
        site_payload = {"id": site_id} if site_id else {"webUrl": site_web_url}
        body["site"] = site_payload
    return _graph_request("POST", url, json=body, allow_statuses={409})


def update_purview_hold_user_source(
    case_id: str,
    hold_id: str,
    user_source_id: str,
    *,
    included_sources: Optional[List[str]] = None,
) -> None:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/userSources/{user_source_id}"
    serialized = _serialize_included_sources(included_sources or PURVIEW_HOLD_SOURCES)
    if not serialized:
        return
    body: Dict[str, Any] = {"includedSources": serialized}
    _graph_request("PATCH", url, json=body, allow_statuses={200, 204})


def delete_purview_hold_user_source(case_id: str, hold_id: str, user_source_id: str) -> bool:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/userSources/{user_source_id}"
    return _graph_delete(url, allow_not_found=True)


def delete_purview_hold_site_source(case_id: str, hold_id: str, site_source_id: str) -> bool:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}/siteSources/{site_source_id}"
    return _graph_delete(url, allow_not_found=True)


def delete_purview_case_legal_hold(case_id: str, hold_id: str) -> None:
    url = f"{purview_security_base()}/security/cases/ediscoveryCases/{case_id}/legalHolds/{hold_id}"
    _graph_delete(url, allow_not_found=True)


def _site_resource_from_url(web_url: str) -> Optional[Dict[str, str]]:
    if not web_url:
        return None
    parsed = urlparse(web_url)
    if not parsed.netloc or not parsed.path:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    if parts[0] in {"personal", "sites"} and len(parts) >= 2:
        site_path = "/" + "/".join(parts[:2])
    else:
        site_path = "/" + parts[0]
    url = f"{purview_graph_base_v1()}/sites/{parsed.netloc}:{site_path}"
    try:
        payload = _graph_request("GET", url, params={"$select": "id,webUrl"})
    except PurviewAPIError:
        return {"webUrl": web_url.strip()}
    if isinstance(payload, dict):
        site_id = payload.get("id")
        site_url = payload.get("webUrl")
        result: Dict[str, str] = {}
        if isinstance(site_id, str) and site_id.strip():
            result["id"] = site_id.strip()
        if isinstance(site_url, str) and site_url.strip():
            result["webUrl"] = site_url.strip()
        if result:
            return result
    return {"webUrl": web_url.strip()}


def build_purview_site_bind_url(*, site_id: Optional[str] = None, web_url: Optional[str] = None) -> Optional[str]:
    if site_id:
        return f"{purview_graph_base_v1()}/sites/{site_id}"
    if not web_url:
        return None
    parsed = urlparse(web_url)
    if not parsed.netloc or not parsed.path:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        return None
    if parts[0] in {"personal", "sites"} and len(parts) >= 2:
        site_path = "/" + "/".join(parts[:2])
    else:
        site_path = "/" + parts[0]
    encoded_path = quote(site_path, safe="/")
    return f"{purview_graph_base_v1()}/sites/{parsed.netloc}:{encoded_path}"


def _personal_host_from_root_host(root_host: str) -> Optional[str]:
    if not root_host:
        return None
    host = root_host.strip().lower()
    if "-my.sharepoint." in host:
        return host
    marker = ".sharepoint."
    if marker in host:
        prefix, suffix = host.split(marker, 1)
        if not prefix:
            return None
        return f"{prefix}-my{marker}{suffix}"
    return None


def _get_sharepoint_personal_host() -> Optional[str]:
    global _sharepoint_personal_host
    if _sharepoint_personal_host:
        return _sharepoint_personal_host
    if purview_onedrive_host():
        _sharepoint_personal_host = purview_onedrive_host()
        return _sharepoint_personal_host
    try:
        payload = _graph_request("GET", f"{purview_graph_base_v1()}/sites/root", params={"$select": "webUrl"})
    except PurviewAPIError:
        payload = None
    if not isinstance(payload, dict):
        host = None
    else:
        web_url = payload.get("webUrl")
        if not isinstance(web_url, str) or not web_url.strip():
            host = None
        else:
            parsed = urlparse(web_url)
            host = _personal_host_from_root_host(parsed.netloc) if parsed.netloc else None
    if not host:
        tenant_prefix = _tenant_prefix_from_org()
        if tenant_prefix:
            host = f"{tenant_prefix}-my.sharepoint.com"
    if host:
        _sharepoint_personal_host = host
    return host


def _tenant_prefix_from_org() -> Optional[str]:
    try:
        payload = _graph_request("GET", f"{purview_graph_base_v1()}/organization", params={"$select": "verifiedDomains"})
    except PurviewAPIError:
        return None
    if not isinstance(payload, dict):
        return None
    orgs = payload.get("value") or []
    if not isinstance(orgs, list) or not orgs:
        return None
    first = orgs[0] if isinstance(orgs[0], dict) else {}
    domains = first.get("verifiedDomains") or []
    if not isinstance(domains, list):
        return None
    preferred = None
    for entry in domains:
        if not isinstance(entry, dict):
            continue
        if entry.get("isInitial") or entry.get("isDefault"):
            preferred = entry.get("name")
            break
    if not preferred and domains:
        fallback = domains[0] if isinstance(domains[0], dict) else {}
        preferred = fallback.get("name")
    if not isinstance(preferred, str) or not preferred.strip():
        return None
    name = preferred.strip().lower()
    if name.endswith(".onmicrosoft.com"):
        return name.split(".onmicrosoft.com", 1)[0]
    return None


def _personal_site_path_from_upn(upn: str) -> Optional[str]:
    text = (upn or "").strip().lower()
    if not text:
        return None
    normalized = text.replace("@", "_").replace(".", "_").replace("#", "_")
    return f"/personal/{normalized}"


def _site_resource_from_upn(upn: str) -> Optional[Dict[str, str]]:
    path = _personal_site_path_from_upn(upn)
    if not path:
        return None
    host = _get_sharepoint_personal_host()
    if not host:
        return None
    encoded_path = quote(path, safe="/")
    url = f"{purview_graph_base_v1()}/sites/{host}:{encoded_path}"
    try:
        payload = _graph_request("GET", url, params={"$select": "id,webUrl"})
    except PurviewAPIError:
        return None
    if isinstance(payload, dict):
        site_id = payload.get("id")
        site_url = payload.get("webUrl")
        result: Dict[str, str] = {}
        if isinstance(site_id, str) and site_id.strip():
            result["id"] = site_id.strip()
        if isinstance(site_url, str) and site_url.strip():
            result["webUrl"] = site_url.strip()
        if result:
            return result
    return None


def get_purview_onedrive_site(email: str) -> Optional[Dict[str, str]]:
    addr = (email or "").strip()
    if not addr:
        return None
    url = f"{purview_graph_base()}/users/{addr}/drive"
    payload = None
    user_upn = None
    try:
        payload = _graph_request("GET", url, params={"$select": "webUrl,sharepointIds"})
    except PurviewAPIError as exc:
        msg = str(exc or "").lower()
        if exc.status_code in {403, 404} or "item not found" in msg:
            payload = None
        else:
            raise
    if not isinstance(payload, dict):
        def _extract_user_id(lookup_payload: Any) -> Optional[str]:
            if isinstance(lookup_payload, dict):
                if isinstance(lookup_payload.get("id"), str) and lookup_payload.get("id").strip():
                    return lookup_payload.get("id").strip()
                users = lookup_payload.get("value") or []
                if isinstance(users, list) and users:
                    entry = users[0] if isinstance(users[0], dict) else {}
                    candidate = entry.get("id")
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
            return None

        def _extract_user_upn(lookup_payload: Any) -> Optional[str]:
            if isinstance(lookup_payload, dict):
                direct = lookup_payload.get("userPrincipalName")
                if isinstance(direct, str) and direct.strip():
                    return direct.strip()
                users = lookup_payload.get("value") or []
                if isinstance(users, list) and users:
                    entry = users[0] if isinstance(users[0], dict) else {}
                    candidate = entry.get("userPrincipalName")
                    if isinstance(candidate, str) and candidate.strip():
                        return candidate.strip()
            return None

        user_id = None
        try:
            direct = _graph_request(
                "GET",
                f"{purview_graph_base()}/users/{addr}",
                params={"$select": "id,mail,userPrincipalName"},
                allow_statuses={404},
            )
            user_id = _extract_user_id(direct)
            user_upn = _extract_user_upn(direct)
        except PurviewAPIError as exc:
            msg = str(exc or "").lower()
            if not (exc.status_code == 404 or "item not found" in msg):
                raise
        if not user_id:
            filter_expr = f"mail eq '{_escape_odata_string(addr)}' or userPrincipalName eq '{_escape_odata_string(addr)}'"
            try:
                lookup = _graph_request(
                    "GET",
                    f"{purview_graph_base()}/users",
                    params={"$filter": filter_expr, "$select": "id,mail,userPrincipalName", "$top": 1},
                    allow_statuses={404},
                )
                user_id = _extract_user_id(lookup)
                if not user_upn:
                    user_upn = _extract_user_upn(lookup)
            except PurviewAPIError as exc:
                msg = str(exc or "").lower()
                if not (exc.status_code == 404 or "item not found" in msg):
                    raise
        if not user_id:
            proxy_filter = (
                f"proxyAddresses/any(c:c eq 'SMTP:{_escape_odata_string(addr)}') "
                f"or proxyAddresses/any(c:c eq 'smtp:{_escape_odata_string(addr)}')"
            )
            try:
                lookup = _graph_request(
                    "GET",
                    f"{purview_graph_base()}/users",
                    params={"$filter": proxy_filter, "$select": "id,mail,userPrincipalName,proxyAddresses", "$top": 1},
                    allow_statuses={404},
                )
                user_id = _extract_user_id(lookup)
                if not user_upn:
                    user_upn = _extract_user_upn(lookup)
            except PurviewAPIError as exc:
                msg = str(exc or "").lower()
                if not (exc.status_code == 404 or "item not found" in msg):
                    raise
        if user_id:
            try:
                payload = _graph_request(
                    "GET",
                    f"{purview_graph_base()}/users/{user_id}/drive",
                    params={"$select": "webUrl,sharepointIds"},
                )
            except PurviewAPIError as exc:
                msg = str(exc or "").lower()
                if exc.status_code in {403, 404} or "item not found" in msg:
                    payload = None
                else:
                    raise

    resource: Dict[str, str] = {}

    def _merge_site_resource(candidate: Optional[Dict[str, str]]) -> None:
        if not isinstance(candidate, dict):
            return
        site_id = candidate.get("id")
        if isinstance(site_id, str) and site_id.strip() and "id" not in resource:
            resource["id"] = site_id.strip()
        site_url = candidate.get("webUrl")
        if isinstance(site_url, str) and site_url.strip() and "webUrl" not in resource:
            resource["webUrl"] = site_url.strip()

    if isinstance(payload, dict):
        sharepoint = payload.get("sharepointIds") or {}
        if isinstance(sharepoint, dict):
            raw_site_id = sharepoint.get("siteId")
            if isinstance(raw_site_id, str) and raw_site_id.strip():
                resource["sharepointSiteId"] = raw_site_id.strip()
            raw_site_url = sharepoint.get("siteUrl")
            if isinstance(raw_site_url, str) and raw_site_url.strip():
                resource["sharepointSiteUrl"] = raw_site_url.strip()
        candidate_urls: list[str] = []
        if resource.get("sharepointSiteUrl"):
            candidate_urls.append(resource["sharepointSiteUrl"])
        web_url = payload.get("webUrl")
        if isinstance(web_url, str) and web_url.strip():
            candidate_urls.append(web_url.strip())
        for candidate in candidate_urls:
            _merge_site_resource(_site_resource_from_url(candidate))
        if "webUrl" not in resource and candidate_urls:
            resource["webUrl"] = candidate_urls[0]

    if not resource.get("id"):
        if not user_upn:
            user_upn = addr
        fallback = _site_resource_from_upn(user_upn)
        _merge_site_resource(fallback)

    if resource:
        if "bindUrl" not in resource:
            web_url = resource.get("webUrl") or resource.get("sharepointSiteUrl")
            bind_url = build_purview_site_bind_url(web_url=web_url) if web_url else None
            if bind_url:
                resource["bindUrl"] = bind_url
        if "bindIdUrl" not in resource:
            site_id = resource.get("id")
            bind_id_url = build_purview_site_bind_url(site_id=site_id) if site_id else None
            if bind_id_url:
                resource["bindIdUrl"] = bind_id_url

    return resource or None


def get_purview_onedrive_site_id(email: str) -> Optional[str]:
    resource = get_purview_onedrive_site(email)
    if not resource:
        return None
    site_id = resource.get("id")
    if isinstance(site_id, str) and site_id.strip():
        return site_id.strip()
    sharepoint_site_id = resource.get("sharepointSiteId")
    if isinstance(sharepoint_site_id, str) and "," in sharepoint_site_id:
        return sharepoint_site_id.strip()
    return None


def _extract_error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except Exception:
        msg = resp.text or f"HTTP {resp.status_code}"
        auth = resp.headers.get("www-authenticate")
        if resp.status_code in (401, 403) and isinstance(auth, str) and auth.strip():
            auth = auth.strip()
            if len(auth) > 600:
                auth = auth[:600] + "…"
            msg = f"{msg} (www-authenticate={auth})"
        return msg
    if isinstance(data, dict):
        raw_error = data.get("error")
        error = raw_error if isinstance(raw_error, dict) else {}
        if isinstance(raw_error, str) and raw_error.strip():
            msg = raw_error.strip()
            auth = resp.headers.get("www-authenticate")
            if resp.status_code in (401, 403) and isinstance(auth, str) and auth.strip():
                auth = auth.strip()
                if len(auth) > 600:
                    auth = auth[:600] + "…"
                msg = f"{msg} (www-authenticate={auth})"
            return msg
        message = error.get("message") if isinstance(error, dict) else None
        if isinstance(message, str) and message.strip():
            msg = message.strip()
            auth = resp.headers.get("www-authenticate")
            if resp.status_code in (401, 403) and isinstance(auth, str) and auth.strip():
                auth = auth.strip()
                if len(auth) > 600:
                    auth = auth[:600] + "…"
                msg = f"{msg} (www-authenticate={auth})"
            return msg
        if isinstance(data.get("error_description"), str):
            msg = data["error_description"]
            auth = resp.headers.get("www-authenticate")
            if resp.status_code in (401, 403) and isinstance(auth, str) and auth.strip():
                auth = auth.strip()
                if len(auth) > 600:
                    auth = auth[:600] + "…"
                msg = f"{msg} (www-authenticate={auth})"
            return msg
        if raw_error:
            msg = str(raw_error)
            auth = resp.headers.get("www-authenticate")
            if resp.status_code in (401, 403) and isinstance(auth, str) and auth.strip():
                auth = auth.strip()
                if len(auth) > 600:
                    auth = auth[:600] + "…"
                msg = f"{msg} (www-authenticate={auth})"
            return msg
    msg = resp.text or f"HTTP {resp.status_code}"
    auth = resp.headers.get("www-authenticate")
    if resp.status_code in (401, 403) and isinstance(auth, str) and auth.strip():
        auth = auth.strip()
        if len(auth) > 600:
            auth = auth[:600] + "…"
        msg = f"{msg} (www-authenticate={auth})"
    return msg


def _jwt_claims_summary(token: str) -> Dict[str, Any]:
    """
    Return a minimal, non-sensitive summary of JWT claims for debugging auth issues.
    """
    import base64

    raw = (token or "").strip()
    if raw.lower().startswith("bearer "):
        raw = raw.split(" ", 1)[1].strip()
    # Avoid logging any token content beyond a tiny prefix.
    prefix = raw[:12]
    parts = raw.split(".")
    if len(parts) < 2:
        return {"valid": False, "reason": "not_jwt", "segments": len(parts), "len": len(raw), "prefix": prefix}
    payload_b64 = parts[1]
    pad = "=" * ((4 - (len(payload_b64) % 4)) % 4)
    try:
        payload = base64.urlsafe_b64decode((payload_b64 + pad).encode("utf-8"))
        data = json.loads(payload.decode("utf-8", "ignore"))
    except Exception:
        return {
            "valid": False,
            "reason": "decode_failed",
            "segments": len(parts),
            "len": len(raw),
            "prefix": prefix,
        }
    scp = data.get("scp")
    roles = data.get("roles")
    summary = {
        "valid": True,
        "tid": data.get("tid"),
        "aud": data.get("aud"),
        "idtyp": data.get("idtyp"),
        "has_scp": bool(isinstance(scp, str) and scp.strip()),
        "scp": scp if isinstance(scp, str) else None,
        "roles_count": len(roles) if isinstance(roles, list) else 0,
    }
    if isinstance(roles, list) and roles:
        # Include up to 15 role strings for debugging. These are not secrets.
        summary["roles_preview"] = [str(r) for r in roles[:15]]
    return summary




