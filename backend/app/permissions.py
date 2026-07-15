from __future__ import annotations

from typing import Optional, Set

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import models
from .safe_log import debug_suppressed as _debug_suppressed
from .ticket_workflow_catalog import (
    category_legacy_fields,
    tech_group_categories,
    ticket_workflows_raw,
)


def _ticket_workflows_raw():
    return ticket_workflows_raw()


def _tech_group_ticket_categories() -> dict[str, Set[str]]:
    return tech_group_categories()


def _tech_category_legacy_fields() -> dict[str, str]:
    return category_legacy_fields()

def _normalize_email(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_email_candidate(value: Optional[str]) -> str:
    text = _normalize_email(value)
    if not text:
        return ""
    if "@" not in text or " " in text:
        return ""
    return text


def _normalize_group(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _split_groups(value: Optional[str]) -> Set[str]:
    normalized = _normalize_group(value)
    if not normalized:
        return set()
    parts = set()
    for chunk in normalized.replace(";", ",").split(","):
        piece = (chunk or "").strip()
        if piece:
            parts.add(piece)
    return parts


def get_requestor_visible_groups(user, db: Optional[Session] = None) -> Set[str]:
    groups: Set[str] = set()
    if not user or not is_requestor(user):
        return groups
    own_group = _normalize_group(getattr(user, "requestor_group", None))
    if own_group:
        groups.add(own_group)
    if own_group and db is not None:
        rows = (
            db.query(models.RequestorGroupAccess.target_group)
            .filter(func.lower(models.RequestorGroupAccess.source_group) == own_group)
            .all()
        )
        for (value,) in rows:
            normalized = _normalize_group(value)
            if normalized:
                groups.add(normalized)
    return groups


def get_role(user) -> str:
    """
    Return a normalized role string for the given SQLAlchemy user model.
    Falls back to sys_admin when is_admin is true, otherwise analyst.
    """
    if not user:
        return "analyst"
    role = getattr(user, "role", None)
    if role is not None:
        try:
            normalized = str(role).strip().lower()
        except Exception:
            normalized = ""
        if normalized:
            return normalized
    return "sys_admin" if getattr(user, "is_admin", False) else "analyst"


def is_sys_admin(user) -> bool:
    return get_role(user) == "sys_admin"


def is_requestor(user) -> bool:
    return get_role(user) == "requestor"


def is_tester(user) -> bool:
    return get_role(user) == "tester"


def is_tech(user) -> bool:
    return get_role(user) == "tech"


def tech_allowed_ticket_categories(user) -> Set[str]:
    if not is_tech(user):
        return set()
    allowed: Set[str] = set()
    for group in _split_groups(getattr(user, "requestor_group", None)):
        allowed.update(_tech_group_ticket_categories().get(group, set()))
    return allowed


def is_valid_tech_group(value: Optional[str]) -> bool:
    groups = _split_groups(value)
    if not groups:
        return False
    return all(group in _tech_group_ticket_categories() for group in groups)


def ensure_not_requestor(user) -> None:
    if is_requestor(user) or is_tech(user) or is_tester(user):
        raise HTTPException(status_code=403, detail="Requestor, tech, and tester accounts are read-only")


def can_access_case_requests(user) -> bool:
    role = get_role(user)
    return role in {"requestor", "analyst", "sys_admin"}


def ensure_case_request_access(user) -> None:
    if not can_access_case_requests(user):
        raise HTTPException(status_code=403, detail="Access denied")


def can_review_case_requests(user) -> bool:
    return get_role(user) in {"analyst", "sys_admin"}


def ensure_case_request_reviewer(user) -> None:
    if not can_review_case_requests(user):
        raise HTTPException(status_code=403, detail="Reviewer privileges required")

def get_requestor_allowed_emails(user, db: Optional[Session] = None) -> Set[str]:
    """
    Returns the set of normalized requestor emails the user can act on.
    Includes their own email (or email-like username) plus peers in the same
    requestor_group (when available).
    """
    allowed: Set[str] = set()
    if not user or not is_requestor(user):
        return allowed

    direct_email = _normalize_email_candidate(getattr(user, "email", None))
    if direct_email:
        allowed.add(direct_email)

    username_email = _normalize_email_candidate(getattr(user, "username", None))
    if username_email:
        allowed.add(username_email)

    groups = get_requestor_visible_groups(user, db)
    if groups and db is not None:
        peers = (
            db.query(models.User.email, models.User.username)
            .filter(
                models.User.role == "requestor",
                func.lower(models.User.requestor_group).in_(groups),
            )
            .all()
        )
        for peer_email, peer_username in peers:
            norm_email = _normalize_email_candidate(peer_email)
            if norm_email:
                allowed.add(norm_email)
            norm_username = _normalize_email_candidate(peer_username)
            if norm_username:
                allowed.add(norm_username)

    return allowed


def ensure_case_visible(case, user, db: Optional[Session] = None) -> None:
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if is_requestor(user):
        case_email = _normalize_email(getattr(case, "requestor", None))
        user_email = _normalize_email_candidate(getattr(user, "email", None))
        user_username_email = _normalize_email_candidate(getattr(user, "username", None))
        direct_emails = {value for value in (user_email, user_username_email) if value}
        # Private cases are visible only to directly assigned requestors, not
        # same-group peers or directionally delegated groups.
        if bool(getattr(case, "is_private", False)):
            try:
                for row in getattr(case, "requestors", []) or []:
                    entry_email = _normalize_email(getattr(row, "email", None))
                    if entry_email and entry_email in direct_emails:
                        return
                    if getattr(row, "user_id", None) == getattr(user, "id", None):
                        return
            except Exception as exc:
                _debug_suppressed("suppressed exception in permissions.py:private_case", exc)
            if case_email and case_email in direct_emails:
                return
            raise HTTPException(status_code=403, detail="Requestor accounts can only access directly assigned private cases")

        allowed = get_requestor_allowed_emails(user, db)
        if user_email:
            allowed.add(user_email)
        if user_username_email:
            allowed.add(user_username_email)
        visible_groups = get_requestor_visible_groups(user, db)
        # direct membership on case_requestors wins
        try:
            for row in getattr(case, "requestors", []) or []:
                entry_email = _normalize_email(getattr(row, "email", None))
                if entry_email and (entry_email in allowed):
                    return
                if getattr(row, "user_id", None) == getattr(user, "id", None):
                    return
                entry_group = _normalize_group(getattr(row, "requestor_group", None))
                if entry_group and entry_group in visible_groups:
                    return
        except Exception as exc:
            _debug_suppressed("suppressed exception in permissions.py:164", exc)
        if case_email and case_email in allowed:
            return
        raise HTTPException(status_code=403, detail="Requestor accounts can only access their assigned cases")
    if is_tester(user):
        name = (getattr(case, "name", "") or "").strip().lower()
        if name.endswith("-test".lower()):
            return
        raise HTTPException(status_code=403, detail="Tester accounts can only access TEST-suffixed cases")
    if is_tech(user):
        allowed = tech_allowed_ticket_categories(user)
        if not allowed:
            raise HTTPException(status_code=403, detail="Tech accounts must belong to a ticket group")
        if case_has_ticket_category(case, allowed):
            return
        raise HTTPException(status_code=403, detail="Tech accounts can only access cases with their assigned ticket types")


def ensure_case_editable(user) -> None:
    ensure_not_requestor(user)


def case_has_ticket_category(case, categories: Set[str]) -> bool:
    try:
        entries = getattr(case, "request_ticket_entries", []) or []
    except Exception:
        entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category = (entry.get("category") or "").strip().lower()
        if category in categories:
            return True
    for category in categories:
        field = _tech_category_legacy_fields().get(category)
        if not field:
            continue
        try:
            value = getattr(case, field, None)
        except Exception:
            value = None
        if isinstance(value, str):
            if value.strip():
                return True
        elif value:
            return True
    return False


def filter_ticket_entries_for_user(entries, user):
    if not is_tech(user):
        return entries or []
    allowed = tech_allowed_ticket_categories(user)
    if not allowed:
        return []
    filtered = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        category = (entry.get("category") or "").strip().lower()
        if category in allowed:
            filtered.append(entry)
    return filtered


def get_tech_visible_case_ids(user, db: Optional[Session] = None) -> Set[int]:
    if not is_tech(user) or db is None:
        return set()
    allowed = tech_allowed_ticket_categories(user)
    if not allowed:
        return set()
    ids: Set[int] = set()
    rows = db.query(models.Case).all()
    for row in rows:
        if case_has_ticket_category(row, allowed):
            ids.add(getattr(row, "id", None))
    return {i for i in ids if i is not None}
