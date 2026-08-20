import {
  MASKED_SECRET_VALUE,
  secretInputValue,
} from './systemUtils.js'
import PersonLookupFieldMappings from './PersonLookupFieldMappings.jsx'

export default function SystemCoreIntegrationConfigSections({ integrationSettings, updateIntegrationConfig }) {
  return (
    <>
          {integrationSettings.providers?.sso_provider === 'oidc' && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>OIDC single sign-on</h3>
              <div className="form-grid">
                <label>Issuer URL<input className="input" value={integrationSettings.configs?.oidc?.issuer || ''} onChange={e => updateIntegrationConfig('oidc', 'issuer', e.target.value)} placeholder="https://idp.example.edu/oauth2/default" /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.oidc?.client_id || ''} onChange={e => updateIntegrationConfig('oidc', 'client_id', e.target.value)} /></label>
                <label>Client Secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.oidc?.client_secret)} onChange={e => updateIntegrationConfig('oidc', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.oidc?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Scopes<input className="input" value={integrationSettings.configs?.oidc?.scopes || ''} onChange={e => updateIntegrationConfig('oidc', 'scopes', e.target.value)} placeholder="openid profile email" /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.person_lookup && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Person lookup</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Use CSV for a mounted directory export or an IDP/HR API for live lookup. Responses should include fields DiscoveryOne can normalize such as display name, email, employee ID, department, title, separation date, and separation status.
              </p>
              {integrationSettings.providers?.person_lookup_provider === 'csv' && (
                <label>CSV file path<input className="input" value={integrationSettings.configs?.person_lookup?.csv_path || ''} onChange={e => updateIntegrationConfig('person_lookup', 'csv_path', e.target.value)} placeholder="/data/system/person_lookup/people.csv" /></label>
              )}
              {['http', 'api', 'idp', 'hr'].includes(integrationSettings.providers?.person_lookup_provider) && (
                <div className="form-grid">
                  <label>Lookup API URL<input className="input" value={integrationSettings.configs?.person_lookup?.http_url || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_url', e.target.value)} placeholder="https://idp.example.edu/people/search" /></label>
                  <label>HTTP method<input className="input" value={integrationSettings.configs?.person_lookup?.http_method || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_method', e.target.value)} placeholder="GET" /></label>
                  <label>Query parameter<input className="input" value={integrationSettings.configs?.person_lookup?.http_query_param || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_query_param', e.target.value)} placeholder="q" /></label>
                  <label>Email parameter<input className="input" value={integrationSettings.configs?.person_lookup?.http_email_param || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_email_param', e.target.value)} placeholder="email" /></label>
                  <label>Results path<input className="input" value={integrationSettings.configs?.person_lookup?.http_results_path || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_results_path', e.target.value)} placeholder="results" /></label>
                  <label>Timeout seconds<input className="input" type="number" min="1" max="120" value={integrationSettings.configs?.person_lookup?.http_timeout_seconds ?? 10} onChange={e => updateIntegrationConfig('person_lookup', 'http_timeout_seconds', e.target.value)} /></label>
                  <label>Auth header<input className="input" value={integrationSettings.configs?.person_lookup?.http_auth_header || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_auth_header', e.target.value)} placeholder="Authorization" /></label>
                  <label>Auth value<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.person_lookup?.http_auth_value)} onChange={e => updateIntegrationConfig('person_lookup', 'http_auth_value', e.target.value)} placeholder={integrationSettings.configs?.person_lookup?.http_auth_value === MASKED_SECRET_VALUE ? 'Configured' : 'Bearer ...'} /></label>
                </div>
              )}
              {integrationSettings.providers?.person_lookup_provider !== 'none' && (
                <PersonLookupFieldMappings
                  config={integrationSettings.configs?.person_lookup}
                  onChange={(field, value) => updateIntegrationConfig('person_lookup', field, value)}
                />
              )}

            </div>
          )}

          {integrationSettings.enabled?.ntp_ack_bridge && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>DMZ NTP Acknowledgment Server</h3>
              <p style={{ color: '#b45309', fontWeight: 700, marginBottom: 6 }}>
                Do not set this up until you have run the DMZ helper script to build the DMZ Server.
              </p>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                After the helper completes, enter the values it prints below. DiscoveryOne uses the external URL in NTP messages and the shared secret to authenticate acknowledgements sent back from the DMZ server.
              </p>
              <div className="form-grid">
                <label>
                  External acknowledgement bridge URL
                  <input
                    className="input"
                    value={integrationSettings.configs?.ntp_ack_bridge?.bridge_url || ''}
                    onChange={e => updateIntegrationConfig('ntp_ack_bridge', 'bridge_url', e.target.value)}
                    placeholder="https://dmz.example.edu/ack?token={token}"
                  />
                  <small style={{ color: 'var(--muted,#6b7280)' }}>Paste the Public acknowledgement URL printed by the helper. The URL must use HTTPS and include {'{token}'}.</small>
                </label>
                <label>
                  Acknowledgement display URL
                  <input
                    className="input"
                    value={integrationSettings.configs?.ntp_ack_bridge?.display_url || ''}
                    onChange={e => updateIntegrationConfig('ntp_ack_bridge', 'display_url', e.target.value)}
                    placeholder="https://dmz.example.edu/"
                  />
                  <small style={{ color: 'var(--muted,#6b7280)' }}>Paste the Acknowledgement display URL printed by the helper. This is the friendly address shown as link text in NTP messages.</small>
                </label>
                <label>
                  Bridge shared secret
                  <input
                    className="input"
                    type="password"
                    value={secretInputValue(integrationSettings.configs?.ntp_ack_bridge?.shared_secret)}
                    onChange={e => updateIntegrationConfig('ntp_ack_bridge', 'shared_secret', e.target.value)}
                    placeholder={integrationSettings.configs?.ntp_ack_bridge?.shared_secret === MASKED_SECRET_VALUE ? 'Configured' : ''}
                  />
                  <small style={{ color: 'var(--muted,#6b7280)' }}>On the DMZ server, run the command printed by the helper to display the shared secret, then enter it here. DiscoveryOne encrypts it before storage.</small>
                </label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.servicenow && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>ServiceNow</h3>
              <div className="form-grid">
                <label>Base URL<input className="input" value={integrationSettings.configs?.servicenow?.base_url || ''} onChange={e => updateIntegrationConfig('servicenow', 'base_url', e.target.value)} placeholder="https://instance.service-now.com" /></label>
                <label>Auth type
                  <select className="input" value={integrationSettings.configs?.servicenow?.auth_type || 'basic'} onChange={e => updateIntegrationConfig('servicenow', 'auth_type', e.target.value)}>
                    <option value="basic">Username and password</option>
                    <option value="oauth">OAuth client credentials</option>
                  </select>
                </label>
                {(integrationSettings.configs?.servicenow?.auth_type || 'basic') === 'oauth' ? (
                  <>
                    <label>OAuth client ID<input className="input" value={integrationSettings.configs?.servicenow?.oauth_client_id || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_client_id', e.target.value)} /></label>
                    <label>OAuth client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.servicenow?.oauth_client_secret)} onChange={e => updateIntegrationConfig('servicenow', 'oauth_client_secret', e.target.value)} placeholder={integrationSettings.configs?.servicenow?.oauth_client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                    <label>OAuth token URL<input className="input" value={integrationSettings.configs?.servicenow?.oauth_token_url || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_token_url', e.target.value)} placeholder="https://instance.service-now.com/oauth_token.do" /></label>
                    <label>OAuth scope<input className="input" value={integrationSettings.configs?.servicenow?.oauth_scope || ''} onChange={e => updateIntegrationConfig('servicenow', 'oauth_scope', e.target.value)} placeholder="OAuth scope" /></label>
                  </>
                ) : (
                  <>
                    <label>Username<input className="input" value={integrationSettings.configs?.servicenow?.username || ''} onChange={e => updateIntegrationConfig('servicenow', 'username', e.target.value)} /></label>
                    <label>Password<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.servicenow?.password)} onChange={e => updateIntegrationConfig('servicenow', 'password', e.target.value)} placeholder={integrationSettings.configs?.servicenow?.password === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                  </>
                )}
                <label>Create table<input className="input" value={integrationSettings.configs?.servicenow?.table || ''} onChange={e => updateIntegrationConfig('servicenow', 'table', e.target.value)} placeholder="incident" /></label>
                <label>Status table<input className="input" value={integrationSettings.configs?.servicenow?.status_table || ''} onChange={e => updateIntegrationConfig('servicenow', 'status_table', e.target.value)} placeholder="incident" /></label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                  <input type="checkbox" checked={!!integrationSettings.configs?.servicenow?.use_import_api} onChange={e => updateIntegrationConfig('servicenow', 'use_import_api', e.target.checked)} />
                  Use ServiceNow Import Set API
                </label>
                <label>Source system<input className="input" value={integrationSettings.configs?.servicenow?.source_system || ''} onChange={e => updateIntegrationConfig('servicenow', 'source_system', e.target.value)} placeholder="discoveryone" /></label>
                <label>Default customer ID<input className="input" value={integrationSettings.configs?.servicenow?.default_customer_id || ''} onChange={e => updateIntegrationConfig('servicenow', 'default_customer_id', e.target.value)} placeholder="Fallback customer ID" /></label>
                <label>App customer ID<input className="input" value={integrationSettings.configs?.servicenow?.customer_id || ''} onChange={e => updateIntegrationConfig('servicenow', 'customer_id', e.target.value)} placeholder="discoveryone" /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.box && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Box</h3>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                Create a Box custom app using Server Authentication with JWT, authorize it in the Box Admin Console, and grant enterprise legal hold access.
              </p>
              <div className="form-grid">
                <label>Enterprise ID<input className="input" value={integrationSettings.configs?.box?.enterprise_id || ''} onChange={e => updateIntegrationConfig('box', 'enterprise_id', e.target.value)} /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.box?.client_id || ''} onChange={e => updateIntegrationConfig('box', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.box?.client_secret)} onChange={e => updateIntegrationConfig('box', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.box?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>JWT public key ID<input className="input" value={integrationSettings.configs?.box?.jwt_key_id || ''} onChange={e => updateIntegrationConfig('box', 'jwt_key_id', e.target.value)} /></label>
                <label>JWT private key<textarea className="input" rows={4} value={secretInputValue(integrationSettings.configs?.box?.jwt_private_key)} onChange={e => updateIntegrationConfig('box', 'jwt_private_key', e.target.value)} placeholder={integrationSettings.configs?.box?.jwt_private_key === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>JWT passphrase<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.box?.jwt_passphrase)} onChange={e => updateIntegrationConfig('box', 'jwt_passphrase', e.target.value)} placeholder={integrationSettings.configs?.box?.jwt_passphrase === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.docusign && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>DocuSign</h3>
              <div className="form-grid">
                <label>Base URL<input className="input" value={integrationSettings.configs?.docusign?.base_url || ''} onChange={e => updateIntegrationConfig('docusign', 'base_url', e.target.value)} /></label>
                <label>Account ID<input className="input" value={integrationSettings.configs?.docusign?.account_id || ''} onChange={e => updateIntegrationConfig('docusign', 'account_id', e.target.value)} /></label>
                <label>Template ID<input className="input" value={integrationSettings.configs?.docusign?.template_id || ''} onChange={e => updateIntegrationConfig('docusign', 'template_id', e.target.value)} /></label>
                <label>Signer role<input className="input" value={integrationSettings.configs?.docusign?.signer_role || ''} onChange={e => updateIntegrationConfig('docusign', 'signer_role', e.target.value)} placeholder="signer" /></label>
                <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#6b7280)', lineHeight: 1.45 }}>Match these values to the text tab labels in your DocuSign template. DiscoveryOne fills these tabs when it sends a consent request.</div>
                <label>Matter name tab label<input className="input" value={integrationSettings.configs?.docusign?.case_name_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'case_name_tab', e.target.value)} placeholder="case_name" /></label>
                <label>Record type tab label<input className="input" value={integrationSettings.configs?.docusign?.record_type_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'record_type_tab', e.target.value)} placeholder="recordtype" /></label>
                <label>Date from tab label<input className="input" value={integrationSettings.configs?.docusign?.date_from_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'date_from_tab', e.target.value)} placeholder="datefrom" /></label>
                <label>Date to tab label<input className="input" value={integrationSettings.configs?.docusign?.date_to_tab || ''} onChange={e => updateIntegrationConfig('docusign', 'date_to_tab', e.target.value)} placeholder="dateto" /></label>
                <label>Integration key<input className="input" value={integrationSettings.configs?.docusign?.integration_key || ''} onChange={e => updateIntegrationConfig('docusign', 'integration_key', e.target.value)} /></label>
                <label>User ID<input className="input" value={integrationSettings.configs?.docusign?.user_id || ''} onChange={e => updateIntegrationConfig('docusign', 'user_id', e.target.value)} /></label>
                <label>Auth server<input className="input" value={integrationSettings.configs?.docusign?.auth_server || ''} onChange={e => updateIntegrationConfig('docusign', 'auth_server', e.target.value)} placeholder="account-d.docusign.com" /></label>
                <label>Private key<textarea className="input" rows={4} value={secretInputValue(integrationSettings.configs?.docusign?.private_key)} onChange={e => updateIntegrationConfig('docusign', 'private_key', e.target.value)} placeholder={integrationSettings.configs?.docusign?.private_key === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Connect HMAC key<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.docusign?.connect_key)} onChange={e => updateIntegrationConfig('docusign', 'connect_key', e.target.value)} placeholder={integrationSettings.configs?.docusign?.connect_key === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Additional Connect HMAC keys<textarea className="input" rows={2} value={secretInputValue(integrationSettings.configs?.docusign?.connect_keys)} onChange={e => updateIntegrationConfig('docusign', 'connect_keys', e.target.value)} placeholder={integrationSettings.configs?.docusign?.connect_keys === MASKED_SECRET_VALUE ? 'Configured' : 'Comma-separated rotated keys'} /></label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={!!integrationSettings.configs?.docusign?.resend_allow_recipient_correction_fallback} onChange={e => updateIntegrationConfig('docusign', 'resend_allow_recipient_correction_fallback', e.target.checked)} />Allow recipient correction fallback on resend</label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.purview && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Microsoft Purview</h3>
              <div className="form-grid">
                <label>Tenant ID<input className="input" value={integrationSettings.configs?.purview?.tenant_id || ''} onChange={e => updateIntegrationConfig('purview', 'tenant_id', e.target.value)} /></label>
                <label>Client ID<input className="input" value={integrationSettings.configs?.purview?.client_id || ''} onChange={e => updateIntegrationConfig('purview', 'client_id', e.target.value)} /></label>
                <label>Client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.purview?.client_secret)} onChange={e => updateIntegrationConfig('purview', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.purview?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>Graph beta base<input className="input" value={integrationSettings.configs?.purview?.graph_base || ''} onChange={e => updateIntegrationConfig('purview', 'graph_base', e.target.value)} placeholder="https://graph.microsoft.com/beta" /></label>
                <label>Graph v1 base<input className="input" value={integrationSettings.configs?.purview?.graph_base_v1 || ''} onChange={e => updateIntegrationConfig('purview', 'graph_base_v1', e.target.value)} placeholder="https://graph.microsoft.com/v1.0" /></label>
                <label>Security base<input className="input" value={integrationSettings.configs?.purview?.security_base || ''} onChange={e => updateIntegrationConfig('purview', 'security_base', e.target.value)} /></label>
                <label>HTTP timeout seconds<input className="input" type="number" min="5" max="300" value={integrationSettings.configs?.purview?.http_timeout_seconds ?? 60} onChange={e => updateIntegrationConfig('purview', 'http_timeout_seconds', e.target.value)} /></label>
                <label>HTTP retry count<input className="input" type="number" min="0" max="10" value={integrationSettings.configs?.purview?.http_retry_count ?? 3} onChange={e => updateIntegrationConfig('purview', 'http_retry_count', e.target.value)} /></label>
                <label>OneDrive lookup limit<input className="input" type="number" min="0" value={integrationSettings.configs?.purview?.status_onedrive_lookup_limit ?? 25} onChange={e => updateIntegrationConfig('purview', 'status_onedrive_lookup_limit', e.target.value)} /></label>
                <label>Status poll delay seconds<input className="input" type="number" min="0" value={integrationSettings.configs?.purview?.status_poll_delay_seconds ?? 120} onChange={e => updateIntegrationConfig('purview', 'status_poll_delay_seconds', e.target.value)} /></label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                  <input type="checkbox" checked={!!integrationSettings.configs?.purview?.add_data_sources} onChange={e => updateIntegrationConfig('purview', 'add_data_sources', e.target.checked)} />
                  Add Purview data sources when creating a matter
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                  <input type="checkbox" checked={!!integrationSettings.configs?.purview?.hold_missing_email_mark_failed} onChange={e => updateIntegrationConfig('purview', 'hold_missing_email_mark_failed', e.target.checked)} />
                  Mark missing-email hold attempts as failed
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                  <input type="checkbox" checked={integrationSettings.configs?.purview?.export_poll_enabled !== false} onChange={e => updateIntegrationConfig('purview', 'export_poll_enabled', e.target.checked)} />
                  Poll Purview exports on a schedule
                </label>
                <label>Export poll hours<input className="input" value={integrationSettings.configs?.purview?.export_poll_hours || '7,18'} onChange={e => updateIntegrationConfig('purview', 'export_poll_hours', e.target.value)} placeholder="7,18" /></label>
                <label>Export poll minute<input className="input" type="number" min="0" max="59" value={integrationSettings.configs?.purview?.export_poll_minute ?? 0} onChange={e => updateIntegrationConfig('purview', 'export_poll_minute', e.target.value)} /></label>
                <label>Export poll timezone<input className="input" value={integrationSettings.configs?.purview?.export_poll_timezone || ''} onChange={e => updateIntegrationConfig('purview', 'export_poll_timezone', e.target.value)} placeholder="America/Los_Angeles" /></label>
                <label>Export poll requestor groups<input className="input" value={integrationSettings.configs?.purview?.export_poll_requestor_groups || 'pra'} onChange={e => updateIntegrationConfig('purview', 'export_poll_requestor_groups', e.target.value)} placeholder="pra" /></label>
              </div>
            </div>
          )}

          {integrationSettings.enabled?.slack && (
            <div style={{ marginTop: 18 }}>
              <h3 style={{ margin: '0 0 8px' }}>Slack</h3>
              <div className="form-grid">
                <label>Legal Holds token<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.slack?.legal_holds_token)} onChange={e => updateIntegrationConfig('slack', 'legal_holds_token', e.target.value)} placeholder={integrationSettings.configs?.slack?.legal_holds_token === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>API base<input className="input" value={integrationSettings.configs?.slack?.api_base || ''} onChange={e => updateIntegrationConfig('slack', 'api_base', e.target.value)} placeholder="https://slack.com/api" /></label>
                <label>OAuth client ID<input className="input" value={integrationSettings.configs?.slack?.client_id || ''} onChange={e => updateIntegrationConfig('slack', 'client_id', e.target.value)} /></label>
                <label>OAuth client secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.slack?.client_secret)} onChange={e => updateIntegrationConfig('slack', 'client_secret', e.target.value)} placeholder={integrationSettings.configs?.slack?.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''} /></label>
                <label>OAuth redirect URI<input className="input" value={integrationSettings.configs?.slack?.oauth_redirect_uri || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_redirect_uri', e.target.value)} /></label>
                <label>OAuth bot scopes<input className="input" value={integrationSettings.configs?.slack?.oauth_scope || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_scope', e.target.value)} /></label>
                <label>OAuth user scopes<input className="input" value={integrationSettings.configs?.slack?.oauth_user_scope || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_user_scope', e.target.value)} /></label>
                <label>OAuth state lifetime seconds<input className="input" type="number" min="60" max="3600" value={integrationSettings.configs?.slack?.oauth_state_ttl_seconds ?? 900} onChange={e => updateIntegrationConfig('slack', 'oauth_state_ttl_seconds', e.target.value)} /></label>
                <label>OAuth authorize URL<input className="input" value={integrationSettings.configs?.slack?.oauth_authorize_url || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_authorize_url', e.target.value)} placeholder="https://slack.com/oauth/v2/authorize" /></label>
                <label>OAuth token URL<input className="input" value={integrationSettings.configs?.slack?.oauth_access_url || ''} onChange={e => updateIntegrationConfig('slack', 'oauth_access_url', e.target.value)} placeholder="https://slack.com/api/oauth.v2.access" /></label>
                <label>Proxy shared secret<input className="input" type="password" value={secretInputValue(integrationSettings.configs?.slack?.shared_secret)} onChange={e => updateIntegrationConfig('slack', 'shared_secret', e.target.value)} placeholder={integrationSettings.configs?.slack?.shared_secret === MASKED_SECRET_VALUE ? 'Configured' : 'Proxy shared secret'} /></label>
              </div>
            </div>
          )}
    </>
  )
}