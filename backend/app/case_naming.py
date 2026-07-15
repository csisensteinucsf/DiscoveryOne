import importlib
import re
from datetime import date
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db
from .case_naming_config import normalize_case_naming_mode
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _case_naming_mode() -> str:
    try:
        settings = load_system_settings()
        raw = settings.get("case_naming") if isinstance(settings.get("case_naming"), dict) else {}
        return normalize_case_naming_mode(raw.get("mode"))
    except Exception:
        return normalize_case_naming_mode(None)


def _case_name_taken(db: Session, candidate: str, *, include_pending: bool = False) -> bool:
    if db.query(models.Case.id).filter(models.Case.name == candidate).first():
        return True
    if include_pending:
        return bool(
            db.query(models.CaseRequest.id)
            .filter(models.CaseRequest.status == "pending")
            .filter(models.CaseRequest.request_type == "new_case")
            .filter(models.CaseRequest.case_name == candidate)
            .first()
        )
    return False


def _unique_case_name(db: Session, base: str, *, include_pending: bool = False) -> str:
    cleaned = re.sub(r"\s+", " ", str(base or "").strip())[:220]
    if len(cleaned) < 2:
        raise HTTPException(status_code=422, detail="Case name must be at least 2 characters")
    if not _case_name_taken(db, cleaned, include_pending=include_pending):
        return cleaned
    idx = 2
    while idx < 10000:
        suffix = f"-{idx}"
        candidate = f"{cleaned[:255 - len(suffix)]}{suffix}"
        if not _case_name_taken(db, candidate, include_pending=include_pending):
            return candidate
        idx += 1
    raise HTTPException(status_code=409, detail="Unable to generate a unique case name")


def _next_created_date_case_name(db: Session, *, include_pending: bool = False) -> str:
    return _unique_case_name(db, date.today().isoformat(), include_pending=include_pending)


def _case_name_from_payload(db: Session, payload: schemas.CaseCreate) -> tuple[str, Optional[str]]:
    mode = _case_naming_mode()
    if mode == "legal_case_name":
        legal_name = (payload.legal_case_name or payload.name or "").strip()
        return _unique_case_name(db, legal_name), None
    if mode == "created_date":
        return _next_created_date_case_name(db), None
    name = (payload.name or "").strip()
    return _unique_case_name(db, name or "New Case"), payload.color

def _load_color_sequence_for_year(y: int):
    try:
        import importlib
        m = importlib.import_module("colors")
        for name in ("COLORS","YEAR_COLORS","COLOR_TABLE","COLOR_MAP"):
            if hasattr(m, name):
                tbl = getattr(m, name)
                if isinstance(tbl, dict):
                    if y in tbl and isinstance(tbl[y], (list, tuple)) and tbl[y]:
                        return list(tbl[y])
                if isinstance(tbl, (list, tuple)) and tbl:
                    return list(tbl)
        for prefix in ("C","Y"):
            attr = f"{prefix}{y}"
            if hasattr(m, attr):
                seq = getattr(m, attr)
                if isinstance(seq, (list, tuple)) and seq:
                    return list(seq)
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_naming.py:6238", exc)
    return ["Apple","Apricot","Auburn","Azure","Blue","Bronze","Burgundy","Cyan","Crimson","Copper","Coral",
            "Denim","Dandelion","Emerald","Eggplant","Fuchsia","Forest","Gold","Green","Grey","Honey","Hazel",
            "Indigo","Ivory","Jade","Jet","Khaki","Kiwi","Lavender","Lilac","Lime","Maroon","Mint","Magenta",
            "Navy","Nutmeg","Olive","Ochre","Orange","Purple","Pink","Plum","Pearl","Peach","Quartz","Red",
            "Rose","Ruby","Rust","Silver","Scarlet","Saffron","Tan","Taupe","Tea","Teal","Thistle","Topaz",
            "Turquoise","Tyrian","Umber","Violet","Vanilla","Wisteria","Wine","Xanthic","Yellow","Zaffre","Zinc"]

def _two_week_bucket_index(today: date, seq_len: int) -> int:
    start = date(today.year, 1, 1)
    days = (today - start).days
    return (days // 14) % max(seq_len, 1)

def _extract_year_and_color_from_name(name: str) -> Tuple[Optional[int], Optional[str]]:
    try:
        if not name or "-" not in name: return (None, None)
        year_str, color = name.split("-", 1)
        year = int(year_str.strip())
        color = color.strip()
        return (year, color if color else None)
    except Exception:
        return (None, None)

def _current_bucket_letter(today: date) -> str:
    idx = _two_week_bucket_index(today, 26)
    return chr(ord("A") + idx)

def _pool_for_letter(year: int, letter: str):
    letter = (letter or "").upper()[:1]
    try:
        m = importlib.import_module("colors")
        if hasattr(m, "color_pool_for_letter"):
            f = getattr(m, "color_pool_for_letter")
            try:
                pool = f(letter, year)
            except TypeError:
                pool = f(letter)
            if isinstance(pool, (list, tuple)) and pool:
                return [str(x) for x in pool if isinstance(x, str)]
    except Exception as exc:
        _debug_suppressed("suppressed exception in case_naming.py:6278", exc)
    seq = _load_color_sequence_for_year(year)
    bucket = [c for c in seq if isinstance(c, str) and c[:1].upper() == letter]
    return bucket or seq

@router.get("/suggest_name_core", summary="Suggest Name")
def suggest_case_name(db: Session = Depends(get_db), request: Request = None, legal_case_name: Optional[str] = Query(None)):
    mode = _case_naming_mode()
    if mode == "legal_case_name":
        legal_name = (legal_case_name or "").strip()
        return {"name": _unique_case_name(db, legal_name, include_pending=True) if legal_name else ""}
    if mode == "created_date":
        return {"name": _next_created_date_case_name(db, include_pending=True)}

    today = date.today()
    current_year = today.year

    try:
        letter = _current_bucket_letter(today)
        pool = _pool_for_letter(current_year, letter) or []
        pool = [str(c).strip() for c in pool if isinstance(c, str) and str(c).strip()]
        pool = sorted(pool, key=lambda s: s.casefold()) or pool
        if not pool:
            raise RuntimeError("Empty color pool")

        q = (db.query(models.Case)
               .filter(models.Case.name.like(f"{current_year}-%"))
               .filter(models.Case.color.isnot(None))
               .filter(func.upper(func.substr(models.Case.color, 1, 1)) == letter))
        if hasattr(models.Case, "created_at"):
            q = q.order_by(models.Case.created_at.desc())
        else:
            q = q.order_by(models.Case.id.desc())
        last_for_letter = q.first()

        start_idx = 0
        if last_for_letter and isinstance(last_for_letter.color, str):
            last_norm = last_for_letter.color.strip().casefold()
            for i, c in enumerate(pool):
                if c.casefold() == last_norm:
                    start_idx = (i + 1) % len(pool)
                    break

        used_names = set(
            n
            for (n,) in db.query(models.Case.name)
            .filter(models.Case.name.like(f"{current_year}-%")).all()
        )
        pending_names = (
            db.query(models.CaseRequest.case_name)
            .filter(models.CaseRequest.status == "pending")
            .filter(models.CaseRequest.request_type == "new_case")
            .all()
        )
        used_names.update(n for (n,) in pending_names if n)
        for off in range(len(pool)):
            idx = (start_idx + off) % len(pool)
            color = pool[idx]
            candidate = f"{current_year}-{color}"
            if candidate not in used_names:
                return {"name": candidate}

        base = f"{current_year}-{pool[start_idx] if pool else 'Blue'}"
        k = 2
        while f"{base}-{k}" in used_names:
            k += 1
        return {"name": f"{base}-{k}"}

    except Exception:
        rows = (db.query(models.Case.color, func.count(models.Case.id))
                  .filter(models.Case.name.like(f"{current_year}-%"))
                  .group_by(models.Case.color).all())
        counts = { (c or "").strip(): n for c, n in rows }
        COLORS = ["Blue","Green","Red","Yellow","Purple","Orange","Teal","Gray"]
        for c in sorted(COLORS, key=lambda x: counts.get(x, 0)):
            cand = f"{current_year}-{c}"
            exists = db.query(models.Case.id).filter(models.Case.name == cand).first()
            if not exists:
                return {"name": cand}
        base = f"{current_year}-{COLORS[0]}"
        k = 2
        while db.query(models.Case.id).filter(models.Case.name == f"{base}-{k}").first():
            k += 1
        return {"name": f"{base}-{k}"}

