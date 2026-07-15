from types import SimpleNamespace

import pytest

from app import preservation_catalog, reports


@pytest.fixture(autouse=True)
def no_custom_sources_by_default(monkeypatch):
    monkeypatch.setattr(
        preservation_catalog,
        "configured_custom_hold_sources",
        lambda enabled_only=True: [],
    )


def test_custodian_configured_hold_flags_only_counts_configured_sources(monkeypatch):
    monkeypatch.setattr(
        preservation_catalog,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [("email", "holds_email", "Email")],
    )
    custodian = SimpleNamespace(holds_email=True, holds_rubrik_restore=True)

    flags = preservation_catalog.custodian_configured_hold_flags(custodian)

    assert flags == {"email": True}
    assert preservation_catalog.custodian_has_configured_hold(custodian) is True


def test_custodian_configured_hold_flags_can_include_enabled_rubrik(monkeypatch):
    monkeypatch.setattr(
        preservation_catalog,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [
            ("email", "holds_email", "Email"),
            ("rubrik_restore", "holds_rubrik_restore", "Rubrik Restore"),
        ],
    )
    custodian = SimpleNamespace(holds_email=False, holds_rubrik_restore=True)

    assert preservation_catalog.custodian_configured_hold_flags(custodian) == {
        "email": False,
        "rubrik_restore": True,
    }
    assert preservation_catalog.custodian_has_configured_hold(custodian) is True


def test_reports_custodian_hold_flags_follow_configured_sources(monkeypatch):
    monkeypatch.setattr(
        preservation_catalog,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [
            ("email", "holds_email", "Email"),
            ("gdrive", "holds_gdrive", "Google Drive"),
        ],
    )
    custodian = SimpleNamespace(holds_email=False, holds_gdrive=True, holds_rubrik_restore=True)

    flags = reports._custodian_hold_flags(custodian)

    assert flags == {"email": False, "gdrive": True, "any": True}
    assert "rubrik_restore" not in flags

def test_custom_preservation_source_is_included_in_report_flags(monkeypatch):
    monkeypatch.setattr(
        preservation_catalog,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [("email", "holds_email", "Email")],
    )
    monkeypatch.setattr(
        preservation_catalog,
        "configured_custom_hold_sources",
        lambda enabled_only=True: [("zoom", "Zoom")],
    )
    custom_record = SimpleNamespace(source_key="zoom", active=True)
    custodian = SimpleNamespace(
        holds_email=False,
        custom_preservation=[custom_record],
    )

    flags = reports._custodian_hold_flags(custodian)

    assert flags == {"email": False, "zoom": True, "any": True}


def test_configured_hold_catalog_combines_builtin_and_custom_sources(monkeypatch):
    monkeypatch.setattr(
        preservation_catalog,
        "configured_builtin_hold_fields",
        lambda enabled_only=True: [("email", "holds_email", "Email")],
    )
    monkeypatch.setattr(
        preservation_catalog,
        "configured_custom_hold_sources",
        lambda enabled_only=True: [("zoom", "Zoom")],
    )

    assert preservation_catalog.configured_hold_catalog() == [
        ("email", "holds_email", "Email"),
        ("zoom", None, "Zoom"),
    ]
