import { SYSTEM_INTEGRATION_FLAGS } from './setupCatalog.js'

export const INTEGRATION_CATALOG = [
  { key: 'oidc', name: 'OIDC single sign-on', category: 'Identity', configKey: 'oidc', description: 'Authenticate users through your organization\'s OpenID Connect identity provider.' },
  { key: 'person_lookup', name: 'Person lookup', category: 'Identity', configKey: 'person_lookup', description: 'Find custodians through a directory export or a live identity and HR API.' },
  { key: 'smtp', name: 'SMTP', category: 'Communication', description: 'Deliver notices, reminders, and application email through your mail server.', externalEditor: 'smtp' },
  { key: 'email_intake', name: 'Email intake', category: 'Communication', configKey: 'email_intake', description: 'Monitor an Exchange Online mailbox for new matter requests.' },
  { key: 'ntp_ack_bridge', name: 'NTP acknowledgment bridge', category: 'Communication', configKey: 'ntp_ack_bridge', description: 'Receive external Notice to Preserve acknowledgments through a DMZ service.' },
  { key: 'servicenow', name: 'ServiceNow', category: 'Legal workflows', configKey: 'servicenow', description: 'Create and reconcile preservation tickets with ServiceNow.' },
  { key: 'docusign', name: 'DocuSign', category: 'Legal workflows', configKey: 'docusign', description: 'Send and track custodian consent documents for electronic signature.' },
  { key: 'purview', name: 'Microsoft Purview', category: 'Preservation', configKey: 'purview', description: 'Automate Microsoft 365 preservation and search export workflows.' },
  { key: 'box', name: 'Box', category: 'Preservation', configKey: 'box', description: 'Connect Box legal holds using a server-authenticated custom application.' },
  { key: 'slack', name: 'Slack', category: 'Preservation', configKey: 'slack', description: 'Manage Slack legal holds and OAuth authorization.' },
  { key: 'google_workspace', name: 'Google Workspace', category: 'Preservation', configKey: 'google_workspace', configurationOnly: true, description: 'Store Google Vault connection details for future automated workflows.' },
  { key: 'dropbox_business', name: 'Dropbox Business', category: 'Preservation', configKey: 'dropbox_business', configurationOnly: true, description: 'Store Dropbox Business connection details for future automated workflows.' },
  { key: 'zoom', name: 'Zoom', category: 'Preservation', configKey: 'zoom', configurationOnly: true, description: 'Store Zoom server-to-server OAuth details for future workflows.' },
  { key: 'intune', name: 'Microsoft Intune', category: 'Security and devices', configKey: 'intune', configurationOnly: true, description: 'Store Microsoft Intune connection details for future device workflows.' },
  { key: 'jamf', name: 'Jamf', category: 'Security and devices', configKey: 'jamf', configurationOnly: true, description: 'Store Jamf Pro connection details for future device workflows.' },
  { key: 'defender', name: 'Microsoft Defender', category: 'Security and devices', configKey: 'defender', configurationOnly: true, description: 'Store Microsoft Defender connection details for future evidence workflows.' },
  { key: 'crowdstrike', name: 'CrowdStrike', category: 'Security and devices', configKey: 'crowdstrike', configurationOnly: true, description: 'Store CrowdStrike Falcon connection details for future evidence workflows.' },
  { key: 'log_shipping', name: 'Off-box log shipping', category: 'Operations', configKey: 'log_shipping', description: 'Send compressed application log archives to a SharePoint library.' },
  { key: 'ai', name: 'AI assistant', category: 'Operations', configKey: 'ai', description: 'Connect an OpenAI-compatible endpoint for enabled assistant features.' },
]

export const INTEGRATION_CATEGORIES = ['All', ...new Set(INTEGRATION_CATALOG.map(item => item.category))]

const providerLink = key => ({
  oidc: ['sso_provider', 'oidc', 'local'],
  servicenow: ['ticket_provider', 'servicenow', 'none'],
  smtp: ['mail_provider', 'smtp', 'none'],
  docusign: ['esign_provider', 'docusign', 'none'],
}[key])

const CONFIG_IDENTITY_FIELDS = {
  oidc: ['issuer', 'client_id', 'client_secret'],
  person_lookup: ['csv_path', 'http_url', 'http_auth_value'],
  ntp_ack_bridge: ['bridge_url', 'shared_secret'],
  email_intake: ['tenant_id', 'client_id', 'client_secret', 'mailbox'],
  servicenow: ['base_url', 'username', 'password', 'oauth_client_id', 'oauth_client_secret'],
  docusign: ['base_url', 'account_id', 'template_id', 'integration_key', 'private_key'],
  purview: ['tenant_id', 'client_id', 'client_secret'],
  box: ['enterprise_id', 'client_id', 'client_secret'],
  slack: ['legal_holds_token', 'client_id'],
  google_workspace: ['customer_id', 'service_account_client_email', 'service_account_private_key'],
  dropbox_business: ['team_id', 'client_id', 'client_secret', 'refresh_token'],
  zoom: ['account_id', 'client_id', 'client_secret'],
  intune: ['tenant_id', 'client_id', 'client_secret'],
  jamf: ['base_url', 'client_id', 'client_secret', 'username', 'password'],
  defender: ['tenant_id', 'client_id', 'client_secret'],
  crowdstrike: ['client_id', 'client_secret'],
  log_shipping: ['tenant_id', 'client_id', 'client_secret', 'sharepoint_site_id'],
  ai: ['url', 'model', 'api_key'],
}

export function cloneIntegrationSettings(settings = {}) {
  return {
    ...settings,
    enabled: { ...(settings.enabled || {}) },
    providers: { ...(settings.providers || {}) },
    providerOptions: Object.fromEntries(
      Object.entries(settings.providerOptions || {}).map(([key, values]) => [key, Array.isArray(values) ? [...values] : values]),
    ),
    configs: Object.fromEntries(
      Object.entries(settings.configs || {}).map(([key, values]) => [key, { ...(values || {}) }]),
    ),
  }
}

export function integrationIsEnabled(settings, key) {
  if (key === 'person_lookup') {
    return !!settings?.enabled?.person_lookup || String(settings?.providers?.person_lookup_provider || 'none') !== 'none'
  }
  if (key === 'purview') {
    return !!settings?.enabled?.purview
      || settings?.providers?.preservation_provider === 'purview'
      || settings?.providers?.search_export_provider === 'purview'
  }
  const link = providerLink(key)
  if (link) return settings?.providers?.[link[0]] === link[1] || !!settings?.enabled?.[key]
  return !!settings?.enabled?.[key]
}

export function integrationHasSavedDetails(settings, integration) {
  if (integrationIsEnabled(settings, integration.key)) return true
  const config = settings?.configs?.[integration.configKey || integration.key]
  if (!config || typeof config !== 'object') return false
  const identityFields = CONFIG_IDENTITY_FIELDS[integration.configKey || integration.key] || []
  return identityFields.some(key => {
    const value = config[key]
    return value !== null && value !== undefined && String(value).trim() !== ''
  })
}

export function setIntegrationEnabled(settings, key, value) {
  const next = cloneIntegrationSettings(settings)
  next.enabled[key] = value

  const link = providerLink(key)
  if (link) next.providers[link[0]] = value ? link[1] : link[2]

  if (key === 'person_lookup') {
    next.providers.person_lookup_provider = value
      ? (next.providers.person_lookup_provider === 'none' ? 'csv' : next.providers.person_lookup_provider || 'csv')
      : 'none'
  }
  if (key === 'purview') {
    next.providers.preservation_provider = value ? 'purview' : 'none'
    next.providers.search_export_provider = value ? 'purview' : 'none'
  }
  return next
}

export function setIntegrationProvider(settings, key, value) {
  const next = cloneIntegrationSettings(settings)
  next.providers[key] = value
  if (key === 'person_lookup_provider') next.enabled.person_lookup = value !== 'none'
  if (key === 'preservation_provider' || key === 'search_export_provider') {
    next.enabled.purview = next.providers.preservation_provider === 'purview'
      || next.providers.search_export_provider === 'purview'
  }
  return next
}

export function setIntegrationConfig(settings, name, key, value) {
  const next = cloneIntegrationSettings(settings)
  next.configs[name] = { ...(next.configs[name] || {}), [key]: value }
  return next
}

export function integrationSettingsForEditor(settings, selectedKey) {
  const next = cloneIntegrationSettings(settings)
  next.enabled = Object.fromEntries(SYSTEM_INTEGRATION_FLAGS.map(([key]) => [key, key === selectedKey]))
  next.providers = {
    ...next.providers,
    sso_provider: selectedKey === 'oidc' ? 'oidc' : 'local',
    person_lookup_provider: selectedKey === 'person_lookup'
      ? (settings?.providers?.person_lookup_provider || 'none')
      : 'none',
  }
  return next
}
