from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .auth import current_user
from .database import get_db
from .preservation_catalog import configured_builtin_hold_fields
from .permissions import (
    ensure_case_visible,
    get_requestor_allowed_emails,
    get_tech_visible_case_ids,
    is_requestor,
    is_sys_admin,
    is_tester,
    is_tech,
)
from .safe_log import debug_suppressed as _debug_suppressed
from .ai_config import ai_client_config, ai_configured, ai_feature_enabled, ai_headers

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _assistant_enabled() -> bool:
    return ai_feature_enabled("assistant_enabled", "AI_ASSISTANT_ENABLED", default=True)


def _assistant_config() -> dict[str, Any]:
    return ai_client_config(feature_prefix="AI_ASSISTANT", timeout_minimum=8.0)


def _assistant_configured() -> bool:
    if not _assistant_enabled():
        return False
    return ai_configured(feature_prefix="AI_ASSISTANT")


def _normalize_text(value: Any, *, max_len: int = 4000) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if not text_value:
        return ""
    return text_value[:max_len]


def _role_name(user: models.User) -> str:
    role = (getattr(user, "role", None) or ("sys_admin" if getattr(user, "is_admin", False) else "analyst") or "").strip().lower()
    return role or "analyst"


def _visible_case_ids(db: Session, actor: models.User) -> Optional[set[int]]:
    if not actor:
        return None
    if is_requestor(actor):
        allowed = get_requestor_allowed_emails(actor, db)
        if not allowed:
            return set()
        rows = (
            db.query(models.Case.id)
            .filter(models.Case.requestor.isnot(None))
            .filter(func.lower(models.Case.requestor).in_(list(allowed)))
            .all()
        )
        ids = {int(row.id) for row in rows}
        # Include explicit requestor memberships too.
        member_rows = (
            db.query(models.CaseRequestor.case_id)
            .filter(models.CaseRequestor.email.isnot(None))
            .filter(func.lower(models.CaseRequestor.email).in_(list(allowed)))
            .all()
        )
        for row in member_rows:
            try:
                ids.add(int(row.case_id))
            except Exception:
                continue
        return ids
    if is_tech(actor):
        return get_tech_visible_case_ids(actor, db)
    if is_tester(actor):
        rows = (
            db.query(models.Case.id)
            .filter(func.lower(models.Case.name).like("%-test"))
            .all()
        )
        return {int(row.id) for row in rows}
    return None


def _extract_json_object(value: Any) -> Optional[dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text_value = value.strip()
    if not text_value:
        return None
    if text_value.startswith("```"):
        text_value = re.sub(r"^```(?:json)?\s*", "", text_value, flags=re.IGNORECASE)
        text_value = re.sub(r"\s*```$", "", text_value)
        text_value = text_value.strip()
    try:
        parsed = json.loads(text_value)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start >= 0 and end > start:
        fragment = text_value[start : end + 1]
        try:
            parsed = json.loads(fragment)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _extract_model_text(payload: dict[str, Any]) -> str:
    try:
        content = (((payload.get("choices") or [{}])[0] or {}).get("message", {}).get("content"))
    except Exception:
        content = None

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
                continue
            if isinstance(part, dict):
                txt = part.get("text") or part.get("content")
                if isinstance(txt, str) and txt.strip():
                    out.append(txt.strip())
        return "\n".join(out).strip()

    if isinstance(payload.get("output_text"), str):
        return str(payload.get("output_text")).strip()

    return ""


def _tokenize(value: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[a-z0-9]{3,}", (value or "").lower())}



def _contains_any(text: str, needles: list[str]) -> bool:
    haystack = (text or "").lower()
    return any((needle or "").lower() in haystack for needle in needles)


INFO_ONLY_INTENT_HINTS = [
    "how do i",
    "how to",
    "what is",
    "what are",
    "why",
    "when",
    "where",
    "explain",
    "walk me through",
    "steps",
    "guide",
    "can i",
    "could i",
]

ACTION_OBJECT_HINTS = [
    "hold",
    "custodian",
    "case",
    "search",
    "ntp",
    "notice",
    "consent",
    "ticket",
    "purview",
    "request",
]

ACTION_VERB_HINTS = [
    "add",
    "apply",
    "assign",
    "change",
    "close",
    "create",
    "delete",
    "edit",
    "execute",
    "place",
    "push",
    "release",
    "remove",
    "reopen",
    "run",
    "send",
    "submit",
    "sync",
    "unassign",
    "update",
]

ACTION_DIRECTIVE_PREFIXES = [
    "please ",
    "can you ",
    "could you ",
    "go ahead and ",
    "do ",
    "run ",
    "execute ",
    "delete ",
    "remove ",
    "add ",
    "apply ",
    "release ",
    "send ",
    "close ",
    "create ",
    "update ",
]


def _is_action_execution_request(question: str) -> bool:
    q = _normalize_text(question, max_len=2000).lower()
    if not q:
        return False

    if _contains_any(q, INFO_ONLY_INTENT_HINTS):
        return False

    has_object = _contains_any(q, ACTION_OBJECT_HINTS)
    has_verb = _contains_any(q, ACTION_VERB_HINTS)
    has_directive = any(q.startswith(prefix) for prefix in ACTION_DIRECTIVE_PREFIXES)
    asks_to_do_it = _contains_any(q, ["for me", "do it", "right now", "now", "immediately"])

    return bool(has_verb and (has_object or has_directive) and (has_directive or asks_to_do_it))


def _info_only_guardrail_answer() -> str:
    return (
        "I can only provide information and guidance. "
        "I cannot perform actions in DiscoveryOne, including placing/removing holds, "
        "creating or deleting cases/custodians, sending notices, or editing records. "
        "Tell me what you want to do and I will provide step-by-step instructions."
    )


ACTION_OFFER_PATTERNS = [
    r"\bwould you like me to\b",
    r"\bdo you want me to\b",
    r"\bshall i\b",
    r"\bi can(?:\s+also)?\s+(?:re-?apply|apply|remove|delete|create|send|update|submit|push|execute|run|place)\b",
    r"\blet me\s+(?:re-?apply|apply|remove|delete|create|send|update|submit|push|execute|run|place)\b",
]


def _contains_action_offer(text: str) -> bool:
    q = _normalize_text(text, max_len=5000).lower()
    if not q:
        return False
    return any(re.search(pattern, q) for pattern in ACTION_OFFER_PATTERNS)


def _sanitize_info_only_answer(answer: str) -> str:
    raw = _normalize_text(answer, max_len=5000)
    if not raw:
        return raw
    if not _contains_action_offer(raw):
        return raw

    segments = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|\n+", raw)
        if (part or "").strip()
    ]
    kept: list[str] = []
    for seg in segments:
        if _contains_action_offer(seg):
            continue
        kept.append(seg)

    if not kept:
        return _info_only_guardrail_answer()

    sanitized = " ".join(kept).strip()
    if not sanitized.lower().endswith((".", "!", "?")):
        sanitized += "."
    sanitized += " I can provide step-by-step instructions only."
    return sanitized

def _requestor_activity_playbooks() -> list[dict[str, Any]]:
    from .ai_assistant_knowledge import REQUESTOR_ACTIVITY_PLAYBOOKS
    return REQUESTOR_ACTIVITY_PLAYBOOKS


def _match_requestor_playbooks(*args, **kwargs):
    from .ai_assistant_knowledge import _match_requestor_playbooks as impl
    return impl(*args, **kwargs)


def _playbook_answer(*args, **kwargs):
    from .ai_assistant_knowledge import _playbook_answer as impl
    return impl(*args, **kwargs)


def _direct_help_answer(*args, **kwargs):
    from .ai_assistant_knowledge import _direct_help_answer as impl
    return impl(*args, **kwargs)


def _knowledge_corpus(*args, **kwargs):
    from .ai_assistant_knowledge import _knowledge_corpus as impl
    return impl(*args, **kwargs)


def _retrieve_knowledge(*args, **kwargs):
    from .ai_assistant_knowledge import _retrieve_knowledge as impl
    return impl(*args, **kwargs)


def _case_search_summary(db: Session, case_id: int) -> dict[str, int]:
    base = (
        db.query(models.HoldSearch)
        .join(models.CaseHold, models.CaseHold.id == models.HoldSearch.hold_id)
        .filter(models.CaseHold.case_id == case_id, models.CaseHold.status == "active")
    )
    return {
        "total": int(base.count() or 0),
        "search_performed": int(base.filter(models.HoldSearch.status_search == "performed").count() or 0),
        "export_performed": int(base.filter(models.HoldSearch.status_export == "performed").count() or 0),
        "delivery_performed": int(base.filter(models.HoldSearch.status_delivery == "performed").count() or 0),
    }

def _recent_case_events(db: Session, case_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        result = db.execute(
            text(
                """
                SELECT created_at, action, details
                  FROM audit_events
                 WHERE target_type = 'case'
                   AND target_id = :case_id
                 ORDER BY created_at DESC, id DESC
                 LIMIT :limit
                """
            ),
            {"case_id": int(case_id), "limit": int(limit)},
        ).mappings().all()
        for row in result or []:
            action = _normalize_text(row.get("action"), max_len=120)
            details = row.get("details")
            details_summary = ""
            if isinstance(details, dict):
                details_summary = _normalize_text(json.dumps(details, default=str), max_len=300)
            else:
                details_summary = _normalize_text(details, max_len=300)
            rows.append(
                {
                    "created_at": _normalize_text(row.get("created_at"), max_len=80),
                    "action": action,
                    "details": details_summary,
                }
            )
    except Exception as exc:
        _debug_suppressed("suppressed exception in ai_assistant.py:recent_case_events", exc)
    return rows


def _build_case_context(db: Session, actor: models.User, case_id: int) -> dict[str, Any]:
    case = db.get(models.Case, case_id)
    ensure_case_visible(case, actor, db)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    custodians = (
        db.query(models.Custodian)
        .filter(models.Custodian.case_id == case_id)
        .order_by(models.Custodian.id.asc())
        .all()
    )

    configured_hold_fields = configured_builtin_hold_fields(enabled_only=True)
    holds = {f"{key}_applied": 0 for key, _field, _label in configured_hold_fields}
    if any(key == "box" for key, _field, _label in configured_hold_fields):
        holds.update({"box_failed": 0, "box_pending": 0, "box_released": 0})

    consent = {
        "not_sent": 0,
        "sent": 0,
        "received": 0,
        "not_required": 0,
    }

    ntp = {
        "not_sent": 0,
        "sent": 0,
        "acknowledged": 0,
    }

    box_issues: list[dict[str, Any]] = []
    for cu in custodians:
        for key, field, _label in configured_hold_fields:
            if bool(getattr(cu, field, False)):
                holds[f"{key}_applied"] += 1
        if "box_failed" in holds and bool(getattr(cu, "holds_box_failed", False)):
            holds["box_failed"] += 1
        if "box_pending" in holds and bool(getattr(cu, "holds_box_pending", False)):
            holds["box_pending"] += 1
        if "box_released" in holds and bool(getattr(cu, "holds_box_released", False)):
            holds["box_released"] += 1

        consent_status = (_normalize_text(getattr(cu, "consent_status", ""), max_len=40) or "").lower()
        if consent_status in consent:
            consent[consent_status] += 1

        ntp_status = (_normalize_text(getattr(cu, "ntp_status", ""), max_len=40) or "").lower()
        if ntp_status in ntp:
            ntp[ntp_status] += 1

        if "box_failed" in holds and bool(getattr(cu, "holds_box_failed", False)):
            box_issues.append(
                {
                    "custodian_id": int(getattr(cu, "id", 0) or 0),
                    "name": _normalize_text(getattr(cu, "name", ""), max_len=120),
                    "email": _normalize_text(getattr(cu, "email", ""), max_len=160),
                    "box_failed": True,
                    "box_pending": bool(getattr(cu, "holds_box_pending", False)),
                    "box_released": bool(getattr(cu, "holds_box_released", False)),
                }
            )

    summary = {
        "case": {
            "id": int(getattr(case, "id", 0) or 0),
            "name": _normalize_text(getattr(case, "name", ""), max_len=200),
            "legal_case_name": _normalize_text(getattr(case, "legal_case_name", ""), max_len=300),
            "closed": bool(getattr(case, "closed", False)),
            "requestor": _normalize_text(getattr(case, "requestor", ""), max_len=160),
        },
        "custodians_total": int(len(custodians)),
        "holds": holds,
        "consent": consent,
        "ntp": ntp,
        "searches": _case_search_summary(db, case_id),
        "box_issue_custodians": box_issues[:20],
        "recent_case_events": _recent_case_events(db, case_id, limit=8),
    }
    return summary


def _build_live_context(
    db: Session,
    actor: models.User,
    *,
    case_id: Optional[int],
    question: str,
    pathname: str,
) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    case_context: Optional[dict[str, Any]] = None
    tool_results: list[dict[str, Any]] = []

    if case_id is not None:
        case_context = _build_case_context(db, actor, case_id)
        tool_results.append(
            {
                "tool": "case_overview",
                "result": {
                    "case": case_context.get("case") or {},
                    "custodians_total": case_context.get("custodians_total", 0),
                    "searches": case_context.get("searches") or {},
                    "consent": case_context.get("consent") or {},
                    "ntp": case_context.get("ntp") or {},
                },
            }
        )

        q_lower = (question or "").lower()
        if "box" in q_lower or "red x" in q_lower or "hold" in q_lower:
            tool_results.append(
                {
                    "tool": "box_hold_diagnostics",
                    "result": {
                        "box_applied": (case_context.get("holds") or {}).get("box_applied", 0),
                        "box_failed": (case_context.get("holds") or {}).get("box_failed", 0),
                        "box_pending": (case_context.get("holds") or {}).get("box_pending", 0),
                        "box_released": (case_context.get("holds") or {}).get("box_released", 0),
                        "box_issue_custodians": case_context.get("box_issue_custodians") or [],
                    },
                }
            )
        if "consent" in q_lower or "docusign" in q_lower:
            tool_results.append(
                {
                    "tool": "consent_diagnostics",
                    "result": case_context.get("consent") or {},
                }
            )
        if "search" in q_lower or "purview" in q_lower or "kql" in q_lower:
            tool_results.append(
                {
                    "tool": "search_diagnostics",
                    "result": case_context.get("searches") or {},
                }
            )
        if not tool_results:
            tool_results.append(
                {
                    "tool": "case_overview",
                    "result": case_context,
                }
            )

    tool_results.append(
        {
            "tool": "ui_context",
            "result": {
                "pathname": pathname,
                "has_case_context": bool(case_context),
            },
        }
    )

    return case_context, tool_results


def _app_playbook() -> str:
    return (
        "You are DiscoveryOne AI Assistant for eDiscovery workflows. "
        "Use only provided context, retrieved knowledge, and tool results. "
        "Do not invent system behavior, case facts, statuses, or integrations. "
        "If data is missing, say unknown and provide concrete next steps. "
        "For status/hold icon interpretation: red X means failed state for that source; pending means in progress; "
        "released means intentionally lifted; applied means successful hold. "
        "Respect role-based visibility and never disclose unauthorized case details. "
        "Operate in information-only mode: never take actions, trigger workflows, or imply that you executed changes. "
        "Never ask for permission to execute actions (for example, do not ask if you should re-apply a hold). "
        "When troubleshooting, explain likely cause, evidence from context, and exact remediation steps."
    )


def _chat_with_versa(messages: list[dict[str, str]]) -> dict[str, Any]:
    if not _assistant_configured():
        return {
            "status": "not_configured",
            "error": "AI assistant is disabled or missing AI URL/model configuration.",
        }

    cfg = _assistant_config()
    url = cfg["url"]
    model = cfg["model"]
    api_key = cfg["api_key"]
    auth_header = cfg["auth_header"]
    timeout_seconds = cfg["timeout_seconds"]

    headers = ai_headers(cfg)
    if api_key:
        if auth_header.lower() == "authorization" and not api_key.lower().startswith("bearer "):
            headers[auth_header] = f"Bearer {api_key}"
        else:
            headers[auth_header] = api_key

    attempts = [
        {"include_model": True, "include_response_format": True, "include_temperature": True},
        {"include_model": True, "include_response_format": False, "include_temperature": True},
        {"include_model": False, "include_response_format": True, "include_temperature": True},
        {"include_model": False, "include_response_format": False, "include_temperature": False},
    ]

    payload: dict[str, Any] | None = None
    status_code: int | None = None
    last_error = "request_failed"

    for spec in attempts:
        body: dict[str, Any] = {"messages": messages}
        if spec.get("include_model"):
            body["model"] = model
        if spec.get("include_temperature"):
            body["temperature"] = 0.1
        if spec.get("include_response_format"):
            body["response_format"] = {"type": "json_object"}

        try:
            response = httpx.post(url, headers=headers, json=body, timeout=timeout_seconds)
            status_code = int(response.status_code)
            response.raise_for_status()
            payload = response.json()
            break
        except httpx.HTTPStatusError as exc:
            status_code = int(getattr(exc.response, "status_code", 0) or 0)
            body_text = (getattr(exc.response, "text", "") or "").strip()
            last_error = f"http_status_error: {status_code} {body_text[:300]}"
        except Exception as exc:
            last_error = str(exc)

    if payload is None:
        return {
            "status": "error",
            "error": last_error,
            "status_code": status_code,
            "model": model,
            "endpoint_host": cfg.get("endpoint_host"),
        }

    content = _extract_model_text(payload)
    parsed = _extract_json_object(content) or _extract_json_object(payload)

    answer = ""
    citations: list[str] = []
    confidence = "low"
    follow_up = ""

    if isinstance(parsed, dict):
        answer = _normalize_text(parsed.get("answer"), max_len=5000)
        citations_raw = parsed.get("citations")
        if isinstance(citations_raw, list):
            for item in citations_raw:
                txt = _normalize_text(item, max_len=200)
                if txt:
                    citations.append(txt)
        confidence = (_normalize_text(parsed.get("confidence"), max_len=20) or "low").lower()
        follow_up = _normalize_text(parsed.get("clarifying_question"), max_len=400)
        if _contains_action_offer(follow_up):
            follow_up = "What part should I explain step-by-step?"

    if not answer:
        answer = _normalize_text(content, max_len=5000)

    answer = _sanitize_info_only_answer(answer)

    if not answer:
        return {
            "status": "error",
            "error": "AI response was empty or not parseable.",
            "status_code": status_code,
            "model": model,
            "endpoint_host": cfg.get("endpoint_host"),
        }

    return {
        "status": "ok",
        "answer": answer,
        "citations": citations[:8],
        "confidence": confidence if confidence in {"low", "medium", "high"} else "low",
        "clarifying_question": follow_up,
        "status_code": status_code,
        "model": model,
        "endpoint_host": cfg.get("endpoint_host"),
    }


class AssistantHistoryItem(BaseModel):
    role: str = Field(default="user")
    content: str = Field(default="")


class AssistantChatRequest(BaseModel):
    message: str = Field(default="")
    history: List[AssistantHistoryItem] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)


@router.post("/help_chat")
def ai_help_chat(
    payload: AssistantChatRequest = Body(default_factory=AssistantChatRequest),
    actor: models.User = Depends(current_user),
    db: Session = Depends(get_db),
    request: Request = None,
):
    if not actor:
        raise HTTPException(status_code=401, detail="Not authenticated")

    question = _normalize_text(payload.message, max_len=2000)
    if not question:
        raise HTTPException(status_code=422, detail="A message is required")

    role = _role_name(actor)
    context = payload.context or {}
    pathname = _normalize_text(context.get("pathname"), max_len=200) or "/"
    search = _normalize_text(context.get("search"), max_len=400)

    case_id: Optional[int] = None
    raw_case_id = context.get("case_id")
    if raw_case_id is not None:
        try:
            case_id = int(raw_case_id)
        except Exception:
            case_id = None
    if case_id is not None and case_id <= 0:
        case_id = None

    if _is_action_execution_request(question):
        blocked_answer = _info_only_guardrail_answer()
        try:
            log_event(
                db,
                action="ai_help_chat_action_blocked",
                actor_id=getattr(actor, "id", None),
                target_type="system",
                details={
                    "case_id": case_id,
                    "pathname": pathname,
                    "question_preview": question[:160],
                    "reason": "info_only_guardrail",
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in ai_assistant.py:log_action_blocked", exc)

        return {
            "status": "ok",
            "answer": blocked_answer,
            "citations": ["info_only_guardrail"],
            "confidence": "high",
            "case_context_used": False,
            "tool_count": 0,
            "knowledge_count": 0,
            "source": "action_blocked",
        }

    matched_requestor_playbooks = (
        _match_requestor_playbooks(question, limit=8) if role == "requestor" else []
    )

    direct_answer = _direct_help_answer(
        question,
        role,
        case_id=case_id,
        pathname=pathname,
    )
    if direct_answer:
        try:
            log_event(
                db,
                action="ai_help_chat_direct",
                actor_id=getattr(actor, "id", None),
                target_type="system",
                details={
                    "task_id": direct_answer.get("task_id"),
                    "case_id": case_id,
                    "pathname": pathname,
                    "question_preview": question[:160],
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in ai_assistant.py:log_direct", exc)

        return {
            "status": "ok",
            "answer": direct_answer.get("answer") or "",
            "citations": direct_answer.get("citations") or [],
            "confidence": direct_answer.get("confidence") or "high",
            "case_context_used": bool(case_id),
            "tool_count": 0,
            "knowledge_count": 0,
            "source": "direct_playbook",
        }
    # Use bounded history to keep prompts small.
    cleaned_history: list[dict[str, str]] = []
    for item in payload.history[-10:]:
        role_name = (item.role or "user").strip().lower()
        if role_name not in {"user", "assistant"}:
            continue
        text_value = _normalize_text(item.content, max_len=1200)
        if not text_value:
            continue
        cleaned_history.append({"role": role_name, "content": text_value})

    knowledge = _retrieve_knowledge(f"{pathname} {search} {question}", limit=5)
    case_context, tool_results = _build_live_context(
        db,
        actor,
        case_id=case_id,
        question=question,
        pathname=pathname,
    )

    context_payload = {
        "app_playbook": {
            "version": "2026-02-25",
            "rules": [
                "Never guess unknown facts.",
                "Use only supplied context and tool outputs.",
                "Respect role visibility.",
                "Provide remediation steps when diagnosing issues.",
            ],
        },
        "user": {
            "id": int(getattr(actor, "id", 0) or 0),
            "role": role,
            "email": _normalize_text(getattr(actor, "email", ""), max_len=200),
        },
        "ui_context": {
            "pathname": pathname,
            "search": search,
            "case_id": case_id,
        },
        "case_context": case_context,
        "retrieved_knowledge": knowledge,
        "tool_results": tool_results,
        "requestor_playbooks": {
            "matched": [
                {
                    "id": pb.get("id"),
                    "title": pb.get("title"),
                    "steps": pb.get("steps") or [],
                    "citations": pb.get("citations") or [],
                }
                for pb in matched_requestor_playbooks
            ],
            "catalog": (
                [{"id": pb.get("id"), "title": pb.get("title")} for pb in _requestor_activity_playbooks()]
                if role == "requestor"
                else []
            ),
        },
    }

    system_prompt = (
        str(cfg.get("system_prompt") or "").strip()
        or _app_playbook()
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(cleaned_history)
    messages.append(
        {
            "role": "user",
            "content": (
                "Return JSON only with schema "
                "{answer:string, confidence:'low'|'medium'|'high', citations:string[], clarifying_question:string}. "
                "If you lack enough facts, set confidence to low, clearly say unknown, and include one clarifying_question. "
                "Do not claim an action happened unless it is present in tool_results/case_context. "
                "Do not offer to perform actions, and do not ask user permission to perform actions. "
                f"\n\nQuestion: {question}\n\nContext JSON: {json.dumps(context_payload, default=str)}"
            ),
        }
    )

    result = _chat_with_versa(messages)

    if result.get("status") != "ok":
        fallback_answer = (
            "DiscoveryOne AI Assistant is unavailable right now. "
            "I could not reach the configured Versa endpoint. "
            "Please try again shortly or use the Help Page option."
        )
        try:
            log_event(
                db,
                action="ai_help_chat_failed",
                actor_id=getattr(actor, "id", None),
                target_type="system",
                details={
                    "status": result.get("status"),
                    "error": result.get("error"),
                    "model": result.get("model"),
                    "endpoint_host": result.get("endpoint_host"),
                    "case_id": case_id,
                    "pathname": pathname,
                    "question_preview": question[:160],
                },
                request=request,
            )
        except Exception as exc:
            _debug_suppressed("suppressed exception in ai_assistant.py:log_failed", exc)

        return {
            "status": "ok",
            "answer": fallback_answer,
            "citations": ["assistant_unavailable"],
            "confidence": "low",
            "case_context_used": bool(case_context),
            "tool_count": len(tool_results),
            "knowledge_count": len(knowledge),
        }

    answer = _normalize_text(result.get("answer"), max_len=5000)
    citations = result.get("citations") if isinstance(result.get("citations"), list) else []
    clarifying_question = _normalize_text(result.get("clarifying_question"), max_len=400)

    try:
        log_event(
            db,
            action="ai_help_chat",
            actor_id=getattr(actor, "id", None),
            target_type="system",
            details={
                "model": result.get("model"),
                "endpoint_host": result.get("endpoint_host"),
                "status_code": result.get("status_code"),
                "case_id": case_id,
                "pathname": pathname,
                "question_preview": question[:160],
                "confidence": result.get("confidence"),
                "citations_count": len(citations),
                "tool_count": len(tool_results),
                "knowledge_count": len(knowledge),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in ai_assistant.py:log_ok", exc)

    response = {
        "status": "ok",
        "answer": answer,
        "citations": citations[:8],
        "confidence": result.get("confidence") or "low",
        "case_context_used": bool(case_context),
        "tool_count": len(tool_results),
        "knowledge_count": len(knowledge),
    }
    if clarifying_question:
        response["clarifying_question"] = clarifying_question
    return response









