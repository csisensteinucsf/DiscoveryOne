"""AI narrative generation for case summary payloads."""

from __future__ import annotations

import json
import logging
from typing import Any
import httpx

from . import models
from .safe_log import debug_suppressed as _debug_suppressed
from .ai_config import ai_client_config, ai_configured, ai_feature_enabled, ai_headers

logger = logging.getLogger(__name__)


def _is_case_summary_ai_configured() -> bool:
    if not ai_feature_enabled("case_summary_enabled", "CASE_SUMMARY_AI_ENABLED", default=True):
        return False
    return ai_configured(feature_prefix="CASE_SUMMARY_AI")


def _extract_json_obj(text: str) -> dict[str, Any] | None:
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


def _as_str_list(value: Any, *, limit: int = 10) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text_value = str(item or "").strip()
        if not text_value:
            continue
        out.append(text_value)
        if len(out) >= max(1, limit):
            break
    return out


def _parse_case_summary_ai(payload: Any) -> dict[str, Any] | None:
    data: dict[str, Any] | None = None
    if isinstance(payload, dict):
        data = payload
    elif isinstance(payload, str):
        data = _extract_json_obj(payload)
    if not isinstance(data, dict):
        return None

    narrative = str(
        data.get("executive_summary")
        or data.get("summary")
        or data.get("narrative")
        or ""
    ).strip()
    case_phase = str(data.get("case_phase") or data.get("phase") or "").strip() or None
    overall_risk = str(data.get("overall_risk") or data.get("risk") or "").strip().lower() or None
    confidence = None
    try:
        if data.get("confidence") is not None:
            confidence = float(data.get("confidence"))
    except Exception:
        confidence = None

    attention_items = _as_str_list(
        data.get("attention_items")
        or data.get("what_needs_attention")
        or data.get("issues")
    )
    recommended_actions = _as_str_list(
        data.get("recommended_actions")
        or data.get("next_actions")
        or data.get("actions")
    )
    progress_highlights = _as_str_list(
        data.get("progress_highlights")
        or data.get("highlights")
    )

    if not narrative and not attention_items and not recommended_actions:
        return None

    return {
        "narrative": narrative,
        "case_phase": case_phase,
        "overall_risk": overall_risk,
        "confidence": confidence,
        "attention_items": attention_items,
        "recommended_actions": recommended_actions,
        "progress_highlights": progress_highlights,
    }


def _compose_case_summary_ai_report_text(
    *,
    case: models.Case,
    ai: dict[str, Any],
    fallback_text: str,
    generated_at: str,
) -> str:
    narrative = str(ai.get("narrative") or "").strip()
    attention_items = _as_str_list(ai.get("attention_items"), limit=20)
    recommended_actions = _as_str_list(ai.get("recommended_actions"), limit=20)
    progress_highlights = _as_str_list(ai.get("progress_highlights"), limit=20)
    lines: list[str] = []
    lines.append("DiscoveryOne AI Case Summary")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Case: {(getattr(case, 'name', None) or '').strip() or '-'}")
    phase = str(ai.get("case_phase") or "").strip()
    risk = str(ai.get("overall_risk") or "").strip()
    if phase:
        lines.append(f"Case phase: {phase}")
    if risk:
        lines.append(f"Overall risk: {risk}")
    confidence = ai.get("confidence")
    if isinstance(confidence, (int, float)):
        lines.append(f"AI confidence: {confidence:.2f}")
    lines.append("")

    if narrative:
        lines.append("Executive summary")
        lines.append(narrative)
        lines.append("")

    if progress_highlights:
        lines.append("Progress highlights")
        for item in progress_highlights:
            lines.append(f"- {item}")
        lines.append("")

    if attention_items:
        lines.append("Needs attention")
        for item in attention_items:
            lines.append(f"- {item}")
        lines.append("")

    if recommended_actions:
        lines.append("Recommended actions")
        for item in recommended_actions:
            lines.append(f"- {item}")
        lines.append("")

    if len(lines) <= 6 and fallback_text:
        return fallback_text
    return "\n".join(lines).strip()


def _build_case_summary_ai(
    *,
    case: models.Case,
    facts: dict[str, Any],
) -> dict[str, Any]:
    if not _is_case_summary_ai_configured():
        return {
            "enabled": False,
            "status": "not_configured",
            "error": "AI integration URL/model is not configured.",
        }

    ai_cfg = ai_client_config(feature_prefix="CASE_SUMMARY_AI", timeout_minimum=5.0)
    url = ai_cfg["url"]
    model = ai_cfg["model"]
    timeout_seconds = ai_cfg["timeout_seconds"]
    temperature = ai_cfg["temperature"]
    endpoint_host = ai_cfg["endpoint_host"]
    headers = ai_headers(ai_cfg)

    compact_facts = {
        "generated_at": facts.get("generated_at"),
        "case": facts.get("case"),
        "sections": facts.get("sections"),
        "needs_attention": facts.get("needs_attention"),
    }

    system_prompt = (
        ai_cfg.get("system_prompt")
        or "You are an eDiscovery legal operations analyst. Produce concise, practical case status summaries and next actions."
    ).strip()

    user_prompt = (
        "Analyze this DiscoveryOne case snapshot and return JSON only with keys: "
        "executive_summary (string), case_phase (string), overall_risk (low|medium|high), "
        "progress_highlights (array of strings), attention_items (array of strings), "
        "recommended_actions (array of strings), confidence (0-1 number). "
        "Prioritize actionable legal-ops guidance and avoid speculation.\n"
        f"Case snapshot JSON: {json.dumps(compact_facts, default=str)}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    logger.info(
        "case_summary_ai %s",
        json.dumps(
            {
                "event": "request_start",
                "case_id": int(getattr(case, "id", 0) or 0),
                "case_name": getattr(case, "name", None),
                "model": model,
                "endpoint_host": endpoint_host,
                "timeout_seconds": timeout_seconds,
            },
            default=str,
        ),
    )

    payload = None
    status_code = None
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
            attempt_body["temperature"] = temperature
        if spec["include_response_format"]:
            attempt_body["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(url, headers=headers, json=attempt_body, timeout=timeout_seconds)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            break
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            body_text = (getattr(exc.response, "text", "") or "").strip()
            body_short = body_text[:500]
            errors.append(
                f"{exc}; attempt={spec}; response_body={body_short}"
            )
            _debug_suppressed("case_summary_ai_request_failed_http", exc)
            continue
        except Exception as exc:
            errors.append(f"{exc}; attempt={spec}")
            _debug_suppressed("case_summary_ai_request_failed", exc)
            continue
    if payload is None:
        logger.info(
            "case_summary_ai %s",
            json.dumps(
                {
                    "event": "request_failed",
                    "case_id": int(getattr(case, "id", 0) or 0),
                    "model": model,
                    "endpoint_host": endpoint_host,
                    "error": errors[-1] if errors else "request_failed",
                    "status_code": status_code,
                },
                default=str,
            ),
        )
        return {
            "enabled": True,
            "status": "error",
            "model": model,
            "endpoint_host": endpoint_host,
            "status_code": status_code,
            "error": errors[-1] if errors else "request_failed",
        }

    content = None
    try:
        content = (
            ((payload.get("choices") or [{}])[0] or {})
            .get("message", {})
            .get("content")
        )
    except Exception:
        content = None

    parsed = _parse_case_summary_ai(content) if content is not None else None
    if parsed is None:
        parsed = _parse_case_summary_ai(payload)

    if parsed is None:
        logger.info(
            "case_summary_ai %s",
            json.dumps(
                {
                    "event": "response_unparseable",
                    "case_id": int(getattr(case, "id", 0) or 0),
                    "model": model,
                    "endpoint_host": endpoint_host,
                    "status_code": status_code,
                },
                default=str,
            ),
        )
        return {
            "enabled": True,
            "status": "error",
            "model": model,
            "endpoint_host": endpoint_host,
            "status_code": status_code,
            "error": "AI response was not valid JSON for required schema.",
        }

    ai_result = {
        "enabled": True,
        "status": "ok",
        "model": model,
        "endpoint_host": endpoint_host,
        "status_code": status_code,
        **parsed,
    }
    logger.info(
        "case_summary_ai %s",
        json.dumps(
            {
                "event": "request_success",
                "case_id": int(getattr(case, "id", 0) or 0),
                "model": model,
                "endpoint_host": endpoint_host,
                "status_code": status_code,
                "attention_count": len(ai_result.get("attention_items") or []),
                "action_count": len(ai_result.get("recommended_actions") or []),
            },
            default=str,
        ),
    )
    return ai_result
