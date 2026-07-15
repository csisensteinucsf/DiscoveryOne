import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")


class FakeQuery:
    def __init__(self, first_item=None, all_items=None):
        self._first_item = first_item
        self._all_items = all_items if all_items is not None else []

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._first_item

    def all(self):
        return list(self._all_items)


class FakeDB:
    def __init__(self, models, custodian, case):
        self.models = models
        self.custodian = custodian
        self.case = case
        self.deleted = []
        self.commits = 0

    def query(self, model):
        if model is self.models.Custodian:
            return FakeQuery(first_item=self.custodian)
        if model is self.models.Search:
            return FakeQuery(all_items=[])
        return FakeQuery()

    def get(self, model, ident):
        if model is self.models.Case:
            return self.case
        return None

    def add(self, obj):
        pass

    def delete(self, obj):
        self.deleted.append(obj)

    def commit(self):
        self.commits += 1


def _entities(models, *, email="user@example.com"):
    custodian = models.Custodian(
        case_id=1,
        name="User",
        email=email,
    )
    custodian.id = 123
    case = models.Case(name="Case A")
    case.id = 1
    actor = models.User(
        username="admin",
        password_hash="x",
        role="sys_admin",
    )
    actor.id = 9
    return custodian, case, actor


def test_delete_custodian_routes_release_through_registered_provider(monkeypatch):
    from app import cases, models, preservation_provider
    from app.preservation_provider_registry import (
        register_preservation_provider,
        unregister_preservation_provider,
    )

    called = {}

    class ExampleProvider:
        name = "example_preservation"
        display_name = "Example Preservation"

        def is_available(self):
            return True

        def remove_custodian(
            self,
            *,
            case_id,
            custodian_id,
            custodian_name,
            custodian_email,
            context,
        ):
            called.update(
                {
                    "case_id": case_id,
                    "custodian_id": custodian_id,
                    "custodian_name": custodian_name,
                    "custodian_email": custodian_email,
                    "context": context,
                }
            )
            return {
                "provider": self.name,
                "status": "released",
                "compatibility_fields": {
                    "provider_release_reference": "external-123",
                },
            }

    register_preservation_provider(
        "example_preservation",
        ExampleProvider,
        replace=True,
    )
    monkeypatch.setattr(
        preservation_provider,
        "current_preservation_provider",
        lambda: "example_preservation",
    )

    custodian, case, actor = _entities(models)
    db = FakeDB(models, custodian, case)
    try:
        response = cases.delete_custodian(
            case_id=1,
            custodian_id=123,
            release_holds=True,
            release_ntp=False,
            close_searches=False,
            approval_note=None,
            db=db,
            request=None,
            _user=actor,
        )
    finally:
        unregister_preservation_provider("example_preservation")

    assert response["ok"] is True
    assert response["preservation_release"]["provider"] == "example_preservation"
    assert response["provider_release_reference"] == "external-123"
    assert called["case_id"] == 1
    assert called["custodian_id"] == 123
    assert called["custodian_name"] == "User"
    assert called["custodian_email"] == "user@example.com"
    assert called["context"].db is db
    assert called["context"].user is actor
    assert db.deleted == [custodian]
    assert db.commits == 1


def test_delete_custodian_leaves_placeholder_policy_to_provider(monkeypatch):
    from app import cases, models, preservation_provider
    from app.preservation_provider_registry import (
        register_preservation_provider,
        unregister_preservation_provider,
    )

    received = []

    class ExampleProvider:
        name = "placeholder_provider"
        display_name = "Placeholder Provider"

        def is_available(self):
            return True

        def remove_custodian(self, **kwargs):
            received.append(kwargs["custodian_email"])
            return {
                "provider": self.name,
                "status": "skipped",
                "reason": "custodian_missing_email",
                "compatibility_fields": {},
            }

    register_preservation_provider(
        "placeholder_provider",
        ExampleProvider,
        replace=True,
    )
    monkeypatch.setattr(
        preservation_provider,
        "current_preservation_provider",
        lambda: "placeholder_provider",
    )

    custodian, case, actor = _entities(
        models,
        email=cases.NO_EMAIL_PLACEHOLDER,
    )
    db = FakeDB(models, custodian, case)
    try:
        response = cases.delete_custodian(
            case_id=1,
            custodian_id=123,
            release_holds=True,
            release_ntp=False,
            close_searches=False,
            approval_note=None,
            db=db,
            request=None,
            _user=actor,
        )
    finally:
        unregister_preservation_provider("placeholder_provider")

    assert response["ok"] is True
    assert response["preservation_release"]["status"] == "skipped"
    assert received == [cases.NO_EMAIL_PLACEHOLDER]
    assert db.deleted == [custodian]