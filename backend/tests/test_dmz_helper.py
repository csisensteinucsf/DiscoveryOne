from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "DiscoveryOne_DMZ.sh"


def test_dmz_helper_is_universal_and_secret_safe():
    text = SCRIPT.read_text(encoding="utf-8")
    lowered = text.lower()

    assert text.startswith("#!/usr/bin/env bash\n")
    assert "ucsf" not in lowered
    assert "docusign" not in lowered
    assert "secrets.token_urlsafe(48)" in text
    assert 'SHARED_SECRET="${SHARED_SECRET:-}"' in text
    assert "--rotate-secret" in text
    assert "UPSTREAM_URL must end in /api/ntp/ack/automate" in text


def test_dmz_helper_hardens_public_token_handling():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "TOKEN_PATTERN" in text
    assert "Cache-Control" in text
    assert "Referrer-Policy" in text
    assert "limit_req zone=discoveryone_ack" in text
    assert 'log_format discoveryone_ack' in text
    assert '"\\$request_method \\$uri \\$server_protocol"' in text
    assert "--no-access-log" in text
    assert "follow_redirects=False" in text
    assert "trust_env=False" in text
    assert "ssl.create_default_context" in text
    assert "error_log /var/log/nginx/discoveryone-ack-error.log crit" in text
    assert "limit_req_log_level notice" in text
    assert "ProtectSystem=strict" in text