import { FieldHelp } from './SetupCoreSteps.jsx'

export default function SetupPrimaryIntegrationFields({ integrationKey, form, updateIntegrationConfig, updateSmtp }) {
  const key = integrationKey
  return (
    <>
                            {key === 'smtp' && form.enabled_integrations.smtp && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <label>
                                  SMTP Host
                                  <input className="input" value={form.smtp?.host || ''} onChange={e => updateSmtp('host', e.target.value)} placeholder="smtp.example.edu" />
                                </label>
                                <label>
                                  SMTP Port
                                  <input className="input" type="number" min="1" max="65535" value={form.smtp?.port || 587} onChange={e => updateSmtp('port', e.target.value)} />
                                </label>
                                <label>
                                  Timeout Seconds
                                  <input className="input" type="number" min="1" max="300" value={form.smtp?.timeout_seconds ?? 15} onChange={e => updateSmtp('timeout_seconds', e.target.value)} />
                                  <FieldHelp>Maximum time to wait for the SMTP server during each connection or send operation.</FieldHelp>
                                </label>
                                <label>
                                  From Address
                                  <input className="input" type="email" value={form.smtp?.from_address || ''} onChange={e => updateSmtp('from_address', e.target.value)} placeholder="ediscovery@example.edu" />
                                </label>
                                <label>
                                  Username
                                  <input className="input" value={form.smtp?.username || ''} onChange={e => updateSmtp('username', e.target.value)} placeholder="SMTP username" />
                                </label>
                                <label>
                                  Password
                                  <input className="input" type="password" value={form.smtp?.password || ''} onChange={e => updateSmtp('password', e.target.value)} placeholder="SMTP password" />
                                  <FieldHelp>Use this only when the SMTP relay requires authentication; the password is encrypted before storage.</FieldHelp>
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={!!form.smtp?.use_tls && !form.smtp?.use_ssl} onChange={e => updateSmtp('use_tls', e.target.checked)} disabled={!!form.smtp?.use_ssl} />
                                  Use STARTTLS
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={!!form.smtp?.use_ssl} onChange={e => updateSmtp('use_ssl', e.target.checked)} />
                                  Use SMTP over SSL
                                </label>
                              </div>
                            )}
    
                            {key === 'servicenow' && form.enabled_integrations.servicenow && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <label>
                                  ServiceNow Base URL
                                  <input className="input" value={form.integration_configs.servicenow?.base_url || ''} onChange={e => updateIntegrationConfig('servicenow', 'base_url', e.target.value)} placeholder="https://instance.service-now.com" />
                                </label>
                                <label>
                                  Auth Type
                                  <select className="input" value={form.integration_configs.servicenow?.auth_type || 'basic'} onChange={e => updateIntegrationConfig('servicenow', 'auth_type', e.target.value)}>
                                    <option value="basic">Username and password</option>
                                    <option value="oauth">OAuth client credentials</option>
                                  </select>
                                </label>
                                {(form.integration_configs.servicenow?.auth_type || 'basic') === 'oauth' ? (
                                  <>
                                    <label>
                                      OAuth Client ID
                                      <input className="input" value={form.integration_configs.servicenow?.oauth_client_id || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_client_id', e.target.value)} />
                                    </label>
                                    <label>
                                      OAuth Client Secret
                                      <input className="input" type="password" value={form.integration_configs.servicenow?.oauth_client_secret || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_client_secret', e.target.value)} />
                                      <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                    </label>
                                    <label>
                                      OAuth Token URL
                                      <input className="input" value={form.integration_configs.servicenow?.oauth_token_url || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_token_url', e.target.value)} placeholder="https://instance.service-now.com/oauth_token.do" />
                                      <FieldHelp>Leave blank to use the standard ServiceNow token URL under the base URL.</FieldHelp>
                                    </label>
                                    <label>
                                      OAuth Scope
                                      <input className="input" value={form.integration_configs.servicenow?.oauth_scope || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_scope', e.target.value)} placeholder="OAuth scope" />
                                    </label>
                                  </>
                                ) : (
                                  <>
                                    <label>
                                      Username
                                      <input className="input" value={form.integration_configs.servicenow?.username || ''} onChange={e => updateIntegrationConfig('servicenow', 'username', e.target.value)} />
                                    </label>
                                    <label>
                                      Password
                                      <input className="input" type="password" value={form.integration_configs.servicenow?.password || ''} onChange={e => updateIntegrationConfig('servicenow', 'password', e.target.value)} />
                                      <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                    </label>
                                  </>
                                )}
                                <label>
                                  Create Table
                                  <input className="input" value={form.integration_configs.servicenow?.table || ''} onChange={e => updateIntegrationConfig('servicenow', 'table', e.target.value)} placeholder="incident" />
                                </label>
                                <label>
                                  Status Table
                                  <input className="input" value={form.integration_configs.servicenow?.status_table || ''} onChange={e => updateIntegrationConfig('servicenow', 'status_table', e.target.value)} placeholder="incident" />
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={!!form.integration_configs.servicenow?.use_import_api} onChange={e => updateIntegrationConfig('servicenow', 'use_import_api', e.target.checked)} />
                                  Use ServiceNow Import Set API
                                </label>
                                <label>
                                  Source System
                                  <input className="input" value={form.integration_configs.servicenow?.source_system || ''} onChange={e => updateIntegrationConfig('servicenow', 'source_system', e.target.value)} placeholder="discoveryone" />
                                </label>
                                <label>
                                  Default Customer ID
                                  <input className="input" value={form.integration_configs.servicenow?.default_customer_id || ''} onChange={e => updateIntegrationConfig('servicenow', 'default_customer_id', e.target.value)} placeholder="Fallback customer ID" />
                                  <FieldHelp>Used only when a user creating tickets does not have their own Employee ID.</FieldHelp>
                                </label>
                                <label>
                                  App Customer ID
                                  <input className="input" value={form.integration_configs.servicenow?.customer_id || ''} onChange={e => updateIntegrationConfig('servicenow', 'customer_id', e.target.value)} placeholder="discoveryone" />
                                </label>
                              </div>
                            )}
    
                            {key === 'box' && form.enabled_integrations.box && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Create a Box custom app in the Box Admin Console using Server Authentication with JWT. Grant enterprise access and enable legal hold scopes before authorizing the app.
                                </div>
                                <label>
                                  Enterprise ID
                                  <input className="input" value={form.integration_configs.box?.enterprise_id || ''} onChange={e => updateIntegrationConfig('box', 'enterprise_id', e.target.value)} />
                                </label>
                                <label>
                                  Client ID
                                  <input className="input" value={form.integration_configs.box?.client_id || ''} onChange={e => updateIntegrationConfig('box', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  Client Secret
                                  <input className="input" type="password" value={form.integration_configs.box?.client_secret || ''} onChange={e => updateIntegrationConfig('box', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  JWT Public Key ID
                                  <input className="input" value={form.integration_configs.box?.jwt_key_id || ''} onChange={e => updateIntegrationConfig('box', 'jwt_key_id', e.target.value)} />
                                </label>
                                <label>
                                  JWT Private Key
                                  <textarea className="input" rows={4} value={form.integration_configs.box?.jwt_private_key || ''} onChange={e => updateIntegrationConfig('box', 'jwt_private_key', e.target.value)} />
                                  <FieldHelp>This private key is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  JWT Passphrase
                                  <input className="input" type="password" value={form.integration_configs.box?.jwt_passphrase || ''} onChange={e => updateIntegrationConfig('box', 'jwt_passphrase', e.target.value)} />
                                  <FieldHelp>This passphrase is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                              </div>
                            )}
    
                            {key === 'docusign' && form.enabled_integrations.docusign && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <label>
                                  DocuSign Base URL
                                  <input className="input" value={form.integration_configs.docusign?.base_url || ''} onChange={e => updateIntegrationConfig('docusign', 'base_url', e.target.value)} />
                                </label>
                                <label>
                                  Account ID
                                  <input className="input" value={form.integration_configs.docusign?.account_id || ''} onChange={e => updateIntegrationConfig('docusign', 'account_id', e.target.value)} />
                                </label>
                                <label>
                                  Template ID
                                  <input className="input" value={form.integration_configs.docusign?.template_id || ''} onChange={e => updateIntegrationConfig('docusign', 'template_id', e.target.value)} />
                                </label>
                                <label>
                                  Signer Role
                                  <input className="input" value={form.integration_configs.docusign?.signer_role || ''} onChange={e => updateIntegrationConfig('docusign', 'signer_role', e.target.value)} placeholder="signer" />
                                </label>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Match these values to the text tab labels in your DocuSign template. DiscoveryOne fills these tabs when it sends a consent request.
                                </div>
                                <label>
                                  Matter Name Tab Label
                                  <input className="input" value={form.integration_configs.docusign?.case_name_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'case_name_tab', e.target.value)} placeholder="case_name" />
                                </label>
                                <label>
                                  Record Type Tab Label
                                  <input className="input" value={form.integration_configs.docusign?.record_type_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'record_type_tab', e.target.value)} placeholder="recordtype" />
                                </label>
                                <label>
                                  Date From Tab Label
                                  <input className="input" value={form.integration_configs.docusign?.date_from_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'date_from_tab', e.target.value)} placeholder="datefrom" />
                                </label>
                                <label>
                                  Date To Tab Label
                                  <input className="input" value={form.integration_configs.docusign?.date_to_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'date_to_tab', e.target.value)} placeholder="dateto" />
                                </label>
                                <label>
                                  Integration Key
                                  <input className="input" value={form.integration_configs.docusign?.integration_key || ''} onChange={e => updateIntegrationConfig('docusign', 'integration_key', e.target.value)} />
                                </label>
                                <label>
                                  User ID
                                  <input className="input" value={form.integration_configs.docusign?.user_id || ''} onChange={e => updateIntegrationConfig('docusign', 'user_id', e.target.value)} />
                                </label>
                                <label>
                                  Auth Server
                                  <input className="input" value={form.integration_configs.docusign?.auth_server || ''} onChange={e => updateIntegrationConfig('docusign', 'auth_server', e.target.value)} placeholder="account-d.docusign.com" />
                                </label>
                                <label>
                                  Private Key
                                  <textarea className="input" rows={4} value={form.integration_configs.docusign?.private_key || ''} onChange={e => updateIntegrationConfig('docusign', 'private_key', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Connect HMAC Key
                                  <input className="input" type="password" value={form.integration_configs.docusign?.connect_key || ''} onChange={e => updateIntegrationConfig('docusign', 'connect_key', e.target.value)} />
                                  <FieldHelp>This secret validates DocuSign Connect webhook payloads and is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Additional Connect HMAC Keys
                                  <textarea className="input" rows={2} value={form.integration_configs.docusign?.connect_keys || ''} onChange={e => updateIntegrationConfig('docusign', 'connect_keys', e.target.value)} placeholder="Comma-separated rotated keys" />
                                  <FieldHelp>Use this while rotating DocuSign Connect HMAC keys; otherwise leave it blank.</FieldHelp>
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={!!form.integration_configs.docusign?.resend_allow_recipient_correction_fallback} onChange={e => updateIntegrationConfig('docusign', 'resend_allow_recipient_correction_fallback', e.target.checked)} />
                                  Allow recipient correction fallback on resend
                                </label>
                              </div>
                            )}
    
                            {key === 'purview' && form.enabled_integrations.purview && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <label>
                                  Tenant ID
                                  <input className="input" value={form.integration_configs.purview?.tenant_id || ''} onChange={e => updateIntegrationConfig('purview', 'tenant_id', e.target.value)} />
                                </label>
                                <label>
                                  Client ID
                                  <input className="input" value={form.integration_configs.purview?.client_id || ''} onChange={e => updateIntegrationConfig('purview', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  Client Secret
                                  <input className="input" type="password" value={form.integration_configs.purview?.client_secret || ''} onChange={e => updateIntegrationConfig('purview', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Graph Beta Base
                                  <input className="input" value={form.integration_configs.purview?.graph_base || ''} onChange={e => updateIntegrationConfig('purview', 'graph_base', e.target.value)} placeholder="https://graph.microsoft.com/beta" />
                                </label>
                                <label>
                                  Graph v1 Base
                                  <input className="input" value={form.integration_configs.purview?.graph_base_v1 || ''} onChange={e => updateIntegrationConfig('purview', 'graph_base_v1', e.target.value)} placeholder="https://graph.microsoft.com/v1.0" />
                                </label>
                                <label>
                                  Security Base
                                  <input className="input" value={form.integration_configs.purview?.security_base || ''} onChange={e => updateIntegrationConfig('purview', 'security_base', e.target.value)} />
                                </label>
                                <label>
                                  HTTP Timeout Seconds
                                  <input className="input" type="number" min="5" max="300" value={form.integration_configs.purview?.http_timeout_seconds ?? 60} onChange={e => updateIntegrationConfig('purview', 'http_timeout_seconds', e.target.value)} />
                                  <FieldHelp>Maximum time to wait for each Microsoft API request.</FieldHelp>
                                </label>
                                <label>
                                  HTTP Retry Count
                                  <input className="input" type="number" min="0" max="10" value={form.integration_configs.purview?.http_retry_count ?? 3} onChange={e => updateIntegrationConfig('purview', 'http_retry_count', e.target.value)} />
                                  <FieldHelp>Number of retries for throttling and temporary Microsoft API failures.</FieldHelp>
                                </label>
                                <label>
                                  OneDrive Lookup Limit
                                  <input className="input" type="number" min="0" value={form.integration_configs.purview?.status_onedrive_lookup_limit ?? 25} onChange={e => updateIntegrationConfig('purview', 'status_onedrive_lookup_limit', e.target.value)} />
                                  <FieldHelp>Limits how many missing OneDrive data sources DiscoveryOne resolves during a status check. Use 0 to disable the lookup.</FieldHelp>
                                </label>
                                <label>
                                  Status Poll Delay Seconds
                                  <input className="input" type="number" min="0" value={form.integration_configs.purview?.status_poll_delay_seconds ?? 120} onChange={e => updateIntegrationConfig('purview', 'status_poll_delay_seconds', e.target.value)} />
                                  <FieldHelp>How long DiscoveryOne waits before checking Purview status after creating or updating holds.</FieldHelp>
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={!!form.integration_configs.purview?.add_data_sources} onChange={e => updateIntegrationConfig('purview', 'add_data_sources', e.target.checked)} />
                                  Add Purview data sources when creating a matter
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={!!form.integration_configs.purview?.hold_missing_email_mark_failed} onChange={e => updateIntegrationConfig('purview', 'hold_missing_email_mark_failed', e.target.checked)} />
                                  Mark missing-email hold attempts as failed
                                </label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                                  <input type="checkbox" checked={form.integration_configs.purview?.export_poll_enabled !== false} onChange={e => updateIntegrationConfig('purview', 'export_poll_enabled', e.target.checked)} />
                                  Poll Purview exports on a schedule
                                </label>
                                <label>
                                  Export Poll Hours
                                  <input className="input" value={form.integration_configs.purview?.export_poll_hours || '7,18'} onChange={e => updateIntegrationConfig('purview', 'export_poll_hours', e.target.value)} placeholder="7,18" />
                                  <FieldHelp>Comma-separated local hours when DiscoveryOne should check for Purview exports.</FieldHelp>
                                </label>
                                <label>
                                  Export Poll Minute
                                  <input className="input" type="number" min="0" max="59" value={form.integration_configs.purview?.export_poll_minute ?? 0} onChange={e => updateIntegrationConfig('purview', 'export_poll_minute', e.target.value)} />
                                </label>
                                <label>
                                  Export Poll Timezone
                                  <input className="input" value={form.integration_configs.purview?.export_poll_timezone || ''} onChange={e => updateIntegrationConfig('purview', 'export_poll_timezone', e.target.value)} placeholder="America/Los_Angeles" />
                                  <FieldHelp>Leave blank to use the server timezone.</FieldHelp>
                                </label>
                                <label>
                                  Export Poll Requestor Groups
                                  <input className="input" value={form.integration_configs.purview?.export_poll_requestor_groups || 'pra'} onChange={e => updateIntegrationConfig('purview', 'export_poll_requestor_groups', e.target.value)} placeholder="pra" />
                                  <FieldHelp>Matters whose primary requestor is in one of these groups are included in scheduled export checks.</FieldHelp>
                                </label>
                              </div>
                            )}
    </>
  )
}