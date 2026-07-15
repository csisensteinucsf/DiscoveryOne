from types import SimpleNamespace
import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # type: ignore

from app.main import app, HEALTHCHECK_SECRET
from app.auth import ALGORITHM, ALLOWED_JWT_ALGORITHMS


@pytest.fixture
def client():
    return TestClient(app)


def test_health_requires_secret_or_localhost(client):
    # No secret provided should 403 (unless no secret configured and client is seen as localhost)
    resp = client.get("/health")
    if HEALTHCHECK_SECRET:
        assert resp.status_code == 403
    else:
        # TestClient uses localhost; should be allowed without secret
        assert resp.status_code == 200

    # With secret header, should allow
    secret = HEALTHCHECK_SECRET or "dev-secret"
    resp2 = client.get("/health", headers={"X-Health-Secret": secret})
    if HEALTHCHECK_SECRET:
        assert resp2.status_code == 200
    else:
        # When secret not configured, header should not hurt
        assert resp2.status_code == 200


def test_ready_requires_secret_or_localhost(client, monkeypatch):
    # Force secret for predictable behavior
    monkeypatch.setenv("HEALTHCHECK_SECRET", "s3cr3t")
    # Re-import app to re-read env is heavy; instead hit endpoint with header
    resp = client.get("/ready")
    assert resp.status_code == 403
    resp2 = client.get("/ready", headers={"X-Health-Secret": "s3cr3t"})
    # DB connection might fail in tests; accept either 200 or 500 but not 403 now
    assert resp2.status_code != 403


def test_jwt_algorithm_allowlist():
    assert ALGORITHM in ALLOWED_JWT_ALGORITHMS


def test_suggest_name_requires_auth(client):
    resp = client.get("/api/cases/suggest_name")
    assert resp.status_code == 401


def test_suggest_name_allows_authenticated_user(client):
    from app.main import current_user

    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=1, username="tester", role="sys_admin", is_admin=True)
    try:
        resp = client.get("/api/cases/suggest_name")
        assert resp.status_code == 200
        payload = resp.json()
        assert isinstance(payload.get("name"), str)
        assert payload.get("name")
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_deprecated_routes_are_removed(client):
    removed = [
        ("post", "/api/auth/auth/refresh"),
        ("get", "/api/cases/suggest_name/_ping"),
        ("get", "/api/cases/1/timeline"),
        ("get", "/api/logs/export"),
        ("get", "/api/reports/deprecated_endpoints"),
        ("get", "/api/reports/deprecated_endpoints/export"),
        ("post", "/api/tools/email-convert-path"),
        ("get", "/api/tools/browse"),
    ]

    for method, path in removed:
        resp = getattr(client, method)(path)
        assert resp.status_code == 404
