from __future__ import annotations

from fastapi import HTTPException

from .institution import (
    is_organization_email,
    is_requestor_email_exception,
    organization_domains,
    organization_domain_label,
)


def is_allowed_requestor_email(email: str | None) -> bool:
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    if is_requestor_email_exception(normalized):
        return True
    if not organization_domains():
        return True
    return is_organization_email(normalized)


def require_allowed_requestor_email(email: str | None, *, label: str = "Requestor email") -> str:
    normalized = (email or "").strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{label} is required")
    if not is_allowed_requestor_email(normalized):
        raise HTTPException(
            status_code=422,
            detail=f"{label} must use an approved organization email address ({organization_domain_label()})",
        )
    return normalized
