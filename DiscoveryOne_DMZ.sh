#!/usr/bin/env bash
#
# DiscoveryOne external NTP acknowledgement bridge installer.
#
# Installs a minimal FastAPI service behind Nginx on a RHEL-compatible DMZ
# host. The bridge receives GET /ack?token=... and forwards the token to the
# internal DiscoveryOne /api/ntp/ack/automate endpoint over HTTPS.

set -Eeuo pipefail
umask 077

APP_USER="discoveryone-acksvc"
APP_HOME="/opt/discoveryone-ack-proxy"
CONFIG_DIR="/etc/discoveryone-ack-proxy"
CONFIG_PATH="${CONFIG_DIR}/config.json"
SECRET_PATH="${CONFIG_DIR}/shared_secret"
SERVICE_NAME="discoveryone-ack-proxy"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
LISTEN_PORT="${LISTEN_PORT:-9000}"
SERVER_NAME="${SERVER_NAME:-}"
UPSTREAM_URL="${UPSTREAM_URL:-}"
TLS_CERT="${TLS_CERT:-}"
TLS_KEY="${TLS_KEY:-}"
UPSTREAM_CA_CERT="${UPSTREAM_CA_CERT:-}"
DISPLAY_NAME="${DISPLAY_NAME:-DiscoveryOne}"
SHARED_SECRET="${SHARED_SECRET:-}"
ROTATE_SECRET=0

usage() {
  cat <<'EOF'
Usage: sudo bash ./DiscoveryOne_DMZ.sh [options]

Options:
  --server-name HOST       Public DNS name for the acknowledgement endpoint
  --upstream-url URL       Internal DiscoveryOne HTTPS automate endpoint
  --tls-cert PATH          PEM certificate chain for the public DNS name
  --tls-key PATH           Unencrypted PEM private key for the certificate
  --upstream-ca-cert PATH  Optional CA PEM for a private upstream certificate
  --display-name NAME      Name shown on acknowledgement pages
  --listen-port PORT       Local application port (default: 9000)
  --rotate-secret          Generate a new bridge shared secret
  -h, --help               Show this help

The shared secret is never accepted as a command-line argument. On first run,
the installer generates one and stores it at:
  /etc/discoveryone-ack-proxy/shared_secret

For unattended installation, SERVER_NAME, UPSTREAM_URL, TLS_CERT, TLS_KEY,
UPSTREAM_CA_CERT, DISPLAY_NAME, LISTEN_PORT, and SHARED_SECRET may be supplied
as environment variables. SHARED_SECRET must contain 32-256 URL-safe
characters. Existing secrets are preserved unless --rotate-secret is used.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

prompt_required() {
  local variable_name="$1"
  local prompt_text="$2"
  local current_value="${!variable_name:-}"
  if [[ -n "${current_value}" ]]; then
    return
  fi
  [[ -t 0 ]] || die "${variable_name} is required for non-interactive installation"
  read -r -p "${prompt_text}: " current_value
  [[ -n "${current_value}" ]] || die "${variable_name} cannot be empty"
  printf -v "${variable_name}" '%s' "${current_value}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-name) SERVER_NAME="${2:-}"; shift 2 ;;
    --upstream-url) UPSTREAM_URL="${2:-}"; shift 2 ;;
    --tls-cert) TLS_CERT="${2:-}"; shift 2 ;;
    --tls-key) TLS_KEY="${2:-}"; shift 2 ;;
    --upstream-ca-cert) UPSTREAM_CA_CERT="${2:-}"; shift 2 ;;
    --display-name) DISPLAY_NAME="${2:-}"; shift 2 ;;
    --listen-port) LISTEN_PORT="${2:-}"; shift 2 ;;
    --rotate-secret) ROTATE_SECRET=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "${EUID}" -eq 0 ]] || die "Run this installer as root (sudo bash ./DiscoveryOne_DMZ.sh)"
command -v dnf >/dev/null 2>&1 || die "This installer requires a RHEL-compatible host with dnf"

prompt_required SERVER_NAME "Public acknowledgement DNS name"
prompt_required UPSTREAM_URL "Internal DiscoveryOne URL ending in /api/ntp/ack/automate"
prompt_required TLS_CERT "TLS certificate-chain PEM path"
prompt_required TLS_KEY "TLS private-key PEM path"

[[ "${SERVER_NAME}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$ ]] || die "SERVER_NAME is not a valid DNS name"
[[ "${LISTEN_PORT}" =~ ^[0-9]+$ ]] || die "LISTEN_PORT must be numeric"
(( LISTEN_PORT >= 1024 && LISTEN_PORT <= 65535 )) || die "LISTEN_PORT must be between 1024 and 65535"
[[ "${TLS_CERT}" =~ ^/[A-Za-z0-9._/+:-]+$ ]] || die "TLS_CERT must be an absolute path without spaces"
[[ "${TLS_KEY}" =~ ^/[A-Za-z0-9._/+:-]+$ ]] || die "TLS_KEY must be an absolute path without spaces"
[[ -f "${TLS_CERT}" ]] || die "TLS certificate not found: ${TLS_CERT}"
[[ -f "${TLS_KEY}" ]] || die "TLS private key not found: ${TLS_KEY}"
if [[ -n "${UPSTREAM_CA_CERT}" ]]; then
  [[ "${UPSTREAM_CA_CERT}" =~ ^/[A-Za-z0-9._/+:-]+$ ]] || die "UPSTREAM_CA_CERT must be an absolute path without spaces"
  [[ -f "${UPSTREAM_CA_CERT}" ]] || die "Upstream CA certificate not found: ${UPSTREAM_CA_CERT}"
fi

printf '[1/8] Installing required packages...\n'
dnf -y install python3 python3-pip nginx firewalld policycoreutils-python-utils openssl curl

"${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else "Python 3.9 or newer is required")'

D1_UPSTREAM_URL="${UPSTREAM_URL}" "${PYTHON_BIN}" - <<'PY'
import os
from urllib.parse import urlsplit

value = os.environ["D1_UPSTREAM_URL"]
parsed = urlsplit(value)
if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
    raise SystemExit("UPSTREAM_URL must be an HTTPS URL without credentials or a fragment")
if not parsed.path.rstrip("/").endswith("/api/ntp/ack/automate"):
    raise SystemExit("UPSTREAM_URL must end in /api/ntp/ack/automate")
PY

openssl x509 -in "${TLS_CERT}" -noout >/dev/null 2>&1 || die "TLS_CERT is not a readable PEM certificate"
openssl pkey -in "${TLS_KEY}" -noout >/dev/null 2>&1 || die "TLS_KEY must be a readable, unencrypted PEM private key"

printf '[2/8] Creating locked-down service account and directories...\n'
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_HOME}" --shell /sbin/nologin "${APP_USER}"
fi
install -d -o root -g root -m 0755 "${APP_HOME}"
install -d -o root -g "${APP_USER}" -m 0750 "${CONFIG_DIR}"

printf '[3/8] Creating Python environment...\n'
if [[ ! -x "${APP_HOME}/venv/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${APP_HOME}/venv"
fi
"${APP_HOME}/venv/bin/pip" install --disable-pip-version-check --upgrade \
  'pip>=24,<27' \
  'fastapi>=0.115,<1' \
  'uvicorn[standard]>=0.30,<1' \
  'httpx>=0.27,<1'

printf '[4/8] Installing acknowledgement bridge application...\n'
cat > "${APP_HOME}/app.py" <<'PY'
from __future__ import annotations

import html
import json
import logging
import os
import re
import ssl
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "/etc/discoveryone-ack-proxy/config.json"))
SECRET_PATH = Path(os.environ.get("SECRET_PATH", "/etc/discoveryone-ack-proxy/shared_secret"))
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
logger = logging.getLogger("discoveryone_ack_proxy")

with CONFIG_PATH.open("r", encoding="utf-8") as handle:
    CONFIG: dict[str, Any] = json.load(handle)

UPSTREAM_URL = str(CONFIG["upstream_url"])
DISPLAY_NAME = str(CONFIG.get("display_name") or "DiscoveryOne")[:120]
UPSTREAM_TIMEOUT = float(CONFIG.get("upstream_timeout_seconds", 8))
UPSTREAM_CA_FILE = str(CONFIG.get("upstream_ca_file") or "").strip()
UPSTREAM_VERIFY = ssl.create_default_context(cafile=UPSTREAM_CA_FILE) if UPSTREAM_CA_FILE else True
UPSTREAM_SECRET = SECRET_PATH.read_text(encoding="utf-8").strip()
if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", UPSTREAM_SECRET):
    raise RuntimeError("Bridge shared secret is missing or invalid")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    safe_title = html.escape(title[:160])
    safe_message = html.escape(message[:1000])
    body = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{safe_title}</title>"
        "</head><body><main><h1>" + safe_title + "</h1><p>" + safe_message + "</p></main></body></html>"
    )
    return HTMLResponse(
        body,
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"},
    )


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return page(f"{DISPLAY_NAME} acknowledgement service", "Use the acknowledgement link included in your notice email.")


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> PlainTextResponse:
    return PlainTextResponse("ok", headers={"Cache-Control": "no-store"})


@app.get("/ack", response_class=HTMLResponse)
async def acknowledge(token: str = Query(default="")) -> HTMLResponse:
    if not TOKEN_PATTERN.fullmatch(token):
        return page("Invalid acknowledgement link", "The acknowledgement link is invalid or incomplete.", 400)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(UPSTREAM_TIMEOUT),
            verify=UPSTREAM_VERIFY,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                UPSTREAM_URL,
                json={"token": token, "secret": UPSTREAM_SECRET, "metadata": {"source": "discoveryone-dmz"}},
                headers={"Accept": "application/json", "User-Agent": "DiscoveryOne-NTP-Bridge/1"},
            )
    except httpx.HTTPError as exc:
        logger.error("DiscoveryOne acknowledgement upstream unavailable (%s)", type(exc).__name__)
        return page("Acknowledgement temporarily unavailable", "Please try the link again later.", 502)

    if response.status_code >= 300:
        logger.error("DiscoveryOne acknowledgement upstream returned status %s", response.status_code)
        return page("Acknowledgement temporarily unavailable", "Please try the link again later.", 502)

    try:
        payload = response.json()
    except ValueError:
        logger.error("DiscoveryOne acknowledgement upstream returned invalid JSON")
        return page("Acknowledgement temporarily unavailable", "Please try the link again later.", 502)

    title = str(payload.get("title") or "Acknowledgement recorded")
    message = str(payload.get("message") or "Your acknowledgement has been recorded. You may close this window.")
    return page(title, message)
PY
chown root:root "${APP_HOME}/app.py"
chmod 0644 "${APP_HOME}/app.py"
chown -R root:root "${APP_HOME}/venv"

if [[ -n "${SHARED_SECRET}" ]]; then
  [[ "${SHARED_SECRET}" =~ ^[A-Za-z0-9_-]{32,256}$ ]] || die "SHARED_SECRET must contain 32-256 URL-safe characters"
elif [[ "${ROTATE_SECRET}" -eq 0 && -s "${SECRET_PATH}" ]]; then
  SHARED_SECRET="$(tr -d '\r\n' < "${SECRET_PATH}")"
else
  SHARED_SECRET="$("${PYTHON_BIN}" -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi
[[ "${SHARED_SECRET}" =~ ^[A-Za-z0-9_-]{32,256}$ ]] || die "Existing bridge secret is invalid; rerun with --rotate-secret"
secret_tmp="$(mktemp)"
printf '%s\n' "${SHARED_SECRET}" > "${secret_tmp}"
install -o root -g "${APP_USER}" -m 0640 "${secret_tmp}" "${SECRET_PATH}"
rm -f "${secret_tmp}"
unset SHARED_SECRET

upstream_ca_target=""
if [[ -n "${UPSTREAM_CA_CERT}" ]]; then
  upstream_ca_target="${CONFIG_DIR}/upstream-ca.pem"
  install -o root -g "${APP_USER}" -m 0640 "${UPSTREAM_CA_CERT}" "${upstream_ca_target}"
fi
config_tmp="$(mktemp)"
D1_UPSTREAM_URL="${UPSTREAM_URL}" D1_DISPLAY_NAME="${DISPLAY_NAME}" D1_UPSTREAM_CA_FILE="${upstream_ca_target}" \
  "${PYTHON_BIN}" - <<'PY' > "${config_tmp}"
import json
import os

print(json.dumps({
    "upstream_url": os.environ["D1_UPSTREAM_URL"],
    "display_name": os.environ["D1_DISPLAY_NAME"],
    "upstream_ca_file": os.environ.get("D1_UPSTREAM_CA_FILE", ""),
    "upstream_timeout_seconds": 8,
}, indent=2))
PY
install -o root -g "${APP_USER}" -m 0640 "${config_tmp}" "${CONFIG_PATH}"
rm -f "${config_tmp}"

printf '[5/8] Installing hardened systemd service...\n'
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=DiscoveryOne NTP acknowledgement bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_HOME}
Environment=CONFIG_PATH=${CONFIG_PATH}
Environment=SECRET_PATH=${SECRET_PATH}
ExecStart=${APP_HOME}/venv/bin/uvicorn app:app --host 127.0.0.1 --port ${LISTEN_PORT} --workers 2 --no-access-log --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectClock=true
ProtectHostname=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_INET AF_INET6
SystemCallArchitectures=native

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

printf '[6/8] Configuring Nginx TLS reverse proxy...\n'
cat > /etc/nginx/conf.d/discoveryone-ack.conf <<EOF
limit_req_zone \$binary_remote_addr zone=discoveryone_ack:10m rate=60r/m;
log_format discoveryone_ack '\$remote_addr - \$remote_user [\$time_local] "\$request_method \$uri \$server_protocol" \$status \$body_bytes_sent "\$http_user_agent"';

server {
    listen 80;
    server_name ${SERVER_NAME};
    access_log /var/log/nginx/discoveryone-ack-access.log discoveryone_ack;
    error_log /var/log/nginx/discoveryone-ack-error.log crit;
    add_header Referrer-Policy no-referrer always;
    return 308 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${SERVER_NAME};
    server_tokens off;

    ssl_certificate ${TLS_CERT};
    ssl_certificate_key ${TLS_KEY};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;

    access_log /var/log/nginx/discoveryone-ack-access.log discoveryone_ack;
    error_log /var/log/nginx/discoveryone-ack-error.log crit;

    client_max_body_size 1k;
    limit_req_status 429;
    limit_req_log_level notice;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header Content-Security-Policy "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;
    add_header Cache-Control "no-store" always;

    location = /ack {
        limit_req zone=discoveryone_ack burst=30 nodelay;
        limit_except GET { deny all; }
        proxy_pass http://127.0.0.1:${LISTEN_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 5s;
        proxy_read_timeout 15s;
    }

    location = /healthz {
        proxy_pass http://127.0.0.1:${LISTEN_PORT};
        proxy_set_header Host \$host;
    }

    location = / {
        proxy_pass http://127.0.0.1:${LISTEN_PORT};
        proxy_set_header Host \$host;
    }

    location / {
        return 404;
    }
}
EOF

if command -v getenforce >/dev/null 2>&1 && [[ "$(getenforce)" != "Disabled" ]]; then
  setsebool -P httpd_can_network_connect 1
fi
nginx -t
systemctl enable --now nginx
systemctl reload nginx

printf '[7/8] Configuring firewall when firewalld is active...\n'
if systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-service=http
  firewall-cmd --permanent --add-service=https
  firewall-cmd --reload
else
  printf 'WARNING: firewalld is not active. Ensure inbound TCP 80/443 is allowed by the host or external firewall.\n' >&2
fi

printf '[8/8] Verifying local services...\n'
systemctl is-active --quiet "${SERVICE_NAME}" || die "${SERVICE_NAME} did not start"
systemctl is-active --quiet nginx || die "nginx did not start"
curl --fail --silent --show-error "http://127.0.0.1:${LISTEN_PORT}/healthz" >/dev/null || die "Local bridge health check failed"

cat <<EOF

DiscoveryOne NTP acknowledgement bridge is running.

Public acknowledgement URL:
  https://${SERVER_NAME}/ack?token={token}

In DiscoveryOne, open System > Integrations, enable DMZ NTP Acknowledgment Server, and set:
  External acknowledgement bridge URL: https://${SERVER_NAME}/ack?token={token}
  Acknowledgement display URL:          https://${SERVER_NAME}/
  Acknowledgement bridge shared secret: run the command below and paste its output

Retrieve the generated bridge secret:
  sudo cat ${SECRET_PATH}

The DMZ host must be able to reach:
  ${UPSTREAM_URL}

The Nginx access log intentionally omits query strings so acknowledgement tokens are not logged.
EOF
