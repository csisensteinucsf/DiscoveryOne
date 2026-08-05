import { FieldHelp } from './SetupCoreSteps.jsx'

export default function SetupExtendedIntegrationFields({ integrationKey, form, updateIntegrationConfig }) {
  const key = integrationKey
  return (
    <>
                            {key === 'google_workspace' && form.enabled_integrations.google_workspace && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Configure a Google Cloud service account with domain-wide delegation, then authorize the Vault API scope for Google Workspace legal holds.
                                </div>
                                <label>
                                  Customer ID
                                  <input className="input" value={form.integration_configs.google_workspace?.customer_id || ''} onChange={e => updateIntegrationConfig('google_workspace', 'customer_id', e.target.value)} placeholder="C012abcde" />
                                </label>
                                <label>
                                  Delegated Admin Email
                                  <input className="input" type="email" value={form.integration_configs.google_workspace?.delegated_admin_email || ''} onChange={e => updateIntegrationConfig('google_workspace', 'delegated_admin_email', e.target.value)} placeholder="vault-admin@example.edu" />
                                </label>
                                <label>
                                  Service Account Client Email
                                  <input className="input" value={form.integration_configs.google_workspace?.service_account_client_email || ''} onChange={e => updateIntegrationConfig('google_workspace', 'service_account_client_email', e.target.value)} placeholder="name@project.iam.gserviceaccount.com" />
                                </label>
                                <label>
                                  Service Account Private Key
                                  <textarea className="input" rows={4} value={form.integration_configs.google_workspace?.service_account_private_key || ''} onChange={e => updateIntegrationConfig('google_workspace', 'service_account_private_key', e.target.value)} />
                                  <FieldHelp>This private key is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Vault Scopes
                                  <input className="input" value={form.integration_configs.google_workspace?.vault_scopes || ''} onChange={e => updateIntegrationConfig('google_workspace', 'vault_scopes', e.target.value)} placeholder="https://www.googleapis.com/auth/ediscovery" />
                                  <FieldHelp>Use the Google Vault scope for Gmail and Google Drive holds.</FieldHelp>
                                </label>
                              </div>
                            )}
    
                            {key === 'dropbox_business' && form.enabled_integrations.dropbox_business && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Create a Dropbox Business app with team access and scoped permissions for team information, member data, and file metadata/content needed for preservation workflows.
                                </div>
                                <label>
                                  Team ID
                                  <input className="input" value={form.integration_configs.dropbox_business?.team_id || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'team_id', e.target.value)} placeholder="dbtid:..." />
                                </label>
                                <label>
                                  OAuth App Key
                                  <input className="input" value={form.integration_configs.dropbox_business?.client_id || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  OAuth App Secret
                                  <input className="input" type="password" value={form.integration_configs.dropbox_business?.client_secret || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Refresh Token
                                  <input className="input" type="password" value={form.integration_configs.dropbox_business?.refresh_token || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'refresh_token', e.target.value)} />
                                  <FieldHelp>Leave blank until live Dropbox API automation is enabled.</FieldHelp>
                                </label>
                                <label>
                                  Scopes
                                  <input className="input" value={form.integration_configs.dropbox_business?.scopes || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'scopes', e.target.value)} />
                                </label>
                              </div>
                            )}
    
                            {key === 'zoom' && form.enabled_integrations.zoom && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Use a Zoom server-to-server OAuth app with admin scopes for users, recordings, meeting metadata, and chat data your legal workflow preserves.
                                </div>
                                <label>
                                  Account ID
                                  <input className="input" value={form.integration_configs.zoom?.account_id || ''} onChange={e => updateIntegrationConfig('zoom', 'account_id', e.target.value)} />
                                </label>
                                <label>
                                  Client ID
                                  <input className="input" value={form.integration_configs.zoom?.client_id || ''} onChange={e => updateIntegrationConfig('zoom', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  Client Secret
                                  <input className="input" type="password" value={form.integration_configs.zoom?.client_secret || ''} onChange={e => updateIntegrationConfig('zoom', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Scopes
                                  <input className="input" value={form.integration_configs.zoom?.scopes || ''} onChange={e => updateIntegrationConfig('zoom', 'scopes', e.target.value)} />
                                </label>
                              </div>
                            )}
    
                            {key === 'intune' && form.enabled_integrations.intune && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Register an Entra ID app with Microsoft Graph application permissions for managed device inventory and preservation handoff workflows.
                                </div>
                                <label>
                                  Tenant ID
                                  <input className="input" value={form.integration_configs.intune?.tenant_id || ''} onChange={e => updateIntegrationConfig('intune', 'tenant_id', e.target.value)} />
                                </label>
                                <label>
                                  Client ID
                                  <input className="input" value={form.integration_configs.intune?.client_id || ''} onChange={e => updateIntegrationConfig('intune', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  Client Secret
                                  <input className="input" type="password" value={form.integration_configs.intune?.client_secret || ''} onChange={e => updateIntegrationConfig('intune', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Graph Base
                                  <input className="input" value={form.integration_configs.intune?.graph_base || ''} onChange={e => updateIntegrationConfig('intune', 'graph_base', e.target.value)} placeholder="https://graph.microsoft.com/v1.0" />
                                </label>
                                <label>
                                  Scopes
                                  <input className="input" value={form.integration_configs.intune?.scopes || ''} onChange={e => updateIntegrationConfig('intune', 'scopes', e.target.value)} />
                                </label>
                              </div>
                            )}
    
                            {key === 'jamf' && form.enabled_integrations.jamf && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Configure Jamf Pro API access for Apple endpoint inventory and preservation handoff workflows.
                                </div>
                                <label>
                                  Jamf Pro Base URL
                                  <input className="input" value={form.integration_configs.jamf?.base_url || ''} onChange={e => updateIntegrationConfig('jamf', 'base_url', e.target.value)} placeholder="https://yourorg.jamfcloud.com" />
                                </label>
                                <label>
                                  Auth Type
                                  <select className="input" value={form.integration_configs.jamf?.auth_type || 'oauth'} onChange={e => updateIntegrationConfig('jamf', 'auth_type', e.target.value)}>
                                    <option value="oauth">OAuth client credentials</option>
                                    <option value="basic">Username and password</option>
                                  </select>
                                </label>
                                {(form.integration_configs.jamf?.auth_type || 'oauth') === 'basic' ? (
                                  <>
                                    <label>
                                      Username
                                      <input className="input" value={form.integration_configs.jamf?.username || ''} onChange={e => updateIntegrationConfig('jamf', 'username', e.target.value)} />
                                    </label>
                                    <label>
                                      Password
                                      <input className="input" type="password" value={form.integration_configs.jamf?.password || ''} onChange={e => updateIntegrationConfig('jamf', 'password', e.target.value)} />
                                      <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                    </label>
                                  </>
                                ) : (
                                  <>
                                    <label>
                                      Client ID
                                      <input className="input" value={form.integration_configs.jamf?.client_id || ''} onChange={e => updateIntegrationConfig('jamf', 'client_id', e.target.value)} />
                                    </label>
                                    <label>
                                      Client Secret
                                      <input className="input" type="password" value={form.integration_configs.jamf?.client_secret || ''} onChange={e => updateIntegrationConfig('jamf', 'client_secret', e.target.value)} />
                                      <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                    </label>
                                  </>
                                )}
                              </div>
                            )}
    
                            {key === 'defender' && form.enabled_integrations.defender && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Register an Entra ID app for Microsoft Defender endpoint evidence and device investigation workflows.
                                </div>
                                <label>
                                  Tenant ID
                                  <input className="input" value={form.integration_configs.defender?.tenant_id || ''} onChange={e => updateIntegrationConfig('defender', 'tenant_id', e.target.value)} />
                                </label>
                                <label>
                                  Client ID
                                  <input className="input" value={form.integration_configs.defender?.client_id || ''} onChange={e => updateIntegrationConfig('defender', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  Client Secret
                                  <input className="input" type="password" value={form.integration_configs.defender?.client_secret || ''} onChange={e => updateIntegrationConfig('defender', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  Defender API Base
                                  <input className="input" value={form.integration_configs.defender?.api_base || ''} onChange={e => updateIntegrationConfig('defender', 'api_base', e.target.value)} placeholder="https://api.securitycenter.microsoft.com" />
                                </label>
                                <label>
                                  Scopes
                                  <input className="input" value={form.integration_configs.defender?.scopes || ''} onChange={e => updateIntegrationConfig('defender', 'scopes', e.target.value)} />
                                </label>
                              </div>
                            )}
    
                            {key === 'crowdstrike' && form.enabled_integrations.crowdstrike && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Create a CrowdStrike Falcon API client with host and investigation permissions needed for endpoint preservation handoff workflows.
                                </div>
                                <label>
                                  Falcon API Base
                                  <input className="input" value={form.integration_configs.crowdstrike?.base_url || ''} onChange={e => updateIntegrationConfig('crowdstrike', 'base_url', e.target.value)} placeholder="https://api.crowdstrike.com" />
                                </label>
                                <label>
                                  Client ID
                                  <input className="input" value={form.integration_configs.crowdstrike?.client_id || ''} onChange={e => updateIntegrationConfig('crowdstrike', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  Client Secret
                                  <input className="input" type="password" value={form.integration_configs.crowdstrike?.client_secret || ''} onChange={e => updateIntegrationConfig('crowdstrike', 'client_secret', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                              </div>
                            )}
    
                            {key === 'log_shipping' && form.enabled_integrations.log_shipping && (
                              <div className='form-grid' style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Upload compressed DiscoveryOne log archives to a SharePoint document library using an Entra ID application.
                                </div>
                                <label>Tenant ID<input className='input' value={form.integration_configs.log_shipping?.tenant_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'tenant_id', e.target.value)} /></label>
                                <label>Client ID<input className='input' value={form.integration_configs.log_shipping?.client_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'client_id', e.target.value)} /></label>
                                <label>Client Secret<input className='input' type='password' value={form.integration_configs.log_shipping?.client_secret || ''} onChange={e => updateIntegrationConfig('log_shipping', 'client_secret', e.target.value)} /><FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp></label>
                                <label>SharePoint Site ID<input className='input' value={form.integration_configs.log_shipping?.sharepoint_site_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_site_id', e.target.value)} placeholder='contoso.sharepoint.com,site-collection-id,site-id' /></label>
                                <label>Drive ID<input className='input' value={form.integration_configs.log_shipping?.sharepoint_drive_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_drive_id', e.target.value)} /><FieldHelp>Provide a drive ID or a drive name.</FieldHelp></label>
                                <label>Drive Name<input className='input' value={form.integration_configs.log_shipping?.sharepoint_drive_name || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_drive_name', e.target.value)} placeholder='Documents' /></label>
                                <label>Destination Folder<input className='input' value={form.integration_configs.log_shipping?.sharepoint_folder || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_folder', e.target.value)} placeholder='DiscoveryOneLogs' /></label>
                                <label>Interval Hours<input className='input' type='number' min='1' max='720' step='0.5' value={form.integration_configs.log_shipping?.interval_hours ?? 24} onChange={e => updateIntegrationConfig('log_shipping', 'interval_hours', e.target.value)} /></label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type='checkbox' checked={form.integration_configs.log_shipping?.run_on_startup !== false} onChange={e => updateIntegrationConfig('log_shipping', 'run_on_startup', e.target.checked)} />Run once when enabled</label>
                                <label>Graph Base<input className='input' value={form.integration_configs.log_shipping?.graph_base || ''} onChange={e => updateIntegrationConfig('log_shipping', 'graph_base', e.target.value)} placeholder='https://graph.microsoft.com/v1.0' /></label>
                                <label>OAuth Scope<input className='input' value={form.integration_configs.log_shipping?.scope || ''} onChange={e => updateIntegrationConfig('log_shipping', 'scope', e.target.value)} placeholder='https://graph.microsoft.com/.default' /></label>
                                <label>Maximum File MB<input className='input' type='number' min='1' max='250' value={form.integration_configs.log_shipping?.max_file_mb ?? 250} onChange={e => updateIntegrationConfig('log_shipping', 'max_file_mb', e.target.value)} /></label>
                                <label>Maximum Archive MB<input className='input' type='number' min='1' max='250' value={form.integration_configs.log_shipping?.max_archive_mb ?? 250} onChange={e => updateIntegrationConfig('log_shipping', 'max_archive_mb', e.target.value)} /></label>
                                <label>Maximum Files<input className='input' type='number' min='1' max='5000' value={form.integration_configs.log_shipping?.max_files ?? 5000} onChange={e => updateIntegrationConfig('log_shipping', 'max_files', e.target.value)} /></label>
                                <label>Request Timeout Seconds<input className='input' type='number' min='5' max='300' value={form.integration_configs.log_shipping?.timeout_seconds ?? 120} onChange={e => updateIntegrationConfig('log_shipping', 'timeout_seconds', e.target.value)} /></label>
                                <label>Retry Count<input className='input' type='number' min='0' max='10' value={form.integration_configs.log_shipping?.retry_count ?? 3} onChange={e => updateIntegrationConfig('log_shipping', 'retry_count', e.target.value)} /></label>
                              </div>
                            )}

                            {key === 'slack' && form.enabled_integrations.slack && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <label>
                                  Legal Holds Token
                                  <input className="input" type="password" value={form.integration_configs.slack?.legal_holds_token || ''} onChange={e => updateIntegrationConfig('slack', 'legal_holds_token', e.target.value)} />
                                  <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
                                </label>
                                <label>
                                  API Base
                                  <input className="input" value={form.integration_configs.slack?.api_base || ''} onChange={e => updateIntegrationConfig('slack', 'api_base', e.target.value)} placeholder="https://slack.com/api" />
                                </label>
                                <label>
                                  OAuth Client ID
                                  <input className="input" value={form.integration_configs.slack?.client_id || ''} onChange={e => updateIntegrationConfig('slack', 'client_id', e.target.value)} />
                                </label>
                                <label>
                                  OAuth Client Secret
                                  <input className="input" type="password" value={form.integration_configs.slack?.client_secret || ''} onChange={e => updateIntegrationConfig('slack', 'client_secret', e.target.value)} />
                                  <FieldHelp>Only needed if this deployment uses Slack OAuth callback support.</FieldHelp>
                                </label>
                                <label>
                                  OAuth Redirect URI
                                  <input className="input" value={form.integration_configs.slack?.oauth_redirect_uri || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_redirect_uri', e.target.value)} />
                                </label>
                                <label>
                                  OAuth Bot Scopes
                                  <input className="input" value={form.integration_configs.slack?.oauth_scope || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_scope', e.target.value)} />
                                </label>
                                <label>
                                  OAuth User Scopes
                                  <input className="input" value={form.integration_configs.slack?.oauth_user_scope || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_user_scope', e.target.value)} />
                                </label>
                                <label>
                                  OAuth State Lifetime Seconds
                                  <input className="input" type="number" min="60" max="3600" value={form.integration_configs.slack?.oauth_state_ttl_seconds ?? 900} onChange={e => updateIntegrationConfig('slack', 'oauth_state_ttl_seconds', e.target.value)} />
                                </label>
                                <label>
                                  OAuth Authorize URL
                                  <input className="input" value={form.integration_configs.slack?.oauth_authorize_url || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_authorize_url', e.target.value)} placeholder="https://slack.com/oauth/v2/authorize" />
                                </label>
                                <label>
                                  OAuth Token URL
                                  <input className="input" value={form.integration_configs.slack?.oauth_access_url || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_access_url', e.target.value)} placeholder="https://slack.com/api/oauth.v2.access" />
                                </label>
                                <label>
                                  Proxy Shared Secret
                                  <input className="input" type="password" value={form.integration_configs.slack?.shared_secret || ''} onChange={e => updateIntegrationConfig('slack', 'shared_secret', e.target.value)} placeholder="Proxy shared secret" />
                                  <FieldHelp>Set this to require X-Proxy-Shared-Secret when the OAuth callback is behind a trusted proxy.</FieldHelp>
                                </label>
                              </div>
                            )}


                            {key === 'ai' && form.enabled_integrations.ai && (
                              <div className="form-grid" style={{ marginTop: 10 }}>
                                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>
                                  Configure an OpenAI-compatible chat completions endpoint for available DiscoveryOne AI features. The API key is encrypted before storage.
                                </div>
                                <label>Endpoint URL<input className="input" value={form.integration_configs.ai?.url || ''} onChange={e => updateIntegrationConfig('ai', 'url', e.target.value)} placeholder="https://api.openai.com/v1/chat/completions" /></label>
                                <label>Model<input className="input" value={form.integration_configs.ai?.model || ''} onChange={e => updateIntegrationConfig('ai', 'model', e.target.value)} placeholder="gpt-4.1-mini" /></label>
                                <label>API Key<input className="input" type="password" value={form.integration_configs.ai?.api_key || ''} onChange={e => updateIntegrationConfig('ai', 'api_key', e.target.value)} /><FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp></label>
                                <label>Auth Header<input className="input" value={form.integration_configs.ai?.auth_header || 'Authorization'} onChange={e => updateIntegrationConfig('ai', 'auth_header', e.target.value)} /></label>
                                <label>Timeout Seconds<input className="input" type="number" min="1" value={form.integration_configs.ai?.timeout_seconds ?? 25} onChange={e => updateIntegrationConfig('ai', 'timeout_seconds', e.target.value)} /></label>
                                <label>Temperature<input className="input" type="number" min="0" max="1" step="0.1" value={form.integration_configs.ai?.temperature ?? 0.1} onChange={e => updateIntegrationConfig('ai', 'temperature', e.target.value)} /></label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={form.integration_configs.ai?.assistant_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'assistant_enabled', e.target.checked)} />Enable AI assistant</label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={form.integration_configs.ai?.case_summary_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'case_summary_enabled', e.target.checked)} />Enable case summary AI</label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={form.integration_configs.ai?.search_builder_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'search_builder_enabled', e.target.checked)} />Enable search builder AI</label>
                                <label>Search Builder Max Suggestions<input className="input" type="number" min="1" max="8" value={(form.integration_configs.ai?.search_builder_max_suggestions ?? 4)} onChange={e => updateIntegrationConfig('ai', 'search_builder_max_suggestions', e.target.value)} /></label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={form.integration_configs.ai?.name_email_review_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'name_email_review_enabled', e.target.checked)} />Enable name/email review rules</label>
                                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={!!form.integration_configs.ai?.name_email_ai_enabled} onChange={e => updateIntegrationConfig('ai', 'name_email_ai_enabled', e.target.checked)} />Use AI for name/email review</label>
                              </div>
                            )}
    </>
  )
}