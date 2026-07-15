import json
import logging
import os
from typing import Any, Dict, Iterable, Optional, Tuple

import httpx

from .app_branding import app_display_name
from .integration_settings import config_value, integration_enabled


logger = logging.getLogger(__name__)

_LEGACY_POLICY_PREFIX = "DiscoveryOne Case"
_POLICY_NAME_LIMIT = 150


def _slack_token() -> str:
    return config_value("slack", "legal_holds_token", "SLACK_LEGAL_HOLDS_TOKEN")


def _slack_api_base() -> str:
    return config_value("slack", "api_base", "SLACK_API_BASE", "https://slack.com/api").rstrip("/")


def _policy_prefix() -> str:
    return config_value("slack", "policy_prefix", "SLACK_LEGAL_HOLDS_POLICY_PREFIX")


def _policy_name_mode() -> str:
    return config_value("slack", "policy_name_mode", "SLACK_LEGAL_HOLDS_POLICY_NAME_MODE", "case_name").lower()

_ADD_ENTITY_IDEMPOTENT_ERRORS = {
    "already_exists",
    "already_in_policy",
    "entity_already_exists",
    "entities_already_exist",
}
_REMOVE_ENTITY_IDEMPOTENT_ERRORS = {
    "entity_not_found",
    "entities_not_found",
    "not_in_policy",
}


class SlackLegalHoldsConfigError(RuntimeError):
    """Raised when the Slack Legal Holds integration is not configured."""


class SlackLegalHoldsAPIError(RuntimeError):
    """Raised when Slack returns an error."""

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code


def _emit(event: str, **fields: Any) -> None:
    try:
        payload = json.dumps(fields, ensure_ascii=True, sort_keys=True, default=str)
    except Exception:
        payload = str(fields)
    logger.info("slack_legal_holds %s %s", event, payload)


def slack_legal_holds_enabled() -> bool:
    return integration_enabled("slack") and bool(_slack_token())


def _normalize_form_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, dict)):
        return json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return str(value)


def _build_form_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in (payload or {}).items():
        if value is None:
            continue
        out[key] = _normalize_form_value(value)
    return out


def _loggable_payload(payload: Dict[str, str]) -> Dict[str, Any]:
    redacted: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"entity_ids", "user_ids", "ids"}:
            try:
                parsed = json.loads(str(value))
                if isinstance(parsed, list):
                    redacted[f"{key}_count"] = len(parsed)
                else:
                    redacted[f"{key}_count"] = 1 if str(value).strip() else 0
            except Exception:
                count = len([x for x in str(value).split(",") if x.strip()])
                redacted[f"{key}_count"] = count
            continue
        if key == "entities":
            try:
                parsed = json.loads(str(value))
                redacted["entities_count"] = len(parsed) if isinstance(parsed, list) else 1
            except Exception:
                redacted["entities"] = "<set>" if value else ""
            continue
        if key in {"cursor"}:
            redacted[key] = "<set>" if value else ""
            continue
        text = str(value)
        if len(text) > 120:
            text = text[:120] + "..."
        redacted[key] = text
    return redacted


def _next_cursor(data: Dict[str, Any]) -> Optional[str]:
    metadata = data.get("response_metadata")
    if not isinstance(metadata, dict):
        return None
    cursor = (metadata.get("next_cursor") or "").strip()
    return cursor or None


def _slack_post(method: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not slack_legal_holds_enabled():
        raise SlackLegalHoldsConfigError(
            "Slack Legal Holds integration is not configured. Configure the Slack Legal Holds token in System > Integrations."
        )
    token = _slack_token()
    url = f"{_slack_api_base()}/{method}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = _build_form_payload(payload)
    _emit("api_request", method=method, payload=_loggable_payload(body))
    try:
        resp = httpx.post(url, headers=headers, data=body, timeout=30)
    except httpx.RequestError as exc:
        _emit("api_request_error", method=method, error=str(exc))
        raise SlackLegalHoldsAPIError(f"Unable to reach Slack API: {exc}") from exc

    _emit("api_response_status", method=method, status_code=resp.status_code)
    if resp.status_code != 200:
        _emit("api_response_http_error", method=method, status_code=resp.status_code, body=(resp.text or "")[:300])
        raise SlackLegalHoldsAPIError(
            f"Slack API returned HTTP {resp.status_code} for {method}",
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except Exception as exc:
        _emit("api_response_invalid_json", method=method, body=(resp.text or "")[:300])
        raise SlackLegalHoldsAPIError("Slack API returned invalid JSON") from exc

    if not isinstance(data, dict):
        _emit("api_response_unexpected_payload", method=method)
        raise SlackLegalHoldsAPIError("Slack API returned an unexpected response payload")

    if not data.get("ok"):
        code = str(data.get("error") or "").strip() or None
        _emit("api_response_error", method=method, error_code=code, status_code=resp.status_code)
        message = f"Slack API {method} failed"
        if code:
            message = f"{message}: {code}"
        raise SlackLegalHoldsAPIError(message, error_code=code, status_code=resp.status_code)

    _emit("api_response_ok", method=method, keys=sorted(data.keys()))
    return data


def _iter_items(method: str, key: str, *, limit: int = 200, **kwargs: Any) -> Iterable[Dict[str, Any]]:
    cursor: Optional[str] = None
    while True:
        payload: Dict[str, Any] = dict(kwargs)
        payload["limit"] = limit
        if cursor:
            payload["cursor"] = cursor
        data = _slack_post(method, payload)
        items = data.get(key) or []
        _emit("page_received", method=method, key=key, count=len(items), has_cursor=bool(_next_cursor(data)))
        for item in items:
            if isinstance(item, dict):
                yield item
        cursor = _next_cursor(data)
        if not cursor:
            break


def _extract_policy_id(policy: Dict[str, Any]) -> Optional[str]:
    for key in ("id", "policy_id"):
        value = policy.get(key)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _extract_policy_name(policy: Dict[str, Any]) -> str:
    return str(policy.get("name") or "").strip()


def _extract_policy_description(policy: Dict[str, Any]) -> str:
    return str(policy.get("description") or "").strip()


def _extract_user_id(item: Dict[str, Any]) -> Optional[str]:
    candidates = [
        item.get("id"),
        item.get("user_id"),
        ((item.get("user") or {}).get("id") if isinstance(item.get("user"), dict) else None),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return None


def _extract_user_email(item: Dict[str, Any]) -> Optional[str]:
    profile = item.get("profile") if isinstance(item.get("profile"), dict) else {}
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    user_profile = user.get("profile") if isinstance(user.get("profile"), dict) else {}
    candidates = [
        item.get("email"),
        profile.get("email"),
        user.get("email"),
        user_profile.get("email"),
    ]
    for candidate in candidates:
        text = (candidate or "").strip()
        if text:
            return text
    return None


def _legacy_case_policy_prefix(case_id: int) -> str:
    return f"{_LEGACY_POLICY_PREFIX} #{case_id}:"


def _case_policy_name(case_id: int, case_name: str) -> str:
    clean_name = " ".join((case_name or "").split()) or f"Case {case_id}"
    policy_prefix = _policy_prefix()
    if _policy_name_mode() == "legacy_prefix":
        prefix = policy_prefix or _LEGACY_POLICY_PREFIX
        label = f"{prefix} #{case_id}: {clean_name}"
        return label[:_POLICY_NAME_LIMIT]
    if policy_prefix:
        label = f"{policy_prefix}: {clean_name}"
    else:
        label = clean_name
    return label[:_POLICY_NAME_LIMIT]


def _policy_matches_case(policy: Dict[str, Any], *, case_id: int, case_name: str) -> bool:
    policy_id = _extract_policy_id(policy)
    if not policy_id:
        return False
    name = _extract_policy_name(policy)
    desc = _extract_policy_description(policy).lower()
    # Strongest signal: our case marker in description (used on policy create).
    if f"case #{case_id}" in desc:
        return True
    # Backward compatibility with older DiscoveryOne naming.
    if name.startswith(_legacy_case_policy_prefix(case_id)):
        return True
    # Name-only match is accepted only for DiscoveryOne-managed descriptions.
    managed_desc = "managed by discoveryone" in desc
    if managed_desc and name == _case_policy_name(case_id, case_name):
        return True
    return False


def _policy_is_released(policy: Dict[str, Any]) -> bool:
    state = str(policy.get("state") or policy.get("status") or "").strip().lower()
    if state in {"released", "inactive", "archived", "closed"}:
        return True
    for key in ("is_released", "released", "is_inactive", "inactive", "is_closed", "closed"):
        value = policy.get(key)
        if isinstance(value, bool) and value:
            return True
        if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "released", "inactive", "closed"}:
            return True
    return False


def _find_policy_by_id(policy_id: str) -> Optional[Dict[str, Any]]:
    target = (policy_id or "").strip()
    if not target:
        return None
    for policy in _iter_items("admin.legalHold.policies.list", "policies", limit=100):
        if _extract_policy_id(policy) == target:
            return policy
    return None


def find_case_policy_id(case_id: int, case_name: str) -> Optional[str]:
    _emit("find_case_policy_start", case_id=case_id, case_name=(case_name or "")[:120])
    for policy in _iter_items("admin.legalHold.policies.list", "policies", limit=100):
        policy_id = _extract_policy_id(policy)
        if not policy_id or not _policy_matches_case(policy, case_id=case_id, case_name=case_name):
            continue
        if _policy_is_released(policy):
            _emit("find_case_policy_skip_released", case_id=case_id, policy_id=policy_id)
            continue
        _emit("find_case_policy_match", case_id=case_id, policy_id=policy_id)
        return policy_id
    _emit("find_case_policy_none", case_id=case_id)
    return None


def ensure_case_policy(case_id: int, case_name: str, existing_policy_id: Optional[str] = None) -> str:
    if existing_policy_id:
        existing = _find_policy_by_id(existing_policy_id)
        if existing and not _policy_is_released(existing):
            _emit("ensure_case_policy_existing", case_id=case_id, policy_id=existing_policy_id)
            return existing_policy_id
        _emit("ensure_case_policy_existing_invalid", case_id=case_id, policy_id=existing_policy_id)
    found = find_case_policy_id(case_id, case_name)
    if found:
        _emit("ensure_case_policy_reuse", case_id=case_id, policy_id=found)
        return found
    created = _slack_post(
        "admin.legalHold.policies.create",
        {
            "name": _case_policy_name(case_id, case_name),
            "description": f"Managed by {app_display_name()} for case #{case_id}.",
        },
    )
    raw_policy = created.get("policy")
    if isinstance(raw_policy, dict):
        policy_id = _extract_policy_id(raw_policy)
    else:
        policy_id = _extract_policy_id(created)
    if not policy_id:
        raise SlackLegalHoldsAPIError("Slack policy creation succeeded but no policy id was returned")
    _emit("ensure_case_policy_created", case_id=case_id, policy_id=policy_id)
    return policy_id

def resolve_slack_user_id_by_email(email: str) -> str:
    target = (email or "").strip().lower()
    if not target:
        raise SlackLegalHoldsAPIError("Slack hold requires a custodian email")
    _emit("resolve_user_start", email=target)
    for item in _iter_items("admin.users.list", "users", limit=100):
        item_email = (_extract_user_email(item) or "").strip().lower()
        if item_email != target:
            continue
        user_id = _extract_user_id(item)
        if user_id:
            _emit("resolve_user_match", email=target, user_id=user_id)
            return user_id
    _emit("resolve_user_not_found", email=target)
    raise SlackLegalHoldsAPIError(
        f"No Slack user found for email '{email}'",
        error_code="user_not_found",
    )


def _add_user_to_policy(policy_id: str, user_id: str) -> None:
    try:
        _slack_post(
            "admin.legalHold.entities.add",
            {"policy_id": policy_id, "entities": [{"entity_type": "USER", "entity_id": user_id}]},
        )
        _emit("entity_add_ok", policy_id=policy_id, user_id=user_id)
    except SlackLegalHoldsAPIError as exc:
        if exc.error_code in _ADD_ENTITY_IDEMPOTENT_ERRORS:
            _emit("entity_add_idempotent", policy_id=policy_id, user_id=user_id, error_code=exc.error_code)
            return
        _emit("entity_add_failed", policy_id=policy_id, user_id=user_id, error_code=exc.error_code)
        raise


def _policy_entity_ids_for_user(policy_id: str, user_id: str) -> list[str]:
    ids: list[str] = []
    for item in _iter_items("admin.legalHold.entities.list", "entities", limit=100, policy_id=policy_id):
        entity_type = str(item.get("entity_type") or "").strip().upper()
        if entity_type != "USER":
            continue
        if str(item.get("entity_id") or "").strip() != user_id:
            continue
        entity_row_id = str(item.get("id") or "").strip()
        if entity_row_id:
            ids.append(entity_row_id)
    _emit("entity_lookup_for_remove", policy_id=policy_id, user_id=user_id, match_count=len(ids))
    return ids


def _remove_user_from_policy(policy_id: str, user_id: str) -> None:
    ids = _policy_entity_ids_for_user(policy_id, user_id)
    if not ids:
        _emit("entity_remove_skip_not_found", policy_id=policy_id, user_id=user_id)
        return
    try:
        _slack_post(
            "admin.legalHold.entities.remove",
            {"policy_id": policy_id, "ids": ids},
        )
        _emit("entity_remove_ok", policy_id=policy_id, user_id=user_id, removed_count=len(ids))
    except SlackLegalHoldsAPIError as exc:
        if exc.error_code in _REMOVE_ENTITY_IDEMPOTENT_ERRORS:
            _emit("entity_remove_idempotent", policy_id=policy_id, user_id=user_id, error_code=exc.error_code)
            return
        _emit("entity_remove_failed", policy_id=policy_id, user_id=user_id, error_code=exc.error_code)
        raise


def sync_slack_hold_for_custodian(
    *,
    case_id: int,
    case_name: str,
    custodian_email: Optional[str],
    enable: bool,
    case_policy_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    if not slack_legal_holds_enabled():
        raise SlackLegalHoldsConfigError(
            "Slack Legal Holds integration is not configured. Configure the Slack Legal Holds token in System > Integrations."
        )
    email = (custodian_email or "").strip()
    _emit(
        "sync_start",
        case_id=case_id,
        case_name=(case_name or "")[:120],
        enable=enable,
        has_email=bool(email),
        has_case_policy_id=bool(case_policy_id),
    )

    if enable:
        if not email:
            raise SlackLegalHoldsAPIError("Slack hold requires a custodian email")
        user_id = resolve_slack_user_id_by_email(email)
        policy_id = ensure_case_policy(case_id, case_name, existing_policy_id=case_policy_id)
        try:
            _add_user_to_policy(policy_id, user_id)
        except SlackLegalHoldsAPIError as exc:
            if exc.error_code == "released_policy_edit_not_allowed":
                _emit(
                    "sync_retry_released_policy",
                    case_id=case_id,
                    stale_policy_id=policy_id,
                    user_id=user_id,
                )
                policy_id = ensure_case_policy(case_id, case_name, existing_policy_id=None)
                _add_user_to_policy(policy_id, user_id)
            else:
                raise
        _emit("sync_success", case_id=case_id, enable=True, policy_id=policy_id, user_id=user_id)
        return policy_id, user_id

    if case_policy_id:
        existing = _find_policy_by_id(case_policy_id)
        if existing and _policy_is_released(existing):
            _emit("sync_release_skip_released_policy", case_id=case_id, policy_id=case_policy_id)
            return None, None
    if not case_policy_id:
        case_policy_id = find_case_policy_id(case_id, case_name)
    if not case_policy_id:
        _emit("sync_release_skip_no_policy", case_id=case_id)
        return None, None
    if not email:
        _emit("sync_release_skip_no_email", case_id=case_id, policy_id=case_policy_id)
        return case_policy_id, None
    user_id = resolve_slack_user_id_by_email(email)
    _remove_user_from_policy(case_policy_id, user_id)
    _emit("sync_success", case_id=case_id, enable=False, policy_id=case_policy_id, user_id=user_id)
    return case_policy_id, user_id
