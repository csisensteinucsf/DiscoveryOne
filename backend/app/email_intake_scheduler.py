from __future__ import annotations

import logging
import threading
import time

from .database import SessionLocal
from .email_intake_graph import load_email_intake_settings
from .email_intake_service import poll_mailbox, retry_due_messages

logger = logging.getLogger(__name__)
_scheduler_started = False


def start_email_intake_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _worker() -> None:
        initial = load_email_intake_settings()
        if initial.startup_delay_seconds:
            time.sleep(initial.startup_delay_seconds)
        next_run = 0.0
        while True:
            settings = load_email_intake_settings()
            if not settings.ready:
                next_run = 0.0
                time.sleep(30.0)
                continue
            now = time.time()
            if now < next_run:
                time.sleep(min(10.0, next_run - now))
                continue
            db = SessionLocal()
            try:
                retry_due_messages(db)
                poll_mailbox(db, settings=settings)
            except Exception as exc:
                logger.exception("Email Intake scheduler iteration failed: %s", exc)
            finally:
                try:
                    db.close()
                except Exception:
                    logger.exception("Email Intake scheduler database close failed")
            refreshed = load_email_intake_settings()
            next_run = time.time() + refreshed.poll_interval_seconds

    thread = threading.Thread(
        target=_worker,
        daemon=True,
        name="email-intake-scheduler",
    )
    thread.start()