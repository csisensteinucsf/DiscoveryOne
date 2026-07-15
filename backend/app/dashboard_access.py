"""Dashboard row visibility helpers."""

from typing import Optional

from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from . import models
from .permissions import (
    get_requestor_allowed_emails,
    get_tech_visible_case_ids,
    is_requestor,
    is_tester,
    is_tech,
)


def _visible_case_ids(db: Session, actor: models.User) -> Optional[set[int]]:
    if is_requestor(actor):
        allowed = get_requestor_allowed_emails(actor, db)
        if not allowed:
            return set()
        allowed_list = list(allowed)
        q = (
            db.query(models.Case.id)
            .outerjoin(models.CaseRequestor, models.CaseRequestor.case_id == models.Case.id)
            .filter(
                or_(
                    func.lower(models.Case.requestor).in_(allowed_list),
                    func.lower(models.CaseRequestor.email).in_(allowed_list),
                    models.CaseRequestor.user_id == actor.id,
                )
            )
        )
        return {row.id for row in q.all()}
    if is_tech(actor):
        return get_tech_visible_case_ids(actor, db)
    if is_tester(actor):
        rows = db.query(models.Case.id).filter(func.lower(models.Case.name).like("%-test")).all()
        return {row.id for row in rows}
    return None


def _filter_case_ids(query, column, case_ids: Optional[set[int]]):
    if case_ids is None:
        return query
    if not case_ids:
        return query.filter(literal(False))  # pragma: no cover - SQL-level false
    return query.filter(column.in_(list(case_ids)))


