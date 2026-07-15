import pytest

from app import (
    esignature_provider_adapters,
    integration_policy,
    integration_settings,
    mail_provider_registry,
    ticket_provider_adapters,
)


def test_enabled_integration_merge_filters_unknown_keys():
    merged = integration_policy.merge_enabled_integrations(
        {"smtp": False},
        {"smtp": True, "not_installed": True},
    )

    assert merged["smtp"] is True
    assert "not_installed" not in merged


def test_provider_merge_rejects_or_ignores_unsupported_values():
    with pytest.raises(ValueError, match="Unsupported provider"):
        integration_policy.merge_provider_settings(
            {"ticket_provider": "none"},
            {"ticket_provider": "not_installed"},
            reject_unsupported=True,
        )

    merged = integration_policy.merge_provider_settings(
        {"ticket_provider": "none"},
        {"ticket_provider": "not_installed"},
        reject_unsupported=False,
    )
    assert merged["ticket_provider"] == "none"


def test_provider_options_include_registered_adapters():
    class ExampleTicketAdapter:
        name = "example_ticket"
        display_name = "Example Ticket"

    class ExampleESignatureAdapter:
        name = "example_sign"
        display_name = "Example Sign"
    class ExampleMailAdapter:
        name = "example_mail"
        display_name = "Example Mail"

    ticket_provider_adapters.register_ticket_provider(ExampleTicketAdapter())
    esignature_provider_adapters.register_esignature_provider(
        ExampleESignatureAdapter()
    )
    mail_provider_registry.register_mail_provider(
        "example_mail",
        ExampleMailAdapter,
        display_name="Example Mail",
    )
    try:
        options = integration_policy.provider_options()
        assert "example_ticket" in options["ticket_provider"]
        assert "example_sign" in options["esign_provider"]
        assert "example_mail" in options["mail_provider"]
        assert "google_workspace" not in options["preservation_provider"]

        merged = integration_policy.merge_provider_settings(
            {},
            {
                "ticket_provider": "example_ticket",
                "esign_provider": "example_sign",
                "mail_provider": "example_mail",
            },
            reject_unsupported=True,
        )
        assert merged["ticket_provider"] == "example_ticket"
        assert merged["esign_provider"] == "example_sign"
        assert merged["mail_provider"] == "example_mail"
    finally:
        ticket_provider_adapters.unregister_ticket_provider("example_ticket")
        mail_provider_registry.unregister_mail_provider("example_mail")
        esignature_provider_adapters.unregister_esignature_provider(
            "example_sign"
        )


def test_provider_changes_reconcile_built_in_enablement_flags():
    enabled = integration_policy.reconcile_provider_enablement(
        {
            "person_lookup": False,
            "servicenow": True,
            "smtp": True,
            "docusign": True,
            "purview": True,
        },
        {
            "person_lookup_provider": "http",
            "ticket_provider": "example_ticket",
            "mail_provider": "example_mail",
            "esign_provider": "example_sign",
        },
        changed_provider_fields={
            "person_lookup_provider",
            "ticket_provider",
            "mail_provider",
            "esign_provider",
        },
    )

    assert enabled["person_lookup"] is True
    assert enabled["servicenow"] is False
    assert enabled["smtp"] is False
    assert enabled["docusign"] is False
    assert enabled["purview"] is True


def test_config_merge_filters_unknown_sections_and_preserves_masked_secret():
    existing_password = integration_settings.encrypt_secret("existing-secret")
    merged = integration_policy.merge_integration_configs(
        {
            "servicenow": {
                "base_url": "https://old.example.test",
                "password": existing_password,
            }
        },
        {
            "servicenow": {
                "base_url": "https://new.example.test",
                "password": integration_settings.MASKED_SECRET_VALUE,
            },
            "not_installed": {"token": "do-not-store"},
        },
    )

    assert merged["servicenow"]["base_url"] == "https://new.example.test"
    assert merged["servicenow"]["password"] == existing_password
    assert "not_installed" not in merged
