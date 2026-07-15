import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI, Request  # type: ignore
from fastapi.testclient import TestClient  # type: ignore

from app.middleware import RequestSizeLimitMiddleware


def _build_app(max_bytes: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=max_bytes)

    @app.post("/api/system/import")
    async def import_case(request: Request):
        await request.body()
        return {"ok": True}

    @app.post("/api/notes")
    async def update_notes(request: Request):
        await request.body()
        return {"ok": True}

    return app


def test_case_import_route_has_higher_request_size_limit(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BYTES_CASE_IMPORT", "20")
    app = _build_app(max_bytes=10)
    client = TestClient(app)

    too_big_for_global = b"x" * 12
    assert client.post("/api/notes", content=too_big_for_global).status_code == 413

    within_import_override = b"x" * 12
    assert client.post("/api/system/import", content=within_import_override).status_code == 200

    too_big_for_import = b"x" * 21
    assert client.post("/api/system/import", content=too_big_for_import).status_code == 413

    os.environ.pop("MAX_REQUEST_BYTES_CASE_IMPORT", None)
