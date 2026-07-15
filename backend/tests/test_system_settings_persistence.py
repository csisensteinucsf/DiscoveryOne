import json

import pytest

from app import system_settings


def test_system_settings_save_is_atomic_and_round_trips(monkeypatch, tmp_path):
    path = tmp_path / "system_settings.json"
    monkeypatch.setattr(system_settings, "SETTINGS_PATH", path)

    system_settings.save_system_settings(
        {
            "initial_setup_completed": True,
            "branding": {"app_name": "Test Discovery"},
            "integration_configs": {
                "slack": {"legal_holds_token": "enc:v1:example"}
            },
        }
    )

    stored = system_settings.load_stored_system_settings()
    assert stored["initial_setup_completed"] is True
    assert stored["branding"]["app_name"] == "Test Discovery"
    assert json.loads(path.read_text(encoding="utf-8")) == stored
    assert list(tmp_path.glob(".*.tmp")) == []


def test_system_settings_load_fails_closed_on_invalid_json(monkeypatch, tmp_path):
    path = tmp_path / "system_settings.json"
    path.write_text('{"initial_setup_completed":', encoding="utf-8")
    monkeypatch.setattr(system_settings, "SETTINGS_PATH", path)

    with pytest.raises(RuntimeError, match="unreadable or invalid"):
        system_settings.load_stored_system_settings()


def test_system_settings_load_rejects_non_object_json(monkeypatch, tmp_path):
    path = tmp_path / "system_settings.json"
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(system_settings, "SETTINGS_PATH", path)

    with pytest.raises(RuntimeError, match="JSON object"):
        system_settings.load_stored_system_settings()