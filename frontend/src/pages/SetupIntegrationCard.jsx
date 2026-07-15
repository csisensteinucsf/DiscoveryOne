import SetupPrimaryIntegrationFields from './SetupPrimaryIntegrationFields.jsx'
import SetupExtendedIntegrationFields from './SetupExtendedIntegrationFields.jsx'

const fieldHelpStyle = { display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, lineHeight: 1.35, marginTop: 6 }

export default function SetupIntegrationCard({
  integrationKey,
  label,
  form,
  requirement,
  toggleIntegration,
  updateIntegrationConfig,
  updateSmtp,
}) {
  const key = integrationKey
  return (
                          <div key={key} style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 12 }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                              <input type="checkbox" checked={!!form.enabled_integrations[key]} onChange={() => toggleIntegration(key)} />
                              {label}
                            </label>
                            <div style={fieldHelpStyle}>
                              {requirement?.text} App-managed values: {(requirement?.values || []).join(', ')}.
                            </div>
    
                            <SetupPrimaryIntegrationFields
                              integrationKey={key}
                              form={form}
                              updateIntegrationConfig={updateIntegrationConfig}
                              updateSmtp={updateSmtp}
                            />
                            <SetupExtendedIntegrationFields
                              integrationKey={key}
                              form={form}
                              updateIntegrationConfig={updateIntegrationConfig}
                            />
                          </div>
  )
}