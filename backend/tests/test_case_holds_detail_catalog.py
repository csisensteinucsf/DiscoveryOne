from app import case_holds_detail


def test_hold_detail_meta_uses_configured_enabled_builtin_sources(monkeypatch):
    monkeypatch.setattr(
        case_holds_detail,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [
            ("email", "holds_email", "Mail"),
            ("box", "holds_box", "Cloud Files"),
        ],
    )

    assert case_holds_detail._hold_detail_meta() == [
        {"key": "holds_email", "label": "Mail"},
        {"key": "holds_box", "label": "Cloud Files"},
    ]


def test_hold_detail_source_mapping_respects_configured_enabled_sources(monkeypatch):
    monkeypatch.setattr(
        case_holds_detail,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [("email", "holds_email", "Mail")],
    )

    assert case_holds_detail._hold_detail_keys_from_sources(["mailbox", "rubrik", "site"]) == {"holds_email"}
    assert case_holds_detail._hold_detail_key_from_field("holds_email_pending") == "holds_email"
    assert case_holds_detail._hold_detail_key_from_field("holds_rubrik_restore_pending") is None


def test_hold_detail_fallback_keeps_universal_defaults_without_rubrik(monkeypatch):
    monkeypatch.setattr(case_holds_detail, "configured_builtin_hold_fields", lambda enabled_only=True: [])

    keys = {item["key"] for item in case_holds_detail._hold_detail_meta()}

    assert {"holds_email", "holds_onedrive", "holds_gdrive", "holds_box", "holds_slack"}.issubset(keys)
    assert "holds_rubrik_restore" not in keys
