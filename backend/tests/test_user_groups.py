from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _setup_db():
    from app import models

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def test_list_groups_prefers_canonical_definition_label():
    from app import models, users

    engine, SessionLocal = _setup_db()
    try:
        with SessionLocal() as db:
            admin = models.User(username="admin@example.com", email="admin@example.com", password_hash="x", is_admin=True, role="sys_admin")
            member = models.User(username="user@example.com", email="user@example.com", password_hash="x", role="requestor", requestor_group="legal")
            db.add_all([
                admin,
                member,
                models.RequestorGroup(name="legal", label="Legal"),
            ])
            db.commit()

            items = users.list_groups(db=db, actor=admin)

            legal = next(item for item in items if item["name"] == "legal")
            assert legal["label"] == "Legal"
            assert legal["user_count"] == 1
            assert legal["users"][0]["requestor_group"] == "legal"
    finally:
        engine.dispose()


def test_create_group_allows_empty_group_with_visibility_targets():
    from app import models, users

    engine, SessionLocal = _setup_db()
    try:
        with SessionLocal() as db:
            admin = models.User(username="admin@example.com", email="admin@example.com", password_hash="x", is_admin=True, role="sys_admin")
            db.add_all([
                admin,
                models.RequestorGroup(name="risk", label="Risk"),
            ])
            db.commit()
            db.refresh(admin)

            result = users.create_group(
                payload={"name": "Compliance", "can_see_groups": ["risk"]},
                db=db,
                request=None,
                actor=admin,
            )

            assert result["name"] == "compliance"
            assert result["label"] == "Compliance"

            groups = users.list_groups(db=db, actor=admin)
            compliance = next(item for item in groups if item["name"] == "compliance")
            assert compliance["label"] == "Compliance"
            assert compliance["user_count"] == 0
            assert compliance["can_see_groups"] == ["risk"]
    finally:
        engine.dispose()
