from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse


def _purview_email_norm(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _purview_name_norm(value: Optional[str]) -> str:
    return " ".join((value or "").strip().lower().split())


_EMAIL_LIKE_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _extract_email_candidates(payload: Any, *, max_depth: int = 3, max_values: int = 10) -> set[str]:
    candidates: set[str] = set()

    def _add(value: Any) -> None:
        if not isinstance(value, str):
            return
        text = value.strip()
        if not text:
            return
        if "@" in text:
            for match in _EMAIL_LIKE_RE.findall(text):
                if len(candidates) >= max_values:
                    return
                candidates.add(match.strip().lower())

    def _walk(value: Any, depth: int) -> None:
        if len(candidates) >= max_values or depth > max_depth:
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if k in {"email", "mail", "userPrincipalName", "upn"}:
                    _add(v)
                _walk(v, depth + 1)
        elif isinstance(value, list):
            for item in value:
                _walk(item, depth + 1)
        else:
            _add(value)

    _walk(payload, 0)
    return candidates


def _purview_hold_display_name(case_name: str) -> str:
    base = (case_name or "").strip()
    return f"{base}-Hold" if base else "Hold"


def _purview_hold_name_match(hold: dict, target_name: str) -> bool:
    hold_name = (hold.get("displayName") or "").strip().lower()
    target = (target_name or "").strip().lower()
    return bool(hold_name and target and hold_name == target)


def _purview_sources_set(included_sources: Optional[list]) -> set[str]:
    if not included_sources:
        return set()
    if isinstance(included_sources, str):
        raw = [included_sources]
    else:
        raw = list(included_sources)
    parts: list[str] = []
    for item in raw:
        if item is None:
            continue
        text = str(item)
        if "," in text:
            parts.extend(piece.strip() for piece in text.split(","))
        else:
            parts.append(text.strip())
    allowed = {"mailbox", "site"}
    return {part.lower() for part in parts if part and part.lower() in allowed}


def _purview_sources_flags(included_sources: Optional[list]) -> dict:
    normalized = _purview_sources_set(included_sources)
    return {
        "mailbox": "mailbox" in normalized,
        "site": "site" in normalized,
    }


def _normalize_site_url(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if text.endswith("/"):
        text = text[:-1]
    return text


def _looks_like_url(value: Optional[str]) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _normalize_personal_key(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or None


def _onedrive_personal_key(email: Optional[str]) -> Optional[str]:
    return _normalize_personal_key(email)


def _personal_key_from_url(url: Optional[str]) -> Optional[str]:
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    path = (parsed.path or "").lower()
    marker = "/personal/"
    if marker not in path:
        return None
    suffix = path.split(marker, 1)[1]
    segment = suffix.strip("/").split("/", 1)[0].strip()
    return _normalize_personal_key(segment)


def _canonical_site_key(resource: Optional[dict]) -> Optional[str]:
    if not isinstance(resource, dict):
        return None
    for key in ("id", "sharepointSiteId"):
        value = resource.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    for key in ("sharepointSiteUrl", "webUrl"):
        value = resource.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_site_url(value)
    return None


def _candidate_site_keys(resource: Optional[dict]) -> list[str]:
    if not isinstance(resource, dict):
        return []
    keys: list[str] = []

    def _add(value: Optional[str], *, normalize_url: bool = False) -> None:
        if not isinstance(value, str):
            return
        raw = value.strip()
        if not raw:
            return
        key = _normalize_site_url(raw) if normalize_url else raw.lower()
        if key and key not in keys:
            keys.append(key)

    _add(resource.get("id"))
    _add(resource.get("sharepointSiteId"))
    _add(resource.get("sharepointSiteUrl"), normalize_url=True)
    _add(resource.get("webUrl"), normalize_url=True)
    return keys


def _purview_site_key(source: dict) -> Optional[str]:
    if not isinstance(source, dict):
        return None
    site = source.get("site")
    if isinstance(site, dict):
        site_id = site.get("id")
        if isinstance(site_id, str) and site_id.strip():
            return site_id.strip().lower()
        web_url = site.get("webUrl")
        if isinstance(web_url, str) and web_url.strip():
            return _normalize_site_url(web_url)
    for key in ("siteWebUrl", "webUrl", "siteUrl", "siteId", "site_id", "id"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_site_url(value) if _looks_like_url(value) else value.strip().lower()
    return None
