from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
import httpx

from .safe_log import debug_suppressed as _debug_suppressed
from .ai_config import ai_client_config, ai_configured, ai_feature_enabled, ai_headers

logger = logging.getLogger(__name__)

_PLACEHOLDER_EMAILS = {"noemail", "unmatched"}


def is_name_email_review_enabled() -> bool:
    return ai_feature_enabled("name_email_review_enabled", "CUSTODIAN_NAME_EMAIL_REVIEW_ENABLED", default=True)


def is_name_email_ai_enabled() -> bool:
    if not ai_feature_enabled("name_email_ai_enabled", "CUSTODIAN_NAME_EMAIL_AI_ENABLED", default=False):
        return False
    return ai_configured(feature_prefix="CUSTODIAN_NAME_EMAIL_AI")


def _mask_email(email: Optional[str]) -> str:
    raw = (email or "").strip().lower()
    if not raw or "@" not in raw:
        return ""
    local, domain = raw.split("@", 1)
    local = local[:1] + "***" if local else "***"
    return f"{local}@{domain}"


def _emit(event: str, **details: Any) -> None:
    payload = {"event": event, **details}
    try:
        logger.info("name_email_review %s", json.dumps(payload, default=str))
    except Exception as exc:
        _debug_suppressed("name_email_review_emit_failed", exc)


def _clean_token_text(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _name_tokens(value: Optional[str]) -> list[str]:
    text = _clean_token_text(value)
    return [token for token in text.split(" ") if token]


def _email_tokens(email: Optional[str]) -> list[str]:
    raw = (email or "").strip().lower()
    if not raw or "@" not in raw:
        return []
    local = raw.split("@", 1)[0]
    if not local or local in _PLACEHOLDER_EMAILS:
        return []
    local = local.replace("+", ".")
    parts = re.split(r"[^a-z0-9]+", local)
    return [token for token in parts if token]


def _first_last_tokens(
    *,
    name: Optional[str],
    lookup_first_name: Optional[str],
    lookup_last_name: Optional[str],
) -> tuple[Optional[str], Optional[str], list[str]]:
    tokens = _name_tokens(name)
    if len(tokens) >= 2:
        return tokens[0], tokens[-1], tokens
    lookup_first = _clean_token_text(lookup_first_name)
    lookup_last = _clean_token_text(lookup_last_name)
    if lookup_first and lookup_last:
        return lookup_first, lookup_last, [lookup_first, lookup_last]
    if len(tokens) == 1 and lookup_last:
        return tokens[0], lookup_last, [tokens[0], lookup_last]
    return None, None, tokens


@dataclass
class NameEmailReviewResult:
    requires_review: bool
    reason: Optional[str] = None
    source: str = "rules"
    confidence: Optional[float] = None


def _rules_review(
    *,
    name: Optional[str],
    email: Optional[str],
    lookup_first_name: Optional[str],
    lookup_last_name: Optional[str],
) -> NameEmailReviewResult:
    email_parts = _email_tokens(email)
    if not email_parts:
        return NameEmailReviewResult(requires_review=False, source="rules")

    first, last, name_parts = _first_last_tokens(
        name=name,
        lookup_first_name=lookup_first_name,
        lookup_last_name=lookup_last_name,
    )
    if not first or not last:
        return NameEmailReviewResult(requires_review=False, source="rules")

    joined = "".join(email_parts)
    overlap = set(name_parts) & set(email_parts)
    first_initial = first[0] if first else ""

    has_first = first in email_parts or first in joined
    has_last = last in email_parts or last in joined
    has_first_last_combo = f"{first}{last}" in joined or f"{last}{first}" in joined
    has_initial_combo = bool(first_initial) and (
        f"{first_initial}{last}" in joined or f"{last}{first_initial}" in joined
    )

    if has_first_last_combo or has_initial_combo:
        return NameEmailReviewResult(requires_review=False, source="rules")
    if has_last and (has_first or has_initial_combo):
        return NameEmailReviewResult(requires_review=False, source="rules")
    if overlap and (first in overlap or last in overlap):
        return NameEmailReviewResult(requires_review=False, source="rules")

    if not overlap and not has_first and not has_last:
        return NameEmailReviewResult(
            requires_review=True,
            reason="Name/email mismatch suspected: email alias does not match expected name tokens.",
            source="rules",
            confidence=0.9,
        )

    return NameEmailReviewResult(requires_review=False, source="rules")


def _extract_json_obj(text: str) -> Optional[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        snippet = raw[start : end + 1]
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _parse_ai_decision(payload: Any) -> Optional[NameEmailReviewResult]:
    data: dict[str, Any]
    if isinstance(payload, dict):
        data = payload
    elif isinstance(payload, str):
        parsed = _extract_json_obj(payload)
        if not parsed:
            return None
        data = parsed
    else:
        return None

    raw_decision = str(
        data.get("decision")
        or data.get("verdict")
        or data.get("result")
        or ""
    ).strip().lower()
    if not raw_decision:
        if isinstance(data.get("requires_review"), bool):
            raw_decision = "review" if data.get("requires_review") else "ok"
        elif isinstance(data.get("needs_review"), bool):
            raw_decision = "review" if data.get("needs_review") else "ok"

    requires_review = raw_decision in {"review", "mismatch", "no", "flag", "needs_review"}
    if raw_decision in {"ok", "match", "yes", "pass"}:
        requires_review = False

    confidence = None
    try:
        if data.get("confidence") is not None:
            confidence = float(data.get("confidence"))
    except Exception:
        confidence = None

    reason = (str(data.get("reason") or data.get("explanation") or "").strip() or None)
    return NameEmailReviewResult(
        requires_review=requires_review,
        reason=reason,
        source="llm",
        confidence=confidence,
    )


def _ai_review(
    *,
    name: Optional[str],
    email: Optional[str],
    lookup_first_name: Optional[str],
    lookup_last_name: Optional[str],
) -> Optional[NameEmailReviewResult]:
    if not is_name_email_ai_enabled():
        return None

    ai_cfg = ai_client_config(feature_prefix="CUSTODIAN_NAME_EMAIL_AI", timeout_minimum=1.0)
    url = ai_cfg["url"]
    model = ai_cfg["model"]
    timeout_seconds = ai_cfg["timeout_seconds"]
    endpoint_host = ai_cfg["endpoint_host"]
    headers = ai_headers(ai_cfg)

    prompt_payload = {
        "name": (name or "").strip(),
        "email": (email or "").strip(),
        "lookup_first_name": (lookup_first_name or "").strip(),
        "lookup_last_name": (lookup_last_name or "").strip(),
    }
    user_prompt = (
        "Determine whether this person name appears to match this corporate email alias. "
        "Be conservative: only flag review when mismatch risk is meaningful. "
        "Return JSON only with keys: decision (ok|review), reason, confidence.\n"
        f"Input: {json.dumps(prompt_payload)}"
    )
    messages = [
        {
            "role": "system",
            "content": "You validate person-name and email-alias consistency for legal workflows.",
        },
        {"role": "user", "content": user_prompt},
    ]
    _emit(
        "ai_request_start",
        email=_mask_email(email),
        model=model,
        endpoint_host=endpoint_host,
        timeout_seconds=timeout_seconds,
    )

    payload = None
    status_code: Optional[int] = None
    errors: list[str] = []
    attempts = [
        {"include_model": True, "include_temperature": True, "include_response_format": True},
        {"include_model": True, "include_temperature": True, "include_response_format": False},
        {"include_model": False, "include_temperature": True, "include_response_format": True},
        {"include_model": False, "include_temperature": True, "include_response_format": False},
        {"include_model": False, "include_temperature": False, "include_response_format": False},
    ]

    for spec in attempts:
        attempt_body: dict[str, Any] = {"messages": messages}
        if spec["include_model"]:
            attempt_body["model"] = model
        if spec["include_temperature"]:
            attempt_body["temperature"] = 0
        if spec["include_response_format"]:
            attempt_body["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(url, headers=headers, json=attempt_body, timeout=timeout_seconds)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            _emit(
                "ai_request_success",
                email=_mask_email(email),
                model=model,
                endpoint_host=endpoint_host,
                status_code=response.status_code,
                attempt=spec,
            )
            break
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            body_text = (getattr(exc.response, "text", "") or "").strip()
            body_short = body_text[:500]
            errors.append(f"{exc}; attempt={spec}; response_body={body_short}")
            _debug_suppressed("name_email_ai_request_failed_http", exc)
            continue
        except Exception as exc:
            errors.append(f"{exc}; attempt={spec}")
            _debug_suppressed("name_email_ai_request_failed", exc)
            continue

    if payload is None:
        _emit(
            "ai_request_failed",
            email=_mask_email(email),
            model=model,
            endpoint_host=endpoint_host,
            error=(errors[-1] if errors else "request_failed"),
            status_code=status_code,
        )
        return None
    try:
        content = (
            ((payload.get("choices") or [{}])[0] or {})
            .get("message", {})
            .get("content")
        )
    except Exception:
        content = None

    parsed = _parse_ai_decision(content) if content is not None else None
    if parsed is not None:
        return parsed
    return _parse_ai_decision(payload)


def evaluate_name_email_review(
    *,
    name: Optional[str],
    email: Optional[str],
    lookup_first_name: Optional[str] = None,
    lookup_last_name: Optional[str] = None,
    use_ai: bool = True,
) -> NameEmailReviewResult:
    review_enabled = is_name_email_review_enabled()
    ai_enabled = use_ai and is_name_email_ai_enabled()

    _emit(
        "review_start",
        email=_mask_email(email),
        review_enabled=review_enabled,
        ai_enabled=ai_enabled,
    )

    if not review_enabled:
        result = NameEmailReviewResult(requires_review=False, source="disabled")
        _emit("review_decision", email=_mask_email(email), source=result.source, requires_review=result.requires_review)
        return result

    rules = _rules_review(
        name=name,
        email=email,
        lookup_first_name=lookup_first_name,
        lookup_last_name=lookup_last_name,
    )
    if rules.requires_review or not use_ai:
        _emit(
            "review_decision",
            email=_mask_email(email),
            source=rules.source,
            requires_review=rules.requires_review,
            confidence=rules.confidence,
            reason=rules.reason,
        )
        return rules

    ai_result = _ai_review(
        name=name,
        email=email,
        lookup_first_name=lookup_first_name,
        lookup_last_name=lookup_last_name,
    )
    if ai_result is None:
        _emit(
            "review_decision",
            email=_mask_email(email),
            source=rules.source,
            requires_review=rules.requires_review,
            confidence=rules.confidence,
            reason=rules.reason,
            ai_fallback=True,
        )
        return rules

    if ai_result.requires_review:
        _emit(
            "review_decision",
            email=_mask_email(email),
            source=ai_result.source,
            requires_review=ai_result.requires_review,
            confidence=ai_result.confidence,
            reason=ai_result.reason,
        )
        return ai_result

    _emit(
        "review_decision",
        email=_mask_email(email),
        source=rules.source,
        requires_review=rules.requires_review,
        confidence=rules.confidence,
        reason=rules.reason,
    )
    return rules


def apply_custodian_name_email_review(custodian: Any, *, use_ai: bool = True) -> NameEmailReviewResult:
    result = evaluate_name_email_review(
        name=getattr(custodian, "name", None),
        email=getattr(custodian, "email", None),
        lookup_first_name=getattr(custodian, "person_first_name", None),
        lookup_last_name=getattr(custodian, "person_last_name", None),
        use_ai=use_ai,
    )
    try:
        custodian.name_email_review_required = bool(result.requires_review)
        custodian.name_email_review_reason = result.reason if result.requires_review else None
        custodian.name_email_review_last_checked_at = datetime.now(timezone.utc)
    except Exception as exc:
        _debug_suppressed("name_email_review_apply_failed", exc)
    return result

