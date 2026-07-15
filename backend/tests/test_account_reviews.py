from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import account_reviews, auth, models
from app.login_history import last_login_map


def _create_user(db_session, **overrides):
    role = overrides.pop("role", "analyst")
    email = overrides.pop("email", None)
    username = overrides.pop("username", email or f"{role}@example.com")
    user = models.User(
        username=username,
        email=email,
        first_name=overrides.pop("first_name", "Test"),
        last_name=overrides.pop("last_name", "User"),
        password_hash=overrides.pop("password_hash", "hashed"),
        is_admin=overrides.pop("is_admin", role == "sys_admin"),
        is_active=overrides.pop("is_active", True),
        role=role,
        local_auth_only=overrides.pop("local_auth_only", False),
        **overrides,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _session_local():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def _create_audit_events_table(db):
    db.execute(
        text(
            """
            CREATE TABLE audit_events (
              id INTEGER PRIMARY KEY,
              actor_id INTEGER,
              action TEXT NOT NULL,
              target_type TEXT,
              target_id INTEGER,
              details TEXT,
              request_ip TEXT,
              user_agent TEXT,
              created_at TIMESTAMP NOT NULL,
              event_hash TEXT
            )
            """
        )
    )
    db.commit()


def test_last_login_map_prefers_audit_events_over_live_sessions():
    engine, SessionLocal = _session_local()
    try:
        with SessionLocal() as db:
            user = _create_user(db, role="analyst", email="analyst@example.com")
            _create_audit_events_table(db)
            db.execute(
                text(
                    "INSERT INTO audit_events (id, actor_id, action, created_at) VALUES (1, :actor_id, 'login', :created_at)"
                ),
                {"actor_id": user.id, "created_at": datetime(2026, 2, 5, 14, 15, tzinfo=timezone.utc)},
            )
            db.commit()

            result = last_login_map(db, [user.id])

            assert result[str(user.id)].strftime("%Y-%m-%d %H:%M") == "2026-02-05 14:15"
    finally:
        engine.dispose()


def test_send_account_review_if_due_sends_inventory_email(monkeypatch):
    engine, SessionLocal = _session_local()
    try:
        with SessionLocal() as db:
            _create_audit_events_table(db)
            _create_user(db, role="sys_admin", email="admin@example.com", first_name="Admin", last_name="User")
            analyst = _create_user(
                db,
                role="analyst",
                email="analyst@example.com",
                first_name="Avery",
                last_name="Analyst",
                local_auth_only=True,
            )
            db.execute(
                text(
                    "INSERT INTO audit_events (id, actor_id, action, created_at) VALUES (1, :actor_id, 'login', :created_at)"
                ),
                {"actor_id": analyst.id, "created_at": datetime(2026, 1, 2, 15, 30, tzinfo=timezone.utc)},
            )
            db.commit()

        sent = []
        saved = {}
        audited = []
        monkeypatch.setattr(account_reviews, "SessionLocal", SessionLocal)
        monkeypatch.setattr(account_reviews, "mail_provider_ready", lambda: True)
        monkeypatch.setattr(account_reviews, "send_email", lambda **kwargs: sent.append(kwargs))
        monkeypatch.setattr(account_reviews, "log_event", lambda *args, **kwargs: audited.append(kwargs))
        monkeypatch.setattr(
            account_reviews,
            "load_system_settings",
            lambda: {
                "account_review": {
                    "enabled": True,
                    "interval_days": 120,
                    "last_sent_at": None,
                }
            },
        )
        monkeypatch.setattr(account_reviews, "save_system_settings", lambda payload: saved.setdefault("payload", payload))

        sent_ok = account_reviews.send_account_review_if_due()

        assert sent_ok is True
        assert len(sent) == 1
        email = sent[0]
        assert email["recipients"] == ["admin@example.com"]
        assert "Account access review required" in email["subject"]
        assert "analyst@example.com" in email["body"]
        assert "last_login=2026-01-02 15:30 UTC" in email["body"]
        assert "local_only=yes" in email["body"]
        assert saved["payload"]["account_review"]["last_sent_at"]
        assert audited and audited[0]["action"] == "account_review_email_sent"
    finally:
        engine.dispose()


def test_send_account_review_if_due_skips_when_interval_not_elapsed(monkeypatch):
    engine, SessionLocal = _session_local()
    try:
        with SessionLocal() as db:
            _create_audit_events_table(db)
            _create_user(db, role="sys_admin", email="admin@example.com")

        sent = []
        monkeypatch.setattr(account_reviews, "SessionLocal", SessionLocal)
        monkeypatch.setattr(account_reviews, "mail_provider_ready", lambda: True)
        monkeypatch.setattr(account_reviews, "send_email", lambda **kwargs: sent.append(kwargs))
        monkeypatch.setattr(
            account_reviews,
            "load_system_settings",
            lambda: {
                "account_review": {
                    "enabled": True,
                    "interval_days": 120,
                    "last_sent_at": (datetime.now(timezone.utc) - timedelta(days=20)).isoformat(),
                }
            },
        )

        sent_ok = account_reviews.send_account_review_if_due()

        assert sent_ok is False
        assert sent == []
    finally:
        engine.dispose()


def test_complete_login_rejects_disabled_user(monkeypatch):
    disabled = models.User(username="disabled@example.com", is_active=False, role="analyst", is_admin=False)
    monkeypatch.setattr(auth, "create_access_token", lambda *args, **kwargs: ("token", datetime.now(timezone.utc) + timedelta(hours=1), "jti"))

    with pytest.raises(HTTPException) as exc:
        auth._complete_login(disabled, response=None, db=None, request=None)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Account disabled"
