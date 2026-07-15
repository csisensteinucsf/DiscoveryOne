import pytest

fastapi = pytest.importorskip("fastapi")


def test_sync_case_purview_exports_clears_without_consent_flag_when_consent_is_received(monkeypatch):
    from app import models, purview_exports

    monkeypatch.setattr(purview_exports, "purview_enabled", lambda: True)
    monkeypatch.setattr(
        purview_exports,
        "find_purview_case_by_display_name",
        lambda display_name: {"id": "pv-case-1", "displayName": display_name},
    )
    monkeypatch.setattr(
        purview_exports,
        "list_purview_case_operations",
        lambda case_id: [
            {
                "id": "op-1",
                "action": "export",
                "status": "succeeded",
                "name": "Case A-Search 1",
            }
        ],
    )
    monkeypatch.setattr(purview_exports, "get_purview_case_operation", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(purview_exports, "log_event", lambda *a, **k: None)

    class FakeQuery:
        def __init__(self, items):
            self._items = list(items or [])

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return list(self._items)

    class FakeDB:
        def __init__(self, case_obj, searches, custodians):
            self._case = case_obj
            self._searches = list(searches or [])
            self._custodians = list(custodians or [])
            self.added = []
            self.commits = 0
            self.rollbacks = 0

        def get(self, model, ident):
            if model is models.Case and ident == getattr(self._case, "id", None):
                return self._case
            return None

        def query(self, model):
            if model is models.Search:
                return FakeQuery(self._searches)
            if model is models.Custodian:
                return FakeQuery(self._custodians)
            return FakeQuery([])

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    case = models.Case(name="Case A")
    case.id = 10

    search = models.Search(
        case_id=10,
        name="Case A-Search 1",
        status_search="performed",
        status_export="performed",
        status_delivery="not performed",
        custodian_ids="[1]",
    )
    search.id = 100
    search.export_without_consent = True

    custodian = models.Custodian(case_id=10, name="User A", email="user@example.com", consent_status="received")
    custodian.id = 1

    db = FakeDB(case, [search], [custodian])

    summary = purview_exports.sync_case_purview_exports(
        db,
        case_id=10,
        actor_id=None,
        request=None,
        source="test",
        send_notifications=False,
    )

    assert summary["ok"] is True
    assert summary["matched_searches_count"] == 1
    assert summary["matched_without_consent_count"] == 0
    assert summary["updated_search_ids"] == [100]
    assert search.export_without_consent is False
    assert db.commits == 1
    assert db.rollbacks == 0

def test_sync_case_purview_exports_clears_without_consent_flag_when_consent_is_not_required(monkeypatch):
    from app import models, purview_exports

    monkeypatch.setattr(purview_exports, "purview_enabled", lambda: True)
    monkeypatch.setattr(
        purview_exports,
        "find_purview_case_by_display_name",
        lambda display_name: {"id": "pv-case-1", "displayName": display_name},
    )
    monkeypatch.setattr(
        purview_exports,
        "list_purview_case_operations",
        lambda case_id: [
            {
                "id": "op-1",
                "action": "export",
                "status": "succeeded",
                "name": "Case A-Search 1",
            }
        ],
    )
    monkeypatch.setattr(purview_exports, "get_purview_case_operation", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(purview_exports, "log_event", lambda *a, **k: None)

    class FakeQuery:
        def __init__(self, items):
            self._items = list(items or [])

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return list(self._items)

    class FakeDB:
        def __init__(self, case_obj, searches, custodians):
            self._case = case_obj
            self._searches = list(searches or [])
            self._custodians = list(custodians or [])
            self.added = []
            self.commits = 0
            self.rollbacks = 0

        def get(self, model, ident):
            if model is models.Case and ident == getattr(self._case, "id", None):
                return self._case
            return None

        def query(self, model):
            if model is models.Search:
                return FakeQuery(self._searches)
            if model is models.Custodian:
                return FakeQuery(self._custodians)
            return FakeQuery([])

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    case = models.Case(name="Case A")
    case.id = 10

    search = models.Search(
        case_id=10,
        name="Case A-Search 1",
        status_search="performed",
        status_export="performed",
        status_delivery="not performed",
        custodian_ids="[1]",
    )
    search.id = 100
    search.export_without_consent = True

    custodian = models.Custodian(case_id=10, name="User A", email="user@example.com", consent_status="na")
    custodian.id = 1

    db = FakeDB(case, [search], [custodian])

    summary = purview_exports.sync_case_purview_exports(
        db,
        case_id=10,
        actor_id=None,
        request=None,
        source="test",
        send_notifications=False,
    )

    assert summary["ok"] is True
    assert summary["matched_searches_count"] == 1
    assert summary["matched_without_consent_count"] == 0
    assert summary["updated_search_ids"] == [100]
    assert search.export_without_consent is False
    assert db.commits == 1
    assert db.rollbacks == 0


def _mk_search(*, case_id: int, search_id: int, name: str):
    from app import models

    row = models.Search(
        case_id=case_id,
        name=name,
        status_search="not performed",
        status_export="not performed",
        status_delivery="not performed",
        custodian_ids="[]",
    )
    row.id = search_id
    return row


def test_match_exports_to_searches_matches_export_suffix_after_search_word():
    from app import purview_exports

    exports = [
        {"name": "2025-Xanthic Search 2 Export"},
        {"name": "2025-Xanthic Search 1 Export"},
    ]
    searches = [
        _mk_search(case_id=1, search_id=10, name="2025-Xanthic-Search 1"),
        _mk_search(case_id=1, search_id=11, name="2025-Xanthic-Search 2"),
    ]

    matched, unmatched = purview_exports._match_exports_to_searches(exports, searches)

    assert len(matched) == 2
    assert unmatched == []
    mapping = {(export.get("name") or ""): (getattr(search, "name", None) or "") for export, search in matched}
    assert mapping["2025-Xanthic Search 2 Export"] == "2025-Xanthic-Search 2"
    assert mapping["2025-Xanthic Search 1 Export"] == "2025-Xanthic-Search 1"


def test_match_exports_to_searches_matches_small_name_typo_when_ids_align():
    from app import purview_exports

    exports = [{"name": "2025-Xandu Export 1"}]
    searches = [_mk_search(case_id=1, search_id=20, name="2025-Xanadu-Search 1")]

    matched, unmatched = purview_exports._match_exports_to_searches(exports, searches)

    assert len(matched) == 1
    assert unmatched == []
    assert matched[0][1].name == "2025-Xanadu-Search 1"


def test_match_exports_to_searches_does_not_match_when_sequence_number_differs():
    from app import purview_exports

    exports = [{"name": "2025-Xandu Export 2"}]
    searches = [_mk_search(case_id=1, search_id=30, name="2025-Xanadu-Search 1")]

    matched, unmatched = purview_exports._match_exports_to_searches(exports, searches)

    assert matched == []
    assert len(unmatched) == 1


def test_match_exports_to_searches_matches_inline_export_indices_and_dot_suffixes():
    from app import purview_exports

    exports = [
        {"name": "2026-Ballet-Export1"},
        {"name": "2026-Ballet-Export 1.a"},
        {"name": "2026-Ballet-Export2"},
        {"name": "2026-Ballet Export 2.a"},
    ]
    searches = [
        _mk_search(case_id=1, search_id=40, name="2026-Ballet-Search1"),
        _mk_search(case_id=1, search_id=41, name="2026-Ballet-Search2"),
        _mk_search(case_id=1, search_id=42, name="2026-Ballet Search 2.a"),
        _mk_search(case_id=1, search_id=43, name="2026-Ballet Search 1.a"),
    ]

    matched, unmatched = purview_exports._match_exports_to_searches(exports, searches)

    assert len(matched) == 4
    assert unmatched == []

    mapping = {(export.get("name") or ""): (getattr(search, "name", None) or "") for export, search in matched}
    assert mapping["2026-Ballet-Export1"] == "2026-Ballet-Search1"
    assert mapping["2026-Ballet-Export2"] == "2026-Ballet-Search2"
    assert mapping["2026-Ballet-Export 1.a"] == "2026-Ballet Search 1.a"
    assert mapping["2026-Ballet Export 2.a"] == "2026-Ballet Search 2.a"
