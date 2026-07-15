"""AI-assisted search suggestion workflow."""

from typing import Any
import json
import re

import httpx

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .safe_log import debug_suppressed as _debug_suppressed
from .search_export_provider import normalize_search_query
from .search_naming import suggest_search_name
from .auth import current_user
from .database import get_db
from .permissions import ensure_case_editable, ensure_case_visible
from .ai_config import ai_client_config, ai_configured, ai_feature_enabled, ai_headers, search_builder_max_suggestions

router = APIRouter(prefix="/api/cases", tags=["searches"])


def _ensure_case(
    db: Session,
    case_id: int,
    user: models.User | None = None,
) -> models.Case:
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if user is not None:
        ensure_case_visible(case, user, db)
    return case


def _search_builder_ai_enabled() -> bool:
    return ai_feature_enabled("search_builder_enabled", "SEARCH_BUILDER_AI_ENABLED", default=True)


def _search_builder_ai_configured() -> bool:
    if not _search_builder_ai_enabled():
        return False
    return ai_configured(feature_prefix="SEARCH_BUILDER_AI")


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_date(value: Any) -> str | None:
    text = _coerce_text(value)
    if not text:
        return None
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    return None


def _safe_int_list(values: Any) -> list[int]:
    out: list[int] = []
    if not isinstance(values, list):
        return out
    for item in values:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _extract_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        fragment = text[start : end + 1]
        try:
            parsed = json.loads(fragment)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _infer_custodian_ids_for_suggestion(
    item: dict[str, Any],
    custodian_index: dict[int, dict[str, Any]],
) -> list[int]:
    if not isinstance(item, dict):
        return []

    parts = [
        _coerce_text(item.get("keywords")) or "",
        _coerce_text(item.get("senders")) or "",
        _coerce_text(item.get("recipients")) or "",
        _coerce_text(item.get("additional")) or "",
        _coerce_text(item.get("kql")) or "",
        _coerce_text(item.get("rationale")) or "",
    ]
    haystack = " ".join(parts).strip().lower()
    if not haystack:
        return []

    matched: list[int] = []
    for cid, meta in custodian_index.items():
        email = (meta.get("email") or "").strip().lower()
        name = (meta.get("name") or "").strip().lower()
        name_tokens = [t for t in (meta.get("name_tokens") or []) if isinstance(t, str) and t]
        alias_tokens = [t for t in (meta.get("alias_tokens") or []) if isinstance(t, str) and t]

        is_match = False
        if email and email in haystack:
            is_match = True
        elif name and name in haystack:
            is_match = True
        elif len(name_tokens) >= 2 and name_tokens[0] in haystack and name_tokens[-1] in haystack:
            is_match = True
        elif len(alias_tokens) >= 2 and alias_tokens[0] in haystack and alias_tokens[-1] in haystack:
            is_match = True

        if is_match:
            matched.append(int(cid))

    return sorted(set(matched))


def _normalize_ai_suggestions(
    *,
    raw: Any,
    case_name: str,
    existing_names: list[str],
    available_custodian_ids: list[int],
    custodian_index: dict[int, dict[str, Any]],
    max_suggestions: int,
) -> list[dict[str, Any]]:
    rows = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    seen_names = {(x or "").strip().lower() for x in existing_names if isinstance(x, str)}
    available_set = set(available_custodian_ids)

    for item in rows:
        if len(out) >= max_suggestions:
            break
        if not isinstance(item, dict):
            continue

        # Search naming is owned by DiscoveryOne auto-naming, not AI.
        name = ""
        auto_name = suggest_search_name(case_name, list(seen_names))
        seen_names.add(auto_name.lower())

        ai_custodian_ids = [cid for cid in _safe_int_list(item.get("custodian_ids")) if cid in available_set]
        inferred_ids = _infer_custodian_ids_for_suggestion(item, custodian_index)
        inferred_ids = [cid for cid in inferred_ids if cid in available_set]
        custodian_ids = ai_custodian_ids or inferred_ids
        if not custodian_ids and len(available_set) == 1:
            custodian_ids = list(available_set)

        out.append(
            {
                "name": name,
                "keywords": _coerce_text(item.get("keywords")) or "",
                "senders": _coerce_text(item.get("senders")) or "",
                "recipients": _coerce_text(item.get("recipients")) or "",
                "date_from": _coerce_date(item.get("date_from")) or "",
                "date_to": _coerce_date(item.get("date_to")) or "",
                "additional": _coerce_text(item.get("additional")) or "",
                "kql": normalize_search_query(item.get("kql")),
                "custodian_ids": sorted(set(custodian_ids)),
                "rationale": _coerce_text(item.get("rationale")) or "",
                "status_search": "not performed",
                "status_export": "not performed",
                "status_delivery": "not performed",
            }
        )
    return out


def _build_ai_search_suggestions(
    *,
    case: models.Case,
    draft: dict[str, Any],
    objective: str | None,
    selected_custodians: list[models.Custodian],
    all_custodians: list[models.Custodian],
    existing_search_names: list[str],
    max_suggestions: int,
) -> dict[str, Any]:
    if not _search_builder_ai_configured():
        return {
            "enabled": False,
            "status": "not_configured",
            "error": "Search builder AI is disabled or the AI integration URL/model is missing.",
            "suggestions": [],
        }

    ai_cfg = ai_client_config(feature_prefix="SEARCH_BUILDER_AI", timeout_minimum=8.0)
    url = ai_cfg["url"]
    model = ai_cfg["model"]
    timeout_seconds = ai_cfg["timeout_seconds"]
    endpoint_host = ai_cfg["endpoint_host"]

    selected_ids = [int(getattr(c, "id", 0) or 0) for c in selected_custodians if int(getattr(c, "id", 0) or 0) > 0]
    assignable_custodians = selected_custodians or all_custodians
    available_ids = [int(getattr(c, "id", 0) or 0) for c in assignable_custodians if int(getattr(c, "id", 0) or 0) > 0]

    custodian_index: dict[int, dict[str, Any]] = {}
    for c in assignable_custodians:
        cid = int(getattr(c, "id", 0) or 0)
        if cid <= 0:
            continue
        name = (_coerce_text(getattr(c, "name", None)) or "").strip().lower()
        email = (_coerce_text(getattr(c, "email", None)) or "").strip().lower()
        alias = email.split("@", 1)[0] if "@" in email else ""
        name_tokens = [t for t in re.split(r"[^a-z0-9]+", name) if len(t) >= 3]
        alias_tokens = [t for t in re.split(r"[^a-z0-9]+", alias) if len(t) >= 3]
        custodian_index[cid] = {
            "name": name,
            "email": email,
            "name_tokens": name_tokens,
            "alias_tokens": alias_tokens,
        }

    draft_payload = {
        "name": _coerce_text(draft.get("name")),
        "keywords": _coerce_text(draft.get("keywords")),
        "senders": _coerce_text(draft.get("senders")),
        "recipients": _coerce_text(draft.get("recipients")),
        "date_from": _coerce_date(draft.get("date_from")),
        "date_to": _coerce_date(draft.get("date_to")),
        "additional": _coerce_text(draft.get("additional")),
        "custodian_ids": _safe_int_list(draft.get("custodian_ids")),
    }
    context_payload = {
        "case": {
            "id": int(getattr(case, "id", 0) or 0),
            "name": getattr(case, "name", None),
            "legal_case_name": getattr(case, "legal_case_name", None),
            "claimant": getattr(case, "claimant", None),
        },
        "objective": _coerce_text(objective),
        "draft": draft_payload,
        "selected_custodians": [
            {
                "name": getattr(c, "name", None),
                "email": getattr(c, "email", None),
            }
            for c in selected_custodians
        ],
        "existing_search_names": [x for x in existing_search_names if isinstance(x, str) and x.strip()],
        "max_suggestions": max_suggestions,
    }

    system_prompt = (
        ai_cfg.get("system_prompt")
        or "You are an eDiscovery analyst assistant specialized in Microsoft Purview search planning. "
        "Produce practical, defensible search criteria with tight scope and minimal noise. "
        "If intent includes distinct topics/date windows, split into multiple searches."
    ).strip()

    user_prompt = (
        "Return JSON only with this schema: "
        "{summary:string, suggestions:[{keywords:string, senders:string, recipients:string, kql:string, "
        "date_from:string, date_to:string, additional:string, custodian_ids:number[], rationale:string}]}. "
        "Use YYYY-MM-DD for date fields or empty string. "
        "kql must be a single-line Microsoft Purview Content Search KQL query ready to paste. "
        "Use straight quotes only (\" not smart quotes), avoid leading wildcards (never *@domain), and use ISO dates (YYYY-MM-DD) for property ranges like received/sent. "
        "In summary and rationale, refer to custodians by name/email only; never use numeric custodian IDs. "
        "Default to exactly one suggestion for a single cohesive requirement. "
        "Only return multiple suggestions when the objective clearly contains distinct, independently actionable requirements that should be run as separate searches. "
        "Do not return alternative phrasings of the same requirement. "
        "For each suggestion, custodian_ids must include only custodians relevant to that specific query and must exclude unrelated custodians. "
        "Keep suggestions aligned with Purview search practices and avoid speculative assumptions.\n"
        f"Context JSON: {json.dumps(context_payload, default=str)}"
    )

    headers = ai_headers(ai_cfg)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    payload = None
    status_code: int | None = None
    errors: list[str] = []
    attempts = [
        {"include_model": True, "include_temperature": True, "include_response_format": True},
        {"include_model": True, "include_temperature": True, "include_response_format": False},
        {"include_model": False, "include_temperature": True, "include_response_format": True},
        {"include_model": False, "include_temperature": True, "include_response_format": False},
        {"include_model": False, "include_temperature": False, "include_response_format": False},
    ]
    for spec in attempts:
        body: dict[str, Any] = {"messages": messages}
        if spec["include_model"]:
            body["model"] = model
        if spec["include_temperature"]:
            body["temperature"] = 0.2
        if spec["include_response_format"]:
            body["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=timeout_seconds)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            break
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            body_text = (getattr(exc.response, "text", "") or "").strip()
            errors.append(f"{exc}; attempt={spec}; response_body={body_text[:500]}")
            continue
        except httpx.ReadTimeout:
            status_code = 504
            errors.append(f"Versa timed out after {int(timeout_seconds)}s while waiting for AI response.")
            break
        except httpx.TimeoutException:
            status_code = 504
            errors.append(f"Versa timed out after {int(timeout_seconds)}s while contacting the AI endpoint.")
            break
        except Exception as exc:
            errors.append(f"{exc}; attempt={spec}")
            continue

    if payload is None:
        return {
            "enabled": True,
            "status": "error",
            "model": model,
            "endpoint_host": endpoint_host,
            "status_code": status_code,
            "error": errors[-1] if errors else "request_failed",
            "suggestions": [],
        }

    content = None
    try:
        content = (((payload.get("choices") or [{}])[0] or {}).get("message", {}).get("content"))
    except Exception:
        content = None

    parsed = _extract_json_object(content) if content is not None else None
    if parsed is None:
        parsed = _extract_json_object(payload)

    if parsed is None:
        return {
            "enabled": True,
            "status": "error",
            "model": model,
            "endpoint_host": endpoint_host,
            "status_code": status_code,
            "error": "AI response was not valid JSON.",
            "suggestions": [],
        }

    raw_suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else None
    suggestions = _normalize_ai_suggestions(
        raw=raw_suggestions,
        case_name=getattr(case, "name", "") or "Case",
        existing_names=existing_search_names,
        available_custodian_ids=available_ids,
        custodian_index=custodian_index,
        max_suggestions=max_suggestions,
    )

    if not suggestions:
        maybe_single = _normalize_ai_suggestions(
            raw=[parsed],
            case_name=getattr(case, "name", "") or "Case",
            existing_names=existing_search_names,
            available_custodian_ids=available_ids,
            custodian_index=custodian_index,
            max_suggestions=max_suggestions,
        )
        suggestions = maybe_single

    return {
        "enabled": True,
        "status": "ok",
        "model": model,
        "endpoint_host": endpoint_host,
        "status_code": status_code,
        "summary": _coerce_text(parsed.get("summary")) if isinstance(parsed, dict) else None,
        "suggestions": suggestions,
    }


@router.post("/{case_id}/searches/ai_suggest")
def ai_suggest_searches(
    case_id: int,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    request: Request = None,
    user: models.User = Depends(current_user),
):
    case = _ensure_case(db, case_id, user)
    ensure_case_editable(user)

    role = ((getattr(user, "role", None) or ("sys_admin" if getattr(user, "is_admin", False) else "analyst")) or "").strip().lower()
    if role not in {"analyst", "sys_admin"}:
        raise HTTPException(status_code=403, detail="Only analysts/admins can use AI search suggestions.")

    draft_raw = payload.get("draft") if isinstance(payload, dict) else {}
    draft = draft_raw if isinstance(draft_raw, dict) else {}
    objective = _coerce_text((payload or {}).get("objective"))

    max_raw = (payload or {}).get("max_suggestions", search_builder_max_suggestions())
    try:
        max_suggestions = int(max_raw)
    except Exception:
        max_suggestions = search_builder_max_suggestions()
    max_suggestions = max(1, min(8, max_suggestions))

    selected_ids = _safe_int_list(draft.get("custodian_ids"))
    all_custodians = db.query(models.Custodian).filter(models.Custodian.case_id == case_id).order_by(models.Custodian.id.asc()).all()
    if selected_ids:
        selected_set = set(selected_ids)
        selected_custodians = [c for c in all_custodians if int(getattr(c, "id", 0) or 0) in selected_set]
    else:
        selected_custodians = list(all_custodians)

    existing_names = [n for (n,) in db.query(models.Search.name).filter(models.Search.case_id == case_id).all() if isinstance(n, str) and n.strip()]

    result = _build_ai_search_suggestions(
        case=case,
        draft=draft,
        objective=objective,
        selected_custodians=selected_custodians,
        all_custodians=all_custodians,
        existing_search_names=existing_names,
        max_suggestions=max_suggestions,
    )

    action = "search_ai_suggest" if result.get("status") == "ok" else "search_ai_suggest_failed"
    try:
        log_event(
            db,
            action=action,
            target_type="case",
            target_id=case_id,
            actor_id=user.id,
            details={
                "case_id": case_id,
                "case_name": getattr(case, "name", None),
                "selected_custodian_count": len(selected_custodians),
                "requested_max_suggestions": max_suggestions,
                "result_status": result.get("status"),
                "suggestions_count": len(result.get("suggestions") or []),
                "error": result.get("error"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in search_ai.py: ai_suggest log", exc)

    return result
