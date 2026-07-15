from app import case_closure, models, system_admin, system_admin_config


def test_public_case_closure_config_clamps_values():
    public = system_admin_config.public_case_closure_config(
        {
            "default_nag_days": "99999",
            "loop_seconds": "1",
            "batch_size": "9999",
        }
    )

    assert public == {
        "default_nag_days": 3650,
        "loop_seconds": 300,
        "batch_size": 500,
    }


def test_system_case_closure_update_saves_normalized_values(monkeypatch):
    store = {"case_closure": {"default_nag_days": 180, "loop_seconds": 3600, "batch_size": 25}}
    monkeypatch.setattr(system_admin, "load_system_settings", lambda: dict(store))
    monkeypatch.setattr(system_admin, "save_system_settings", lambda data: store.update(data))
    monkeypatch.setattr(system_admin, "log_event", lambda *args, **kwargs: None)
    actor = models.User(id=1, username="admin", role="sys_admin", is_admin=True)

    result = system_admin.sys_update_case_closure(
        payload=system_admin_config.CaseClosurePayload(
            default_nag_days=45,
            loop_seconds=60,
            batch_size=0,
        ),
        actor=actor,
        request=None,
        db=None,
    )

    assert result["case_closure"] == {
        "default_nag_days": 45,
        "loop_seconds": 300,
        "batch_size": 1,
    }
    assert store["case_closure"] == result["case_closure"]


def test_case_closure_runtime_helpers_use_app_managed_settings(monkeypatch):
    monkeypatch.setenv("CASE_CLOSURE_NAG_DAYS", "999")
    monkeypatch.setenv("CASE_CLOSURE_LOOP_SECONDS", "999")
    monkeypatch.setenv("CASE_CLOSURE_BATCH_SIZE", "999")
    monkeypatch.setattr(
        case_closure,
        "load_system_settings",
        lambda: {
            "case_closure": {
                "default_nag_days": 30,
                "loop_seconds": 450,
                "batch_size": 7,
            }
        },
    )

    assert case_closure.case_closure_default_nag_days() == 30
    assert case_closure.case_closure_loop_seconds() == 450
    assert case_closure.case_closure_batch_size() == 7
