# DiscoveryOne

Internal eDiscovery workspace that tracks matters, custodians, holds, NTP/consent proofs, search requests, reports, tools, and system administration in one place. The frontend is Vite + React; the backend is FastAPI + Postgres with Caddy in front and ClamAV for upload scanning.

## What it does
- Case + request intake: requestors submit new cases/custodian/search/close requests; analysts/admins approve or decline with reasons and badges for pending work.
- Case workspace: manage custodians, legal names, claimants, holds (Email for O365/Google, OneDrive, Google Drive, Box, Dropbox, Slack, Zoom), NTP + consent status with proof uploads, searches, notes, and progress badges.
- Custodian views: roster and detail lookup with hold, NTP, and consent coverage across cases.
- Reporting: CSV exports for analysts, holds, consents, case summaries/aging, custodian gaps, and search execution.
- Tools: MSG/EML → ZIP conversion with upload/convert/download progress and a JSON audit report.
- Admin & security: user/role management, MFA enrollment, SMTP, branding, backups/restores, edge TLS via Caddy/ACME, and detailed audit logs (actors, IPs, payloads).

## Architecture
- `frontend/` – Vite + React SPA (secured routes, toasts, confirm dialogs, help system).
- `backend/` – FastAPI service with JWT sessions, CSRF/rate limiting, file scanning, backups, reports, and audit logging.
- `db` – Postgres (containerized).
- `clamav` – Virus scanning for uploads.
- `caddy` – Serves the built SPA and proxies `/api` to the backend over TLS.

## Quick start (Docker Compose)
1) Build and run: `docker compose up -d --build`
2) Visit `https://localhost:48080`. On a fresh database, DiscoveryOne redirects to `/setup` so you can configure HTTPS/TLS, the public app URL, institution, logo, integration defaults, and first sys-admin account. The default certificate is self-signed, so the browser warning is expected on first run.

The default Compose stack is self-bootstrapping:
- Postgres uses private Docker-network defaults unless overridden.
- `SECRET_KEY`, `SETTINGS_ENCRYPTION_KEY`, and `BACKUP_ENCRYPTION_KEY` are generated on first backend startup and persisted in the `backend-data` volume.
- Caddy listens on HTTPS host port `48080` by default to avoid colliding with NAS/admin interfaces and common app ports.

Create a repo-root `.env` only when you want container bootstrap overrides:
```
HTTPS_PORT=443
POSTGRES_PASSWORD=replace-with-strong-db-password
```

Front-end dev only? Use `cd frontend && npm install && npm run dev` and point `VITE_API_BASE` at your backend (`https://localhost:443/api`).
## Environment and Secrets
The universal build can start without a repo-root `.env` file. Keep `.env` for bootstrap-only overrides that must exist before the app starts, keep it out of Git, and run Compose from the repo root. Configure app-managed integration values in first-time setup or System settings.

Recommended deployment flow:
```
# Optional: cp .env.example .env, then edit only bootstrap/runtime overrides
docker compose up -d --build
```

Important notes:
- `docker-compose.yml` reads `.env` when it exists, and can also start without it using internal defaults.
- New deployments should enter integration connection values and secrets through setup or System settings; DiscoveryOne stores supported secret fields encrypted. `.env` integration variables are legacy/bootstrap fallbacks only.
- `SECRET_KEY` can be omitted; the backend generates and persists one in the Docker `backend-data` volume on first startup.
- `VITE_*` values are baked into the frontend build. Rebuild the frontend container after changing them.
- Backend-only env changes require a backend container restart.
- First-time setup is available only until a sys-admin exists, `initial_setup_completed` is stored, or `INITIAL_SETUP_COMPLETED=1` is set.
- Runtime admin settings such as uploaded logos and non-secret UI settings are stored under the Docker `backend-data` volume.
- Do not duplicate first-time setup values in `.env`; the template intentionally omits organization, public URL, allowed host, provider selection, and enabled integration fields so stored settings remain authoritative.

First-time setup stores these non-secret values internally:

| Setting area | Examples |
|---|---|
| Deployment | Public URL, allowed hosts, TLS mode |
| Institution | Organization name, short name, requestor domains, support email, SSO display name |
| Integrations | Provider selections and enabled workflows |
| Branding | Uploaded logo |
| Preservation | Built-in and custom preservation sources |

Setup and System store provider connection details internally, encrypting secret fields before writing them to the `backend-data` volume. Existing `.env` integration variables are still accepted as legacy fallbacks, but new deployments should enter these values in the app.

| Integration | App-managed values |
|---|---|
| Person lookup | CSV path or IDP/HR API URL/auth header/token |
| OIDC SSO | Issuer, client ID, client secret, scopes, redirect URIs |
| SMTP | Host, port, sender, optional username/password, TLS/SSL mode |
| ServiceNow | Base URL, auth type, username/password or OAuth client values, table, customer IDs, workflow routing |
| Purview | Tenant ID, client ID, client secret, Graph endpoints |
| Google Workspace | Customer ID, delegated admin email, service account client email/private key, Vault scopes |
| Box | Enterprise ID, client ID/secret, JWT key ID, private key, passphrase |
| Dropbox Business | Team ID, OAuth app key/secret, optional refresh token, preservation scopes |
| Zoom | Account ID, server-to-server OAuth client ID/secret, admin scopes |
| Microsoft Intune | Tenant ID, client ID/secret, Graph base, Graph scopes |
| Jamf | Jamf Pro URL, OAuth client credentials or username/password |
| Microsoft Defender | Tenant ID, client ID/secret, Defender API base, scopes |
| CrowdStrike | Falcon cloud API base, client ID/secret |
| DocuSign | Account/template/auth values, private key, Connect HMAC keys, and consent template tab mappings |
| Slack | Legal Holds token, API base, optional OAuth callback values |

## Purview integration
To enable the "Create case in Purview" action within a case, enable Purview in setup and enter the tenant ID, client ID, and client secret in the wizard. The app stores the client secret encrypted.

Purview export sync:
- DiscoveryOne can poll Purview exports on a schedule configured in Setup/System and manually from the Case Detail -> Purview modal via **Check for exports**.
- Scheduled polling includes: (a) cases with active/pending Purview holds, and (b) cases where the requestor belongs to configured groups from the Purview integration settings even when no hold exists.
- When an export name matches a DiscoveryOne search name pattern (`Search`/`Export` variants), DiscoveryOne marks that search as search+export performed.
- If this auto-mark happens while assigned custodians still lack consent, the search is flagged as exported without consent (shown in red in the Searches tab).
- If exports exist but there are no searches, or export names do not match searches, DiscoveryOne emails analysts/sys-admins with the findings.

Search delivery reminders:
- For open cases, if one or more searches are marked Export=`performed` and Delivery!=`performed`, DiscoveryOne sends a reminder to the assigned analyst.
- Reminder cadence is configured in System > Notifications. The default is weekly per case, and administrators can change the interval, scheduler check cadence, and batch size without editing `.env`.
- Each email is one-per-case and includes all exported-not-delivered searches with their search details.

## Google Workspace integration
Google Workspace credential storage is configuration-ready, but this build does not yet include an executable Google Vault adapter. Administrators may store the customer ID, delegated Vault admin email, and service account credentials for future use; Gmail and Google Drive preservation must be tracked manually until that adapter is implemented. Google Drive can still be enabled as a manual preservation source.

## Box integration
Enable Box in setup when custodians may require Box legal holds. Create a custom Box app with JWT authentication in the Box Admin Console, authorize it for the enterprise, and grant the legal hold permissions your Box governance model requires. Enter the enterprise ID, client ID/secret, JWT public key ID, private key, and passphrase in setup; secrets are stored encrypted.

## DocuSign e-signature integration
Enable DocuSign in setup when consent requests should be sent through a DocuSign template. Enter the account/template/auth values and private key in setup or System settings; secret fields are stored encrypted. DiscoveryOne also lets administrators map the consent template text tab labels for case name, record type, start date, and end date so organizations can use their own DocuSign template field names without editing code.

## Additional preservation and endpoint integrations
Setup and System can also store encrypted configuration for Dropbox Business, Zoom, Microsoft Intune, Jamf, Microsoft Defender, CrowdStrike, DocuSign Connect, and NTP acknowledgement bridges. These are configuration-ready integrations for organizations that preserve enterprise file stores, meeting/chat platforms, or endpoint evidence; live API execution should be implemented provider-by-provider before marking any of those workflows fully automated.

## Slack legal holds integration
To enable Slack hold creation/release when custodians are approved with `holds_slack`:

Enable Slack in setup and enter the Legal Holds token in the wizard. The app stores the token encrypted.

Internal callback endpoint implemented by this app:

- `GET /api/slack/oauth/callback`

Admin helper endpoint to generate signed OAuth state + authorize URL:

- `GET /api/slack/oauth/authorize_url`

## ServiceNow integration
The backend can create external tickets for configured legal hold and restore workflows. Enable a ticket provider in setup and enter its base URL, auth type, credentials, and table/mapping values in the wizard. Passwords and OAuth client secrets are stored encrypted.

## Notes
- Upload scanning is enabled by default via the `clamav` container; set `UPLOAD_SCAN_DISABLE=1` only in trusted dev environments.
- The ClamAV service persists `/var/lib/clamav`, explicitly starts `freshclam`, and checks for definition updates with `FRESHCLAM_CHECKS` times per day. Runtime health exposes the loaded signature version/date and marks definitions stale when they exceed `CLAMAV_SIGNATURE_MAX_AGE_HOURS`.
- SMTP and branding assets can be configured from the System area after you authenticate.
- Sys admin / analyst alerts can post to Microsoft Teams. Configure the webhook and per-event messages in System > Notifications; the webhook is encrypted in app-managed settings.
- NTP acknowledgement proxy: `DiscoveryOne_DMZ.sh` builds a small DMZ host that receives one-click acknowledgement hits from NTP emails (via `/ack?token=...`) and relays them to the internal API. It provisions a FastAPI + Gunicorn app behind Nginx with TLS, validates a shared secret, and returns a branded confirmation page so recipients know their preservation notice was recorded.

### NTP acknowledgement proxy setup (DMZ)
1) Copy `DiscoveryOne_DMZ.sh` to your DMZ host (RHEL-based), make it executable, and edit the variables at the top: `UPSTREAM_URL` (your internal `.../api/ntp/ack/automate` endpoint), `SHARED_SECRET`, `SERVER_NAME`, `TLS_CERT`/`TLS_KEY`, and optional `RETURN_HTML`.
2) Run the script with sudo (`sudo ./DiscoveryOne_DMZ.sh`). It installs Python/Nginx, builds the FastAPI + Gunicorn app under a dedicated user, configures TLS, firewalld, and sets up systemd + Nginx.
3) Point DNS for `SERVER_NAME` at the DMZ host. In DiscoveryOne, open System > NTP Templates and set the Power Automate acknowledgement URL to `https://SERVER_NAME/ack?token={token}` and the shared secret to match `SHARED_SECRET` so outbound NTP links work end-to-end.













