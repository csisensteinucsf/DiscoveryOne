from __future__ import annotations

from datetime import datetime, timezone, timedelta
from hashlib import sha256
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from . import models


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _fingerprint(value: str) -> str:
    if value is None:
        return ""
    return sha256(value.encode("utf-8")).hexdigest()


def _trim(text: Optional[str], length: int) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    return text[:length]


def clear_expired_sessions(db: Session) -> None:
    """Best-effort cleanup to keep the table small."""
    try:
        db.query(models.SessionToken).filter(models.SessionToken.expires_at < _now()).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


def create_session_token(
    db: Session,
    *,
    user_id: int,
    token: str,
    jti: str,
    expires_at: datetime,
    user_agent: Optional[str],
    ip: Optional[str],
) -> models.SessionToken:
    clear_expired_sessions(db)
    now = _now()
    row = models.SessionToken(
        id=str(uuid4()),
        user_id=str(user_id),
        jti=jti,
        token_hash=_fingerprint(token),
        user_agent=_trim(user_agent, 255),
        ip=_trim(ip, 63),
        expires_at=expires_at,
        revoked_at=None,
        created_at=now,
        last_seen_at=now,
    )
    db.add(row)
    db.commit()
    return row


def revoke_session_by_jti(db: Session, jti: Optional[str]) -> None:
    if not jti:
        return
    try:
        db.query(models.SessionToken).filter(models.SessionToken.jti == jti, models.SessionToken.revoked_at.is_(None)).update(
            {"revoked_at": _now()},
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        db.rollback()


def revoke_all_sessions_for_user(db: Session, user_id: int) -> None:
    try:
        db.query(models.SessionToken).filter(models.SessionToken.user_id == str(user_id), models.SessionToken.revoked_at.is_(None)).update(
            {"revoked_at": _now()},
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        db.rollback()


def revoke_all_auth_tokens_for_user(db: Session, user_id: int, *, commit: bool = True) -> None:
    """Revoke access and refresh records together, optionally in the caller's transaction."""
    try:
        revoked_at = _now()
        db.query(models.SessionToken).filter(
            models.SessionToken.user_id == str(user_id),
            models.SessionToken.revoked_at.is_(None),
        ).update({"revoked_at": revoked_at}, synchronize_session=False)
        db.query(models.RefreshToken).filter(
            models.RefreshToken.user_id == str(user_id),
            models.RefreshToken.revoked_at.is_(None),
        ).update({"revoked_at": revoked_at}, synchronize_session=False)
        if commit:
            db.commit()
    except Exception:
        db.rollback()
        raise


def revoke_session_by_id(db: Session, session_id: Optional[str], *, user_id: Optional[int] = None) -> None:
    if not session_id:
        return
    try:
        query = db.query(models.SessionToken).filter(
            models.SessionToken.id == session_id,
            models.SessionToken.revoked_at.is_(None),
        )
        if user_id is not None:
            query = query.filter(models.SessionToken.user_id == str(user_id))
        query.update({"revoked_at": _now()}, synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


def touch_session(db: Session, session_id: Optional[str], *, only_if_older_seconds: int = 0) -> None:
    if not session_id:
        return
    try:
        now = _now()
        query = db.query(models.SessionToken).filter(
            models.SessionToken.id == session_id,
            models.SessionToken.revoked_at.is_(None),
        )
        if only_if_older_seconds > 0:
            threshold = now - timedelta(seconds=only_if_older_seconds)
            query = query.filter(
                models.SessionToken.last_seen_at.is_(None) | (models.SessionToken.last_seen_at < threshold)
            )
        updated = query.update({"last_seen_at": now}, synchronize_session=False)
        if updated:
            db.commit()
        else:
            db.rollback()
    except Exception:
        db.rollback()


def create_refresh_token(
    db: Session,
    *,
    user_id: int,
    token: str,
    jti: str,
    expires_at: datetime,
    user_agent: Optional[str],
    ip: Optional[str],
) -> models.RefreshToken:
    now = _now()
    row = models.RefreshToken(
        id=str(uuid4()),
        user_id=str(user_id),
        jti=jti,
        token_hash=_fingerprint(token),
        user_agent=_trim(user_agent, 255),
        ip=_trim(ip, 63),
        expires_at=expires_at,
        revoked_at=None,
        created_at=now,
    )
    db.add(row)
    db.commit()
    return row


def revoke_refresh_by_jti(db: Session, jti: Optional[str]) -> None:
    if not jti:
        return
    try:
        db.query(models.RefreshToken).filter(models.RefreshToken.jti == jti, models.RefreshToken.revoked_at.is_(None)).update(
            {"revoked_at": _now()},
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        db.rollback()


def revoke_all_refresh_for_user(db: Session, user_id: int) -> None:
    try:
        db.query(models.RefreshToken).filter(models.RefreshToken.user_id == str(user_id), models.RefreshToken.revoked_at.is_(None)).update(
            {"revoked_at": _now()},
            synchronize_session=False,
        )
        db.commit()
    except Exception:
        db.rollback()


def revoke_refresh_by_id(db: Session, refresh_id: Optional[str], *, user_id: Optional[int] = None) -> None:
    if not refresh_id:
        return
    try:
        query = db.query(models.RefreshToken).filter(
            models.RefreshToken.id == refresh_id,
            models.RefreshToken.revoked_at.is_(None),
        )
        if user_id is not None:
            query = query.filter(models.RefreshToken.user_id == str(user_id))
        query.update({"revoked_at": _now()}, synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()


def find_valid_refresh(db: Session, token: str, *, user_agent: Optional[str] = None, ip: Optional[str] = None) -> Optional[models.RefreshToken]:
    """
    Validate refresh token by hash, ensure not expired/revoked. Best-effort UA/IP check.
    """
    if not token:
        return None
    fp = _fingerprint(token)
    now = _now()
    record = (
        db.query(models.RefreshToken)
        .filter(models.RefreshToken.token_hash == fp)
        .filter(models.RefreshToken.revoked_at.is_(None))
        .first()
    )
    if not record or _as_utc(record.expires_at) <= now:
        return None
    # Soft match on UA/IP if provided (do not fail if missing)
    if user_agent and record.user_agent and _trim(user_agent, 255) != record.user_agent:
        return None
    if ip and record.ip and _trim(ip, 63) != record.ip:
        return None
    return record


def consume_valid_refresh(db: Session, token: str, *, user_agent: Optional[str] = None, ip: Optional[str] = None) -> Optional[models.RefreshToken]:
    """Atomically revoke and return a valid refresh token exactly once."""
    record = find_valid_refresh(db, token, user_agent=user_agent, ip=ip)
    if not record:
        return None
    now = _now()
    try:
        updated = (
            db.query(models.RefreshToken)
            .filter(
                models.RefreshToken.id == record.id,
                models.RefreshToken.revoked_at.is_(None),
                models.RefreshToken.expires_at > now,
            )
            .update({"revoked_at": now}, synchronize_session=False)
        )
        if updated != 1:
            db.rollback()
            return None
        db.commit()
        return record
    except Exception:
        db.rollback()
        return None
