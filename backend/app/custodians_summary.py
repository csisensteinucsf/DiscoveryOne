from typing import Optional, Dict, Any, Tuple, List, Set
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import or_, func, literal
from .database import get_db
from . import models
from .auth import current_user as get_current_user
from .permissions import (
    get_visible_case_ids,
    is_requestor,
    is_tester,
    is_tech,
    get_requestor_allowed_emails,
    get_tech_visible_case_ids,
    ensure_not_requestor,
)
from .audit import log_event

router = APIRouter(prefix="/api/custodians", tags=["custodians"])


class DirectoryCustodianInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)


class DirectoryCustodianBatch(BaseModel):
    custodians: List[DirectoryCustodianInput] = Field(min_length=1, max_length=500)


def _normalize_directory_email(value: str) -> str:
    email = (value or "").strip().lower()
    if email.count("@") != 1 or " " in email:
        raise HTTPException(status_code=422, detail=f"Invalid custodian email: {value}")
    local, domain = email.split("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise HTTPException(status_code=422, detail=f"Invalid custodian email: {value}")
    return email


def _custodian_key(name: str, email: Optional[str]) -> Tuple[str, str]:
    email_key = (email or "").strip().lower()
    if email_key:
        return ("email", email_key)
    return ("name", (name or "").strip().lower())


def _normalize_person_label(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    out = []
    for ch in text:
        if ch.isalnum() or ch == "@":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _custodian_matches_claimant(*, claimant: Optional[str], name: Optional[str], email: Optional[str]) -> bool:
    claim = _normalize_person_label(claimant)
    if not claim or claim in {"na", "n/a", "n a"}:
        return False
    email_norm = _normalize_person_label(email)
    if "@" in claim and email_norm and email_norm == claim:
        return True
    name_norm = _normalize_person_label(name)
    if not name_norm:
        return False
    if name_norm == claim:
        return True
    if len(claim) >= 4 and (claim in name_norm or name_norm in claim):
        return True
    return False


def _is_separated(custodian: models.Custodian) -> bool:
    status = (getattr(custodian, "employment_status", None) or "").strip().lower()
    if status.startswith("separated"):
        return True
    end_date = (getattr(custodian, "employment_end_date", None) or "").strip()
    if not end_date:
        return False
    try:
        ts = datetime.fromisoformat(end_date).date()
    except Exception:
        try:
            ts = datetime.strptime(end_date[:10], "%Y-%m-%d").date()
        except Exception:
            return False
    return ts <= datetime.now(timezone.utc).date()


def _visible_case_ids(db: Session, actor: Optional[models.User]) -> Optional[Set[int]]:
    return get_visible_case_ids(actor, db)


def _filter_by_case_ids(query, column, case_ids: Optional[Set[int]]):
    if case_ids is None:
        return query
    if not case_ids:
        return query.filter(literal(False))
    return query.filter(column.in_(case_ids))


def _snapshot_score(custodian: models.Custodian) -> int:
    fields = [
        getattr(custodian, "employee_id", None),
        getattr(custodian, "person_department_id", None),
        getattr(custodian, "person_department", None),
        getattr(custodian, "person_title", None),
        getattr(custodian, "employment_end_date", None),
    ]
    score = sum(1 for value in fields if bool((value or "").strip() if isinstance(value, str) else value is not None))
    if getattr(custodian, "person_lookup_last_at", None):
        score += 100
    return score


def _apply_snapshot(bucket: Dict[str, Any], custodian: models.Custodian) -> None:
    score = _snapshot_score(custodian)
    if score < bucket.get("_snapshot_score", -1):
        return
    employee_id = getattr(custodian, "employee_id", None)
    bucket["_snapshot_score"] = score
    bucket["employment_end_date"] = getattr(custodian, "employment_end_date", None)
    bucket["employment_status"] = getattr(custodian, "employment_status", None)
    bucket["external_id"] = employee_id
    bucket["employee_id"] = employee_id
    bucket["first_name"] = getattr(custodian, "person_first_name", None)
    bucket["last_name"] = getattr(custodian, "person_last_name", None)
    bucket["department_id"] = getattr(custodian, "person_department_id", None)
    bucket["department"] = getattr(custodian, "person_department", None)
    bucket["title"] = getattr(custodian, "person_title", None)
    bucket["current_employee"] = getattr(custodian, "person_current_employee", None)
    bucket["person_lookup_last_at"] = getattr(custodian, "person_lookup_last_at", None)


def _latest_consent_status_by_custodian(db: Session, custodians: List[models.Custodian]) -> Dict[Tuple[int, int], Dict[str, Any]]:
    custodian_ids = [int(c.id) for c in custodians if getattr(c, "id", None)]
    if not custodian_ids:
        return {}
    rows = (
        db.query(models.CaseConsent)
        .filter(models.CaseConsent.custodian_id.in_(custodian_ids))
        .order_by(models.CaseConsent.id.desc())
        .all()
    )
    latest: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for consent in rows:
        case_id = int(getattr(consent, "case_id", 0) or 0)
        custodian_id = int(getattr(consent, "custodian_id", 0) or 0)
        if not case_id or not custodian_id:
            continue
        key = (case_id, custodian_id)
        if key in latest:
            continue
        latest[key] = {
            "status": getattr(consent, "status", None),
            "sent_at": getattr(consent, "sent_at", None),
            "completed_at": getattr(consent, "completed_at", None),
            "envelope_id": getattr(consent, "envelope_id", None),
            "source": "docusign",
        }
    return latest


def _case_consent_ref(
    custodian: models.Custodian,
    consent_lookup: Dict[Tuple[int, int], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    case_id = int(getattr(custodian, "case_id", 0) or 0)
    custodian_id = int(getattr(custodian, "id", 0) or 0)
    envelope = consent_lookup.get((case_id, custodian_id)) if case_id and custodian_id else None
    custodian_status = (getattr(custodian, "consent_status", None) or "not sent").strip() or "not sent"
    status = (envelope or {}).get("status") or custodian_status
    status_norm = str(status or "").strip().lower()
    if status_norm in {"", "not sent", "none"}:
        return None
    ref = {
        "status": status,
        "custodian_status": custodian_status,
        "source": "docusign" if envelope else "custodian",
        "sent_at": None,
        "completed_at": None,
    }
    if envelope:
        sent_at = envelope.get("sent_at")
        completed_at = envelope.get("completed_at")
        ref["sent_at"] = sent_at.isoformat() if sent_at else None
        ref["completed_at"] = completed_at.isoformat() if completed_at else None
    return ref


@router.get("", summary="List custodians across all cases")
def list_custodians(
    q: Optional[str] = Query(None, description="Search name/email/case (case-insensitive)"),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    case_ids = _visible_case_ids(db, actor)
    query = (
        db.query(
            models.Custodian,
            models.Case.id.label("case_id"),
            models.Case.name.label("case_name"),
            models.Case.closed.label("case_closed"),
            models.Case.claimant.label("case_claimant"),
        )
        .join(models.Case, models.Case.id == models.Custodian.case_id)
    )

    query = _filter_by_case_ids(query, models.Case.id, case_ids)

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.Custodian.name.ilike(like),
                models.Custodian.email.ilike(like),
                models.Case.name.ilike(like),
                models.Custodian.person_department.ilike(like),
                models.Custodian.person_title.ilike(like),
                models.Custodian.employee_id.ilike(like),
            )
        )

    rows = query.all()

    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if not (is_requestor(actor) or is_tech(actor) or is_tester(actor)):
        directory_query = db.query(models.CustodianDirectoryEntry)
        if q:
            like = f"%{q.strip()}%"
            directory_query = directory_query.filter(or_(
                models.CustodianDirectoryEntry.name.ilike(like),
                models.CustodianDirectoryEntry.email.ilike(like),
            ))
        for entry in directory_query.all():
            key = _custodian_key(entry.name, entry.email)
            grouped[key] = {
                "directory_id": entry.id,
                "name": entry.name,
                "email": entry.email,
                "open_cases": [],
                "closed_cases": [],
                "active_holds": False,
                "is_separated": False,
                "employment_end_date": None,
                "employment_status": None,
                "external_id": None,
                "employee_id": None,
                "first_name": None,
                "last_name": None,
                "department_id": None,
                "department": None,
                "title": None,
                "current_employee": None,
                "person_lookup_last_at": None,
                "_snapshot_score": -1,
            }
    for cust, case_id, case_name, case_closed, case_claimant in rows:
        key = _custodian_key(cust.name or "", cust.email)
        bucket = grouped.get(key)
        if not bucket:
            bucket = {
                "name": cust.name,
                "email": cust.email,
                "open_cases": [],
                "closed_cases": [],
                "active_holds": False,
                "is_separated": False,
                "employment_end_date": None,
                "employment_status": None,
                "external_id": None,
        "employee_id": None,
                "first_name": None,
                "last_name": None,
                "department_id": None,
                "department": None,
                "title": None,
                "current_employee": None,
                "person_lookup_last_at": None,
                "_snapshot_score": -1,
            }
            grouped[key] = bucket

        is_claimant = _custodian_matches_claimant(
            claimant=case_claimant,
            name=getattr(cust, "name", None),
            email=getattr(cust, "email", None),
        )
        case_ref = {
            "id": case_id,
            "name": case_name,
            "closed": bool(case_closed),
            "is_claimant": bool(is_claimant),
        }
        if case_closed:
            bucket["closed_cases"].append(case_ref)
        else:
            bucket["open_cases"].append(case_ref)

        if any([
            cust.holds_email,
            cust.holds_onedrive,
            cust.holds_box,
            cust.holds_slack,
            cust.holds_rubrik_restore,
        ]):
            bucket["active_holds"] = True

        if _is_separated(cust):
            bucket["is_separated"] = True

        _apply_snapshot(bucket, cust)

    out: List[Dict[str, Any]] = list(grouped.values())
    out.sort(key=lambda x: (x["name"] or "", x["email"] or ""))
    for item in out:
        item["open_cases"] = [{"id": c["id"], "name": c["name"], "is_claimant": bool(c.get("is_claimant"))} for c in item["open_cases"]]
        item["closed_cases"] = [{"id": c["id"], "name": c["name"], "is_claimant": bool(c.get("is_claimant"))} for c in item["closed_cases"]]
        item.pop("_snapshot_score", None)
    return out


@router.post("", summary="Add custodians to the reusable D1 directory")
def add_directory_custodians(
    payload: DirectoryCustodianBatch,
    request: Request,
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    ensure_not_requestor(actor)
    normalized = []
    seen = set()
    for item in payload.custodians:
        name = item.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Custodian name is required")
        email = _normalize_directory_email(item.email)
        if email in seen:
            continue
        seen.add(email)
        normalized.append((name, email))

    existing_rows = (
        db.query(func.lower(models.CustodianDirectoryEntry.email))
        .filter(func.lower(models.CustodianDirectoryEntry.email).in_([email for _, email in normalized]))
        .all()
        if normalized
        else []
    )
    existing = {value for (value,) in existing_rows}
    created = []
    for name, email in normalized:
        if email in existing:
            continue
        entry = models.CustodianDirectoryEntry(name=name, email=email)
        db.add(entry)
        db.flush()
        created.append({"directory_id": entry.id, "name": entry.name, "email": entry.email})
        log_event(
            db,
            action="custodian_directory_create",
            actor_id=getattr(actor, "id", None),
            target_type="custodian_directory",
            target_id=entry.id,
            details={"name": entry.name, "email": entry.email},
            request=request,
        )
    db.commit()
    return {
        "created": created,
        "created_count": len(created),
        "duplicate_count": len(payload.custodians) - len(created),
    }


@router.get("/detail", summary="Get custodian detail by email or name")
def custodian_detail(
    email: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    if not email and not name:
        raise HTTPException(status_code=400, detail="Provide email or name")

    q = db.query(
        models.Custodian,
        models.Case.id.label("case_id"),
        models.Case.name.label("case_name"),
        models.Case.closed.label("case_closed"),
        models.Case.claimant.label("case_claimant"),
    ).join(models.Case, models.Case.id == models.Custodian.case_id)

    case_ids = _visible_case_ids(db, actor)
    q = _filter_by_case_ids(q, models.Case.id, case_ids)

    if email:
        q = q.filter(models.Custodian.email.ilike(email.strip()))
    else:
        q = q.filter(models.Custodian.name.ilike(name.strip()))

    rows = q.all()
    if not rows:
        raise HTTPException(status_code=404, detail="Custodian not found")
    consent_lookup = _latest_consent_status_by_custodian(db, [row[0] for row in rows])

    first = rows[0][0]
    detail = {
        "name": first.name,
        "email": first.email,
        "active_holds": False,
        "is_separated": False,
        "employment_end_date": None,
        "employment_status": None,
        "external_id": None,
        "employee_id": None,
        "first_name": None,
        "last_name": None,
        "department_id": None,
        "department": None,
        "title": None,
        "current_employee": None,
        "person_lookup_last_at": None,
        "holds": {
            "email": False,
            "onedrive": False,
            "box": False,
            "slack": False,
            "rubrik_restore": False,
        },
        "cases": [],
        "ntp_statuses": [],
        "consent_statuses": [],
        "_snapshot_score": -1,
    }
    for cust, case_id, case_name, case_closed, case_claimant in rows:
        detail["cases"].append({
            "id": case_id,
            "name": case_name,
            "closed": bool(case_closed),
            "is_claimant": bool(_custodian_matches_claimant(
                claimant=case_claimant,
                name=getattr(cust, "name", None),
                email=getattr(cust, "email", None),
            )),
            "consent": _case_consent_ref(cust, consent_lookup),
        })
        if any([
            cust.holds_email,
            cust.holds_onedrive,
            cust.holds_box,
            cust.holds_slack,
            cust.holds_rubrik_restore,
        ]):
            detail["active_holds"] = True
        detail["holds"]["email"] = detail["holds"]["email"] or bool(cust.holds_email)
        detail["holds"]["onedrive"] = detail["holds"]["onedrive"] or bool(cust.holds_onedrive)
        detail["holds"]["box"] = detail["holds"]["box"] or bool(cust.holds_box)
        detail["holds"]["slack"] = detail["holds"]["slack"] or bool(cust.holds_slack)
        detail["holds"]["rubrik_restore"] = detail["holds"]["rubrik_restore"] or bool(cust.holds_rubrik_restore)
        if getattr(cust, "ntp_status", None):
            detail["ntp_statuses"].append(cust.ntp_status)
        if getattr(cust, "consent_status", None):
            detail["consent_statuses"].append(cust.consent_status)
        if _is_separated(cust):
            detail["is_separated"] = True
        _apply_snapshot(detail, cust)

    detail["ntp_statuses"] = sorted(set(detail["ntp_statuses"]))
    detail["consent_statuses"] = sorted(set(detail["consent_statuses"]))
    detail.pop("_snapshot_score", None)
    return detail
