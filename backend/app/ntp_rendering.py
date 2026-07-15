from __future__ import annotations

import hashlib
import html
import re
import secrets
from typing import Dict, List, Optional

import bleach
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session, selectinload

from . import models
from . import ntp as ntp_core
from .system_settings import load_system_settings


def _normalize_highlight_markers(value: str) -> str:
    """Ensure any marked/highlighted spans keep a data-highlight marker before sanitization."""
    def _ensure_data_attr(tag: str) -> str:
        if "data-highlight" in tag.lower():
            return tag
        return f"{tag[:-1]} data-highlight=\"1\">"

    text = re.sub(
        r"<mark\b[^>]*>",
        lambda m: _ensure_data_attr(m.group(0)),
        value,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"<span\b[^>]*background-color[^>]*>",
        lambda m: _ensure_data_attr(m.group(0)),
        text,
        flags=re.IGNORECASE,
    )
    return text


def _sanitize_template_html(value: Optional[str]) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    text = text.replace("<div", "<p").replace("</div>", "</p>")
    text = _normalize_highlight_markers(text)
    clean_kwargs = {
        "tags": ntp_core._ALLOWED_TEMPLATE_TAGS,
        "attributes": ntp_core._ALLOWED_TEMPLATE_ATTRS,
        "protocols": ntp_core._ALLOWED_TEMPLATE_PROTOCOLS,
        "strip": True,
    }
    if ntp_core._CSS_SANITIZER:
        clean_kwargs["css_sanitizer"] = ntp_core._CSS_SANITIZER
    try:
        if ntp_core._CSS_SANITIZER:
            cleaned = bleach.clean(text, **clean_kwargs)
        else:
            cleaned = bleach.clean(text, styles=ntp_core._ALLOWED_TEMPLATE_STYLES, **clean_kwargs)  # type: ignore[call-arg]
    except TypeError:
        cleaned = bleach.clean(text, **clean_kwargs)
    return _apply_highlight_style(cleaned)


def _apply_highlight_style(html_value: str) -> str:
    """Ensure highlights survive sanitization and render in email clients."""
    has_mark = "<mark" in html_value.lower()
    has_span_bg = "background-color" in html_value.lower()
    has_data_hl = "data-highlight" in html_value.lower()
    if not has_mark and not has_span_bg and not has_data_hl:
        return html_value
    open_tag = f'<span style="{ntp_core._HIGHLIGHT_STYLE}" data-highlight="1">'
    html_value = re.sub(r"<mark(\s[^>]*)?>", open_tag, html_value, flags=re.IGNORECASE)
    html_value = re.sub(r"</mark\s*>", "</span>", html_value, flags=re.IGNORECASE)
    html_value = re.sub(
        r"<span\b[^>]*data-highlight[^>]*>",
        open_tag,
        html_value,
        flags=re.IGNORECASE,
    )
    html_value = re.sub(
        r"<span\b[^>]*background-color[^>]*>",
        open_tag,
        html_value,
        flags=re.IGNORECASE,
    )
    return html_value


def _normalize_group_name(value: Optional[str]) -> Optional[str]:
    text = (value or "").strip().lower()
    return text or None


def _user_group(user: Optional[models.User]) -> Optional[str]:
    if not user:
        return None
    return _normalize_group_name(getattr(user, "requestor_group", None))


def _template_group_names(template: models.NTPTemplate) -> List[str]:
    names: List[str] = []
    for row in getattr(template, "groups", []) or []:
        norm = _normalize_group_name(getattr(row, "group_name", None))
        if norm and norm not in names:
            names.append(norm)
    return sorted(names)


def _apply_template_groups(template: models.NTPTemplate, groups: Optional[List[str]]) -> None:
    desired = {_normalize_group_name(value) for value in (groups or [])}
    desired.discard(None)
    existing = {row.group_name: row for row in getattr(template, "groups", []) or []}
    for row in list(getattr(template, "groups", []) or []):
        if row.group_name not in desired:
            template.groups.remove(row)
    for name in desired:
        if name not in existing:
            template.groups.append(models.NTPTemplateGroup(group_name=name))


def _template_allows_user(template: models.NTPTemplate, user: models.User) -> bool:
    if not ntp_core.is_requestor(user):
        return True
    group = _user_group(user)
    if not group:
        return False
    return group in _template_group_names(template)


def _templates_for_user(db: Session, user: models.User) -> List[models.NTPTemplate]:
    query = (
        db.query(models.NTPTemplate)
        .options(selectinload(models.NTPTemplate.groups))
        .order_by(models.NTPTemplate.name.asc())
    )
    if ntp_core.is_requestor(user):
        group = _user_group(user)
        if not group:
            return []
        query = (
            query.join(
                models.NTPTemplateGroup,
                models.NTPTemplateGroup.template_id == models.NTPTemplate.id,
            )
            .filter(models.NTPTemplateGroup.group_name == group)
            .distinct()
        )
    return query.all()


def _acknowledgement_page(title: str, message: str, *, status_code: int = 200) -> HTMLResponse:
    html_value = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{ntp_core.app_display_name()} - Notice</title>
    <style>
      body {{
        margin: 0;
        font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #0f172a;
        color: #e2e8f0;
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 24px;
      }}
      .wrap {{
        max-width: 480px;
        width: 100%;
        text-align: center;
      }}
      .brand h1 {{
        margin: 0;
        font-size: 32px;
        color: #f8fafc;
      }}
      .brand p {{
        margin: 4px 0 24px;
        color: #94a3b8;
        font-size: 14px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }}
      .card {{
        background: #0f172a;
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 16px;
        padding: 32px 28px;
        box-shadow: 0 15px 50px rgba(15, 23, 42, 0.4);
      }}
      .card h2 {{
        margin-top: 0;
        font-size: 22px;
        color: #f1f5f9;
      }}
      .card p {{
        color: #cbd5f5;
        line-height: 1.6;
        margin-bottom: 0;
      }}
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="brand">
        <h1>{ntp_core.app_display_name()}</h1>
        <p>{ntp_core.app_tagline()}</p>
      </div>
      <div class="card">
        <h2>{title}</h2>
        <p>{message}</p>
      </div>
    </div>
  </body>
</html>"""
    return HTMLResponse(html_value, status_code=status_code)


def _render_template(text: str, context: Dict[str, str]) -> str:
    rendered = text or ""
    ack_url = (context.get("ack_link_url") or context.get("ack_link") or "").strip()
    ack_label = (context.get("ack_link_text") or "").strip() or ack_url
    if ack_url:
        escaped_url = html.escape(ack_url, quote=True)
        escaped_label = html.escape(ack_label or ack_url, quote=True)
        anchor = f'<a href="{escaped_url}" target="_blank" rel="noopener noreferrer">{escaped_label}</a>'
        rendered = rendered.replace("{{ack_link}}", anchor)
        rendered = rendered.replace("{{ack_link_url}}", anchor)
        rendered = rendered.replace("{{ack_link_text}}", escaped_label)
    for key, value in context.items():
        if key in {"ack_link", "ack_link_url", "ack_link_text"}:
            continue
        token = "{{" + key + "}}"
        safe_value = html.escape(value or "", quote=True)
        rendered = rendered.replace(token, safe_value)
    return rendered


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


def _render_bodies(template_text: str, context: Dict[str, str]) -> tuple[str, str]:
    rendered = _render_template(template_text, context)
    candidate = rendered.strip()
    has_markup = bool(re.search(r"<[^>]+>", candidate))
    if has_markup:
        html_body = _sanitize_template_html(candidate).replace("\n", "<br />")
        text_body = _strip_tags(html_body)
    else:
        text_body = _sanitize_template_html(candidate)
        html_body = _sanitize_template_html(text_body.replace("\n", "<br />"))
    return text_body, html_body


def _merge_cc_lists(*sources: Optional[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for source in sources:
        for addr in _parse_email_list(source):
            key = addr.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(addr)
    return deduped


def _required_ntp_archive_bcc() -> str:
    try:
        settings = load_system_settings()
        value = ((settings.get("ntp") or {}).get("archive_bcc_address") or "").strip().lower()
        if value and "@" in value:
            return value
    except Exception as exc:
        ntp_core._debug_suppressed("suppressed exception in ntp_rendering.py:_required_ntp_archive_bcc", exc)
    return ntp_core.ntp_default_archive_bcc()


def _normalize_template_bcc_for_storage(raw: Optional[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for addr in _parse_email_list(raw):
        key = addr.lower()
        if key in ntp_core.ntp_reserved_archive_bcc_addresses():
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(addr)
    return deduped


def _merge_bcc_lists(*sources: Optional[str]) -> List[str]:
    required = _required_ntp_archive_bcc()
    deduped: List[str] = []
    seen = set()

    required_key = required.lower()
    if required_key:
        deduped.append(required)
        seen.add(required_key)

    for source in sources:
        for addr in _normalize_template_bcc_for_storage(source):
            key = addr.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(addr)
    return deduped


def _hash_ntp_token(value: str) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _create_ntp_token(
    db: Session,
    *,
    case_id: int,
    custodian_id: int,
    template_id: Optional[int],
) -> tuple[models.NTPTargetToken, str]:
    token_value = secrets.token_urlsafe(32)
    token = models.NTPTargetToken(
        token=_hash_ntp_token(token_value),
        case_id=case_id,
        custodian_id=custodian_id,
        template_id=template_id,
    )
    db.add(token)
    db.flush()
    return token, token_value


def _normalize_variables(raw: Dict[str, str]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    items = raw.items() if raw else []
    for key, value in items:
        if value is None:
            cleaned[key] = ""
        else:
            cleaned[key] = str(value).strip()
    if "cc" in cleaned:
        cleaned["cc"] = ", ".join(_parse_email_list(cleaned["cc"]))
    if "bcc" in cleaned:
        cleaned["bcc"] = ", ".join(_normalize_template_bcc_for_storage(cleaned["bcc"]))
    return cleaned


def _pretty_email_address(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw or "@" not in raw:
        return raw
    local, domain = raw.split("@", 1)
    local = local.strip()
    domain = domain.strip().lower()
    if not local or not domain:
        return raw

    def _pretty_token(token: str) -> str:
        lower = (token or "").lower()
        for idx, ch in enumerate(lower):
            if ch.isalpha():
                return lower[:idx] + lower[idx].upper() + lower[idx + 1:]
        return lower

    parts = re.split(r"([._-])", local)
    local_pretty = "".join(part if part in {".", "_", "-"} else _pretty_token(part) for part in parts)
    return f"{local_pretty}@{domain}"


def _build_ntp_context(
    case: models.Case,
    custodian: models.Custodian,
    requestor_label: str,
    ack_link: str,
    ack_display: str,
    variables: Dict[str, str],
) -> Dict[str, str]:
    custodian_email = _pretty_email_address(getattr(custodian, "email", None))
    context = {
        "case_name": case.name or "",
        "legal_case_name": case.legal_case_name or "",
        "custodian_name": custodian.name or "",
        "custodian_email": custodian_email or "",
        "requestor": requestor_label,
        "ack_link": ack_link,
        "ack_link_text": ack_display,
        "ack_link_url": ack_link,
        "claimant": getattr(case, "claimant", "") or "",
    }
    for key, value in (variables or {}).items():
        if key == "ack_link":
            continue
        context[key] = value
    return context


def _parse_email_list(raw: Optional[str]) -> List[str]:
    emails: List[str] = []
    if not raw:
        return emails
    for part in raw.split(","):
        addr = (part or "").strip()
        if addr:
            emails.append(addr)
    return emails
