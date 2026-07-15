# backend/app/custodian_guard.py
# Global SQLAlchemy guard that prevents inserting CSV header-like rows as custodians,
# no matter which endpoint or code path attempts to insert them.

from __future__ import annotations
from sqlalchemy import event
from sqlalchemy.orm import Session as SASession
from typing import Iterable
import re

from . import models  # requires models to be imported before install()
from .safe_log import debug_suppressed as _debug_suppressed

_HEADER_TOKENS = {
    "name","full name","display name","custodian",
    "email","email address","e-mail","address","first","last","first name","last name"
}
_HEADER_PAIRS = {
    ("name", "email"),
    ("full name", "email"),
    ("display name", "email"),
    ("custodian", "email"),
    ("custodian name", "email address"),
    ("first name", "email"),
    ("last name", "email"),
}
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")

def _is_header_like(name: str|None, email: str|None) -> bool:
    n = (name or "").strip().lower()
    e = (email or "").strip().lower()
    if not n and not e:
        return False
    if (n, e) in _HEADER_PAIRS:
        return True
    if n in _HEADER_TOKENS and e in _HEADER_TOKENS:
        return True
    if not e and n in _HEADER_TOKENS:
        return True
    return False

def _is_obviously_bad_email(email: str|None) -> bool:
    if not email: return False
    return _EMAIL_RE.search(email) is None

def install_custodian_guard():
    """Register a before_flush hook that expunges header-like custodian rows.
    Call once during app startup (e.g., in main.py after importing models).
    """
    @event.listens_for(SASession, "before_flush")
    def _strip_headers_before_flush(session, flush_context, instances):
        to_expunge = []
        for obj in list(session.new):
            if isinstance(obj, models.Custodian):
                if _is_header_like(obj.name, obj.email):
                    to_expunge.append(obj)
                elif _is_obviously_bad_email(obj.email):
                    # null out invalid emails rather than store garbage
                    obj.email = None
        for obj in to_expunge:
            try:
                session.expunge(obj)  # remove from session so it's never inserted
            except Exception as exc:
                _debug_suppressed("suppressed exception in custodian_guard.py:55", exc)
