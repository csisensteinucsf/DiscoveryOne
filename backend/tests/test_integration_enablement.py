from app import integration_settings
from app import institution
from app import slack_legal_holds
from app import docusign_client
from app import docusign_webhook
from app import esignature_provider
from app import esignature_provider_adapters
from app import servicenow
from app import purview
from app import emailer
from app import smtp_mail_provider
from app import mail_provider_registry
from app import ticket_provider_labels
from app import ticket_provider
from app import ticket_provider_adapters
from app import case_purview_gateway
from app import ai_config
from app import purview_exports
from app import purview_http
from app import schemas


def test_slack_requires_enabled_integration_even_when_token_is_configured(monkeypatch):
    monkeypatch.delenv("SLACK_ENABLED", raising=False)
    monkeypatch.delenv("SLACK_LEGAL_HOLDS_TOKEN", raising=False)
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "enabled_integrations": {"slack": False},
            "integration_configs": {"slack": {"legal_holds_token": "stored-token"}},
        },
    )

    assert slack_legal_holds.slack_legal_holds_enabled() is False


def test_slack_enabled_from_settings_when_token_is_configured(monkeypatch):
    monkeypatch.delenv("SLACK_ENABLED", raising=False)
    monkeypatch.delenv("SLACK_LEGAL_HOLDS_TOKEN", raising=False)
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "enabled_integrations": {"slack": True},
            "integration_configs": {"slack": {"legal_holds_token": "stored-token"}},
        },
    )

    assert slack_legal_holds.slack_legal_holds_enabled() is True


def test_slack_enabled_env_flag_can_override_settings(monkeypatch):
    monkeypatch.setenv("SLACK_ENABLED", "true")
    monkeypatch.setenv("SLACK_LEGAL_HOLDS_TOKEN", "env-token")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {"enabled_integrations": {"slack": False}, "integration_configs": {}},
    )

    assert slack_legal_holds.slack_legal_holds_enabled() is True


def _docusign_config(enabled=False, provider="none"):
    return {
        "enabled_integrations": {"docusign": enabled},
        "integrations": {"esign_provider": provider},
        "integration_configs": {
            "docusign": {
                "base_url": "https://demo.docusign.net/restapi",
                "account_id": "acct",
                "template_id": "template",
                "signer_role": "signer",
                "integration_key": "integration",
                "user_id": "user",
                "auth_server": "account-d.docusign.com",
                "private_key": "private",
            }
        },
    }


def test_docusign_requires_enabled_integration_or_selected_provider(monkeypatch):
    monkeypatch.delenv("DOCUSIGN_ENABLED", raising=False)
    monkeypatch.delenv("ESIGN_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _docusign_config(False, "none"))

    assert docusign_client.docusign_enabled() is False
    try:
        docusign_client._config()
    except docusign_client.DocuSignError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("DocuSign config should fail when disabled")


def test_docusign_enabled_when_esign_provider_selects_docusign(monkeypatch):
    monkeypatch.delenv("DOCUSIGN_ENABLED", raising=False)
    monkeypatch.delenv("ESIGN_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _docusign_config(False, "docusign"))

    assert docusign_client.docusign_enabled() is True
    assert docusign_client._config()["template_id"] == "template"


def test_docusign_enabled_env_flag_can_override_settings(monkeypatch):
    monkeypatch.setenv("DOCUSIGN_ENABLED", "true")
    monkeypatch.delenv("ESIGN_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _docusign_config(False, "none"))

    assert docusign_client.docusign_enabled() is True


def test_esignature_facade_requires_configured_provider(monkeypatch):
    monkeypatch.setattr(esignature_provider, "_provider", lambda: "none")
    monkeypatch.setattr(docusign_client, "docusign_enabled", lambda: False)

    try:
        esignature_provider.resend_request("env-1")
    except esignature_provider.ESignatureProviderError as exc:
        assert "No e-signature provider" in str(exc)
    else:
        raise AssertionError("e-signature facade should require a configured provider")


def test_esignature_facade_wraps_provider_errors(monkeypatch):
    monkeypatch.setattr(esignature_provider, "_provider", lambda: "docusign")
    monkeypatch.setattr(docusign_client, "docusign_enabled", lambda: True)

    def fail(_envelope_id):
        raise docusign_client.DocuSignError("provider failed")

    monkeypatch.setattr(docusign_client, "resend_envelope", fail)

    try:
        esignature_provider.resend_request("env-1")
    except esignature_provider.ESignatureProviderError as exc:
        assert "provider failed" in str(exc)
    else:
        raise AssertionError("e-signature facade should wrap provider errors")


def test_esignature_registry_supports_non_docusign_adapter(monkeypatch):
    class ExampleESignatureAdapter:
        name = "example_sign"
        display_name = "Example Sign"

        def is_available(self):
            return True

        def send_consent_request(self, **kwargs):
            self.sent = kwargs
            return "request-1"

        def resend_request(self, request_id):
            return request_id

        def void_request(self, request_id, reason):
            self.voided = (request_id, reason)

        def download_completed_document(self, request_id):
            return (b"signed", "signed.pdf")

    adapter = ExampleESignatureAdapter()
    esignature_provider_adapters.register_esignature_provider(adapter)
    monkeypatch.setattr(
        esignature_provider,
        "current_esignature_provider",
        lambda: "example_sign",
    )
    try:
        request_id = esignature_provider.send_consent_request(
            custodian_name="Jane Custodian",
            custodian_email="jane@example.test",
            fields={"record_type": "Email"},
        )
        resent = esignature_provider.resend_request(request_id)
        esignature_provider.void_request(request_id, "Case closed")
        document, filename = esignature_provider.download_completed_document(request_id)

        assert request_id == "request-1"
        assert adapter.sent["fields"] == {"record_type": "Email"}
        assert resent == "request-1"
        assert adapter.voided == ("request-1", "Case closed")
        assert document == b"signed"
        assert filename == "signed.pdf"
    finally:
        esignature_provider_adapters.unregister_esignature_provider("example_sign")


def test_esignature_facade_dispatches_to_explicit_request_owner(monkeypatch):
    class OwnerAdapter:
        name = "owner_sign"
        display_name = "Owner Sign"

        def is_available(self):
            return True

        def resend_request(self, request_id):
            return f"owner:{request_id}"

    adapter = OwnerAdapter()
    esignature_provider_adapters.register_esignature_provider(adapter)
    monkeypatch.setattr(esignature_provider, "current_esignature_provider", lambda: "none")
    try:
        assert (
            esignature_provider.resend_request("request-42", provider="owner_sign")
            == "owner:request-42"
        )
    finally:
        esignature_provider_adapters.unregister_esignature_provider("owner_sign")


def test_docusign_envelope_uses_configured_template_tab_labels(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 201
        text = '{"envelopeId":"env-1"}'

        def json(self):
            return {"envelopeId": "env-1"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(
        docusign_client,
        "_config",
        lambda: {
            "base_url": "https://demo.docusign.net/restapi",
            "account_id": "acct",
            "template_id": "template",
            "signer_role": "Signer 1",
            "case_name_tab": "matterName",
            "record_type_tab": "recordCategory",
            "date_from_tab": "startDate",
            "date_to_tab": "endDate",
        },
    )
    monkeypatch.setattr(docusign_client, "_get_token", lambda _cfg: "token")
    monkeypatch.setattr(docusign_client.httpx, "Client", FakeClient)

    envelope_id = docusign_client.send_consent_envelope(
        custodian_name="Jane Custodian",
        custodian_email="jane@example.test",
        case_name="Matter Alpha",
        text_tabs=[
            {"tabLabel": "recordtype", "value": "Email"},
            {"tabLabel": "datefrom", "value": "2026-01-01"},
            {"tabLabel": "dateto", "value": "2026-02-01"},
            {"tabLabel": "casename", "value": "Matter Alpha"},
        ],
    )

    assert envelope_id == "env-1"
    role = captured["json"]["templateRoles"][0]
    assert role["roleName"] == "Signer 1"
    tabs = role["tabs"]["textTabs"]
    assert {"tabLabel": "matterName", "value": "Matter Alpha"} in tabs
    assert {"tabLabel": "recordCategory", "value": "Email"} in tabs
    assert {"tabLabel": "startDate", "value": "2026-01-01"} in tabs
    assert {"tabLabel": "endDate", "value": "2026-02-01"} in tabs
    assert {"tabLabel": "casename", "value": "Matter Alpha"} in tabs


def test_ticket_provider_facade_requires_configured_provider(monkeypatch):
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "none")
    monkeypatch.setattr(servicenow, "servicenow_enabled", lambda: False)

    try:
        ticket_provider.get_ticket_statuses(["INC001"])
    except ticket_provider.TicketProviderError as exc:
        assert "No external ticket provider" in str(exc)
    else:
        raise AssertionError("ticket provider facade should require a configured provider")


def test_ticket_provider_facade_wraps_adapter_errors(monkeypatch):
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "servicenow")
    monkeypatch.setattr(servicenow, "servicenow_enabled", lambda: True)

    def fail(_tickets):
        raise servicenow.ServiceNowError("adapter failed")

    monkeypatch.setattr(servicenow, "get_ticket_statuses", fail)

    try:
        ticket_provider.get_ticket_statuses(["INC001"])
    except ticket_provider.TicketProviderError as exc:
        assert "adapter failed" in str(exc)
    else:
        raise AssertionError("ticket provider facade should wrap adapter errors")


def test_ticket_provider_closed_status_goes_through_adapter(monkeypatch):
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "servicenow")
    monkeypatch.setattr(servicenow, "servicenow_enabled", lambda: True)
    monkeypatch.setattr(servicenow, "_is_closed_state", lambda value: value == "provider-closed")

    assert ticket_provider.is_closed_status("provider-closed") is True
    assert ticket_provider.is_closed_status("closed") is False


def test_ticket_provider_builds_legacy_ticket_number_link_through_adapter(monkeypatch):
    class Config:
        base_url = "https://snow.example.test"
        status_table = "incident"
        table = "incident"

    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "servicenow")
    monkeypatch.setattr(servicenow, "load_config", lambda: Config())

    link = ticket_provider.ticket_link(ticket_number="INC001", fallback="")

    assert link.startswith("https://snow.example.test/nav_to.do?uri=")
    assert "INC001" in link


def test_ticket_provider_generic_closed_status_includes_canceled(monkeypatch):
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "none")
    monkeypatch.setattr(servicenow, "servicenow_enabled", lambda: False)

    assert ticket_provider.is_closed_status("Canceled by requester") is True


def test_ticket_provider_registry_supports_non_servicenow_adapter(monkeypatch):
    class ExampleTicketAdapter:
        name = "example"
        display_name = "Example Tickets"

        def is_available(self):
            return True

        def create_ticket(self, **kwargs):
            return {"number": "EXT-1", "sys_id": "external-1"}

        def get_ticket_statuses(self, ticket_numbers):
            return {number: {"status": "done"} for number in ticket_numbers}

        def is_closed_status(self, status):
            return status == "done"

        def default_customer_id(self):
            return "customer-1"

        def ticket_link(self, *, sys_id=None, ticket_number=None, fallback="N/A"):
            identifier = sys_id or ticket_number
            return f"https://tickets.example.test/{identifier}" if identifier else fallback

    ticket_provider_adapters.register_ticket_provider(ExampleTicketAdapter())
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "example")
    try:
        created = ticket_provider.create_ticket(category="legal_hold")
        statuses = ticket_provider.get_ticket_statuses(["EXT-1"])

        assert created["number"] == "EXT-1"
        assert statuses["EXT-1"]["status"] == "done"
        assert ticket_provider.is_closed_status("done") is True
        assert ticket_provider.default_customer_id() == "customer-1"
        assert ticket_provider.ticket_link(sys_id="external-1") == "https://tickets.example.test/external-1"
        assert ticket_provider_labels.ticket_provider_label("example") == "Example Tickets"
    finally:
        ticket_provider_adapters.unregister_ticket_provider("example")


def _servicenow_config(enabled=False, provider="none"):
    return {
        "enabled_integrations": {"servicenow": enabled},
        "integrations": {"ticket_provider": provider},
        "integration_configs": {
            "servicenow": {
                "base_url": "https://snow.example.test",
                "auth_type": "basic",
                "username": "api-user",
                "password": "api-pass",
            }
        },
    }


def test_servicenow_requires_enabled_integration_or_selected_provider(monkeypatch):
    monkeypatch.delenv("SERVICENOW_ENABLED", raising=False)
    monkeypatch.delenv("TICKET_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _servicenow_config(False, "none"))

    assert servicenow.servicenow_enabled() is False
    try:
        servicenow.load_config()
    except servicenow.ServiceNowError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("ServiceNow config should fail when disabled")


def test_servicenow_enabled_when_ticket_provider_selects_servicenow(monkeypatch):
    monkeypatch.delenv("SERVICENOW_ENABLED", raising=False)
    monkeypatch.delenv("TICKET_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _servicenow_config(False, "servicenow"))

    assert servicenow.servicenow_enabled() is True
    assert servicenow.load_config().base_url == "https://snow.example.test"


def _purview_settings(enabled=False, provider="none"):
    return {
        "enabled_integrations": {"purview": enabled},
        "integrations": {"preservation_provider": provider},
        "integration_configs": {
            "purview": {
                "tenant_id": "tenant",
                "client_id": "client",
                "client_secret": "secret",
                "scope": "https://graph.microsoft.com/.default",
            }
        },
    }

def test_purview_requires_enabled_integration_or_selected_provider(monkeypatch):
    monkeypatch.delenv("PURVIEW_ENABLED", raising=False)
    monkeypatch.delenv("PRESERVATION_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _purview_settings(False, "none"))

    assert purview.purview_enabled() is False
    try:
        purview._get_access_token()
    except purview.PurviewConfigError as exc:
        assert "disabled" in str(exc).lower()
    else:
        raise AssertionError("Purview auth should fail when disabled")


def test_purview_enabled_when_preservation_provider_selects_purview(monkeypatch):
    monkeypatch.delenv("PURVIEW_ENABLED", raising=False)
    monkeypatch.delenv("PRESERVATION_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: _purview_settings(False, "purview"))

    assert purview.purview_enabled() is True


def _smtp_settings(enabled=False, provider="none"):
    return {
        "enabled_integrations": {"smtp": enabled},
        "integrations": {"mail_provider": provider},
        "smtp": {
            "host": "smtp.example.test",
            "port": 587,
            "from_address": "noreply@example.test",
            "username": "",
            "password": None,
            "use_tls": True,
            "use_ssl": False,
        },
    }


def test_smtp_requires_enabled_integration_or_selected_mail_provider(monkeypatch):
    monkeypatch.delenv("SMTP_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    settings_payload = _smtp_settings(False, "none")
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: settings_payload)
    monkeypatch.setattr(smtp_mail_provider, "load_system_settings", lambda: settings_payload)

    settings = emailer.load_smtp_settings()
    assert emailer.smtp_enabled() is False
    assert settings.is_configured is False
    try:
        emailer.send_email(recipients=["user@example.test"], subject="Test", body="Body", settings=settings)
    except Exception as exc:
        assert "disabled" in str(getattr(exc, "detail", exc)).lower()
    else:
        raise AssertionError("SMTP send should fail when mail provider is disabled")


def test_mail_registry_supports_non_smtp_provider(monkeypatch):
    deliveries = []

    class ExampleMailProvider:
        name = "example_mail"
        display_name = "Example Mail"

        def is_available(self):
            return True

        def send_email(self, **kwargs):
            deliveries.append(kwargs)

    mail_provider_registry.register_mail_provider(
        "example_mail",
        ExampleMailProvider,
        display_name="Example Mail",
    )
    monkeypatch.setattr(
        emailer,
        "current_mail_provider",
        lambda: "example_mail",
    )
    try:
        assert emailer.mail_provider_ready() is True
        emailer.send_email(
            recipients=["user@example.test"],
            subject="Provider test",
            body="Body",
        )

        assert len(deliveries) == 1
        assert deliveries[0]["recipients"] == ["user@example.test"]
        assert deliveries[0]["provider_context"] is None
    finally:
        mail_provider_registry.unregister_mail_provider("example_mail")


def test_smtp_enabled_when_mail_provider_selects_smtp(monkeypatch):
    monkeypatch.delenv("SMTP_ENABLED", raising=False)
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    settings_payload = _smtp_settings(False, "smtp")
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: settings_payload)
    monkeypatch.setattr(smtp_mail_provider, "load_system_settings", lambda: settings_payload)

    settings = emailer.load_smtp_settings()
    assert emailer.smtp_enabled() is True
    assert settings.is_configured is True


def test_smtp_enabled_env_flag_can_override_settings(monkeypatch):
    monkeypatch.setenv("SMTP_ENABLED", "true")
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    settings_payload = _smtp_settings(False, "none")
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: settings_payload)
    monkeypatch.setattr(smtp_mail_provider, "load_system_settings", lambda: settings_payload)

    assert emailer.smtp_enabled() is True


def test_ticket_provider_label_defaults_to_generic_external_ticket(monkeypatch):
    monkeypatch.delenv("TICKET_PROVIDER", raising=False)
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: {"integrations": {"ticket_provider": "servicenow"}})

    assert ticket_provider_labels.external_ticket_label() == "ServiceNow ticket"
    assert ticket_provider_labels.generic_external_ticket_label() == "external ticket"


def test_external_ticket_schema_names_are_canonical_with_legacy_aliases():
    assert schemas.ServiceNowTicketTimeWindow is schemas.ExternalTicketTimeWindow
    assert schemas.ServiceNowTicketRequest is schemas.ExternalTicketRequest
    assert schemas.ServiceNowTicketResponse is schemas.ExternalTicketResponse
    assert schemas.ServiceNowTicketStatus is schemas.ExternalTicketStatus
    assert schemas.ServiceNowTicketEmailRequest is schemas.ExternalTicketEmailRequest

def test_purview_runtime_options_use_app_managed_settings(monkeypatch):
    for name in (
        "PURVIEW_ADD_DATA_SOURCES",
        "PURVIEW_HOLD_MISSING_EMAIL_MARK_FAILED",
        "PURVIEW_STATUS_ONEDRIVE_LOOKUP_LIMIT",
        "PURVIEW_STATUS_POLL_DELAY_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "integration_configs": {
                "purview": {
                    "add_data_sources": True,
                    "hold_missing_email_mark_failed": True,
                    "status_onedrive_lookup_limit": "7",
                    "status_poll_delay_seconds": "15.5",
                }
            }
        },
    )

    assert case_purview_gateway.add_data_sources_enabled() is True
    assert case_purview_gateway.hold_missing_email_mark_failed() is True
    assert case_purview_gateway.status_onedrive_lookup_limit() == 7
    assert case_purview_gateway.status_poll_delay_seconds() == 15.5


def test_purview_export_poll_options_use_app_managed_settings(monkeypatch):
    for name in (
        "PURVIEW_EXPORT_POLL_ENABLED",
        "PURVIEW_EXPORT_POLL_HOURS",
        "PURVIEW_EXPORT_POLL_MINUTE",
        "PURVIEW_EXPORT_POLL_TIMEZONE",
        "PURVIEW_EXPORT_POLL_REQUESTOR_GROUPS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "integration_configs": {
                "purview": {
                    "export_poll_enabled": False,
                    "export_poll_hours": "6,19",
                    "export_poll_minute": "42",
                    "export_poll_timezone": "America/Los_Angeles",
                    "export_poll_requestor_groups": "pra,legal",
                }
            }
        },
    )

    assert purview_exports.purview_export_poll_enabled() is False
    assert purview_exports.purview_export_poll_hours() == "6,19"
    assert purview_exports.purview_export_poll_minute() == 42
    assert purview_exports.purview_export_poll_timezone() == "America/Los_Angeles"
    assert purview_exports.purview_export_poll_requestor_groups() == "pra,legal"


def test_ai_config_uses_app_managed_settings(monkeypatch):
    for name in (
        "AI_ENABLED", "AI_URL", "AI_MODEL", "AI_API_KEY", "AI_AUTH_HEADER",
        "AI_TIMEOUT_SECONDS", "AI_TEMPERATURE", "AI_SYSTEM_PROMPT",
        "SEARCH_BUILDER_AI_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "enabled_integrations": {"ai": True},
            "integration_configs": {
                "ai": {
                    "url": "https://ai.example.test/v1/chat/completions",
                    "model": "legal-model",
                    "api_key": "stored-key",
                    "auth_header": "X-API-Key",
                    "timeout_seconds": "12",
                    "temperature": "0.3",
                    "system_prompt": "Use legal operations tone.",
                    "search_builder_enabled": False,
                }
            },
        },
    )

    cfg = ai_config.ai_client_config(feature_prefix="SEARCH_BUILDER_AI")

    assert ai_config.ai_integration_enabled() is True
    assert ai_config.ai_configured(feature_prefix="SEARCH_BUILDER_AI") is True
    assert ai_config.ai_feature_enabled("search_builder_enabled", "SEARCH_BUILDER_AI_ENABLED", default=True) is False
    assert cfg["url"] == "https://ai.example.test/v1/chat/completions"
    assert cfg["model"] == "legal-model"
    assert cfg["timeout_seconds"] == 12
    assert cfg["temperature"] == 0.3
    assert cfg["system_prompt"] == "Use legal operations tone."
    assert ai_config.ai_headers(cfg)["X-API-Key"] == "stored-key"


def test_ai_saved_disable_overrides_legacy_environment(monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "1")
    monkeypatch.setenv("AI_URL", "https://legacy-ai.example.test")
    monkeypatch.setenv("AI_MODEL", "legacy-model")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "enabled_integrations": {"ai": False},
            "integration_configs": {"ai": {}},
        },
    )
    monkeypatch.setattr(
        "app.system_settings.load_system_settings",
        integration_settings.load_system_settings,
    )

    assert ai_config.ai_integration_enabled() is False

def test_ai_public_config_masks_api_key(monkeypatch):
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "integration_configs": {
                "ai": {"url": "https://ai.example.test", "model": "m", "api_key": "secret"}
            }
        },
    )

    public = integration_settings.public_integration_config("ai")

    assert public["api_key"] == integration_settings.MASKED_SECRET_VALUE


def test_docusign_public_config_masks_connect_keys(monkeypatch):
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "integration_configs": {
                "docusign": {
                    "private_key": "private",
                    "connect_key": "connect-secret",
                    "connect_keys": "old-secret,new-secret",
                }
            }
        },
    )

    public = integration_settings.public_integration_config("docusign")

    assert public["private_key"] == integration_settings.MASKED_SECRET_VALUE
    assert public["connect_key"] == integration_settings.MASKED_SECRET_VALUE
    assert public["connect_keys"] == integration_settings.MASKED_SECRET_VALUE


def test_docusign_webhook_connect_keys_use_app_managed_settings(monkeypatch):
    monkeypatch.delenv("DOCUSIGN_CONNECT_KEY", raising=False)
    monkeypatch.delenv("DOCUSIGN_CONNECT_KEYS", raising=False)
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "integration_configs": {
                "docusign": {"connect_keys": "old-secret, new-secret"}
            }
        },
    )

    assert docusign_webhook._parse_connect_keys() == ["old-secret", "new-secret"]

def test_completed_setup_integration_settings_win_over_env(monkeypatch):
    monkeypatch.setenv("DOCUSIGN_ENABLED", "true")
    monkeypatch.setenv("ESIGN_PROVIDER", "docusign")
    monkeypatch.setenv("SERVICENOW_ENABLED", "true")
    monkeypatch.setenv("TICKET_PROVIDER", "servicenow")
    monkeypatch.setenv("SEARCH_EXPORT_PROVIDER", "purview")
    settings_payload = {
        "initial_setup_completed": True,
        "enabled_integrations": {"docusign": False, "servicenow": False},
        "integrations": {"esign_provider": "none", "ticket_provider": "none", "search_export_provider": "none"},
        "integration_configs": {},
    }
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: settings_payload)
    monkeypatch.setattr(institution, "load_system_settings", lambda: settings_payload)

    assert integration_settings.integration_enabled("docusign") is False
    assert integration_settings.provider_value("esign_provider") == "none"
    assert integration_settings.integration_active("servicenow", provider_key="ticket_provider", provider="servicenow") is False
    loaded = institution.load_integration_settings()
    assert loaded["esign_provider"] == "none"
    assert loaded["ticket_provider"] == "none"
    assert loaded["search_export_provider"] == "none"
    assert loaded["enabled_integrations"]["docusign"] is False
    assert loaded["enabled_integrations"]["servicenow"] is False


def test_env_integration_values_can_bootstrap_before_setup(monkeypatch):
    monkeypatch.setenv("DOCUSIGN_ENABLED", "true")
    monkeypatch.setenv("ESIGN_PROVIDER", "docusign")
    settings_payload = {
        "initial_setup_completed": False,
        "enabled_integrations": {"docusign": False},
        "integrations": {"esign_provider": "none"},
        "integration_configs": {},
    }
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: settings_payload)
    monkeypatch.setattr(institution, "load_system_settings", lambda: settings_payload)

    assert integration_settings.integration_enabled("docusign") is True
    assert integration_settings.provider_value("esign_provider") == "docusign"
    loaded = institution.load_integration_settings()
    assert loaded["esign_provider"] == "docusign"
    assert loaded["enabled_integrations"]["docusign"] is True


def test_config_values_ignore_legacy_env_after_completed_setup(monkeypatch):
    monkeypatch.setenv("SNOW_BASE_URL", "https://legacy.example.test")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "integration_configs": {"servicenow": {}},
        },
    )

    assert integration_settings.config_value(
        "servicenow",
        "base_url",
        "SNOW_BASE_URL",
        "https://default.example.test",
    ) == "https://default.example.test"


def test_config_values_can_bootstrap_from_env_before_setup(monkeypatch):
    monkeypatch.setenv("SNOW_BASE_URL", "https://legacy.example.test")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": False,
            "integration_configs": {"servicenow": {}},
        },
    )

    assert integration_settings.config_value(
        "servicenow",
        "base_url",
        "SNOW_BASE_URL",
    ) == "https://legacy.example.test"


def test_smtp_does_not_fall_back_to_env_after_completed_setup(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.legacy.example.test")
    monkeypatch.setenv("SMTP_FROM_ADDRESS", "legacy@example.test")
    settings_payload = {
        "initial_setup_completed": True,
        "enabled_integrations": {"smtp": True},
        "integrations": {"mail_provider": "smtp"},
        "smtp": {
            "host": "",
            "port": 587,
            "from_address": "",
            "username": "",
            "password": None,
            "use_tls": True,
            "use_ssl": False,
            "timeout_seconds": 22,
        },
    }
    monkeypatch.setattr(integration_settings, "load_system_settings", lambda: settings_payload)
    monkeypatch.setattr(smtp_mail_provider, "load_system_settings", lambda: settings_payload)

    settings = smtp_mail_provider.load_smtp_settings()

    assert settings.host == ""
    assert settings.sender == ""
    assert settings.timeout == 22
    assert settings.is_configured is False


def test_purview_http_reliability_uses_app_managed_settings(monkeypatch):
    monkeypatch.setenv("PURVIEW_HTTP_TIMEOUT_SECONDS", "299")
    monkeypatch.setenv("PURVIEW_HTTP_RETRY_COUNT", "9")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "integration_configs": {
                "purview": {
                    "http_timeout_seconds": "35",
                    "http_retry_count": "4",
                }
            },
        },
    )

    assert purview_http.http_timeout_seconds() == 35
    assert purview_http.http_retry_count() == 4


def test_conventional_future_provider_secrets_are_encrypted_and_masked(monkeypatch):
    from cryptography.fernet import Fernet

    monkeypatch.setenv("SETTINGS_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    merged = integration_settings.merge_integration_config(
        "future_provider",
        {},
        {"access_token": "raw-secret", "endpoint": "https://provider.example.test"},
    )

    assert merged["access_token"].startswith("enc:v1:")
    monkeypatch.setattr(
        integration_settings,
        "load_system_settings",
        lambda: {"integration_configs": {"future_provider": merged}},
    )
    public = integration_settings.public_integration_config("future_provider")

    assert public["access_token"] == integration_settings.MASKED_SECRET_VALUE
    assert public["endpoint"] == "https://provider.example.test"