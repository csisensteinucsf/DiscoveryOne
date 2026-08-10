from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import system_admin


def _sys_admin():
    return SimpleNamespace(id=7, role="sys_admin", is_admin=True)


def test_backend_restart_is_disabled_without_supervisor_opt_in(monkeypatch):
    monkeypatch.delenv("APP_RESTART_ENABLED", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        system_admin.sys_restart_backend(actor=_sys_admin(), request=None, db=SimpleNamespace())

    assert exc_info.value.status_code == 409
    assert "deployment manager" in str(exc_info.value.detail)


def test_backend_restart_requires_system_admin(monkeypatch):
    monkeypatch.setenv("APP_RESTART_ENABLED", "1")
    actor = SimpleNamespace(id=8, role="analyst", is_admin=False)

    with pytest.raises(HTTPException) as exc_info:
        system_admin.sys_restart_backend(actor=actor, request=None, db=SimpleNamespace())

    assert exc_info.value.status_code == 403


def test_backend_restart_is_audited_and_queued(monkeypatch):
    monkeypatch.setenv("APP_RESTART_ENABLED", "true")
    audit_events = []
    threads = []

    class FakeThread:
        def __init__(self, *, target, daemon, name):
            self.target = target
            self.daemon = daemon
            self.name = name
            self.started = False
            threads.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: audit_events.append(kwargs))
    monkeypatch.setattr(system_admin.threading, "Thread", FakeThread)

    result = system_admin.sys_restart_backend(actor=_sys_admin(), request=None, db=SimpleNamespace())

    assert result["ok"] is True
    assert audit_events == [
        {
            "action": "system_backend_restart",
            "actor_id": 7,
            "target_type": "system",
            "details": {"source": "system_integrations"},
            "request": None,
        }
    ]
    assert len(threads) == 1
    assert threads[0].target is system_admin._restart_backend_after_delay
    assert threads[0].daemon is True
    assert threads[0].name == "backend-restart"
    assert threads[0].started is True
