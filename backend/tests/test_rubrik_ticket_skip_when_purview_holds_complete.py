import pytest

fastapi = pytest.importorskip("fastapi")


def test_filter_rubrik_targets_clears_flags_when_purview_email_hold_complete_even_if_onedrive_pending():
    from app import case_requests, models

    class FakeDB:
        def __init__(self):
            self.added = []
            self.commits = 0
            self.rollbacks = 0

        def add_all(self, items):
            self.added.extend(list(items or []))

        def add(self, item):
            self.added.append(item)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    db = FakeDB()
    cust = models.Custodian(case_id=1, name="User", email="user@example.com")
    cust.id = 1
    cust.holds_email = True
    cust.holds_email_pending = False
    cust.holds_email_failed = False
    cust.holds_onedrive = True
    cust.holds_onedrive_pending = True
    cust.holds_onedrive_failed = False
    cust.holds_rubrik_restore = True
    cust.holds_rubrik_restore_pending = True
    cust.holds_rubrik_restore_failed = False

    kept = case_requests._filter_rubrik_targets_after_purview(db, [cust])
    assert kept == []
    assert cust.holds_rubrik_restore is False
    assert cust.holds_rubrik_restore_pending is False
    assert cust.holds_rubrik_restore_failed is False
    assert db.commits == 1
    assert db.rollbacks == 0


def test_filter_rubrik_targets_keeps_when_email_hold_not_complete():
    from app import case_requests, models

    class FakeDB:
        def __init__(self):
            self.commits = 0

        def add_all(self, items):
            return None

        def commit(self):
            self.commits += 1

        def rollback(self):
            return None

    db = FakeDB()
    cust = models.Custodian(case_id=1, name="User", email="user@example.com")
    cust.id = 2
    cust.holds_email = True
    cust.holds_email_pending = True
    cust.holds_email_failed = False
    cust.holds_onedrive = True
    cust.holds_onedrive_pending = False
    cust.holds_onedrive_failed = False
    cust.holds_rubrik_restore = True
    cust.holds_rubrik_restore_pending = True

    kept = case_requests._filter_rubrik_targets_after_purview(db, [cust])
    assert kept == [cust]
    assert cust.holds_rubrik_restore_pending is True
    assert db.commits == 0
