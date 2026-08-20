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
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    campus: str = Field(min_length=1, max_length=255)
    department: Optional[str] = Field(default=None, max_length=255)
    employee_id: Optional[str] = Field(default=None, max_length=128)
    title: Optional[str] = Field(default=None, max_length=255)
    employment_status: Optional[str] = Field(default=None, max_length=128)

    @property
    def name(self) -> str:
        return f"{self.first_name.strip()} {self.last_name.strip()}".strip()


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
    bucket["campus"] = getattr(custodian, "campus", None)
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
                models.Custodian.campus.ilike(like),
                models.Custodian.person_first_name.ilike(like),
                models.Custodian.person_last_name.ilike(like),
                models.Custodian.employment_status.ilike(like),
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
                models.CustodianDirectoryEntry.first_name.ilike(like),
                models.CustodianDirectoryEntry.last_name.ilike(like),
                models.CustodianDirectoryEntry.campus.ilike(like),
                models.CustodianDirectoryEntry.department.ilike(like),
                models.CustodianDirectoryEntry.employee_id.ilike(like),
                models.CustodianDirectoryEntry.title.ilike(like),
                models.CustodianDirectoryEntry.employment_status.ilike(like),
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
                "employment_status": entry.employment_status,
                "external_id": entry.employee_id,
                "employee_id": entry.employee_id,
                "first_name": entry.first_name,
                "last_name": entry.last_name,
                "department_id": None,
                "department": entry.department,
                "title": entry.title,
                "campus": entry.campus,
                "current_employee": None,
                "person_lookup_last_at": None,
                "_snapshot_score": 50,
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
                "campus": None,
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
        first_name = item.first_name.strip()
        last_name = item.last_name.strip()
        campus = item.campus.strip()
        if not first_name or not last_name or not campus:
            raise HTTPException(status_code=422, detail="First name, last name, email, and campus are required")
        email = _normalize_directory_email(item.email)
        if email in seen:
            continue
        seen.add(email)
        normalized.append((item, email))

    existing_rows = (
        db.query(func.lower(models.CustodianDirectoryEntry.email))
        .filter(func.lower(models.CustodianDirectoryEntry.email).in_([email for _, email in normalized]))
        .all()
        if normalized
        else []
    )
    existing = {value for (value,) in existing_rows}
    created = []
    for item, email in normalized:
        if email in existing:
            continue
        entry = models.CustodianDirectoryEntry(
            name=item.name,
            email=email,
            first_name=item.first_name.strip(),
            last_name=item.last_name.strip(),
            campus=item.campus.strip(),
            department=(item.department or "").strip() or None,
            employee_id=(item.employee_id or "").strip() or None,
            title=(item.title or "").strip() or None,
            employment_status=(item.employment_status or "").strip() or None,
        )
        db.add(entry)
        db.flush()
        created.append({
            "directory_id": entry.id,
            "name": entry.name,
            "email": entry.email,
            "first_name": entry.first_name,
            "last_name": entry.last_name,
            "campus": entry.campus,
            "department": entry.department,
            "employee_id": entry.employee_id,
            "title": entry.title,
            "employment_status": entry.employment_status,
        })
        log_event(
            db,
            action="custodian_directory_create",
            actor_id=getattr(actor, "id", None),
            target_type="custodian_directory",
            target_id=entry.id,
            details={"name": entry.name, "email": entry.email, "campus": entry.campus},
            request=request,
        )
    db.commit()
    return {
        "created": created,
        "created_count": len(created),
        "duplicate_count": len(payload.custodians) - len(created),
    }


@router.put("/profile", summary="Update a reusable custodian profile")
def update_custodian_profile(
    payload: DirectoryCustodianInput,
    request: Request,
    email: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    actor: models.User = Depends(get_current_user),
):
    if is_requestor(actor) or is_tech(actor) or is_tester(actor):
        raise HTTPException(status_code=403, detail="You do not have permission to edit custodian profiles")
    if not email and not name:
        raise HTTPException(status_code=400, detail="Provide the custodian email or name")

    directory_query = db.query(models.CustodianDirectoryEntry)
    if email:
        directory_query = directory_query.filter(func.lower(models.CustodianDirectoryEntry.email) == email.strip().lower())
    else:
        directory_query = directory_query.filter(func.lower(models.CustodianDirectoryEntry.name) == name.strip().lower())
    directory_entry = directory_query.first()

    case_query = db.query(models.Custodian)
    case_ids = _visible_case_ids(db, actor)
    case_query = _filter_by_case_ids(case_query, models.Custodian.case_id, case_ids)
    if email:
        case_query = case_query.filter(func.lower(models.Custodian.email) == email.strip().lower())
    else:
        case_query = case_query.filter(func.lower(models.Custodian.name) == name.strip().lower())
    case_custodians = case_query.all()

    if directory_entry is None and not case_custodians:
        raise HTTPException(status_code=404, detail="Custodian not found")

    normalized_email = _normalize_directory_email(payload.email)
    first_name = payload.first_name.strip()
    last_name = payload.last_name.strip()
    campus = payload.campus.strip()
    if not first_name or not last_name or not campus:
        raise HTTPException(status_code=422, detail="First name, last name, email, and campus are required")
    full_name = payload.name

    duplicate_directory = (
        db.query(models.CustodianDirectoryEntry)
        .filter(func.lower(models.CustodianDirectoryEntry.email) == normalized_email)
    )
    if directory_entry is not None:
        duplicate_directory = duplicate_directory.filter(models.CustodianDirectoryEntry.id != directory_entry.id)
    if duplicate_directory.first() is not None:
        raise HTTPException(status_code=409, detail="Another custodian already uses that email address")

    source = directory_entry or case_custodians[0]
    before = {
        "first_name": getattr(source, "first_name", None) or getattr(source, "person_first_name", None),
        "last_name": getattr(source, "last_name", None) or getattr(source, "person_last_name", None),
        "email": getattr(source, "email", None),
        "campus": getattr(source, "campus", None),
        "department": getattr(source, "department", None) or getattr(source, "person_department", None),
        "employee_id": getattr(source, "employee_id", None),
        "title": getattr(source, "title", None) or getattr(source, "person_title", None),
        "employment_status": getattr(source, "employment_status", None),
    }
    after = {
        "first_name": first_name,
        "last_name": last_name,
        "email": normalized_email,
        "campus": campus,
        "department": (payload.department or "").strip() or None,
        "employee_id": (payload.employee_id or "").strip() or None,
        "title": (payload.title or "").strip() or None,
        "employment_status": (payload.employment_status or "").strip() or None,
    }

    if directory_entry is None:
        directory_entry = models.CustodianDirectoryEntry()
        db.add(directory_entry)
    directory_entry.name = full_name
    directory_entry.email = normalized_email
    directory_entry.first_name = first_name
    directory_entry.last_name = last_name
    directory_entry.campus = campus
    directory_entry.department = after["department"]
    directory_entry.employee_id = after["employee_id"]
    directory_entry.title = after["title"]
    directory_entry.employment_status = after["employment_status"]
    db.flush()

    for custodian in case_custodians:
        custodian.name = full_name
        custodian.email = normalized_email
        custodian.campus = campus
        custodian.person_first_name = first_name
        custodian.person_last_name = last_name
        custodian.person_department = after["department"]
        custodian.employee_id = after["employee_id"]
        custodian.person_title = after["title"]
        custodian.employment_status = after["employment_status"]
        db.add(custodian)

    changes = {
        field: {"old": before.get(field), "new": value}
        for field, value in after.items()
        if before.get(field) != value
    }
    log_event(
        db,
        action="custodian_directory_update",
        actor_id=getattr(actor, "id", None),
        target_type="custodian_directory",
        target_id=directory_entry.id,
        details={
            "custodian_name": full_name,
            "custodian_email": normalized_email,
            "affected_case_ids": sorted({int(item.case_id) for item in case_custodians}),
            "changes": changes,
        },
        request=request,
    )
    db.commit()
    return custodian_detail(email=normalized_email, name=None, db=db, actor=actor)
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
    directory_entry = None
    if not (is_requestor(actor) or is_tech(actor) or is_tester(actor)):
        directory_query = db.query(models.CustodianDirectoryEntry)
        if email:
            directory_query = directory_query.filter(models.CustodianDirectoryEntry.email.ilike(email.strip()))
        else:
            directory_query = directory_query.filter(models.CustodianDirectoryEntry.name.ilike(name.strip()))
        directory_entry = directory_query.first()
    if not rows and directory_entry is None:
        raise HTTPException(status_code=404, detail="Custodian not found")
    consent_lookup = _latest_consent_status_by_custodian(db, [row[0] for row in rows])

    first = rows[0][0] if rows else directory_entry
    detail = {
        "directory_id": getattr(directory_entry, "id", None),
        "can_edit": not (is_requestor(actor) or is_tech(actor) or is_tester(actor)),
        "name": first.name,
        "email": first.email,
        "active_holds": False,
        "is_separated": False,
        "employment_end_date": None,
        "employment_status": getattr(directory_entry, "employment_status", None),
        "external_id": getattr(directory_entry, "employee_id", None),
        "employee_id": getattr(directory_entry, "employee_id", None),
        "first_name": getattr(directory_entry, "first_name", None),
        "last_name": getattr(directory_entry, "last_name", None),
        "department_id": None,
        "department": getattr(directory_entry, "department", None),
        "title": getattr(directory_entry, "title", None),
        "campus": getattr(directory_entry, "campus", None),
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
        "_snapshot_score": 50 if directory_entry is not None else -1,
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
