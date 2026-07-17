import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import cases, custodians_summary, dashboard_access, models, permissions, reports


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            yield db
    finally:
        engine.dispose()


def _user(db, username, role, *, group=None):
    row = models.User(
        username=username,
        email=username,
        password_hash="unused",
        role=role,
        is_admin=role == "sys_admin",
        is_active=True,
        requestor_group=group,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _case(db, name, *, requestor, private=False, requestor_group=None, requestor_user_id=None):
    row = models.Case(name=name, requestor=requestor, is_private=private, closed=False)
    db.add(row)
    db.flush()
    db.add(
        models.CaseRequestor(
            case_id=row.id,
            user_id=requestor_user_id,
            email=requestor,
            requestor_group=requestor_group,
            is_primary=True,
        )
    )
    db.commit()
    db.refresh(row)
    return row


def test_canonical_requestor_scope_excludes_peer_private_cases(db_session):
    actor = _user(db_session, "peer@example.edu", "requestor", group="legal")
    public_peer = _case(
        db_session,
        "Public Peer Case",
        requestor="owner@example.edu",
        private=False,
        requestor_group="legal",
    )
    private_peer = _case(
        db_session,
        "Private Peer Case",
        requestor="owner@example.edu",
        private=True,
        requestor_group="legal",
    )
    private_direct = _case(
        db_session,
        "Private Direct Case",
        requestor=actor.email,
        private=True,
        requestor_group="legal",
        requestor_user_id=actor.id,
    )

    expected = {public_peer.id, private_direct.id}
    assert permissions.get_visible_case_ids(actor, db_session) == expected
    assert dashboard_access._visible_case_ids(db_session, actor) == expected
    assert reports._visible_case_ids(db_session, actor) == expected
    assert custodians_summary._visible_case_ids(db_session, actor) == expected
    assert private_peer.id not in expected


def test_tester_case_collection_is_limited_to_test_suffix(db_session):
    tester = _user(db_session, "tester@example.edu", "tester")
    _case(db_session, "Production Matter", requestor="owner@example.edu", private=True)
    test_case = _case(db_session, "Workflow-TEST", requestor="owner@example.edu", private=False)

    visible = permissions.get_visible_case_ids(tester, db_session)
    assert visible == {test_case.id}

    listed = cases.list_cases(db=db_session, _user=tester)
    assert [item.id for item in listed] == [test_case.id]


def test_requestor_cannot_delete_case_even_when_directly_assigned(db_session):
    actor = _user(db_session, "requestor@example.edu", "requestor", group="legal")
    case = _case(
        db_session,
        "Direct Requestor Case",
        requestor=actor.email,
        private=True,
        requestor_group="legal",
        requestor_user_id=actor.id,
    )

    with pytest.raises(HTTPException) as exc:
        cases.delete_case(case.id, db=db_session, _user=actor)

    assert exc.value.status_code == 403
    assert db_session.get(models.Case, case.id) is not None


def test_analyst_retains_full_case_visibility(db_session):
    analyst = _user(db_session, "analyst@example.edu", "analyst")
    assert permissions.get_visible_case_ids(analyst, db_session) is None
