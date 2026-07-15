from fastapi import HTTPException

from app import institution
from app.requestor_email_policy import is_allowed_requestor_email, require_allowed_requestor_email


def test_requestor_email_policy_allows_all_when_domains_are_unconfigured(monkeypatch):
    monkeypatch.delenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", raising=False)
    monkeypatch.delenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", raising=False)
    assert is_allowed_requestor_email("person@example.com") is True


def test_requestor_email_policy_allows_configured_domain(monkeypatch):
    monkeypatch.setenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", "example.edu")
    monkeypatch.delenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", raising=False)
    assert is_allowed_requestor_email("person@example.edu") is True


def test_requestor_email_policy_allows_named_exceptions(monkeypatch):
    monkeypatch.setenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", "example.edu")
    monkeypatch.setenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", "person@external.example")
    assert is_allowed_requestor_email("person@external.example") is True


def test_requestor_email_policy_rejects_other_domains_when_configured(monkeypatch):
    monkeypatch.setenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", "example.edu")
    monkeypatch.delenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", raising=False)
    assert is_allowed_requestor_email("person@example.com") is False
    assert is_allowed_requestor_email("someone@campus.net.example.edu") is False


def test_require_allowed_requestor_email_raises_for_disallowed_email(monkeypatch):
    monkeypatch.setenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", "example.edu")
    monkeypatch.delenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", raising=False)
    try:
        require_allowed_requestor_email("person@example.com", label="Requestor account email")
        assert False, "Expected HTTPException for disallowed requestor email"
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "Requestor account email must use an approved organization email address (@example.edu)"

def test_completed_setup_institution_settings_win_over_env(monkeypatch):
    monkeypatch.setenv("ORG_NAME", "Env University")
    monkeypatch.setenv("ORG_SHORT_NAME", "ENV")
    monkeypatch.setenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", "env.example")
    monkeypatch.setenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", "env-person@external.example")
    monkeypatch.setenv("SSO_DISPLAY_NAME", "Env SSO")
    monkeypatch.setenv("SUPPORT_EMAIL", "env-support@example.edu")
    monkeypatch.setattr(
        institution,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": True,
            "institution": {
                "org_name": "Stored University",
                "org_short_name": "STORED",
                "allowed_requestor_email_domains": ["stored.example"],
                "requestor_email_exceptions": ["stored-person@external.example"],
                "sso_display_name": "Stored SSO",
                "support_email": "stored-support@example.edu",
            },
        },
    )

    settings = institution.load_institution_settings()

    assert settings["org_name"] == "Stored University"
    assert settings["org_short_name"] == "STORED"
    assert settings["allowed_requestor_email_domains"] == ["stored.example"]
    assert settings["requestor_email_exceptions"] == ["stored-person@external.example"]
    assert settings["sso_display_name"] == "Stored SSO"
    assert settings["support_email"] == "stored-support@example.edu"
    assert is_allowed_requestor_email("person@stored.example") is True
    assert is_allowed_requestor_email("person@env.example") is False


def test_env_institution_values_can_bootstrap_before_setup(monkeypatch):
    monkeypatch.setenv("ORG_ALLOWED_REQUESTOR_EMAIL_DOMAINS", "env.example")
    monkeypatch.setenv("ORG_REQUESTOR_EMAIL_EXCEPTIONS", "env-person@external.example")
    monkeypatch.setattr(
        institution,
        "load_system_settings",
        lambda: {
            "initial_setup_completed": False,
            "institution": {
                "allowed_requestor_email_domains": ["stored.example"],
                "requestor_email_exceptions": ["stored-person@external.example"],
            },
        },
    )

    assert is_allowed_requestor_email("person@env.example") is True
    assert is_allowed_requestor_email("person@stored.example") is False
    assert is_allowed_requestor_email("env-person@external.example") is True
