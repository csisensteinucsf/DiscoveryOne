import BrandLogo from '../components/BrandLogo.jsx'
import { CASE_NAMING_OPTIONS } from './setupCatalog.js'

export { CASE_NAMING_OPTIONS }

const fieldHelpStyle = { display: 'block', marginTop: 4, color: 'var(--muted,#6b7280)', fontSize: 13, lineHeight: 1.35 }

export const FieldHelp = ({ children }) => <span style={fieldHelpStyle}>{children}</span>

export function SetupHeader({ apiBase, appName }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', marginBottom: 20 }}>
      <BrandLogo apiBase={apiBase} height={54} />
      <div>
        <h2 style={{ margin: 0 }}>First-Time Setup</h2>
        <div style={{ color: 'var(--muted,#6b7280)', marginTop: 4 }}>{appName}</div>
      </div>
    </div>
  )
}

export function DeploymentStep({
  form,
  update,
  setTlsCertificateFile,
  setTlsPrivateKeyFile,
}) {
  return (
    <div className="form-grid">
      <label>
        Public App URL
        <input className="input" value={form.app_base_url} onChange={e => update('app_base_url', e.target.value)} placeholder="https://discoveryone.example.edu" />
        <FieldHelp>This must be an HTTPS URL; DiscoveryOne uses it when it creates links in email notifications, approvals, and workflow messages.</FieldHelp>
      </label>
      <label>
        Allowed Hostnames
        <input className="input" value={form.allowed_hosts} onChange={e => update('allowed_hosts', e.target.value)} placeholder="discoveryone.example.edu, discoveryone.local" />
        <FieldHelp>These hostnames are trusted when DiscoveryOne receives web requests, which helps prevent links from being generated for unexpected domains.</FieldHelp>
      </label>
      <label>
        TLS Certificate Mode
        <select className="input" value={form.tls_mode} onChange={e => update('tls_mode', e.target.value)}>
          <option value="self_signed">Use self-signed certificate</option>
          <option value="uploaded">Upload trusted certificate</option>
        </select>
        <FieldHelp>HTTPS/TLS is required. Self-signed TLS is acceptable for first run and local testing, but users will see browser warnings until a trusted certificate is configured.</FieldHelp>
      </label>
      <label>
        TLS Common Name
        <input className="input" value={form.tls_common_name} onChange={e => update('tls_common_name', e.target.value)} placeholder="discoveryone.example.edu" />
        <FieldHelp>This should match the DNS name users type in the browser, and it should also appear in the uploaded certificate subject or subject alternative names.</FieldHelp>
      </label>
      <label>
        TLS Certificate
        <input className="input" type="file" accept=".crt,.cer,.pem" onChange={e => setTlsCertificateFile(e.target.files?.[0] || null)} />
        <FieldHelp>Upload the public certificate or PEM certificate chain when using a trusted certificate; the setup wizard stores it with the deployment settings.</FieldHelp>
      </label>
      <label>
        TLS Private Key
        <input className="input" type="file" accept=".key,.pem" onChange={e => setTlsPrivateKeyFile(e.target.files?.[0] || null)} />
        <FieldHelp>Upload the matching PEM private key for the certificate; keep this file private because it proves control of the HTTPS identity.</FieldHelp>
      </label>
    </div>
  )
}

export function InstitutionStep({ form, update }) {
  return (
    <div className="form-grid">
      <label>
        Organization Name
        <input className="input" value={form.org_name} onChange={e => update('org_name', e.target.value)} placeholder="example: University of California" />
        <FieldHelp>This is the full institution or system name used in organization-facing labels and policy language.</FieldHelp>
      </label>
      <label>
        Short Name
        <input className="input" value={form.org_short_name} onChange={e => update('org_short_name', e.target.value)} placeholder="example: UC Example" />
        <FieldHelp>This is the shorter organization, campus, or unit name used where the full organization name would be too long.</FieldHelp>
      </label>
      <label>
        Allowed Requestor Domains
        <input className="input" value={form.allowed_requestor_email_domains} onChange={e => update('allowed_requestor_email_domains', e.target.value)} placeholder="example.edu, law.example.edu" />
        <FieldHelp>These email domains are treated as organization-owned requestor domains; leave the field empty if requestors from any domain should be allowed.</FieldHelp>
      </label>
      <label>
        Requestor Email Exceptions
        <textarea className="input" rows={3} value={form.requestor_email_exceptions} onChange={e => update('requestor_email_exceptions', e.target.value)} placeholder="outside.counsel@example.com" />
        <FieldHelp>Enter complete email addresses, separated by commas or new lines, that may submit requests even when their domains are not listed above.</FieldHelp>
      </label>      <label>
        Support Email
        <input className="input" type="email" value={form.support_email} onChange={e => update('support_email', e.target.value)} placeholder="support@example.edu" />
        <FieldHelp>This address is shown as the support contact for users who need help with access or workflow questions.</FieldHelp>
      </label>
      <label>
        SSO Display Name
        <input className="input" value={form.sso_display_name} onChange={e => update('sso_display_name', e.target.value)} />
        <FieldHelp>This is the user-facing name for your single sign-on option, such as organization SSO or an OIDC provider name.</FieldHelp>
      </label>
    </div>
  )
}

export function AdminStep({ form, update, passwordTooShort, passwordMismatch }) {
  return (
    <>
      <div className="form-grid">
        <label>
          Username
          <input className="input" value={form.admin_username} readOnly required />
          <FieldHelp>The first local sys-admin account is always named admin; use it only to finish setup and create named user accounts.</FieldHelp>
        </label>
        <label>
          Password
          <input className="input" type="password" value={form.admin_password} onChange={e => update('admin_password', e.target.value)} minLength={12} required />
          <FieldHelp>This password protects the first sys-admin account and must be at least 12 characters with multiple character types.</FieldHelp>
        </label>
        <label>
          Confirm Password
          <input className="input" type="password" value={form.confirm_password} onChange={e => update('confirm_password', e.target.value)} minLength={12} required />
          <FieldHelp>This must match the password above so DiscoveryOne can create the initial administrator safely.</FieldHelp>
        </label>
      </div>
      {passwordTooShort && <p style={{ color: '#b91c1c' }}>Password must be at least 12 characters.</p>}
      {passwordMismatch && <p style={{ color: '#b91c1c' }}>Passwords do not match.</p>}
    </>
  )
}

export function BrandingStep({ form, update, logoFile, logoPreview, setLogoFile }) {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="form-grid">
        <label>
          App Name
          <input className="input" value={form.app_name} onChange={e => update('app_name', e.target.value)} placeholder="DiscoveryOne" />
          <FieldHelp>This is the product name users see in the browser title, login screen, app shell, and notification templates.</FieldHelp>
        </label>
        <label>
          App Tagline
          <input className="input" value={form.app_tagline} onChange={e => update('app_tagline', e.target.value)} placeholder="eDiscovery Case Manager" />
          <FieldHelp>This short description appears under the app name in the sidebar and can be changed later in System.</FieldHelp>
        </label>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
      <label className="btn secondary" style={{ display: 'inline-block', cursor: 'pointer' }}>
        Choose Logo
        <input
          type="file"
          accept="image/png,image/jpeg"
          onChange={e => setLogoFile(e.target.files?.[0] || null)}
          style={{ display: 'none' }}
        />
      </label>
      <span style={{ color: 'var(--muted,#6b7280)' }}>{logoFile?.name || 'Using default D1 logo'}</span>
      <img src={logoPreview || '/img/D1_Logo.png'} alt="Logo preview" style={{ height: 72, maxWidth: 240, objectFit: 'contain' }} />
      <div style={{ ...fieldHelpStyle, flexBasis: '100%' }}>This logo appears in the app shell and login/setup surfaces; if no file is uploaded, DiscoveryOne uses the default D1 logo.</div>
      </div>
    </div>
  )
}

export function CaseNamingStep({ form, updateCaseNamingMode }) {
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {CASE_NAMING_OPTIONS.map(([mode, label, description]) => (
        <label
          key={mode}
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'flex-start',
            padding: '12px 14px',
            border: '1px solid var(--border,#d1d5db)',
            borderRadius: 8,
            background: form.case_naming?.mode === mode ? '#eefdf8' : 'var(--panel,#fff)',
          }}
        >
          <input
            type="radio"
            name="case_naming_mode"
            checked={form.case_naming?.mode === mode}
            onChange={() => updateCaseNamingMode(mode)}
            style={{ marginTop: 3 }}
          />
          <span>
            <strong>{label}</strong>
            <FieldHelp>{description}</FieldHelp>
          </span>
        </label>
      ))}
    </div>
  )
}
