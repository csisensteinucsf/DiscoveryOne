from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import bindparam, func, text
from sqlalchemy.orm import Session

from . import models

_LOGIN_ACTIONS = ("login", "login_success", "auth_login_success")


def _coerce_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text_value = str(value).strip()
    if not text_value:
        return None
    try:
        parsed = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def last_login_map(db: Session, user_ids: Iterable[object]) -> dict[str, datetime]:
    ids = [int(value) for value in user_ids if str(value or "").strip()]
    if not ids:
        return {}

    results: dict[str, datetime] = {}

    try:
        stmt = text(
            """
            SELECT actor_id, MAX(created_at) AS last_login
              FROM audit_events
             WHERE actor_id IN :user_ids
               AND action IN :actions
             GROUP BY actor_id
            """
        ).bindparams(
            bindparam("user_ids", expanding=True),
            bindparam("actions", expanding=True),
        )
        rows = db.execute(stmt, {"user_ids": ids, "actions": list(_LOGIN_ACTIONS)}).mappings().all()
        for row in rows:
            actor_id = row.get("actor_id")
            last_login = _coerce_datetime(row.get("last_login"))
            if actor_id is None or last_login is None:
                continue
            results[str(actor_id)] = last_login
    except Exception:
        results = {}

    missing = [str(user_id) for user_id in ids if str(user_id) not in results]
    if not missing:
        return results

    try:
        rows = (
            db.query(
                models.SessionToken.user_id,
                func.max(func.coalesce(models.SessionToken.last_seen_at, models.SessionToken.created_at)).label("last_login"),
            )
            .filter(models.SessionToken.user_id.in_(missing))
            .group_by(models.SessionToken.user_id)
            .all()
        )
        for row in rows:
            user_id = getattr(row, "user_id", None)
            last_login = _coerce_datetime(getattr(row, "last_login", None))
            if user_id is None or last_login is None:
                continue
            results[str(user_id)] = last_login
    except Exception:
        return results

    return results
