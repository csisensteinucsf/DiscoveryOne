import pytest
from fastapi import HTTPException

from app import emailer, esignature_provider, preservation_provider, ticket_provider


def test_none_provider_selection_never_activates_an_adapter(monkeypatch):
    monkeypatch.setattr(preservation_provider, "current_preservation_provider", lambda: "none")
    monkeypatch.setattr(esignature_provider, "current_esignature_provider", lambda: "none")
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "none")
    monkeypatch.setattr(emailer, "current_mail_provider", lambda: "none")

    assert preservation_provider._active_adapter(required=False) is None
    assert esignature_provider._active_adapter(required=False) is None
    assert ticket_provider._active_adapter(required=False) is None
    assert emailer._active_mail_adapter(required=False) is None


def test_none_provider_selection_reports_configuration_error(monkeypatch):
    monkeypatch.setattr(preservation_provider, "current_preservation_provider", lambda: "none")
    monkeypatch.setattr(esignature_provider, "current_esignature_provider", lambda: "none")
    monkeypatch.setattr(ticket_provider, "current_ticket_provider", lambda: "none")
    monkeypatch.setattr(emailer, "current_mail_provider", lambda: "none")

    with pytest.raises(HTTPException, match="No automated preservation provider"):
        preservation_provider._active_adapter(required=True)
    with pytest.raises(esignature_provider.ESignatureProviderError, match="No e-signature provider"):
        esignature_provider._active_adapter(required=True)
    with pytest.raises(ticket_provider.TicketProviderError, match="No external ticket provider"):
        ticket_provider._active_adapter(required=True)
    with pytest.raises(HTTPException, match="No mail provider"):
        emailer._active_mail_adapter(required=True)