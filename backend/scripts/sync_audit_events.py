import argparse
from typing import Iterable

from sqlalchemy import text

from app.audit import (
    _audit_event_exists,
    _insert_audit_event,
    _iter_audit_log_paths,
    _parse_audit_line,
    _read_audit_lines,
)
from app.database import SessionLocal


def _iter_matching_events(actions: set[str], target_ids: set[int]) -> Iterable[dict]:
    for path in _iter_audit_log_paths(max_files=None):
        try:
            iterator = _read_audit_lines(path)
        except Exception as exc:
            print(f"[audit-sync] skip unreadable path={path} error={exc}")
            continue
        for line in iterator:
            if actions and not any(action in line for action in actions):
                continue
            parsed = _parse_audit_line(line)
            if not parsed:
                continue
            action = str(parsed.get("action") or "")
            if actions and action not in actions:
                continue
            target_id = parsed.get("target_id")
            if target_ids and target_id not in target_ids:
                continue
            yield parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill selected audit.log actions into audit_events.")
    parser.add_argument(
        "--action",
        dest="actions",
        action="append",
        default=["registration_request_delete"],
        help="Audit action to backfill. Repeat for multiple actions.",
    )
    parser.add_argument(
        "--target-id",
        dest="target_ids",
        type=int,
        action="append",
        default=[],
        help="Optional target_id filter. Repeat for multiple ids.",
    )
    args = parser.parse_args()

    actions = {str(x).strip() for x in (args.actions or []) if str(x).strip()}
    target_ids = {int(x) for x in (args.target_ids or []) if int(x) > 0}

    db = SessionLocal()
    summary = {
        "scanned": 0,
        "matched": 0,
        "inserted": 0,
        "skipped": 0,
        "failed": 0,
    }
    try:
        for parsed in _iter_matching_events(actions, target_ids):
            summary["matched"] += 1
            event_hash = parsed.get("event_hash")
            try:
                exists = False
                if event_hash:
                    exists = bool(
                        db.execute(
                            text("SELECT 1 FROM audit_events WHERE event_hash = :event_hash LIMIT 1"),
                            {"event_hash": event_hash},
                        ).scalar()
                    )
                if not exists:
                    exists = _audit_event_exists(
                        db,
                        created_at=parsed["created_at"],
                        action=parsed["action"],
                        actor_id=parsed["actor_id"],
                        target_type=parsed["target_type"],
                        target_id=parsed["target_id"],
                        details=parsed["details"],
                        request_ip=parsed["request_ip"],
                        user_agent=parsed["user_agent"],
                    )
                if exists:
                    summary["skipped"] += 1
                    continue
                _insert_audit_event(
                    db,
                    created_at=parsed["created_at"],
                    action=parsed["action"],
                    actor_id=parsed["actor_id"],
                    target_type=parsed["target_type"],
                    target_id=parsed["target_id"],
                    details=parsed["details"],
                    request_ip=parsed["request_ip"],
                    user_agent=parsed["user_agent"],
                    event_hash=event_hash,
                )
                summary["inserted"] += 1
            except Exception as exc:
                summary["failed"] += 1
                try:
                    db.rollback()
                except Exception:
                    pass
                print(
                    f"[audit-sync] failed action={parsed.get('action')} target_id={parsed.get('target_id')} error={exc}"
                )
        print(summary)
    finally:
        db.close()


if __name__ == "__main__":
    main()
