import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

fastapi = pytest.importorskip("fastapi")


def test_log_scope_private_cases_uses_direct_requestor_identity(monkeypatch):
    from app import logs

    captured = {}

    class _Rows:
        def all(self):
            return []

    class _Result:
        def mappings(self):
            return _Rows()

    class _Db:
        def execute(self, sql, params):
            captured["sql"] = str(sql)
            captured["params"] = params
            return _Result()

    user = SimpleNamespace(
        id=7,
        email="direct.requestor@example.com",
        username="direct.username@example.com",
        role="requestor",
    )
    monkeypatch.setattr(
        logs,
        "get_requestor_allowed_emails",
        lambda _user, _db: {
            "direct.requestor@example.com",
            "direct.username@example.com",
            "same.group.peer@example.com",
        },
    )

    assert logs._requestor_visible_case_ids(_Db(), user) == []

    assert "c.is_private IS TRUE" in captured["sql"]
    assert "c.is_private IS NOT TRUE" in captured["sql"]
    assert captured["params"]["direct_emails"] == [
        "direct.requestor@example.com",
        "direct.username@example.com",
    ]
    assert "same.group.peer@example.com" not in captured["params"]["direct_emails"]
    assert "same.group.peer@example.com" in captured["params"]["allowed_emails"]


def test_get_requestor_allowed_emails_includes_email_like_username_when_email_blank():
    from app import models, permissions

    user = models.User(username="secondary.requestor@example.com", email=None, role="requestor")
    allowed = permissions.get_requestor_allowed_emails(user, db=None)

    assert "secondary.requestor@example.com" in allowed


def test_ensure_case_visible_allows_secondary_requestor_by_username_email():
    from app import models, permissions

    user = models.User(id=7, username="secondary.requestor@example.com", email=None, role="requestor")
    case = models.Case(name="Case A", requestor="primary.requestor@example.com")
    case.requestors = [
        models.CaseRequestor(
            case_id=1,
            email="secondary.requestor@example.com",
            user_id=None,
            is_primary=False,
        )
    ]

    # Should not raise 403 when secondary requestor is assigned by email.
    permissions.ensure_case_visible(case, user, db=None)


def test_normalize_requestor_entries_links_user_by_username_email():
    from app import cases, models

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        user = models.User(
            username="secondary.requestor@example.com",
            email=None,
            password_hash="x",
            role="requestor",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        entries = cases._normalize_requestor_entries(
            db,
            [{"email": "secondary.requestor@example.com", "is_primary": False}],
            None,
        )

        assert len(entries) == 1
        assert entries[0]["user_id"] == user.id
        # Single entry is promoted to primary by normalizer.
        assert entries[0]["is_primary"] is True


def test_approve_new_case_request_keeps_additional_private_requestors():
    from app import case_requests, models

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        reviewer = models.User(
            username="admin@example.com",
            email="admin@example.com",
            password_hash="x",
            role="sys_admin",
            is_admin=True,
        )
        analyst = models.User(
            username="analyst@example.com",
            email="analyst@example.com",
            password_hash="x",
            role="analyst",
            is_admin=False,
        )
        primary = models.User(
            username="primary.requestor@example.com",
            email="primary.requestor@example.com",
            password_hash="x",
            role="requestor",
            requestor_group="group-a",
        )
        secondary = models.User(
            username="secondary.requestor@example.com",
            email="secondary.requestor@example.com",
            password_hash="x",
            role="requestor",
        )
        db.add_all([reviewer, analyst, primary, secondary])
        db.commit()
        db.refresh(reviewer)
        db.refresh(analyst)
        db.refresh(primary)
        db.refresh(secondary)

        record = models.CaseRequest(
            request_type="new_case",
            status="pending",
            case_name="2026-Blue",
            payload=json.dumps(
                {
                    "name": "2026-Blue",
                    "is_private": True,
                    "custodian_entry_mode": "none",
                    "custodians": [],
                    "requestors": [
                        {
                            "email": primary.email,
                            "user_id": primary.id,
                            "requestor_group": primary.requestor_group,
                            "is_primary": True,
                        },
                        {
                            "email": secondary.email,
                            "is_primary": False,
                        },
                    ],
                }
            ),
            requestor_id=primary.id,
            requestor_email=primary.email,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        case_requests.approve_case_request(
            record.id,
            payload_body={"analyst_id": analyst.id},
            db=db,
            actor=reviewer,
            request=None,
        )

        approved_case = db.get(models.Case, record.case_id)
        assert approved_case is not None
        assert approved_case.is_private is True
        assert approved_case.requestor == primary.email

        requestors = sorted(
            approved_case.requestors,
            key=lambda row: (0 if row.is_primary else 1, row.email or ""),
        )
        assert [row.email for row in requestors] == [primary.email, secondary.email]
        assert requestors[0].is_primary is True
        assert requestors[0].user_id == primary.id
        assert requestors[0].requestor_group == "group-a"
        assert requestors[1].is_primary is False
        assert requestors[1].user_id == secondary.id
