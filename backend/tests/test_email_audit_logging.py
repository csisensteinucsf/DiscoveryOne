import pytest


def test_email_sent_is_audited_action():
    audit = pytest.importorskip("app.audit")
    assert "email_sent" in audit.BIG_ACTIONS


def test_send_email_triggers_audit_hook(monkeypatch):
    emailer = pytest.importorskip("app.emailer")
    smtp_provider = pytest.importorskip("app.smtp_mail_provider")

    class DummySMTP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send_message(self, msg, from_addr=None, to_addrs=None):
            return None

    monkeypatch.setattr(smtp_provider, "_smtp_client", lambda settings: DummySMTP())

    audit_calls = []

    def _capture_audit(**kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(smtp_provider, "_audit_email_sent", _capture_audit)

    settings = emailer.SMTPSettings(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        use_tls=False,
        use_ssl=False,
        timeout=1.0,
        sender="noreply@example.test",
    )

    emailer.send_email(
        recipients=["user@example.test"],
        subject="Hello",
        body="Body",
        settings=settings,
    )

    assert len(audit_calls) == 1
    assert audit_calls[0]["subject"] == "Hello"
    assert audit_calls[0]["to_addrs"] == ["user@example.test"]


def test_send_email_can_disable_audit_hook(monkeypatch):
    emailer = pytest.importorskip("app.emailer")
    smtp_provider = pytest.importorskip("app.smtp_mail_provider")

    class DummySMTP:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send_message(self, msg, from_addr=None, to_addrs=None):
            return None

    monkeypatch.setattr(smtp_provider, "_smtp_client", lambda settings: DummySMTP())

    audit_calls = []
    monkeypatch.setattr(smtp_provider, "_audit_email_sent", lambda **kwargs: audit_calls.append(kwargs))

    settings = emailer.SMTPSettings(
        host="smtp.example.test",
        port=587,
        username=None,
        password=None,
        use_tls=False,
        use_ssl=False,
        timeout=1.0,
        sender="noreply@example.test",
    )

    emailer.send_email(
        recipients=["user@example.test"],
        subject="Hello",
        body="Body",
        settings=settings,
        audit_log=False,
    )

    assert audit_calls == []

