"""Dashboard row visibility helpers."""

from typing import Optional

from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from . import models
from .permissions import get_visible_case_ids


def _visible_case_ids(db: Session, actor: models.User) -> Optional[set[int]]:
    return get_visible_case_ids(actor, db)


def _filter_case_ids(query, column, case_ids: Optional[set[int]]):
    if case_ids is None:
        return query
    if not case_ids:
        return query.filter(literal(False))  # pragma: no cover - SQL-level false
    return query.filter(column.in_(list(case_ids)))


