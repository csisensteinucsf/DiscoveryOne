import { INTEGRATION_FLAGS } from './systemUtils.js'
import SystemIntegrationConfigSections from './SystemIntegrationConfigSections.jsx'

const PROVIDER_LABELS = {
  none: 'None',
  local: 'Local accounts',
  oidc: 'OIDC single sign-on',
  csv: 'CSV/static directory file',
  http: 'IDP/HR API',
  servicenow: 'ServiceNow',
  smtp: 'SMTP',
  docusign: 'DocuSign',
  purview: 'Microsoft Purview',
  google_workspace: 'Google Workspace',
}

const PERSON_LOOKUP_ALIASES = new Set(['api', 'idp', 'hr', 'static'])

const providerLabel = value => PROVIDER_LABELS[value] || String(value || '')
  .split('_')
  .filter(Boolean)
  .map(part => part.charAt(0).toUpperCase() + part.slice(1))
  .join(' ')

const providerChoices = (settings, key, fallback, { hideAliases = false } = {}) => {

  const installed = Array.isArray(settings.providerOptions?.[key])
    ? settings.providerOptions[key]
    : fallback
  const values = installed.map(value => String(value || '').trim()).filter(Boolean)
  return [...new Set(values)].filter(value => !hideAliases || !PERSON_LOOKUP_ALIASES.has(value))
}

export default function SystemIntegrationsPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  integrationSettings,
  updateIntegrationEnabled,
  updateIntegrationProvider,
  updateIntegrationConfig,
  saveIntegrationSettings,
  integrationSaving,
  integrationStatus,
}) {
  return (
    <>
      {isSysAdmin ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={titleStyle}>Integration Settings</div>
          <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
            Configure provider choices and connection values inside DiscoveryOne. Secrets entered here are encrypted before they are stored; existing saved secrets show as configured and are preserved unless you replace them.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: 10, marginBottom: 18 }}>
            {INTEGRATION_FLAGS.map(([key, label]) => (
              <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                <input
                  type="checkbox"
                  checked={!!integrationSettings.enabled?.[key]}
                  onChange={e => updateIntegrationEnabled(key, e.target.checked)}
                />
                {label}
              </label>
            ))}
          </div>

          <div className="form-grid">
            <label>
              SSO Provider
              <select className="input" value={integrationSettings.providers?.sso_provider || 'local'} onChange={e => updateIntegrationProvider('sso_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'sso_provider', ['local', 'oidc']).map(value => (
                  <option key={value} value={value}>{providerLabel(value)}</option>
                ))}
              </select>
            </label>
            <label>
              Person Lookup Provider
              <select className="input" value={integrationSettings.providers?.person_lookup_provider || 'none'} onChange={e => updateIntegrationProvider('person_lookup_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'person_lookup_provider', ['none', 'csv', 'http'], { hideAliases: true }).map(value => (
                  <option key={value} value={value}>{value === 'none' ? 'Manual entry' : providerLabel(value)}</option>
                ))}
              </select>
            </label>
            <label>
              Ticket Provider
              <select className="input" value={integrationSettings.providers?.ticket_provider || 'none'} onChange={e => updateIntegrationProvider('ticket_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'ticket_provider', ['none', 'servicenow']).map(value => (
                  <option key={value} value={value}>{providerLabel(value)}</option>
                ))}
              </select>
            </label>
            <label>
              Mail Provider
              <select className="input" value={integrationSettings.providers?.mail_provider || 'smtp'} onChange={e => updateIntegrationProvider('mail_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'mail_provider', ['none', 'smtp']).map(value => (
                  <option key={value} value={value}>{providerLabel(value)}</option>
                ))}
              </select>
            </label>
            <label>
              E-signature Provider
              <select className="input" value={integrationSettings.providers?.esign_provider || 'none'} onChange={e => updateIntegrationProvider('esign_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'esign_provider', ['none', 'docusign']).map(value => (
                  <option key={value} value={value}>{providerLabel(value)}</option>
                ))}
              </select>
            </label>
            <label>
              Preservation Automation Provider
              <select className="input" value={integrationSettings.providers?.preservation_provider || 'none'} onChange={e => updateIntegrationProvider('preservation_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'preservation_provider', ['none', 'purview']).map(value => (
                  <option key={value} value={value}>{providerLabel(value)}</option>
                ))}
              </select>
            </label>
            <label>
              Search Export Provider
              <select className="input" value={integrationSettings.providers?.search_export_provider || 'none'} onChange={e => updateIntegrationProvider('search_export_provider', e.target.value)}>
                {providerChoices(integrationSettings, 'search_export_provider', ['none', 'purview']).map(value => (
                  <option key={value} value={value}>{providerLabel(value)}</option>
                ))}
              </select>
            </label>          </div>

          <SystemIntegrationConfigSections
            integrationSettings={integrationSettings}
            updateIntegrationConfig={updateIntegrationConfig}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
            <button className="btn secondary" onClick={saveIntegrationSettings} disabled={integrationSaving}>
              {integrationSaving ? 'Saving' : 'Save Integration Settings'}
            </button>
            {integrationStatus && (
              <span style={{ color: integrationStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
                {integrationStatus}
              </span>
            )}
          </div>
        </div>
      ) : adminOnlyCard('Only system administrators can configure integrations.')}
    </>
  )
}
