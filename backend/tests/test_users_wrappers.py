from types import SimpleNamespace

from app import schemas, users


def test_replace_user_forwards_keyword_args(monkeypatch):
    captured = {}

    def fake_update_user(user_id, payload, *, db=None, request=None, actor=None):
        captured["user_id"] = user_id
        captured["payload"] = payload
        captured["db"] = db
        captured["request"] = request
        captured["actor"] = actor
        return {"ok": True}

    monkeypatch.setattr(users, "update_user", fake_update_user)

    payload = schemas.UserUpdate(username="updated")
    db = object()
    request = object()
    actor = SimpleNamespace(id=7)

    result = users.replace_user(12, payload, db=db, request=request, actor=actor)

    assert result == {"ok": True}
    assert captured["user_id"] == 12
    assert captured["payload"] is payload
    assert captured["db"] is db
    assert captured["request"] is request
    assert captured["actor"] is actor


def test_reset_password_compat_forwards_keyword_args(monkeypatch):
    captured = {}

    def fake_reset_password(user_id, payload, *, db=None, request=None, actor=None):
        captured["user_id"] = user_id
        captured["payload"] = payload
        captured["db"] = db
        captured["request"] = request
        captured["actor"] = actor
        return None

    monkeypatch.setattr(users, "reset_password", fake_reset_password)

    payload = schemas.PasswordReset(password="SuperSecret123")
    db = object()
    request = object()
    actor = SimpleNamespace(id=9)

    result = users.reset_password_compat(14, payload, db=db, request=request, actor=actor)

    assert result is None
    assert captured["user_id"] == 14
    assert captured["payload"] is payload
    assert captured["db"] is db
    assert captured["request"] is request
    assert captured["actor"] is actor
