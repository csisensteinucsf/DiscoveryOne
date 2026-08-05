import {
  MASKED_SECRET_VALUE,
  secretInputValue,
} from './systemUtils.js'

export default function SystemAdditionalIntegrationConfigSections({ integrationSettings, updateIntegrationConfig }) {
  return (
    <>
          {integrationSettings.enabled?.google_workspace && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Google Workspace</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores Google Workspace Vault credentials for a future adapter. This build does not execute Vault holds; track Gmail and Google Drive preservation manually.
              </p>
              <div className="form-grid">
                <label>Customer ID<input className="input" value={integrationSettings.configs?.google_workspace?.customer_id || ''} onChange={e => updateIntegrationConfig('google_workspace', 'customer_id', e.target.value)} placeholder="C012abcde" /></label>
                <label>Delegated admin email<input className="input" type="email" value={integrationSettings.configs?.google_workspace?.delegated_admin_email || ''} onChange={e => updateIntegrationConfig('google_workspace', 'delegated_admin_email', e.target.value)} /></label>
                <label>Service account client email<input className="input" value={integrationSettings.configs?.google_workspace?.service_account_client_email || ''} onChange={e => updateIntegrationConfig('google_workspace', 'service_account_client_email', e.target.value)} /></label>
                <label>Service account private key<textarea className="input" rows={4} value={secretInputValue(integrationSettings.configs?.google_workspace?.service_account_private_key)} onChange={e => updateIntegrationConfig('google_workspace', 'service_account_private_key', e.target.value)} placeholder={integrationSettings.configs?.google_workspace?.service_account_private_key === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Vault scopes<input className="input" value={integrationSettings.configs?.google_workspace?.vault_scopes || ''} onChange={e => updateIntegrationConfig('google_workspace', 'vault_scopes', e.target.value)} placeholder="https://www.googleapis.com/auth/ediscovery" /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.dropbox_business && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Dropbox Business</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores Dropbox Business credentials for a future adapter. This build does not execute Dropbox preservation; track it manually.
              </p>
              <div className="form-grid">
                <label>Team ID<input className="input" value={integrationSettings.configs?.dropbox_business?.team_id || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'team_id', e.target.value)} placeholder="dbtid:..." /></label>
                <label>OAuth app key<input className="input" value={integrationSettings.configs?.dropbox_business?.client_id || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'client_id', e.target.value)} /></label>
                <label>OAuth app secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.dropbox_business?.client_secret)} onChange={e => updateIntegrationConfig('dropbox_business', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.dropbox_business?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Refresh token<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.dropbox_business?.refresh_token)} onChange={e => updateIntegrationConfig('dropbox_business', 'refresh_token', e.target.value)} placeholder={integrationSettings.configs?.dropbox_business?.refresh_token === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Scopes<input className="input" value={integrationSettings.configs?.dropbox_business?.scopes || ''} onChange={e => updateIntegrationConfig('dropbox_business', 'scopes', e.target.value)} /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.zoom && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Zoom</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores Zoom credentials for a future adapter. This build does not collect Zoom data or execute preservation; track it manually.
              </p>
              <div className="form-grid">
                <label>Account ID<input className="input" value={integrationSettings.configs?.zoom?.account_id || ''} onChange={e => updateIntegrationConfig('zoom', 'account_id', e.target.value)} /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.zoom?.client_id || ''} onChange={e => updateIntegrationConfig('zoom', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.zoom?.client_secret)} onChange={e => updateIntegrationConfig('zoom', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.zoom?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Scopes<input className="input" value={integrationSettings.configs?.zoom?.scopes || ''} onChange={e => updateIntegrationConfig('zoom', 'scopes', e.target.value)} /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.intune && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Microsoft Intune</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores Intune credentials for a future adapter. This build does not collect device inventory or execute endpoint preservation.
              </p>
              <div className="form-grid">
                <label>Tenant ID<input className="input" value={integrationSettings.configs?.intune?.tenant_id || ''} onChange={e => updateIntegrationConfig('intune', 'tenant_id', e.target.value)} /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.intune?.client_id || ''} onChange={e => updateIntegrationConfig('intune', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.intune?.client_secret)} onChange={e => updateIntegrationConfig('intune', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.intune?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Graph base<input className="input" value={integrationSettings.configs?.intune?.graph_base || ''} onChange={e => updateIntegrationConfig('intune', 'graph_base', e.target.value)} placeholder="https://graph.microsoft.com/v1.0" /></label>
                <label>Scopes<input className="input" value={integrationSettings.configs?.intune?.scopes || ''} onChange={e => updateIntegrationConfig('intune', 'scopes', e.target.value)} /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.jamf && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Jamf</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores Jamf Pro credentials for a future adapter. This build does not collect device inventory or execute endpoint preservation.
              </p>
              <div className="form-grid">
                <label>Jamf Pro base URL<input className="input" value={integrationSettings.configs?.jamf?.base_url || ''} onChange={e => updateIntegrationConfig('jamf', 'base_url', e.target.value)} placeholder="https://yourorg.jamfcloud.com" /></label>
                <label>Auth type<select className="input" value={integrationSettings.configs?.jamf?.auth_type || 'oauth'} onChange={e => updateIntegrationConfig('jamf', 'auth_type', e.target.value)}><option value="oauth">OAuth client credentials</option><option value="basic">Username and password</option></select></label>
                {(integrationSettings.configs?.jamf?.auth_type || 'oauth') === 'basic' ? (
                  <>
                    <label>Username<input className="input" value={integrationSettings.configs?.jamf?.username || ''} onChange={e => updateIntegrationConfig('jamf', 'username', e.target.value)} /></label>
                    <label>Password<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.jamf?.password)} onChange={e => updateIntegrationConfig('jamf', 'password', e.target.value)} placeholder={integrationSettings.configs?.jamf?.password === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                  </>
                ) : (
                  <>
                    <label>Client ID<input className="input" value={integrationSettings.configs?.jamf?.client_id || ''} onChange={e => updateIntegrationConfig('jamf', 'client_id', e.target.value)} /></label>
                    <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.jamf?.client_secret)} onChange={e => updateIntegrationConfig('jamf', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.jamf?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                  </>
                )}
              </div>
            </div>
          )}

          {integrationSettings.enabled?.defender && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Microsoft Defender</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores Microsoft Defender credentials for a future adapter. This build does not collect endpoint evidence.
              </p>
              <div className="form-grid">
                <label>Tenant ID<input className="input" value={integrationSettings.configs?.defender?.tenant_id || ''} onChange={e => updateIntegrationConfig('defender', 'tenant_id', e.target.value)} /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.defender?.client_id || ''} onChange={e => updateIntegrationConfig('defender', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.defender?.client_secret)} onChange={e => updateIntegrationConfig('defender', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.defender?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Defender API base<input className="input" value={integrationSettings.configs?.defender?.api_base || ''} onChange={e => updateIntegrationConfig('defender', 'api_base', e.target.value)} placeholder="https://api.securitycenter.microsoft.com" /></label>
                <label>Scopes<input className="input" value={integrationSettings.configs?.defender?.scopes || ''} onChange={e => updateIntegrationConfig('defender', 'scopes', e.target.value)} /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.crowdstrike && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>CrowdStrike</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configuration only: stores CrowdStrike Falcon credentials for a future adapter. This build does not collect endpoint evidence.
              </p>
              <div className="form-grid">
                <label>Falcon API base<input className="input" value={integrationSettings.configs?.crowdstrike?.base_url || ''} onChange={e => updateIntegrationConfig('crowdstrike', 'base_url', e.target.value)} placeholder="https://api.crowdstrike.com" /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.crowdstrike?.client_id || ''} onChange={e => updateIntegrationConfig('crowdstrike', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.crowdstrike?.client_secret)} onChange={e => updateIntegrationConfig('crowdstrike', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.crowdstrike?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
              </div>
            </div>
          )}


          {integrationSettings.enabled?.log_shipping && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Off-box Log Shipping</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Upload compressed DiscoveryOne log archives to a SharePoint document library using an Entra ID application.
              </p>
              <div className='form-grid'>
                <label>Tenant ID<input className='input' value={integrationSettings.configs?.log_shipping?.tenant_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'tenant_id', e.target.value)} /></label>
                <label>Client ID<input className='input' value={integrationSettings.configs?.log_shipping?.client_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className='input' type='password' value={secretInputValue(integrationSettings.configs?.log_shipping?.client_secret)} onChange={e => updateIntegrationConfig('log_shipping', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.log_shipping?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>SharePoint site ID<input className='input' value={integrationSettings.configs?.log_shipping?.sharepoint_site_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_site_id', e.target.value)} placeholder='contoso.sharepoint.com,site-collection-id,site-id' /></label>
                <label>Drive ID<input className='input' value={integrationSettings.configs?.log_shipping?.sharepoint_drive_id || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_drive_id', e.target.value)} placeholder='Use either drive ID or drive name' /></label>
                <label>Drive name<input className='input' value={integrationSettings.configs?.log_shipping?.sharepoint_drive_name || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_drive_name', e.target.value)} placeholder='Documents' /></label>
                <label>Destination folder<input className='input' value={integrationSettings.configs?.log_shipping?.sharepoint_folder || ''} onChange={e => updateIntegrationConfig('log_shipping', 'sharepoint_folder', e.target.value)} placeholder='DiscoveryOneLogs' /></label>
                <label>Interval hours<input className='input' type='number' min='1' max='720' step='0.5' value={integrationSettings.configs?.log_shipping?.interval_hours ?? 24} onChange={e => updateIntegrationConfig('log_shipping', 'interval_hours', e.target.value)} /></label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type='checkbox' checked={integrationSettings.configs?.log_shipping?.run_on_startup !== false} onChange={e => updateIntegrationConfig('log_shipping', 'run_on_startup', e.target.checked)} />Run once when enabled</label>
                <label>Graph base<input className='input' value={integrationSettings.configs?.log_shipping?.graph_base || ''} onChange={e => updateIntegrationConfig('log_shipping', 'graph_base', e.target.value)} placeholder='https://graph.microsoft.com/v1.0' /></label>
                <label>OAuth scope<input className='input' value={integrationSettings.configs?.log_shipping?.scope || ''} onChange={e => updateIntegrationConfig('log_shipping', 'scope', e.target.value)} placeholder='https://graph.microsoft.com/.default' /></label>
                <label>Maximum file MB<input className='input' type='number' min='1' max='250' value={integrationSettings.configs?.log_shipping?.max_file_mb ?? 250} onChange={e => updateIntegrationConfig('log_shipping', 'max_file_mb', e.target.value)} /></label>
                <label>Maximum archive MB<input className='input' type='number' min='1' max='250' value={integrationSettings.configs?.log_shipping?.max_archive_mb ?? 250} onChange={e => updateIntegrationConfig('log_shipping', 'max_archive_mb', e.target.value)} /></label>
                <label>Maximum files<input className='input' type='number' min='1' max='5000' value={integrationSettings.configs?.log_shipping?.max_files ?? 5000} onChange={e => updateIntegrationConfig('log_shipping', 'max_files', e.target.value)} /></label>
                <label>Request timeout seconds<input className='input' type='number' min='5' max='300' value={integrationSettings.configs?.log_shipping?.timeout_seconds ?? 120} onChange={e => updateIntegrationConfig('log_shipping', 'timeout_seconds', e.target.value)} /></label>
                <label>Retry count<input className='input' type='number' min='0' max='10' value={integrationSettings.configs?.log_shipping?.retry_count ?? 3} onChange={e => updateIntegrationConfig('log_shipping', 'retry_count', e.target.value)} /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.ai && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>AI assistant</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Configure an OpenAI-compatible chat completions endpoint for available DiscoveryOne AI features. Secrets are encrypted before storage.
              </p>
              <div className="form-grid">
                <label>Endpoint URL<input className="input" value={integrationSettings.configs?.ai?.url || ''} onChange={e => updateIntegrationConfig('ai', 'url', e.target.value)} placeholder="https://api.openai.com/v1/chat/completions" /></label>
                <label>Model<input className="input" value={integrationSettings.configs?.ai?.model || ''} onChange={e => updateIntegrationConfig('ai', 'model', e.target.value)} /></label>
                <label>API key<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.ai?.api_key)} onChange={e => updateIntegrationConfig('ai', 'api_key', e.target.value)} placeholder={integrationSettings.configs?.ai?.api_key === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Auth header<input className="input" value={integrationSettings.configs?.ai?.auth_header || 'Authorization'} onChange={e => updateIntegrationConfig('ai', 'auth_header', e.target.value)} /></label>
                <label>Timeout seconds<input className="input" type="number" min="1" value={integrationSettings.configs?.ai?.timeout_seconds ?? 25} onChange={e => updateIntegrationConfig('ai', 'timeout_seconds', e.target.value)} /></label>
                <label>Temperature<input className="input" type="number" min="0" max="1" step="0.1" value={integrationSettings.configs?.ai?.temperature ?? 0.1} onChange={e => updateIntegrationConfig('ai', 'temperature', e.target.value)} /></label>
                <label>System prompt<textarea className="input" rows={3} value={integrationSettings.configs?.ai?.system_prompt || ''} onChange={e => updateIntegrationConfig('ai', 'system_prompt', e.target.value)} placeholder="Shared AI system prompt override" /></label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={integrationSettings.configs?.ai?.assistant_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'assistant_enabled', e.target.checked)} />Enable AI assistant</label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={integrationSettings.configs?.ai?.case_summary_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'case_summary_enabled', e.target.checked)} />Enable case summary AI</label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={integrationSettings.configs?.ai?.search_builder_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'search_builder_enabled', e.target.checked)} />Enable search builder AI</label>
                <label>Search builder max suggestions<input className="input" type="number" min="1" max="8" value={integrationSettings.configs?.ai?.search_builder_max_suggestions ?? 4} onChange={e => updateIntegrationConfig('ai', 'search_builder_max_suggestions', e.target.value)} /></label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={integrationSettings.configs?.ai?.name_email_review_enabled !== false} onChange={e => updateIntegrationConfig('ai', 'name_email_review_enabled', e.target.checked)} />Enable name/email review rules</label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={!!integrationSettings.configs?.ai?.name_email_ai_enabled} onChange={e => updateIntegrationConfig('ai', 'name_email_ai_enabled', e.target.checked)} />Use AI for name/email review</label>
              </div>
            </div>
          )}
    </>
  )
}