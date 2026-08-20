const helpStyle = { display: 'block', marginTop: 6, color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, lineHeight: 1.4 }

export default function SystemInstitutionPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  institutionSettings,
  institutionSaving,
  institutionStatus,
  updateInstitutionSetting,
  saveInstitutionSettings,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can configure institution policy.')
  }

  const statusIsError = institutionStatus && !institutionStatus.toLowerCase().includes('saved')

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>Institution Policy</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        These values control organization-facing language, requestor email policy, support contact information, and the name shown for single sign-on.
      </p>
      <div className="form-grid">
        <label>
          Organization Name
          <input className="input" value={institutionSettings.org_name || ''} onChange={event => updateInstitutionSetting('org_name', event.target.value)} placeholder="example: University of California" />
          <span style={helpStyle}>The full institution or system name used in organization-facing labels and policy language.</span>
        </label>
        <label>
          Short Name
          <input className="input" value={institutionSettings.org_short_name || ''} onChange={event => updateInstitutionSetting('org_short_name', event.target.value)} placeholder="example: UCSF" />
          <span style={helpStyle}>The shorter campus or unit name used where the full organization name would be too long.</span>
        </label>
        <label>
          Allowed Requestor Domains
          <textarea className="input" rows={3} value={institutionSettings.allowed_requestor_email_domains || ''} onChange={event => updateInstitutionSetting('allowed_requestor_email_domains', event.target.value)} placeholder="example.edu&#10;law.example.edu" />
          <span style={helpStyle}>Requests from these email domains are treated as organization-owned; leave this empty to allow any domain.</span>
        </label>
        <label>
          Requestor Email Exceptions
          <textarea className="input" rows={3} value={institutionSettings.requestor_email_exceptions || ''} onChange={event => updateInstitutionSetting('requestor_email_exceptions', event.target.value)} placeholder="outside.counsel@example.com" />
          <span style={helpStyle}>These complete email addresses may submit requests even when their domains are not in the allowed list.</span>
        </label>
        <label>
          Support Email
          <input className="input" type="email" value={institutionSettings.support_email || ''} onChange={event => updateInstitutionSetting('support_email', event.target.value)} placeholder="support@example.edu" />
          <span style={helpStyle}>The support contact shown to users for access and workflow assistance.</span>
        </label>        <label>
          Internal Counsel Label
          <input className="input" value={institutionSettings.internal_counsel_label || ''} onChange={event => updateInstitutionSetting('internal_counsel_label', event.target.value)} placeholder="Internal Counsel" />
          <span style={helpStyle}>The label used for your organization's attorney field on matter forms and matter lists, such as UC Attorney or Agency Counsel.</span>
        </label>
        <label>
          SSO Display Name
          <input className="input" value={institutionSettings.sso_display_name || ''} onChange={event => updateInstitutionSetting('sso_display_name', event.target.value)} placeholder="Organization SSO" />
          <span style={helpStyle}>The user-facing name displayed for the configured OIDC single sign-on option.</span>
        </label>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
        <button className="btn secondary" type="button" onClick={saveInstitutionSettings} disabled={institutionSaving}>
          {institutionSaving ? 'Saving' : 'Save Institution Settings'}
        </button>
        {institutionStatus && (
          <span style={{ color: statusIsError ? '#b91c1c' : 'var(--muted,#6b7280)' }}>{institutionStatus}</span>
        )}
      </div>
    </div>
  )
}
