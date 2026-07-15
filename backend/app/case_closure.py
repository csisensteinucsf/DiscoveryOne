import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

from sqlalchemy import func

from . import models
from .app_branding import app_team_name, branded_subject
from .database import SessionLocal
from .emailer import mail_provider_ready, send_email
from .notifications import _app_base_url
from .runtime_paths import runtime_file
from .system_settings import load_system_settings

_CLOSURE_SCHEDULER_STARTED = False
_CLOSURE_LOCK_FD: Optional[int] = None

CASE_CLOSURE_LOCK_FILE = os.getenv("CASE_CLOSURE_LOCK_FILE", runtime_file("ediscovery_case_closure.lock"))


def _case_closure_settings() -> dict:
    try:
        settings = load_system_settings().get("case_closure") or {}
    except Exception:
        settings = {}
    return settings if isinstance(settings, dict) else {}


def _bounded_int(value, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _setting_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    settings = _case_closure_settings()
    return _bounded_int(settings.get(name), default, minimum=minimum, maximum=maximum)


def case_closure_default_nag_days() -> int:
    return _setting_int("default_nag_days", 180, minimum=1, maximum=3650)


def case_closure_loop_seconds() -> int:
    return _setting_int("loop_seconds", 3600, minimum=300, maximum=86400)


def case_closure_batch_size() -> int:
    return _setting_int("batch_size", 25, minimum=1, maximum=500)


def _acquire_closure_scheduler_lock() -> bool:
    global _CLOSURE_LOCK_FD
    lock_path = (CASE_CLOSURE_LOCK_FILE or "").strip()
    if not lock_path or fcntl is None:
        return True
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return True
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _CLOSURE_LOCK_FD = fd
        return True
    except (BlockingIOError, OSError):
        try:
            os.close(fd)
        except OSError:
            pass
        return False


def _eligible_cases(db):
    """
    Return up to the configured batch size whose reminder interval has elapsed.
    Uses the per-case closure_nag_days when set; otherwise falls back to the default.
    """
    candidates = (
        db.query(models.Case)
        .filter(models.Case.closed.is_(False))
        .filter(func.coalesce(func.trim(models.Case.requestor), "") != "")
        .order_by(models.Case.last_closure_nag_at.asc().nullsfirst(), models.Case.created_at.asc())
        .limit(case_closure_batch_size() * 4)
        .all()
    )
    now = datetime.now(timezone.utc)
    default_days = case_closure_default_nag_days()
    batch_size = case_closure_batch_size()
    due = []
    for case in candidates:
        raw_days = getattr(case, "closure_nag_days", None)
        try:
            days = int(raw_days) if raw_days is not None else default_days
        except Exception:
            days = default_days
        if days <= 0:
            days = default_days
        created = getattr(case, "created_at", None) or now
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created + timedelta(days=days) > now:
            continue  # too new for a reminder
        last = getattr(case, "last_closure_nag_at", None)
        if last is None:
            due.append(case)
        else:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last + timedelta(days=days) <= now:
                due.append(case)
        if len(due) >= batch_size:
            break
    return due


def _send_closure_prompt(case: models.Case, base_url: str) -> None:
    recipient = (getattr(case, "requestor", "") or "").strip()
    if not recipient:
        return
    case_id = getattr(case, "id", None)
    label = getattr(case, "name", None) or (f"Case #{case_id}" if case_id else "this case")
    legal = getattr(case, "legal_case_name", None)
    analyst = getattr(case, "analyst", None)
    analyst_name = ""
    analyst_email = ""
    if analyst:
        first = (getattr(analyst, "first_name", "") or "").strip()
        last = (getattr(analyst, "last_name", "") or "").strip()
        analyst_name = " ".join(part for part in (first, last) if part) or getattr(analyst, "username", "") or ""
        analyst_email = (getattr(analyst, "email", "") or "").strip()
    link = f"{base_url}/cases/{case_id}?action=request_close" if case_id else base_url
    subject_label = f"{label} - {legal}" if legal else label
    subject = branded_subject(f"Can we close {subject_label}?")
    details = []
    if legal:
        details.append(f"Legal Case: {legal}")
    if analyst_name or analyst_email:
        reach = " ".join(part for part in (analyst_name, analyst_email) if part)
        details.append(f"Analyst: {reach}")
    meta_block = "\n".join(details)
    body_parts = [
        "Hello,",
        "",
        f"We are checking in on {label}. If this case can be closed, please confirm by visiting:",
        link,
        "",
        "You will be asked to sign in and then you can submit the closure request. If the case should remain open, no action is required.",
    ]
    if meta_block:
        body_parts.extend(["", meta_block, "Please reach out to the assigned analyst if you have questions."])
    body_parts.extend(["", "Thank you,", app_team_name()])
    body = "\n".join(body_parts)
    send_email(recipients=[recipient], subject=subject, body=body)


def _process_closure_prompts() -> None:
    db = SessionLocal()
    try:
        if not mail_provider_ready():
            return
        try:
            base_url = _app_base_url()
        except Exception as exc:
            print(f"[case closure] base URL not configured: {exc}")
            return

        cases = _eligible_cases(db)
        if not cases:
            return
        now = datetime.now(timezone.utc)
        for case in cases:
            try:
                _send_closure_prompt(case, base_url)
                case.last_closure_nag_at = now
            except Exception as exc:
                print(f"[case closure] failed to send prompt for case {getattr(case, 'id', '?')}: {exc}")
        db.commit()
    finally:
        db.close()


def start_case_closure_scheduler() -> None:
    global _CLOSURE_SCHEDULER_STARTED
    if _CLOSURE_SCHEDULER_STARTED:
        return
    if not _acquire_closure_scheduler_lock():
        print("[case closure] another process holds the scheduler lock; skipping start")
        return
    _CLOSURE_SCHEDULER_STARTED = True

    def _worker():
        while True:
            try:
                _process_closure_prompts()
            except Exception as exc:  # pragma: no cover - best-effort background worker
                print(f"[case closure] worker failure: {exc}")
            time.sleep(case_closure_loop_seconds())

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


