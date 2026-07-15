from types import SimpleNamespace

import httpx

from app import searches


def _case_stub() -> SimpleNamespace:
    return SimpleNamespace(
        id=123,
        name="Versa Timeout Matter",
        legal_case_name=None,
        claimant=None,
    )


def test_build_ai_search_suggestions_returns_clear_timeout_error_and_stops_retrying(monkeypatch):
    monkeypatch.setenv("SEARCH_BUILDER_AI_ENABLED", "true")
    monkeypatch.setenv("AI_URL", "https://example.test/v1/chat/completions")
    monkeypatch.setenv("AI_MODEL", "gpt-test")
    monkeypatch.setenv("SEARCH_BUILDER_AI_TIMEOUT_SECONDS", "12")

    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append({"url": url, "body": json, "timeout": timeout})
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(searches.httpx, "post", fake_post)

    result = searches._build_ai_search_suggestions(
        case=_case_stub(),
        draft={},
        objective="Find communications about the outage.",
        selected_custodians=[],
        all_custodians=[],
        existing_search_names=[],
        max_suggestions=3,
    )

    assert result["status"] == "error"
    assert result["status_code"] == 504
    assert result["endpoint_host"] == "example.test"
    assert result["suggestions"] == []
    assert result["error"] == "Versa timed out after 12s while waiting for AI response."
    assert len(calls) == 1


def test_build_ai_search_suggestions_uses_search_specific_timeout_env(monkeypatch):
    monkeypatch.setenv("SEARCH_BUILDER_AI_ENABLED", "true")
    monkeypatch.setenv("AI_URL", "https://example.test/v1/chat/completions")
    monkeypatch.setenv("AI_MODEL", "gpt-test")
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "25")
    monkeypatch.setenv("SEARCH_BUILDER_AI_TIMEOUT_SECONDS", "11")

    observed = {}

    def fake_post(url, *, headers, json, timeout):
        observed["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"ok","suggestions":[{"keywords":"outage","senders":"",'
                                '"recipients":"","kql":"outage","date_from":"",'
                                '"date_to":"","additional":"","custodian_ids":[],"rationale":"tight"}]}'
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(searches.httpx, "post", fake_post)

    result = searches._build_ai_search_suggestions(
        case=_case_stub(),
        draft={},
        objective="Find communications about the outage.",
        selected_custodians=[],
        all_custodians=[],
        existing_search_names=[],
        max_suggestions=3,
    )

    assert result["status"] == "ok"
    assert observed["timeout"] == 11.0