from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pyotp")


def test_require_employee_id_uses_user_value():
    from app.cases import _require_employee_id

    user = SimpleNamespace(id=1, role="analyst", username="analyst1", employee_id="E-8418846")
    assert _require_employee_id(user) == "E8418846"


def test_case_requests_imports_require_employee_id():
    from app import case_requests, cases

    assert case_requests._require_employee_id is cases._require_employee_id
