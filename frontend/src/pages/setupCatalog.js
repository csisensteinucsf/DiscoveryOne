export const SETUP_INTEGRATION_FLAGS = [
  ['smtp', 'SMTP'],
  ['log_shipping', 'Off-box log shipping'],
  ['servicenow', 'ServiceNow'],
  ['docusign', 'DocuSign'],
  ['purview', 'Purview'],
  ['google_workspace', 'Google Workspace (configuration only)'],
  ['dropbox_business', 'Dropbox Business (configuration only)'],
  ['zoom', 'Zoom (configuration only)'],
  ['intune', 'Microsoft Intune (configuration only)'],
  ['jamf', 'Jamf (configuration only)'],
  ['defender', 'Microsoft Defender (configuration only)'],
  ['crowdstrike', 'CrowdStrike (configuration only)'],
  ['slack', 'Slack'],
  ['box', 'Box'],
  ['ai', 'AI assistant'],
]

export const SYSTEM_INTEGRATION_FLAGS = [
  ['person_lookup', 'Person lookup'],
  ['ntp_ack_bridge', 'DMZ NTP Acknowledgment Server'],
  ...SETUP_INTEGRATION_FLAGS,
]

export const INTEGRATION_FLAGS = SETUP_INTEGRATION_FLAGS

export const PROVIDER_DEFAULTS = {
  person_lookup_provider: 'none',
  sso_provider: 'local',
  ticket_provider: 'none',
  mail_provider: 'smtp',
  esign_provider: 'none',
  preservation_provider: 'none',
  search_export_provider: 'none',
}

export const SMTP_DEFAULTS = {
  host: '',
  port: 587,
  from_address: '',
  username: '',
  password: '',
  use_tls: true,
  use_ssl: false,
  timeout_seconds: 15,
}

export const SERVICENOW_DEFAULTS = {
  base_url: '',
  auth_type: 'basic',
  username: '',
  password: '',
  oauth_client_id: '',
  oauth_client_secret: '',
  oauth_token_url: '',
  oauth_scope: '',
  table: 'incident',
  status_table: 'incident',
  use_import_api: false,
  customer_id: 'discoveryone',
  source_system: 'discoveryone',
  default_customer_id: '',
  box_short_description: 'Box hold needed for legal case',
  box_release_assignment_group: '',
  box_release_incident_keyword: '',
  box_release_short_description: 'Box hold release request for legal case',
}

export const BOX_DEFAULTS = {
  enterprise_id: '',
  client_id: '',
  client_secret: '',
  jwt_key_id: '',
  jwt_private_key: '',
  jwt_passphrase: '',
}

export const GOOGLE_WORKSPACE_DEFAULTS = {
  customer_id: '',
  delegated_admin_email: '',
  service_account_client_email: '',
  service_account_private_key: '',
  vault_scopes: 'https://www.googleapis.com/auth/ediscovery',
}

export const DROPBOX_BUSINESS_DEFAULTS = {
  team_id: '',
  client_id: '',
  client_secret: '',
  refresh_token: '',
  scopes: 'team_info.read team_data.member files.metadata.read files.content.read',
}

export const ZOOM_DEFAULTS = {
  account_id: '',
  client_id: '',
  client_secret: '',
  scopes: 'user:read:admin recording:read:admin chat_message:read:admin',
}

export const INTUNE_DEFAULTS = {
  tenant_id: '',
  client_id: '',
  client_secret: '',
  graph_base: 'https://graph.microsoft.com/v1.0',
  scopes: 'https://graph.microsoft.com/.default',
}

export const JAMF_DEFAULTS = {
  base_url: '',
  auth_type: 'oauth',
  client_id: '',
  client_secret: '',
  username: '',
  password: '',
}

export const DEFENDER_DEFAULTS = {
  tenant_id: '',
  client_id: '',
  client_secret: '',
  api_base: 'https://api.securitycenter.microsoft.com',
  scopes: 'https://api.securitycenter.microsoft.com/.default',
}

export const CROWDSTRIKE_DEFAULTS = {
  base_url: 'https://api.crowdstrike.com',
  client_id: '',
  client_secret: '',
}

export const LOG_SHIPPING_DEFAULTS = {
  tenant_id: '',
  client_id: '',
  client_secret: '',
  sharepoint_site_id: '',
  sharepoint_drive_id: '',
  sharepoint_drive_name: '',
  sharepoint_folder: 'DiscoveryOneLogs',
  interval_hours: 24,
  run_on_startup: true,
  graph_base: 'https://graph.microsoft.com/v1.0',
  scope: 'https://graph.microsoft.com/.default',
  max_file_mb: 250,
  max_archive_mb: 250,
  max_files: 5000,
  timeout_seconds: 120,
  retry_count: 3,
}

export const AI_DEFAULTS = {
  url: '',
  model: '',
  api_key: '',
  auth_header: 'Authorization',
  timeout_seconds: 25,
  temperature: 0.1,
  system_prompt: '',
  assistant_enabled: true,
  case_summary_enabled: true,
  search_builder_enabled: true,
  search_builder_max_suggestions: 4,
  name_email_review_enabled: true,
  name_email_ai_enabled: false,
}

export const BUILT_IN_PRESERVATION = [
  ['email', 'Email (O365/Google)', true],
  ['onedrive', 'OneDrive', true],
  ['gdrive', 'Google Drive', false],
  ['box', 'Box', true],
  ['dropbox', 'Dropbox', false],
  ['slack', 'Slack', true],
  ['zoom', 'Zoom', false],
]

export const INTEGRATION_REQUIREMENTS = {
  smtp: {
    text: 'Enable SMTP mail delivery for notifications. Configure SMTP host, sender, and port in System mail settings after setup.',
    values: ['Host', 'Port', 'Sender address'],
  },
  servicenow: {
    text: 'Enable ticket creation workflows.',
    values: ['Base URL', 'Auth type', 'Username/password or OAuth client', 'Table'],
  },
  docusign: {
    text: 'Enable e-signature workflows.',
    values: ['Base URL', 'Account ID', 'Template ID', 'Signer role', 'Template tab labels', 'Integration key', 'User ID', 'Private key', 'Connect HMAC key'],
  },
  purview: {
    text: 'Enable Microsoft Purview preservation automation.',
    values: ['Tenant ID', 'Client ID', 'Client secret', 'Graph base', 'Security base'],
  },
  google_workspace: {
    text: 'Store Google Workspace Vault connection settings for a future adapter. This build does not execute Google Vault holds; track Gmail and Google Drive preservation manually.',
    values: ['Customer ID', 'Delegated admin', 'Service account client email', 'Private key', 'Vault scope'],
  },
  dropbox_business: {
    text: 'Store Dropbox Business connection settings for a future adapter. This build does not execute Dropbox holds; track Dropbox preservation manually.',
    values: ['Team ID', 'OAuth app key', 'OAuth app secret', 'Refresh token or app authorization', 'Team/content scopes'],
  },
  zoom: {
    text: 'Store Zoom connection settings for a future adapter. This build does not execute Zoom preservation; track Zoom preservation manually.',
    values: ['Account ID', 'Server-to-server OAuth client ID', 'Client secret', 'Admin scopes'],
  },
  intune: {
    text: 'Store Intune connection settings for a future adapter. This build does not execute endpoint preservation or inventory collection.',
    values: ['Tenant ID', 'Client ID', 'Client secret', 'Graph scopes'],
  },
  jamf: {
    text: 'Store Jamf Pro connection settings for a future adapter. This build does not execute endpoint preservation or inventory collection.',
    values: ['Base URL', 'OAuth client ID/secret or username/password'],
  },
  defender: {
    text: 'Store Microsoft Defender connection settings for a future adapter. This build does not collect endpoint evidence.',
    values: ['Tenant ID', 'Client ID', 'Client secret', 'Defender API base'],
  },
  crowdstrike: {
    text: 'Store CrowdStrike Falcon connection settings for a future adapter. This build does not collect endpoint evidence.',
    values: ['Falcon cloud API base', 'Client ID', 'Client secret'],
  },
  log_shipping: {
    text: 'Ship DiscoveryOne log archives to a SharePoint document library through Microsoft Graph.',
    values: ['Tenant ID', 'Client ID', 'Client secret', 'SharePoint site', 'Drive ID or name', 'Destination folder', 'Schedule and upload limits'],
  },
  slack: {
    text: 'Enable Slack preservation tracking/workflows.',
    values: ['Legal Holds token', 'API base', 'OAuth client fields if callback support is used'],
  },
  box: {
    text: 'Enable Box legal hold workflows through a Box custom app using JWT authentication.',
    values: ['Enterprise ID', 'Client ID', 'Client secret', 'JWT public key ID', 'Private key', 'Passphrase'],
  },
  ai: {
    text: 'Enable AI-assisted case summaries, search drafting, and assistant features through an OpenAI-compatible chat completions endpoint.',
    values: ['Endpoint URL', 'Model', 'API key', 'Feature toggles'],
  },
}

export const INTEGRATION_CONFIG_DEFAULTS = {
  oidc: {},
  person_lookup: { max_custodians: 100, http_timeout_seconds: 10 },
  ntp_ack_bridge: { bridge_url: '', display_url: '', shared_secret: '' },
  servicenow: SERVICENOW_DEFAULTS,
  box: BOX_DEFAULTS,
  google_workspace: GOOGLE_WORKSPACE_DEFAULTS,
  dropbox_business: DROPBOX_BUSINESS_DEFAULTS,
  zoom: ZOOM_DEFAULTS,
  intune: INTUNE_DEFAULTS,
  jamf: JAMF_DEFAULTS,
  defender: DEFENDER_DEFAULTS,
  crowdstrike: CROWDSTRIKE_DEFAULTS,
  log_shipping: LOG_SHIPPING_DEFAULTS,
  purview: { http_timeout_seconds: 60, http_retry_count: 3 },
  docusign: { signer_role: 'signer', auth_server: 'account-d.docusign.com', case_name_tab: 'case_name', record_type_tab: 'recordtype', date_from_tab: 'datefrom', date_to_tab: 'dateto', resend_allow_recipient_correction_fallback: false, connect_key: '', connect_keys: '' },
  slack: {
    api_base: 'https://slack.com/api',
    oauth_authorize_url: 'https://slack.com/oauth/v2/authorize',
    oauth_access_url: 'https://slack.com/api/oauth.v2.access',
    oauth_state_ttl_seconds: 900,
  },
  ai: AI_DEFAULTS,
}

export const EMPTY_INTEGRATION_CONFIG_DEFAULTS = {
  oidc: {},
  person_lookup: {},
  ntp_ack_bridge: {},
  servicenow: {},
  box: {},
  google_workspace: {},
  dropbox_business: {},
  zoom: {},
  intune: {},
  jamf: {},
  defender: {},
  crowdstrike: {},
  log_shipping: {},
  purview: {},
  docusign: {},
  slack: {},
  ai: {},
}

export const ENABLED_INTEGRATION_DEFAULTS = Object.fromEntries(
  SYSTEM_INTEGRATION_FLAGS.map(([key]) => [key, false])
)

export const PRESERVATION_SOURCE_DEFAULTS = Object.fromEntries(
  BUILT_IN_PRESERVATION.map(([key, , enabled]) => [key, enabled])
)

export const CASE_NAMING_MODE_DEFAULT = 'legal_case_name'

export const CASE_NAMING_OPTIONS = [
  ['legal_case_name', 'Use Legal Case Name', 'The submitted legal case name becomes the DiscoveryOne case name. Duplicate names receive a numeric suffix.'],
  ['created_date', 'Use Created Date + Sequence', 'DiscoveryOne generates names from the creation date and stores the submitted legal case name separately.'],
  ['color', 'Use Color Naming', 'Use the legacy yearly color naming sequence and store the submitted legal case name separately.'],
]

export const CASE_NAMING_MODES = CASE_NAMING_OPTIONS.map(([mode]) => mode)

export function normalizeCaseNamingMode(value) {
  const mode = String(value || CASE_NAMING_MODE_DEFAULT).trim().toLowerCase()
  return CASE_NAMING_MODES.includes(mode) ? mode : CASE_NAMING_MODE_DEFAULT
}

