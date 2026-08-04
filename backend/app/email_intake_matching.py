from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Iterable

from bs4 import BeautifulSoup

MAX_BODY_TEXT = 100_000
ALLOWED_EXTRACTED_FIELDS = {
    "case_name",
    "legal_case_name",
    "claimant",
    "internal_counsel",
    "outside_counsel",
    "matter_number",
    "description",
    "custodians",
    "hold_name",
}


@dataclass(frozen=True)
class NormalizedEmail:
    graph_message_id: str
    internet_message_id: str | None
    change_key: str | None
    sender: str
    recipients: tuple[str, ...]
    subject: str
    body_text: str
    received_at: datetime | None
    has_attachments: bool


def _json_value(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def html_to_plain_text(value: Any) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for node in soup(["script", "style", "iframe", "object", "embed"]):
        node.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_BODY_TEXT]


def _email_address(value: Any) -> str:
    if isinstance(value, dict):
        value = ((value.get("emailAddress") or {}).get("address"))
    return parseaddr(str(value or ""))[1].strip().lower()


def _recipient_addresses(message: dict[str, Any]) -> tuple[str, ...]:
    rows: list[str] = []
    for field in ("toRecipients", "ccRecipients", "bccRecipients"):
        for item in message.get(field) or []:
            address = _email_address(item)
            if address and address not in rows:
                rows.append(address)
    return tuple(rows)


def _parse_graph_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_graph_message(message: dict[str, Any]) -> NormalizedEmail:
    body = message.get("body") or {}
    body_content = body.get("content") if isinstance(body, dict) else ""
    content_type = str(body.get("contentType") or "text").strip().lower() if isinstance(body, dict) else "text"
    body_text = html_to_plain_text(body_content) if content_type == "html" else str(body_content or "").strip()[:MAX_BODY_TEXT]
    sender = _email_address(message.get("from") or message.get("sender"))
    return NormalizedEmail(
        graph_message_id=str(message.get("id") or "").strip(),
        internet_message_id=str(message.get("internetMessageId") or "").strip() or None,
        change_key=str(message.get("changeKey") or "").strip() or None,
        sender=sender,
        recipients=_recipient_addresses(message),
        subject=str(message.get("subject") or "").strip(),
        body_text=body_text,
        received_at=_parse_graph_datetime(message.get("receivedDateTime")),
        has_attachments=bool(message.get("hasAttachments")),
    )


def _patterns(value: Any) -> list[str]:
    return [item.strip().lower() for item in re.split(r"[\r\n;]+", str(value or "")) if item.strip()]


def _matches_pattern(value: str, configured: Any) -> bool:
    patterns = _patterns(configured)
    if not patterns:
        return True
    candidate = str(value or "").lower()
    for pattern in patterns:
        if any(char in pattern for char in "*?["):
            if fnmatch.fnmatchcase(candidate, pattern):
                return True
        elif pattern in candidate:
            return True
    return False


def _body_markers(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    parsed = _json_value(value, [])
    if parsed:
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [item.strip() for item in str(value or "").splitlines() if item.strip()]


def template_matches(template: Any, email: NormalizedEmail) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if not _matches_pattern(email.sender, getattr(template, "sender_pattern", None)):
        failures.append("sender")
    recipients = ";".join(email.recipients)
    if not _matches_pattern(recipients, getattr(template, "recipient_pattern", None)):
        failures.append("recipient")
    if not _matches_pattern(email.subject, getattr(template, "subject_pattern", None)):
        failures.append("subject")
    body_lower = email.body_text.lower()
    missing_markers = [marker for marker in _body_markers(getattr(template, "body_markers", None)) if marker.lower() not in body_lower]
    if missing_markers:
        failures.append("body markers: " + ", ".join(missing_markers))
    return not failures, failures


def first_matching_template(templates: Iterable[Any], email: NormalizedEmail) -> Any | None:
    ordered = sorted(
        (item for item in templates if bool(getattr(item, "enabled", True))),
        key=lambda item: (int(getattr(item, "priority", 100) or 100), int(getattr(item, "id", 0) or 0)),
    )
    for template in ordered:
        matched, _ = template_matches(template, email)
        if matched:
            return template
    return None


def _line_marker_value(body: str, marker: Any) -> str:
    target = str(marker or "").strip()
    if not target:
        return ""
    target_lower = target.lower()
    lines = body.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.lower().startswith(target_lower):
            continue
        value = stripped[len(target):].strip().lstrip(":=-").strip()
        if value:
            return value
        for following in lines[index + 1:index + 4]:
            value = following.strip()
            if value:
                return value
    return ""


def _parse_custodians(value: Any) -> list[dict[str, Any]]:
    text = str(value or "").strip()
    if not text:
        return []
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in re.split(r"[;\n]+", text):
        item = raw.strip()
        if not item:
            continue
        name, address = parseaddr(item)
        if not address and "," in item:
            pieces = [part.strip() for part in item.split(",", 1)]
            name = pieces[0]
            address = pieces[1] if len(pieces) > 1 and "@" in pieces[1] else ""
        address = address.strip().lower()
        display = (name or (address.split("@", 1)[0] if address else item)).strip()
        key = address or display.lower()
        if not display or key in seen:
            continue
        seen.add(key)
        results.append({"name": display, "email": address or None, "holds": {}})
    return results


def extract_case_request_payload(template: Any, email: NormalizedEmail, *, requestor_from_sender: bool = True) -> dict[str, Any]:
    markers = _json_value(getattr(template, "field_markers", None), {})
    defaults = _json_value(getattr(template, "default_values", None), {})
    values: dict[str, Any] = {
        key: value
        for key, value in defaults.items()
        if key in ALLOWED_EXTRACTED_FIELDS and value not in (None, "")
    }
    for field, marker in markers.items():
        if field not in ALLOWED_EXTRACTED_FIELDS:
            continue
        extracted = _line_marker_value(email.body_text, marker)
        if extracted:
            values[field] = extracted

    case_name = str(values.get("case_name") or values.get("legal_case_name") or email.subject or "Email intake request").strip()
    legal_name = str(values.get("legal_case_name") or case_name).strip()
    description = str(values.get("description") or email.body_text or "").strip()[:20_000]
    hold_name = str(values.get("hold_name") or getattr(template, "hold_name", None) or "Hold A").strip()[:255]
    payload: dict[str, Any] = {
        "name": case_name[:255],
        "legal_case_name": legal_name[:255],
        "claimant": str(values.get("claimant") or "").strip() or None,
        "internal_counsel": str(values.get("internal_counsel") or "").strip() or None,
        "outside_counsel": str(values.get("outside_counsel") or "").strip() or None,
        "matter_number": str(values.get("matter_number") or "").strip() or None,
        "description": description,
        "custodian_entry_mode": "manual",
        "custodians": _parse_custodians(values.get("custodians")),
        "hold_name": hold_name or "Hold A",
        "email_intake": {
            "graph_message_id": email.graph_message_id,
            "internet_message_id": email.internet_message_id,
            "sender": email.sender,
            "recipients": list(email.recipients),
            "subject": email.subject,
            "received_at": email.received_at.isoformat() if email.received_at else None,
        },
    }
    if requestor_from_sender and email.sender:
        payload["requestors"] = [{"email": email.sender, "is_primary": True}]
    return payload