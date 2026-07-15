import { FieldHelp } from './SetupCoreSteps.jsx'
import SetupIntegrationCard from './SetupIntegrationCard.jsx'

export default function SetupIntegrationsStep({
  form,
  INTEGRATION_FLAGS,
  INTEGRATION_REQUIREMENTS,
  toggleIntegration,
  updateProvider,
  updateIntegrationConfig,
  updateSmtp,
}) {
  return (
    <div style={{ display: 'grid', gap: 18 }}>
                    <div>
                      <h4 style={{ margin: '0 0 10px' }}>Authentication</h4>
                      <label>
                        SSO Provider
                        <select className="input" value={form.integrations.sso_provider} onChange={e => updateProvider('sso_provider', e.target.value)}>
                          <option value="local">Local</option>
                          <option value="oidc">OIDC</option>
                        </select>
                        <FieldHelp>This selects whether users sign in locally or through a generic OIDC-compatible single sign-on provider. Enter OIDC settings here or later in System.</FieldHelp>
                      </label>
                      {form.integrations.sso_provider === 'oidc' && (
                        <div className="form-grid" style={{ marginTop: 12 }}>
                          <label>
                            OIDC Issuer
                            <input className="input" value={form.integration_configs.oidc?.issuer || ''} onChange={e => updateIntegrationConfig('oidc', 'issuer', e.target.value)} placeholder="https://idp.example.edu/oauth2/default" />
                          </label>
                          <label>
                            Client ID
                            <input className="input" value={form.integration_configs.oidc?.client_id || ''} onChange={e => updateIntegrationConfig('oidc', 'client_id', e.target.value)} />
                          </label>
                          <label>
                            Client Secret
                            <input className="input" type="password" value={form.integration_configs.oidc?.client_secret || ''} onChange={e => updateIntegrationConfig('oidc', 'client_secret', e.target.value)} />
                            <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                          </label>
                          <label>
                            Scopes
                            <input className="input" value={form.integration_configs.oidc?.scopes || ''} onChange={e => updateIntegrationConfig('oidc', 'scopes', e.target.value)} placeholder="openid profile email" />
                          </label>
                        </div>
                      )}
                    </div>
    
                    <div>
                      <h4 style={{ margin: '0 0 10px' }}>Workflow Integrations</h4>
                      <div style={{ display: 'grid', gap: 14 }}>
                        {INTEGRATION_FLAGS.map(([key, label]) => (
                          <SetupIntegrationCard
                            key={key}
                            integrationKey={key}
                            label={label}
                            form={form}
                            requirement={INTEGRATION_REQUIREMENTS[key]}
                            toggleIntegration={toggleIntegration}
                            updateIntegrationConfig={updateIntegrationConfig}
                            updateSmtp={updateSmtp}
                          />                        ))}
                      </div>
                    </div>
                  </div>
  )
}