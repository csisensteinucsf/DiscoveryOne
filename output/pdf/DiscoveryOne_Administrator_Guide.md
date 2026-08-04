# DiscoveryOne Administrator Guide

## Universal Build - Installation, First-Time Configuration, Integrations, and Operations

**Guide date:** August 3, 2026  
**Repository:** https://github.com/csisensteinucsf/DiscoveryOne  
**Audience:** eDiscovery managers, application administrators, infrastructure teams, identity teams, and integration owners  
**Deployment:** Docker Compose with React, FastAPI, PostgreSQL, Caddy, and ClamAV

> **Release posture:** Treat the current universal build as a pilot/beta release. Validate it in a non-production environment with your institution's identity, mail, preservation, ticketing, backup, and security controls before using it for active legal matters.

This guide starts with an empty server and ends with a running, validated DiscoveryOne deployment. It also explains every integration exposed by the current application.

<!-- PAGEBREAK -->

## 1. How to Use This Guide

Follow Parts I through IV in order:

1. Plan the deployment and collect prerequisites.
2. Install Docker and obtain the source.
3. Start the stack and complete the nine-step wizard.
4. Perform post-installation tests before inviting users.

Part V explains all integrations. Do not enable every integration simply because it appears. Enable only products your organization uses and only after the platform owner has supplied a dedicated service identity and least-privilege permissions.

### 1.1 Capability labels

| Label | Meaning |
|---|---|
| Automated | DiscoveryOne contains an executable adapter or active workflow. |
| Optional automated | Automation works when enabled; manual tracking remains available when disabled. |
| Configuration only | DiscoveryOne stores fields for a future adapter but does not call that product API in this build. |
| Planned | Deployment guidance is included, but the adapter is not executable in this build. |
| Built in | Part of the Compose stack; no external tenant/API account normally required. |
| Manual tracking | Staff update status without DiscoveryOne changing the source system. |

### 1.2 Security rules

- Never commit `.env`, certificates, keys, backups, logs, or application data to Git.
- Create a separate service identity for each integration.
- Grant only permissions required by enabled workflows.
- Store integration secrets through **System > Integrations**. Supported secret fields are encrypted.
- Keep `admin` as a recovery account; use named sys-admin accounts normally.
- Require HTTPS.
- Back up PostgreSQL plus persistent volumes and upload folders.
- Test restore before production.
- Review logs and ClamAV after installation and each upgrade.

<!-- PAGEBREAK -->

# Part I - Deployment Planning

## 2. Architecture

| Service | Purpose | User exposure |
|---|---|---|
| `caddy` | HTTPS, headers, frontend, `/api` proxy | Host TCP 48080 by default |
| `frontend` | Builds React output | No direct host port |
| `backend` | FastAPI, migrations, schedulers, integrations, audit | Docker network only |
| `db` | PostgreSQL | Docker network only |
| `clamav` | Upload malware scan/signature updates | Docker network only |

The optional `e2e` service runs browser tests and is not part of a normal startup.

### 2.1 Persistent data inventory

| Location | Contents | Priority |
|---|---|---|
| `pgdata` volume | PostgreSQL files | Critical |
| `backend-data` volume | generated keys, encrypted settings, setup state, assets | Critical |
| `caddy-data` volume | Caddy internal CA and TLS data | High |
| `caddy-config` volume | Caddy runtime configuration | Medium |
| `clamav-db` volume | signatures | Low/rebuildable |
| `frontend-dist` volume | compiled frontend | Low/rebuildable |
| `backups/` | encrypted DB backups | Critical/off-host copy |
| `case_request_uploads/` | request files and consent proofs | Critical |
| `logs/` | app, audit, backup logs | High |

An in-app database backup does not replace backups of `backend-data` and `case_request_uploads`.

### 2.2 Network matrix

| Direction | Port/protocol | Purpose |
|---|---|---|
| Users to DiscoveryOne | TCP 48080 HTTPS (default) | Web access |
| Users to DiscoveryOne | TCP 443 HTTPS (optional mapping) | Standard production URL |
| Server outbound | TCP 443 | images, OIDC, SaaS APIs |
| Backend to mail relay | TCP 25/465/587 | SMTP |
| DMZ inbound | TCP 443 | Public NTP acknowledgements |
| DMZ outbound | TCP 443 | Internal acknowledgement API |

Never expose PostgreSQL, backend port 8000, or ClamAV port 3310 publicly.

## 3. Platform and Capacity

### 3.1 Pilot sizing

| Resource | Small pilot | Larger campus pilot |
|---|---|---|
| CPU | 4 cores | 8+ cores |
| RAM | 8 GB | 16+ GB |
| Free disk | 50 GB | 200+ GB with monitoring |
| Architecture | x86-64 recommended | x86-64 recommended |
| Host | Supported Linux/NAS containers | Managed Linux VM preferred |

ClamAV is the largest startup memory/download consumer. Actual storage depends on attachments, imports, backups, and logs.

### 3.2 Required prerequisites

- Docker Engine or compatible NAS container platform.
- Docker Compose v2 (`docker compose`).
- Git or GitHub ZIP transfer.
- DNS control.
- Trusted certificate or private-CA distribution plan.
- SMTP relay if mail is used.
- Admin access to each external product being integrated.

### 3.3 Pre-install worksheet

Collect:

- final HTTPS URL and server IP;
- DNS name and host port;
- full organization and short campus/unit names;
- allowed requestor domains and explicit exceptions;
- support email;
- app name/tagline/logo;
- case naming choice;
- preservation sources;
- first admin password;
- OIDC details;
- SMTP details;
- integration owners, licensing, and credentials.

## 4. TLS Strategy

DiscoveryOne must run through HTTPS.

### 4.1 Default Caddy internal certificate

Use for first run/testing or a managed private-CA deployment.

- Caddy creates/renews an internal certificate.
- Browsers warn until clients trust the Caddy root.
- Traffic is still encrypted.

Export the root after startup:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./discoveryone-caddy-root.crt
```

Distribute it only through an approved certificate/device-management process.

### 4.2 Organization-issued certificate

The certificate SAN must contain the exact DNS hostname. Use PEM chain and matching unencrypted PEM key.

The wizard stores uploaded TLS files in backend settings, but the current Compose stack does not automatically mount them into Caddy. A production certificate therefore also requires Caddy mounts/configuration.

Host layout:

```text
deploy/tls/fullchain.pem
deploy/tls/privkey.pem
```

Add to the Caddy service volumes:

```yaml
      - ./deploy/tls/fullchain.pem:/etc/caddy/tls/fullchain.pem:ro
      - ./deploy/tls/privkey.pem:/etc/caddy/tls/privkey.pem:ro
```

Replace the internal TLS block in `Caddyfile`:

```caddyfile
:443 {
    tls /etc/caddy/tls/fullchain.pem /etc/caddy/tls/privkey.pem
```

Keep the remaining handlers/headers unchanged. Validate:

```bash
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
docker compose restart caddy
curl -v https://discoveryone.example.edu:48080/
```

### 4.3 Public ACME certificate

Caddy can automate a public certificate when DNS points to the host, ports 80/443 reach Caddy, the site address is the public hostname, and `caddy-data` persists. Change the site address from `:443` to the hostname and remove the internal issuer. Review https://caddyserver.com/docs/automatic-https before using this option.

<!-- PAGEBREAK -->

# Part II - Installation

## 5. Obtain the Source

```text
https://github.com/csisensteinucsf/DiscoveryOne
```

### 5.1 Linux with Git

```bash
sudo mkdir -p /opt/discoveryone
sudo chown "$USER":"$USER" /opt/discoveryone
git clone https://github.com/csisensteinucsf/DiscoveryOne.git /opt/discoveryone
cd /opt/discoveryone
test -f docker-compose.yml
test -f Caddyfile
test -f .env.example
```

### 5.2 ZIP method

1. Open GitHub.
2. Select **Code > Download ZIP**.
3. Transfer ZIP to server.
4. Extract to a permanent application folder.
5. Enter the folder containing `docker-compose.yml`.

### 5.3 QNAP NAS

1. Install/start **Container Station**.
2. Create/select `/share/SSD_Container/DiscoveryOne`.
3. Enable SSH temporarily if policy permits.
4. Connect:

```bash
ssh admin@QNAP_IP_ADDRESS
```

5. Obtain source:

```bash
cd /share/SSD_Container
git clone https://github.com/csisensteinucsf/DiscoveryOne.git DiscoveryOne
cd DiscoveryOne
```

If Git is unavailable, extract the GitHub ZIP into the share.

6. Verify and prepare host folders:

```bash
docker compose version
mkdir -p logs backups case_request_uploads
ls -ld logs backups case_request_uploads
```

Use QNAP ACLs to grant container write access. Do not make the entire repository world-writable. For `Permission denied`, fix only the named folder and recreate backend.

## 6. Bootstrap Environment

DiscoveryOne starts without `.env`. For production/pilot, create it before PostgreSQL initializes:

```bash
cp .env.example .env
chmod 600 .env
```

Minimum review:

```dotenv
HTTPS_PORT=48080
POSTGRES_USER=ediscovery
POSTGRES_PASSWORD=REPLACE_WITH_A_LONG_RANDOM_VALUE
POSTGRES_DB=ediscovery
HEALTHCHECK_SECRET=REPLACE_WITH_A_DIFFERENT_LONG_RANDOM_VALUE
```

Generate secrets with an approved password manager or:

```bash
openssl rand -base64 36
```

Rules:

- Set DB password before first startup. Later environment changes do not update an existing database user's password.
- Do not duplicate UI-managed organization/provider/integration values in `.env`.
- `SECRET_KEY`, `SETTINGS_ENCRYPTION_KEY`, and `BACKUP_ENCRYPTION_KEY` auto-generate into `backend-data`.
- Never delete `backend-data` casually.
- Keep `.env` out of Git.

Review runtime controls:

- restrict `TRUSTED_PROXY_IPS`;
- keep `RATE_LIMITS=1`;
- keep `UPLOAD_SCAN_DISABLE=0`;
- align session timeout with policy;
- adjust upload/import limits only for documented needs;
- size log rotation for storage/retention.

## 7. Start

```bash
docker compose up -d --build
docker compose ps
```

First run downloads images, builds frontend, updates ClamAV, initializes PostgreSQL, and migrates schema.

Expected healthy/running services: db, clamav, backend, frontend output, caddy.

Diagnostics:

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 db
docker compose logs --tail=200 clamav
docker compose logs --tail=200 caddy
docker compose port caddy 443
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
curl -vk https://127.0.0.1:48080/
```

This should report HTTP sent to HTTPS:

```bash
curl -v http://127.0.0.1:48080/
```

## 8. One-Time Setup Code

```bash
docker compose logs backend | grep "One-time setup code"
```

Expected:

```text
[setup] One-time setup code: <random-value>
[setup] Enter this code on the Administrator step.
```

It is not the admin password. If needed:

```bash
docker compose restart backend
docker compose logs --tail=100 backend
```

## 9. Open Setup

```text
https://SERVER_IP_OR_NAME:48080
```

With default TLS, accept the warning only after verifying the expected host. The app redirects to `/setup`.

<!-- PAGEBREAK -->

# Part III - Nine-Step Wizard

## 10. Deployment

### Public App URL

Complete HTTPS origin, including nonstandard port:

```text
https://discoveryone.example.edu
https://discoveryone.example.edu:48080
```

Do not use Docker name `caddy`; do not add `/api`.

### Allowed Hostnames

```text
discoveryone.example.edu, discoveryone.internal.example.edu
```

No schemes, paths, or wildcards. Add an IP only if intentionally used.

### TLS

- Self-signed: first run/private CA.
- Uploaded: stores files; complete Section 4.2 for Caddy.
- Common Name: browser DNS name/certificate SAN.
- Certificate: `.crt`, `.cer`, `.pem`, with needed intermediates.
- Key: matching `.key`/`.pem`, protected.

## 11. Institution

- **Organization Name:** full name; example `University of California`.
- **Short Name:** campus/unit; example `UCSF`.
- **Allowed Requestor Domains:** `example.edu, law.example.edu`; empty means any domain.
- **Exceptions:** full approved external addresses, one per line.
- **Support Email:** user help contact.
- **SSO Display Name:** e.g. `Campus Single Sign-On`.

## 12. Administrator

1. Paste setup code.
2. Username remains `admin`.
3. Use a random 12+ character password.
4. Confirm it.

After setup create named admins, enroll MFA, and vault `admin` for recovery.

## 13. Branding

- App Name: login/navigation/browser/notifications.
- Tagline: sidebar description.
- Logo: PNG/JPEG; D1 logo is default.

## 14. Case Naming

| Mode | Behavior |
|---|---|
| Legal Case Name | Legal name is case name; duplicates receive suffix. |
| Created Date + Sequence | Generated name; legal name stored separately. |
| Color Naming | Legacy yearly color sequence. |

Legal Case Name is recommended for most new deployments.

## 15. Preservation

Built-ins: Email (default), OneDrive (default), Google Drive, Box (default), Dropbox, Slack (default), Zoom.

All sources allow manual status tracking without integration.

Custom source examples:

```text
Network Home Drive
Research File Share
GitHub Enterprise
Physical Device
```

Each line becomes one tracking item.

## 16. Person Lookup

Person lookup searches custodians. SSO authenticates app users.

| Provider | Use |
|---|---|
| None/manual | Staff types details. |
| CSV/static | Periodic HR/identity export. |
| IDP/HR API | Live HTTPS JSON search. |

### CSV

Typical container path:

```text
/data/system/person_lookup/people.csv
```

Recommended headers:

```text
display_name,first_name,middle_name,last_name,email,employee_id,department,title,separation_date,separation_status
```

Secure the export and assign a refresh owner/frequency.

### IDP/HR API

Collect URL, method, query/email parameters, results path, timeout, auth header/value, and field mappings.

```text
URL: https://identity.example.edu/api/people/search
Method: GET
Query parameter: query
Email parameter: email
Results path: results
Auth header: Authorization
Auth value: Bearer <service-token>
```

Example:

```json
{
  "results": [{
    "profile": {"displayName": "Alex Example", "givenName": "Alex", "familyName": "Example"},
    "contact": {"primaryEmail": "alex.example@example.edu"},
    "employment": {
      "employeeId": "10001234",
      "department": "Legal",
      "title": "Analyst",
      "endDate": null,
      "status": "active"
    }
  }]
}
```

Map display name, names, email, Employee ID, department, title, separation date/status.

Acceptance test:

1. Search by name, email, Employee ID.
2. Verify active title/department.
3. Verify separated employee.
4. Verify unknown person.
5. Verify limit/timeout.
6. Ensure secrets/full HR responses are not logged.

## 17. Integrations

### OIDC authentication

Enter issuer, client ID/secret, and `openid profile email`.

Register:

```text
https://YOUR_HOST/api/auth/oidc/callback
https://YOUR_HOST/api/auth/oidc/logout/callback
```

Include `:48080` if public URL uses it.

### Workflows

Enable only ready products. Secrets are encrypted. Configuration-only cards do not automate preservation.

## 18. Review

Verify URL/TLS, organization, admin, branding, case naming, sources, person lookup, SMTP, integrations. Select **Complete Setup** once. Setup locks and future changes are made under **System**.

<!-- PAGEBREAK -->

# Part IV - Post-Installation

## 19. Accounts and MFA

1. Sign in as `admin`.
2. **System > Users**.
3. Create at least two named sys-admins.
4. Enroll MFA.
5. Create analyst/requestor accounts.
6. Vault recovery admin.

| Role | Use |
|---|---|
| Sys Admin | System/users/integrations |
| Analyst | Case/workflow work |
| Tech | Technical workflow group |
| Requestor | Submit permitted requests |
| Tester | Controlled testing |

## 20. Deployment/Branding

In **System > Branding**, confirm app name/tagline/logo, Public App URL, Allowed Hosts. Generate a link and verify final URL.

## 21. SMTP

1. Enter host, port, sender.
2. Credentials only if required.
3. STARTTLS (often 587) or implicit SSL (often 465), not both.
4. Save.
5. Send test.
6. Confirm sender, links, delivery, and safe error logging.

## 22. Notifications

Configure event emails, subjects/bodies, consent completion, weekly pending schedule/timezone, and optional restricted Teams webhook. Save and trigger safe tests.

## 23. Backups

1. Confirm encryption healthy.
2. Enable automatic backups.
3. Interval default 6 hours.
4. Retention default 48 hours; align with policy.
5. Run now.
6. Confirm encrypted file in `backups/`.
7. Copy off-host.
8. Plan isolated restore.

Also back up `backend-data`, uploads, and TLS.

## 24. ClamAV

Built in; no account or API key. In **System > ClamAV Monitor**, confirm Ready, current definitions, versions, and acceptable age.

## 25. Baseline Test

1. Create synthetic analyst/requestor/case.
2. Add active and separated custodians.
3. Track every source pending/hold/released.
4. Verify manual tracking without integrations.
5. Test NTP/consent email.
6. Upload benign proof.
7. Complete search.
8. Add note/attachment.
9. Export report.
10. Review audit.
11. Run/download backup.
12. Test login/SSO/MFA.

<!-- PAGEBREAK -->

# Part V - Integration Guide

## 26. Capability Matrix

| Integration | Status | Use |
|---|---|---|
| OIDC SSO | Automated | Authentication |
| Person Lookup | Automated | Identity lookup |
| SMTP | Automated | Email |
| Teams Webhook | Automated | Alerts |
| ServiceNow | Automated | Tickets |
| Purview | Automated | eDiscovery/holds/searches |
| Microsoft Graph Email Intake | Planned | Future email-to-case mailbox monitoring |
| Box | Automated | Legal holds |
| Slack | Optional automated | Legal Holds API/manual fallback |
| DocuSign | Automated | Consent signing/callbacks |
| Log Shipping | Automated | Logs to SharePoint |
| AI Assistant | Optional automated | OpenAI-compatible features |
| DMZ NTP Bridge | Optional automated | Public acknowledgements |
| Google Workspace | Configuration only | Future Vault adapter |
| Dropbox | Configuration only | Future adapter |
| Zoom | Configuration only | Future adapter |
| Intune | Configuration only | Future endpoint adapter |
| Jamf | Configuration only | Future endpoint adapter |
| Defender | Configuration only | Future evidence adapter |
| CrowdStrike | Configuration only | Future evidence adapter |
| ClamAV | Built in | Malware scanning |

## 27. OIDC SSO - Automated

### IdP preparation

1. Create confidential web application.
2. Restrict approved groups.
3. Register exact login/logout callbacks.
4. Enable authorization-code flow.
5. Provide stable subject, email, names.
6. Create/track secret expiration.
7. Record issuer exposing `/.well-known/openid-configuration`.

Entra example:

```text
https://login.microsoftonline.com/TENANT_ID/v2.0
```

Reference: https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc

### DiscoveryOne

Set SSO Provider to OIDC; enter issuer, client ID/secret, scopes; save.

### Validate

Test in private browser before ending the only admin session. Test permitted/denied users, mapping, logout, and audit. Keep `admin` local.

## 28. Person Lookup - Automated

Use Section 16. API requires dedicated read-only identity, narrow fields, HTTPS/token auth, mappings, rotation, latency monitoring. CSV requires protected export, persistent path, refresh owner, duplicate/missing-data tests.

The user-facing external identifier is always **Employee ID**.

## 29. SMTP - Automated

Mail-team tasks:

1. Dedicated sender.
2. Host/port/encryption/auth.
3. Permit server IP if relay.
4. SPF/DKIM/DMARC as required.
5. Restrict relay identity.

Fields: Host, Port, Timeout, From, optional Username/Password, STARTTLS, SSL. Validate test email and one real template.

## 30. Teams Notifications - Automated

Configured in **System > Notifications**:

1. Create approved webhook/workflow in restricted channel.
2. Paste HTTPS URL.
3. Select events/templates.
4. Save/test.

Treat webhook as a secret.

## 31. ServiceNow - Automated

### Prepare

1. Dedicated integration user/OAuth client.
2. Grant selected table or Import Set create/read/update only.
3. Decide Table API vs Import Set.
4. Create/test transform map if needed.
5. Confirm required fields, assignment groups, states, employee/customer identifiers.
6. Permit server outbound IP.

Auth:

- Basic dedicated service user.
- OAuth client ID/secret, optional scope/token URL.

Common token URL:

```text
https://INSTANCE.service-now.com/oauth_token.do
```

Fields: Base URL, Auth Type, credentials, token URL/scope, Create/Status Tables, Import Set toggle, Source System, Default/App Customer IDs.

Configure ticket categories, groups, descriptions, release keywords, and field mappings in System ticket workflows.

Validate ticket creation/routing/mapping/link/status sync/error path and confirm no unrelated table access.

## 32. Microsoft Purview - Automated

DiscoveryOne uses app-only Microsoft Graph calls for eDiscovery cases, custodians, Exchange and OneDrive sources, legal holds, searches, operations, and export-status matching. Use a dedicated single-tenant Entra registration named for the Purview integration. Do not reuse the OIDC sign-in or email-intake registration.

### 32.1 Licensing and administrative prerequisites

- Confirm the tenant has the Microsoft Purview and eDiscovery licensing required for every enabled workflow.
- App-only eDiscovery Graph access requires cases with premium features enabled.
- The administrator creating the registration needs permission to register applications and grant tenant-wide admin consent.
- Human staff using the Purview portal still need the appropriate eDiscovery Manager or eDiscovery Administrator role.
- Purview user-role assignments do not replace Graph application permissions, and delegated user permissions do not replace app-only permissions.

References:

- https://learn.microsoft.com/en-us/purview/edisc-ref-api-guide
- https://learn.microsoft.com/en-us/purview/edisc-permissions
- https://learn.microsoft.com/en-us/graph/api/security-casesroot-post-ediscoverycases?view=graph-rest-1.0

### 32.2 Register the Purview application

1. Open Microsoft Entra admin center and select **Entra ID > App registrations > New registration**.
2. Enter a descriptive name such as `DiscoveryOne Purview`.
3. Select **Accounts in this organizational directory only**.
4. Leave Redirect URI empty. This adapter uses the OAuth client-credentials flow and does not perform an interactive sign-in.
5. Record the **Directory (tenant) ID** and **Application (client) ID**.
6. Open **Certificates & secrets** and create a dedicated client secret for the current DiscoveryOne build.
7. Copy the secret **Value**, not the secret ID, and record its owner and expiration in the institution credential-management system.
8. Do not place the secret in Git, documentation, screenshots, tickets, or chat. Enter it only in **System > Integrations > Purview**.

### 32.3 Configure app-only authorization

DiscoveryOne uses the OAuth client-credentials flow. The Entra permissions and the Purview role assignments below are both required; completing only one side does not authorize the integration.

#### Microsoft Graph application permissions

Open **API permissions > Add a permission > Microsoft Graph > Application permissions** and add:

| Permission | Requirement | Why DiscoveryOne uses it |
|---|---|---|
| `eDiscovery.Read.All` | Required by Microsoft's app-only eDiscovery setup | Reads cases, custodians, sources, holds, searches, operations, and export status. |
| `eDiscovery.ReadWrite.All` | Required | Creates and updates eDiscovery cases, custodians, sources, holds, searches, and related workflow state. |
| `User.Read.All` | Required by DiscoveryOne | Resolves custodian object IDs, UPNs, primary mail addresses, and proxy addresses used for Exchange and OneDrive source matching. |
| `Sites.Read.All` | Required when OneDrive or SharePoint sources are enabled | Reads the tenant root-site metadata and resolves personal or SharePoint site resources used by the eDiscovery source API. |

Select **Grant admin consent** after adding the permissions. Confirm that every row is an **Application** permission and shows **Granted** for the tenant.

Do not add delegated `User.Read`; client-credentials tokens do not use delegated permissions. Do not add SharePoint or Microsoft Graph `Sites.FullControl.All`, `Sites.ReadWrite.All`, `Files.Read.All`, `Mail.Read`, or `Mail.Send` for this adapter. DiscoveryOne resolves users and read-only site metadata, while eDiscovery performs the preservation operations.

`Sites.Read.All` must be added under **Microsoft Graph**, not under the SharePoint API.

#### Register the service principal with Purview

Microsoft also requires the app's service principal to be registered with the compliance PowerShell endpoint and assigned Purview eDiscovery roles.

1. In **Entra ID > Enterprise applications**, open the `DiscoveryOne Purview` enterprise application and record its **Object ID**. Do not use the similarly named application-object ID from **App registrations**.
2. Run the following as an administrator authorized to manage Purview eDiscovery. Replace every placeholder.

```powershell
Install-Module ExchangeOnlineManagement -Scope CurrentUser
Import-Module ExchangeOnlineManagement
Connect-IPPSSession

New-ServicePrincipal `
  -AppId '<APPLICATION-CLIENT-ID>' `
  -ObjectId '<ENTERPRISE-APP-SERVICE-PRINCIPAL-OBJECT-ID>' `
  -DisplayName 'DiscoveryOne Purview'

Get-ServicePrincipal

Add-RoleGroupMember `
  -Identity 'eDiscoveryManager' `
  -Member '<ENTERPRISE-APP-SERVICE-PRINCIPAL-OBJECT-ID>'

Get-RoleGroupMember -Identity 'eDiscoveryManager'

Add-eDiscoveryCaseAdmin `
  -User '<ENTERPRISE-APP-SERVICE-PRINCIPAL-OBJECT-ID>'

Get-eDiscoveryCaseAdmin
```

3. Verify that `Get-ServicePrincipal`, `Get-RoleGroupMember`, and `Get-eDiscoveryCaseAdmin` show the new service principal.
4. Allow time for Microsoft permission and role changes to propagate before testing.

Reference: https://learn.microsoft.com/en-us/graph/security-ediscovery-appauthsetup

### 32.4 Configure DiscoveryOne

In **System > Integrations > Purview**, configure:

- Enabled state and provider selection.
- Directory (tenant) ID.
- Application (client) ID.
- Client secret value.
- OAuth scope, normally `https://graph.microsoft.com/.default`.
- Microsoft Graph beta, v1.0, and security API base URLs; retain defaults unless Microsoft or the tenant requires a documented override.
- Request timeout and retry controls.
- OneDrive source limits and missing-email behavior.
- Source-addition and status-delay settings.
- Export polling enablement, schedule, timezone, and eligible requestor groups.

Use **Test connection** before enabling automated workflows. A token being issued proves only authentication; it does not prove that Purview licensing, application permissions, or each workflow endpoint is authorized.

### 32.5 Purview validation sequence

Use a non-production test matter and synthetic custodians.

1. Acquire a token and confirm the token contains the expected application roles.
2. Create or locate an eDiscovery premium case.
3. Add an Exchange custodian and confirm its Entra identity resolves correctly.
4. Add an Exchange mailbox source.
5. Add a OneDrive source and confirm site resolution succeeds.
6. Create a legal hold, add sources, and verify hold status.
7. Release one source and then release/delete the test hold.
8. Create or synchronize a search.
9. Verify operation and export-status polling.
10. Confirm DiscoveryOne audit records contain the action and provider identifiers but no access token or client secret.
11. Remove a test permission only in a lab and confirm the connection test reports an actionable `401` or `403` rather than silently succeeding.

Troubleshooting:

- `401` normally indicates an incorrect tenant/client credential, expired secret, invalid scope, or wrong token authority.
- `403` normally indicates missing admin consent, missing Graph application permission, unsupported licensing, non-premium app-only case access, or tenant policy.
- User lookup failures indicate `User.Read.All`, alias, UPN, or proxy-address issues.
- OneDrive lookup failures indicate `Sites.Read.All`, an invalid personal-site URL, site provisioning, or cross-geo access issues.
- Retest after Microsoft API, licensing, consent, conditional-access, or Purview role changes.

### 32.6 Export package download permission

The current adapter observes eDiscovery operations and matches export activity to DiscoveryOne searches. It does not download export packages. Do not grant the separate `MicrosoftPurviewEDiscovery` application permission `eDiscovery.Download.Read` unless package downloading is implemented and enabled in a future release.

## 32A. Microsoft Graph Email Intake - Planned

> **Current status:** This section is deployment preparation for the planned email-to-case integration. The current build does not yet monitor a mailbox, and administrators should not expect these values to appear in System until that integration is released.

The planned adapter will poll one Exchange Online mailbox with Microsoft Graph delta queries, match messages against administrator-defined templates, scan accepted attachments with ClamAV, and create a pending Case Request for human review. Use a dedicated registration named `DiscoveryOne Email Intake`; do not reuse the Purview or OIDC registration.

### 32A.1 Prepare the mailbox

1. Create a dedicated shared mailbox such as `ediscovery-intake@example.edu`.
2. Restrict interactive mailbox membership to the smallest operational group.
3. Decide whether to monitor `Inbox` or a dedicated child folder.
4. If transport or inbox rules route messages, document and test every rule and preserve an unmatched-message path.
5. Disable automatic external forwarding unless separately approved.
6. Apply the institution's retention, litigation-hold, audit, and data-loss-prevention requirements to the intake mailbox.
7. Define allowed sender domains and explicit sender exceptions.
8. Define maximum message and attachment sizes and the handling of encrypted or password-protected attachments.
9. Decide whether processed messages remain untouched. Read-only processing is recommended because DiscoveryOne will maintain its own idempotency ledger.

### 32A.2 Register the mailbox application

1. Create a single-tenant Entra app named `DiscoveryOne Email Intake`.
2. Leave Redirect URI empty because the integration uses client credentials.
3. Record the tenant ID, client ID, and **Enterprise application service-principal Object ID**.
4. Use a certificate when the released adapter supports it. For a lab or a secret-based release, create a dedicated client secret and record its value and expiration.
5. Do not add delegated permissions.

### 32A.3 Choose one mailbox authorization model

**Lab-only, fastest setup:** Add Microsoft Graph application `Mail.Read` and grant admin consent. This permission is tenant-wide and can read every mailbox, so use it only in an isolated lab tenant or with explicit security approval.

**Production, recommended:** Use Exchange Online RBAC for Applications to assign `Application Mail.Read` only to the intake mailbox. Do not also leave an organization-wide Entra `Mail.Read` grant on the same service principal; Entra grants and Exchange RBAC grants are additive.

`Mail.ReadBasic` is insufficient because it excludes message bodies and attachments. Use `Application Mail.ReadWrite` only if a future configuration explicitly moves, marks, or deletes processed messages. `Mail.Send` is not required.

### 32A.4 Configure mailbox-scoped Exchange RBAC

Run these commands as an authorized Exchange Online administrator. Replace every placeholder and verify the mailbox alias before creating the scope.

```powershell
Install-Module ExchangeOnlineManagement -Scope CurrentUser
Connect-ExchangeOnline

New-ServicePrincipal `
  -AppId '<APPLICATION-CLIENT-ID>' `
  -ObjectId '<ENTERPRISE-APP-SERVICE-PRINCIPAL-OBJECT-ID>' `
  -DisplayName 'DiscoveryOne Email Intake'

New-ManagementScope `
  -Name 'DiscoveryOne Intake Mailbox' `
  -RecipientRestrictionFilter "Alias -eq 'ediscovery-intake'"

New-ManagementRoleAssignment `
  -Name 'DiscoveryOne Intake Mail Read' `
  -Role 'Application Mail.Read' `
  -App '<ENTERPRISE-APP-SERVICE-PRINCIPAL-OBJECT-ID>' `
  -CustomResourceScope 'DiscoveryOne Intake Mailbox'

Test-ServicePrincipalAuthorization `
  -Identity '<APPLICATION-CLIENT-ID>' `
  -Resource 'ediscovery-intake@example.edu'
```

The test result must show the intake mailbox is in scope. Repeat the test against an unrelated mailbox and confirm it is out of scope. Use the service-principal Object ID from **Enterprise applications**, not the similarly named application-object ID shown on App registrations.

Reference: https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac

### 32A.5 Planned DiscoveryOne settings

The released integration should request and encrypt:

- Directory tenant ID and application client ID.
- Client secret or certificate/private-key reference.
- Mailbox UPN/SMTP address.
- Folder ID or well-known folder name.
- Poll interval and Graph request timeout.
- Allowed sender addresses and domains.
- Maximum message and attachment sizes.
- Default template and unmatched-message disposition.
- Read-only versus read/write processing mode.
- Initial synchronization cutoff so existing historical mail is not accidentally converted into cases.

The server requires outbound TCP 443 and DNS resolution for:

```text
login.microsoftonline.com
graph.microsoft.com
```

### 32A.6 Message processing and security requirements

- Use `GET /users/{mailbox}/mailFolders/{folder}/messages/delta` and persist the opaque delta link after each successful synchronization round.
- Store the Graph message ID, internet message ID, received timestamp, processing result, template ID, and created request ID to prevent duplicates.
- Default to a pending Case Request. Do not create an active case without review unless an administrator explicitly enables a narrowly trusted template.
- Treat HTML email as untrusted. Convert or sanitize it; never execute scripts or load remote content.
- Scan every accepted attachment with ClamAV before storage or parsing.
- Reject or quarantine oversized, encrypted, executable, malformed, or malware-positive attachments according to policy.
- Use structured parsers and explicit field mappings; do not infer legal instructions from arbitrary prose.
- Record processing and rejection events without logging message bodies, tokens, credentials, or sensitive attachments.
- Honor Microsoft Graph `Retry-After` responses and avoid retry storms.

### 32A.7 Mailbox validation and monitoring

Before enabling intake:

1. Confirm the app can acquire a client-credentials token.
2. Confirm the intake mailbox is accessible.
3. Confirm an unrelated mailbox is inaccessible when Exchange RBAC is used.
4. Send a synthetic matching message and verify one pending Case Request is created.
5. Poll again and verify the same message is not duplicated.
6. Test unmatched sender, unmatched template, oversized attachment, malware test file, and malformed message handling.
7. Rotate the credential and repeat the test.

Monitor and alert on:

- Credential or certificate expiration.
- Last poll attempt and last successful poll.
- Age of the persisted delta checkpoint.
- Last processed message and pending-review count.
- Microsoft Graph `401`, `403`, `404`, `410`, and `429` responses.
- Consecutive poll failures and scheduler health.
- Template-match failures, duplicate suppression, and quarantine counts.
- ClamAV readiness and signature age.

References:

- https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app
- https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow
- https://learn.microsoft.com/en-us/graph/api/message-delta?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/delta-query-messages
- https://learn.microsoft.com/en-us/graph/api/message-list-attachments?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac

## 33. Box - Automated

Requires Box Governance/legal-hold scope.

1. Confirm Governance.
2. Create Platform App, Server Authentication/JWT.
3. App + Enterprise Access for managed users/content.
4. Minimum scopes.
5. Request legal-hold scope; `manage_legal_holds` depends on enterprise content.
6. Box Admin authorizes.
7. Protect JWT config.

References:

- https://developer.box.com/guides/legal-holds/index
- https://developer.box.com/guides/authorization
- https://developer.box.com/guides/api-calls/permissions-and-errors/scopes

Fields: Enterprise ID, Client ID/Secret, JWT Public Key ID, complete PEM Private Key, Passphrase.

Validate authentication, test user, create/confirm/release assignment, audit. Reauthorize after scope changes. Manual Box tracking works without adapter.

## 34. Slack - Optional Automated

Requires Enterprise Grid/API and Org Owner.

Scopes:

```text
admin.legal_holds:read
admin.legal_holds:write
```

Reference: https://api.slack.com/enterprise/legal-holds/reference

Fields: Legal Holds Token, API Base, optional OAuth Client ID/Secret, Redirect URI, bot/user scopes, state lifetime, authorize/token URLs, optional Proxy Secret.

Callback:

```text
https://HOST/api/slack/oauth/callback
```

Validate create/add/release in test policy. Remove credentials and verify manual tracking.

## 35. DocuSign - Automated

Prepare:

1. Confirm API/Connect plan.
2. Create integration key.
3. Configure JWT/RSA key.
4. Record API User and Account ID.
5. Complete one-time consent.
6. Create consent template.
7. Add signer role (`signer` default).
8. Add text tabs for case, record type, date from/to.
9. Record template ID/labels.
10. Configure Connect callback.
11. Enable HMAC.

Use `account-d.docusign.com` only for demo.

Fields: Base URL, Account/Template IDs, Signer Role, four Tab Labels, Integration Key, User ID, Auth Server, Private Key, HMAC Key(s), recipient-correction fallback.

Validate synthetic send, tab population, completion callback, resend, invalid-HMAC rejection.

Reference: https://www.docusign.com/blog/developers/manually-authenticating-hmac-signatures-docusign-connect-webhook-configurations

## 36. SharePoint Log Shipping - Automated

Prepare:

1. Dedicated Entra app.
2. Prefer `Sites.Selected`; grant write only to target.
3. Use `Sites.ReadWrite.All` only after approval.
4. Consent and create tracked secret.
5. Restricted library/folder.
6. Record site/drive IDs.

Reference: https://learn.microsoft.com/en-us/graph/permissions-reference

Fields: Tenant/Client/Secret, Site, Drive ID or Name, Folder, Interval, Run Once, Graph Base, Scope, max file/archive/files, timeout/retries.

Validate run-once archive, contents, absence of secrets/tokens, site restriction, next schedule/cleanup.

## 37. AI Assistant - Optional Automated

Before enabling: privacy/security/legal approval, permitted-data definition, retention/training review, restricted project/key, budget controls, mandatory human review.

Fields: Endpoint, Model, API Key, Auth Header, Timeout, Temperature, System Prompt, feature toggles, max suggestions, name/email review controls.

Validate with synthetic data; verify failures do not block core work.

## 38. DMZ NTP Bridge - Optional Automated

Do not configure until helper completes.

Prerequisites: RHEL 9 compatible host, `dnf`, Python 3.9+, sudo, systemd/Nginx, public DNS/cert, inbound 443, outbound HTTPS to internal DiscoveryOne.

Interactive:

```bash
sudo bash ./DiscoveryOne_DMZ.sh
```

Non-interactive:

```bash
sudo bash ./DiscoveryOne_DMZ.sh \
  --server-name ack.example.edu \
  --upstream-url https://discoveryone.internal.example.edu/api/ntp/ack/automate \
  --tls-cert /root/tls/fullchain.pem \
  --tls-key /root/tls/privkey.pem \
  --display-name DiscoveryOne
```

Add `--upstream-ca-cert /root/tls/internal-root.pem` for private upstream CA.

The helper creates service user, `/opt/discoveryone-ack-proxy`, protected `/etc` config, systemd service, Nginx TLS/rate limit, firewall rules, and secret.

Retrieve:

```bash
sudo cat /etc/discoveryone-ack-proxy/shared_secret
```

Enter in **System > Integrations**:

```text
External URL: https://ack.example.edu/ack?token={token}
Display URL:  https://ack.example.edu/
Secret:       <generated value>
```

The literal `{token}` is required.

Validate:

```bash
systemctl status discoveryone-ack-proxy
systemctl status nginx
curl -v https://ack.example.edu/healthz
curl -v https://ack.example.edu/
```

Send controlled NTP and confirm acknowledgement. Access logs omit query strings. Rotate with `--rotate-secret`, update DiscoveryOne immediately, retest.

## 39. Google Workspace - Configuration Only

No Vault hold execution. Track Gmail/Drive manually.

Future preparation:

1. Cloud project/service account.
2. Enable Vault API.
3. Domain-wide delegation.
4. Authorize only required Vault scope.
5. Give delegated admin required Vault privileges/matter access.

Fields: Customer ID, Delegated Admin Email, Service Account Email/Private Key, Vault Scope `https://www.googleapis.com/auth/ediscovery`.

Reference: https://developers.google.com/workspace/vault/guides/holds

## 40. Dropbox Business - Configuration Only

No automated preservation.

Fields: Team ID, OAuth App Key/Secret, optional Refresh Token, Scopes.

Default staged scopes:

```text
team_info.read team_data.member files.metadata.read files.content.read
```

Future work: scoped Business app, minimum permissions, admin authorization, protected token.

Reference: https://developers.dropbox.com/oauth-guide

## 41. Zoom - Configuration Only

No collection/preservation automation.

Fields: Account ID, Client ID/Secret, Scopes.

Future work: Server-to-Server OAuth app, approved admin scopes, activate.

Reference: https://developers.zoom.us/docs/rooms/s2s-oauth/

## 42. Microsoft Intune - Configuration Only

No inventory/endpoint preservation.

Fields: Tenant ID, Client ID/Secret, Graph Base, `.default` Scope.

Do not grant device permissions merely because fields exist. Only create/consent an app for a reviewed adapter design with exact endpoints and least privilege.

## 43. Jamf - Configuration Only

No inventory/endpoint preservation.

Fields: Jamf URL, auth type, Client ID/Secret or Username/Password.

Future work: create least-privilege API Role, API Client, record credentials, rotate secret after role changes.

Reference: https://developer.jamf.com/jamf-pro/docs/client-credentials

## 44. Microsoft Defender - Configuration Only

No endpoint evidence collection.

Fields: Tenant ID, Client ID/Secret, API Base `https://api.securitycenter.microsoft.com`, Scope `https://api.securitycenter.microsoft.com/.default`.

Future app permissions must match exact endpoints.

Reference: https://learn.microsoft.com/en-us/defender-endpoint/api/exposed-apis-create-app-webapp

## 45. CrowdStrike - Configuration Only

No Falcon evidence collection.

Fields: regional Falcon API Base, Client ID/Secret.

Future work: Falcon admin creates OAuth2 client in correct region with only required scopes. Never reuse interactive admin credentials.

## 46. ClamAV - Built In

No account/key/subscription. The `clamav/clamav:1.4_base` service scans/updates internally.

```bash
docker compose ps clamav
docker compose logs --tail=200 clamav
docker compose exec clamav clamdscan --version
```

Never expose port 3310.

<!-- PAGEBREAK -->

# Part VI - Routine Administration

## 47. Settings Ownership

Use UI for institution, URL/hosts, branding, sources, providers, encrypted secrets, SMTP, notifications, backups, naming, ticket workflows. Use `.env` for pre-start bootstrap/runtime controls. When a secret shows **Configured**, leaving it unchanged preserves it.

## 48. Users

Create named accounts with name/email/role/group. Use SSO by default. Use local-only only for controlled recovery/service needs. Enter Employee ID when ticket workflows require it. Disable departures rather than deleting audit history.

## 49. Preservation Changes

In **System > Preservation**, manage built-ins/customs. Disabling does not erase history. Manual tracking remains fallback.

## 50. Credential Rotation

1. Create new provider credential.
2. Keep old during overlap.
3. Replace in System.
4. Save/test/audit.
5. Revoke old.
6. Update expiration inventory.

## 51. Logs

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 caddy
docker compose logs --tail=200 clamav
tail -f logs/app.log
tail -f logs/audit.log
tail -f logs/backup.log
```

Review case metadata/emails/tokens before external sharing.

## 52. Backup/Restore Runbook

Backup: confirm encryption; run; verify/copy off-host; back up volumes/uploads/TLS; record version/time.

Restore test: isolated deployment; upload encrypted backup; supply external key only if needed; confirm destructive prompt; validate users/cases/custodians/attachments/settings/audit; destroy test data by policy.

Restore replaces the current database.

## 53. Upgrade

1. Review changes.
2. Maintenance window.
3. Back up DB/volumes off-host.
4. Record status/images.
5. `git pull --ff-only`.
6. `docker compose up -d --build`.
7. Follow backend migration logs.
8. Confirm health.
9. Run smoke, browser-console, and integration tests.

Never use `docker compose down -v`; `-v` deletes volumes.

## 54. Stop/Start

```bash
docker compose stop
docker compose start
docker compose up -d --build
docker compose ps
```

<!-- PAGEBREAK -->

# Part VII - Troubleshooting

## 55. SSL Protocol Error

```bash
docker compose ps caddy
docker compose port caddy 443
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
curl -vk https://127.0.0.1:48080/
```

- HTTP-to-HTTPS error: use `https://`.
- TLS internal error: Caddy/certificate.
- refused: container/port/firewall.
- warning only: encrypted but untrusted root.

## 56. Backend Unhealthy

```bash
docker compose logs --tail=300 backend
docker compose logs --tail=200 db
docker compose ps
```

Common: migration, DB password mismatch, folder permission, entrypoint line endings, ClamAV health, invalid integration config. Do not delete volumes.

## 57. Permission Denied

```bash
ls -ld logs backups case_request_uploads
docker compose up -d --force-recreate backend
```

Fix only the affected owner/ACL.

## 58. Setup Page Missing

Setup locks after admin/setup completion. Change settings under System. Do not delete production data to rerun wizard.

## 59. OIDC Redirect Mismatch

```text
https://HOST[:PORT]/api/auth/oidc/callback
```

Scheme, host, port, path, and case must match. Check Public App URL/proxy headers.

## 60. Email Failure

Test in System; verify host/port/TLS, DNS/firewall, relay allow list, credentials, sender authorization, and backend logs.

## 61. Enabled Integration Does Nothing

Google, Dropbox, Zoom, Intune, Jamf, Defender, CrowdStrike are configuration-only. Use manual tracking. Automated products require both enable checkbox and provider selection.

## 62. Preservation Integration Error

Manual tracking should work without automation. Confirm current build, disable provider, save/reload, retest, capture browser/backend errors.

## 63. ClamAV Slow

```bash
docker compose logs -f clamav
docker compose ps clamav
```

Check outbound access, RAM, disk. Do not bypass in production.

## 64. Disk Growth

```bash
docker system df
du -sh logs backups case_request_uploads
```

Review retention, rotation, attachments, build cache, log shipping, snapshots. Never remove volumes without mapping data.

<!-- PAGEBREAK -->

# Part VIII - Go-Live

## 65. Go-Live Checklist

### Infrastructure

- [ ] DNS correct.
- [ ] Trusted certificate matches hostname.
- [ ] Only required ports exposed.
- [ ] DB/backend/ClamAV not public.
- [ ] Time sync and storage monitoring healthy.

### Application/access

- [ ] Services healthy.
- [ ] URL/hosts/institution/branding correct.
- [ ] Naming/sources approved.
- [ ] Manual tracking works.
- [ ] Two named sys-admins and MFA.
- [ ] Recovery admin vaulted.
- [ ] OIDC tested.
- [ ] Least-privilege roles.

### Messaging/integrations

- [ ] SMTP and generated links pass.
- [ ] Templates localized.
- [ ] Each integration has owner/test.
- [ ] Service identities least privilege.
- [ ] Credential expirations tracked.
- [ ] Configuration-only products documented as manual.

### Protection/operations

- [ ] ClamAV ready/current.
- [ ] Encrypted backups run/off-host.
- [ ] Restore tested.
- [ ] Logs retained/shipped.
- [ ] Upgrade/incident owners named.
- [ ] Pilot accepted before real matters.

## 66. Command Quick Reference

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=200 backend
docker compose logs -f backend
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
curl -vk https://127.0.0.1:48080/
docker compose restart backend
docker compose up -d --build --force-recreate backend
docker compose stop
docker compose start
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./discoveryone-caddy-root.crt
bash ./DiscoveryOne_DMZ.sh --help
```

## 67. Official References

- Repository: https://github.com/csisensteinucsf/DiscoveryOne
- Docker: https://docs.docker.com/engine/install/
- Compose: https://docs.docker.com/compose/
- Caddy: https://caddyserver.com/docs/automatic-https
- Microsoft OIDC: https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc
- Graph eDiscovery: https://learn.microsoft.com/en-us/graph/api/resources/security-ediscoverycase
- Graph permissions: https://learn.microsoft.com/en-us/graph/permissions-reference
- Box: https://developer.box.com/guides/legal-holds/index
- Slack: https://api.slack.com/enterprise/legal-holds/reference
- Google Vault: https://developers.google.com/workspace/vault/guides/holds
- Dropbox: https://developers.dropbox.com/oauth-guide
- Zoom: https://developers.zoom.us/docs/rooms/s2s-oauth/
- Jamf: https://developer.jamf.com/jamf-pro/docs/client-credentials
- Defender: https://learn.microsoft.com/en-us/defender-endpoint/api/exposed-apis-create-app-webapp
- DocuSign HMAC: https://www.docusign.com/blog/developers/manually-authenticating-hmac-signatures-docusign-connect-webhook-configurations

## 68. Final Operational Principle

DiscoveryOne should remain usable when optional integrations are unavailable. Preserve the ability to create cases, add custodians, manually track every source, use approved alternative notice processes, and maintain audit history. Enable automation only after end-to-end testing with the institution's tenant, permissions, licensing, network, and legal workflow.

---

**Document control:** Review this guide against the checked-out repository before each deployment. Provider portals, API permissions, and licensing change; use official documentation and a non-production acceptance test before enabling an integration.
