"""Static help playbooks and retrieval corpus for the AI assistant."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Tuple

from .safe_log import debug_suppressed as _debug_suppressed


def _tokenize(value: str) -> set[str]:
    return {m.group(0).lower() for m in re.finditer(r"[a-z0-9]{3,}", (value or "").lower())}


def _contains_any(text: str, needles: list[str]) -> bool:
    haystack = (text or "").lower()
    return any((needle or "").lower() in haystack for needle in needles)


REQUESTOR_ACTIVITY_PLAYBOOKS: list[dict[str, Any]] = [
    {
        "id": "requestor_access_login",
        "title": "Access, Login, and Password Recovery",
        "keywords": ["login", "log in", "sign in", "password", "reset", "register", "registration", "mfa", "access"],
        "steps": [
            "Open Login and use your approved work email.",
            "If you do not have an account, submit a registration request.",
            "If login fails and you already have an account, use Forgot Password.",
            "After login, open System and complete MFA setup if prompted.",
        ],
        "citations": ["help:access"],
    },
    {
        "id": "requestor_cases_navigation",
        "title": "Cases Page Navigation",
        "keywords": ["cases", "find case", "open case", "filter", "missing case", "case list"],
        "steps": [
            "Select Cases from the left sidebar.",
            "Use filters (Name, Legal Name, Analyst, Requestor) to find your matter.",
            "Open the case row to enter Case Detail.",
            "If a case is missing, verify requestor assignment/visibility before escalating.",
        ],
        "citations": ["help:cases"],
    },
    {
        "id": "requestor_case_detail",
        "title": "Case Detail Review",
        "keywords": ["case detail", "tabs", "custodians tab", "searches tab", "notes", "sla"],
        "steps": [
            "Open the case from Cases.",
            "Review header context first (case name, legal case, claimant, analyst).",
            "Use tabs to inspect Custodians, Searches, Tickets, Consent, SLA, and Notes.",
            "For changes, use request workflows instead of direct edits.",
        ],
        "citations": ["help:case-detail", "help:case-detail-tab-details"],
    },
    {
        "id": "requestor_requests_tracking",
        "title": "Requests Page Tracking",
        "keywords": ["requests", "pending", "approved", "declined", "request card", "track request"],
        "steps": [
            "Open Requests.",
            "Review Pending first, then Declined and Approved sections.",
            "Open cards to inspect payload, attachments, and status details.",
            "For declined requests, submit a corrected replacement request.",
        ],
        "citations": ["help:requests", "help:request-card-anatomy"],
    },
    {
        "id": "requestor_new_case_request",
        "title": "New Case Request",
        "keywords": ["new case", "open case intake", "intake", "create case", "request new case"],
        "steps": [
            "Open Requests and click New Case Request.",
            "Complete case details (case name, legal case, claimant, description).",
            "Add custodians with accurate name/email and hold scope.",
            "Add optional search details if needed.",
            "Submit and monitor the request in Pending.",
        ],
        "citations": ["help:new-case-request"],
    },
    {
        "id": "requestor_custodian_update",
        "title": "Custodian Update Request",
        "keywords": ["add custodian", "add custodians", "remove custodian", "custodian update", "update custodian", "request to add custodians"],
        "steps": [
            "Open the target case and go to Custodians tab.",
            "Click `Request to add custodians`.",
            "Enter each custodian with full name and email.",
            "Specify hold changes and notes clearly.",
            "Submit and monitor Requests > Pending.",
            "After approval, verify the new custodian(s) in the case roster.",
        ],
        "citations": ["help:custodian-update-request", "help:case-detail", "ui:case-detail-custodians-request"],
    },
    {
        "id": "requestor_search_request",
        "title": "Search Request",
        "keywords": ["search request", "search", "keywords", "senders", "recipients", "date range", "kql"],
        "steps": [
            "Open Requests and start Search Request for the target case.",
            "Enter keywords, senders/recipients, and date range.",
            "Add additional instructions for expected output.",
            "Use separate search entries for unrelated objectives.",
            "Submit and track status in Requests and case search views.",
        ],
        "citations": ["help:search-request"],
    },
    {
        "id": "requestor_case_closure",
        "title": "Case Closure Request",
        "keywords": ["close case", "closure", "request case closure", "release holds"],
        "steps": [
            "Open Case Detail and click Request Case Closure.",
            "Confirm the target case and add closure notes/constraints.",
            "Submit and monitor Pending/Approved in Requests.",
            "Re-open the case after approval to verify closure state.",
        ],
        "citations": ["help:close-case-request"],
    },
    {
        "id": "requestor_ntp_send",
        "title": "NTP Send Flow",
        "keywords": ["ntp", "notice", "send ntp", "template", "reminder", "send notices"],
        "steps": [
            "Open Case Detail and click NTPs.",
            "Select an NTP template and optional reminder settings.",
            "Populate variables and recipient selection.",
            "Click Send Notices.",
            "Confirm NTP status updates in Custodians tab.",
        ],
        "citations": ["help:ntp-send", "help:case-detail"],
    },
    {
        "id": "requestor_dashboards",
        "title": "Dashboards",
        "keywords": ["dashboard", "widget", "drilldown", "metrics"],
        "steps": [
            "Open Dashboards.",
            "Refresh metrics before interpreting data.",
            "Use widgets/drilldowns to investigate case status.",
            "Open active case records from drilldowns for validation.",
        ],
        "citations": ["help:dashboards"],
    },
    {
        "id": "requestor_reports",
        "title": "Reports",
        "keywords": ["report", "export csv", "timeline", "custodian report"],
        "steps": [
            "Open Reports.",
            "Run the relevant report section or timeline query.",
            "Use Export CSV for snapshots.",
            "Open linked cases to verify findings.",
        ],
        "citations": ["help:reports"],
    },
    {
        "id": "requestor_logs",
        "title": "Logs",
        "keywords": ["logs", "audit", "action", "actor id", "ip", "filter logs"],
        "steps": [
            "Open Logs.",
            "Apply filters (action, actor, contains, IP) to narrow events.",
            "Inspect details payload for specific field changes.",
            "Capture timestamp/action/details when escalating.",
        ],
        "citations": ["help:logs"],
    },
    {
        "id": "requestor_system",
        "title": "System (Requestor Scope)",
        "keywords": ["system", "preferences", "theme", "session", "security", "mfa", "password"],
        "steps": [
            "Open System.",
            "Set preferences (theme/case sort), manage sessions, and update password.",
            "Complete MFA setup or reset if prompted.",
            "Use role-permitted settings only; analyst/admin-only areas are restricted.",
        ],
        "citations": ["help:system"],
    },
]


def _match_requestor_playbooks(question: str, *, limit: int = 6) -> list[dict[str, Any]]:
    q = (question or "").strip().lower()
    if not q:
        return []

    tokens = _tokenize(q)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for pb in REQUESTOR_ACTIVITY_PLAYBOOKS:
        score = 0
        for kw in pb.get("keywords") or []:
            key = (kw or "").strip().lower()
            if not key:
                continue
            if key in q:
                score += 8 if " " in key else 5
            elif key in tokens:
                score += 3
        title_tokens = _tokenize(pb.get("title") or "")
        score += len(tokens.intersection(title_tokens))
        if score > 0:
            ranked.append((score, pb))

    ranked.sort(key=lambda item: item[0], reverse=True)
    matched = [row for _, row in ranked[: max(1, min(limit, 20))]]
    return matched


def _playbook_answer(playbook: dict[str, Any]) -> str:
    title = (playbook.get("title") or "Requestor workflow").strip()
    steps = [str(step).strip() for step in (playbook.get("steps") or []) if str(step).strip()]
    if not steps:
        return title
    lines = [f"{title}:"]
    for idx, step in enumerate(steps, start=1):
        lines.append(f"{idx}. {step}")
    return "\n".join(lines)


def _direct_help_answer(
    question: str,
    role: str,
    *,
    case_id: Optional[int],
    pathname: str,
) -> Optional[dict[str, Any]]:
    q = (question or "").strip().lower()
    if not q:
        return None

    role_norm = (role or "").strip().lower()
    is_howto = _contains_any(q, ["how do i", "how to", "steps", "walk me through", "where do i", "what are the steps"])
    asks_add_custodian = ("custodian" in q) and _contains_any(q, ["add", "new", "create"])
    asks_ntp_template = (
        (_contains_any(q, ["ntp template", "notice to preserve template"]) or (pathname == "/system" and "ntp" in q))
        and _contains_any(q, ["create", "new", "add", "make"])
    )

    if asks_ntp_template and (is_howto or pathname == "/system"):
        if role_norm in {"tech", "tester"}:
            return {
                "task_id": "ntp_template_unavailable",
                "answer": (
                    "NTP means Notice to Preserve. Tech and tester accounts do not manage NTP templates. "
                    "Ask an analyst or system administrator to create or update the template in System > NTP Templates."
                ),
                "confidence": "high",
                "citations": ["ui:system-ntp-templates", "help:system"],
            }

        lines = [
            "1. Open System and go to the `NTP Templates` tab.",
            "2. Click `New Template`.",
            "3. Enter the template name, subject, optional description/CC recipients, and the email body.",
            "4. Use the supported placeholders shown on the page, such as `{{case_name}}`, `{{custodian_name}}`, `{{custodian_email}}`, `{{requestor}}`, and `{{ack_link}}`.",
            "5. Optionally mark the template as the default for NTP sends or mark NTP emails as high importance.",
        ]
        if role_norm == "requestor":
            lines.append("6. Your template will be limited to your requestor group automatically.")
            lines.append("7. Click `Save Template`.")
        else:
            lines.append("6. Set `Group Access` if the template should be available to specific requestor groups, or leave it blank for analysts/sys admins only.")
            lines.append("7. Click `Save Template`.")
            lines.append("8. If you want to start from existing language, use `Copy` on an existing template and edit the duplicate.")
        return {
            "task_id": "ntp_template_create",
            "answer": "\n".join(lines),
            "confidence": "high",
            "citations": ["ui:system-ntp-templates", "help:system", "help:ntp-template-management"],
        }

    if role_norm == "requestor" and asks_add_custodian and is_howto:
        custodian_playbook = next(
            (pb for pb in REQUESTOR_ACTIVITY_PLAYBOOKS if pb.get("id") == "requestor_custodian_update"),
            None,
        )
        if custodian_playbook:
            return {
                "task_id": "requestor_custodian_update",
                "answer": _playbook_answer(custodian_playbook),
                "confidence": "high",
                "citations": (custodian_playbook.get("citations") or [])[:8],
            }

    if role_norm == "requestor":
        matched = _match_requestor_playbooks(q, limit=3)
        if matched and (is_howto or _contains_any(q, ["add", "send", "submit", "open", "find", "where", "what do i click"])):
            best = matched[0]
            return {
                "task_id": best.get("id") or "requestor_playbook",
                "answer": _playbook_answer(best),
                "confidence": "high",
                "citations": (best.get("citations") or [])[:8],
            }

    if asks_add_custodian and is_howto:
        lines: list[str] = []
        if role_norm == "tech":
            if case_id is None:
                lines.append("1. Select Cases and open the target case.")
            lines.append("2. In tech mode, custodian additions are usually handled via request workflow.")
            lines.append("3. Use Requests > custodian update (or ask analyst/sys admin) to add custodians.")
            lines.append("4. After approval, verify the new custodian in Case Detail > Custodians.")
            return {
                "task_id": "add_custodian_tech",
                "answer": "\n".join(lines),
                "confidence": "medium",
                "citations": ["help:tech-case-detail", "help:custodian-update-request"],
            }

        if case_id is None:
            lines.append("1. Select Cases and open the target case.")
        lines.append("2. In Case Detail, open the Custodians tab.")
        lines.append("3. Click `Add Custodians` (or use import for bulk adds).")
        lines.append("4. Enter name and email for each row.")
        lines.append("5. Complete person lookup: select the correct match, or enable override when needed.")
        lines.append("6. Click `Add`, then verify the custodian appears in the list.")
        return {
            "task_id": "add_custodian_analyst",
            "answer": "\n".join(lines),
            "confidence": "high",
            "citations": ["ui:case-detail-add-custodians-modal", "help:case-detail"],
        }

    return None
@lru_cache(maxsize=1)
def _knowledge_corpus() -> list[dict[str, str]]:
    items: list[dict[str, str]] = [
        {
            "id": "playbook-holds",
            "title": "Hold Status Meanings",
            "text": (
                "In DiscoveryOne hold UX, a red X indicates a failed hold operation for that source. "
                "For Box specifically, red X usually maps to holds_box_failed=true. "
                "Pending indicates request submitted but not yet confirmed. "
                "Released indicates a hold was intentionally lifted. "
                "Green/active indicators represent successful applied hold states."
            ),
        },
        {
            "id": "playbook-consent",
            "title": "Consent and N/A Rules",
            "text": (
                "Custodians marked consent N/A must remain excluded from consent send actions. "
                "Consent statuses include not sent, sent, received, and not required. "
                "If consent is not required, the reason should be shown and no send action should be taken."
            ),
        },
        {
            "id": "playbook-search",
            "title": "Purview KQL Guardrails",
            "text": (
                "Use Purview-safe KQL. Avoid leading wildcards like *@domain. "
                "Use property syntax compatible with Purview and ISO-like date formats where possible. "
                "If a query fails validation, explain exactly which part is invalid and provide corrected alternatives."
            ),
        },
        {
            "id": "playbook-ntp-basics",
            "title": "NTP Basics and Template Management",
            "text": (
                "In DiscoveryOne, NTP means Notice to Preserve. "
                "Sending NTP notices is a case-level workflow from Case Detail > NTPs, but creating NTP templates is a System-level workflow from System > NTP Templates. "
                "Analysts and sys admins can create reusable templates there. Requestor accounts can manage templates only when their account belongs to a requestor group, and those templates are scoped to that group. "
                "Tech and tester accounts do not manage NTP templates."
            ),
        },
        {
            "id": "playbook-ntp-template-fields",
            "title": "NTP Template Fields",
            "text": (
                "NTP templates include name, subject, optional description, optional CC recipients, and the HTML body. "
                "The System > NTP Templates screen shows supported placeholders such as case_name, legal_case_name, custodian_name, custodian_email, requestor, ack_link, claimant, and outside_counsel fields. "
                "Templates can also be marked as the default for NTP sends and as high importance."
            ),
        },
        {
            "id": "playbook-privacy",
            "title": "Role and Data Access",
            "text": (
                "Answers must respect role visibility. Do not disclose case-specific data for unauthorized users. "
                "If data is missing or unavailable, explicitly say unknown and provide next steps instead of guessing."
            ),
        },
    ]

    repo_root = Path(__file__).resolve().parents[2]
    candidate_docs = [
        ("tech_documentation", repo_root / "tech_documentation"),
        ("help_page", repo_root / "frontend" / "src" / "pages" / "Help.jsx"),
    ]

    for prefix, path in candidate_docs:
        try:
            if not path.exists() or not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8", errors="ignore")
            # Very light JSX/HTML noise cleanup for retrieval snippets.
            cleaned = re.sub(r"<[^>]+>", " ", raw)
            cleaned = re.sub(r"\{[^{}]{0,120}\}", " ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned)
            # Split into pseudo-paragraph chunks.
            for idx, chunk in enumerate(re.split(r"(?<=[\.!\?])\s+", cleaned)):
                text_chunk = (chunk or "").strip()
                if len(text_chunk) < 120:
                    continue
                items.append(
                    {
                        "id": f"{prefix}-{idx+1}",
                        "title": f"{prefix} snippet {idx+1}",
                        "text": text_chunk[:900],
                    }
                )
                if idx >= 40:
                    break
        except Exception as exc:
            _debug_suppressed("suppressed exception in ai_assistant.py:knowledge_load", exc)

    return items


def _retrieve_knowledge(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    corpus = _knowledge_corpus()
    q_tokens = _tokenize(query)
    if not q_tokens:
        return corpus[: min(limit, len(corpus))]

    ranked: list[Tuple[int, dict[str, str]]] = []
    for item in corpus:
        text_blob = f"{item.get('title', '')} {item.get('text', '')}".lower()
        score = 0
        for token in q_tokens:
            if token in text_blob:
                score += 1
        if score > 0:
            ranked.append((score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    selected = [item for _, item in ranked[:limit]]
    if selected:
        return selected
    return corpus[: min(limit, len(corpus))]


