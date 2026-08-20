import { MASKED_SECRET_VALUE, secretInputValue } from './systemUtils.js'

const fieldHelp = {
  tenant_id: 'Directory (tenant) ID for the Entra application.',
  client_id: 'Application (client) ID for the Entra application.',
  mailbox: 'Exchange Online mailbox that receives matter-request email.',
  folder_id: 'Well-known folder name such as inbox, or a Graph mail-folder ID.',
}

export default function SystemEmailIntakeConfig({ integrationSettings, updateIntegrationConfig }) {
  const config = integrationSettings.configs?.email_intake || {}
  const update = (key, value) => updateIntegrationConfig('email_intake', key, value)

  return (
    <section style={{ marginTop: 22, paddingTop: 20, borderTop: '1px solid var(--border,#d1d5db)' }}>
      <h3 style={{ margin: '0 0 6px' }}>Email Intake</h3>
      <p style={{ color: 'var(--muted,#6b7280)', margin: '0 0 12px' }}>
        This integration polls one Exchange Online folder through Microsoft Graph and creates pending Matter Requests for analyst approval. Register an Entra application with Microsoft Graph <strong>Mail.Read</strong> application permission, grant admin consent, and restrict the application to this mailbox with Exchange application RBAC or an application access policy where available.
      </p>
      <div className="form-grid">
        <label>
          Tenant ID
          <input className="input" value={config.tenant_id || ''} onChange={e => update('tenant_id', e.target.value)} />
          <span className="form-help">{fieldHelp.tenant_id}</span>
        </label>
        <label>
          Client ID
          <input className="input" value={config.client_id || ''} onChange={e => update('client_id', e.target.value)} />
          <span className="form-help">{fieldHelp.client_id}</span>
        </label>
        <label>
          Client secret
          <input
            className="input"
            type="password"
            value={secretInputValue(config.client_secret)}
            onChange={e => update('client_secret', e.target.value)}
            placeholder={config.client_secret === MASKED_SECRET_VALUE ? 'Configured' : ''}
          />
          <span className="form-help">Secret value created under Certificates &amp; secrets; it is encrypted before storage.</span>
        </label>
        <label>
          Monitored mailbox
          <input className="input" type="email" value={config.mailbox || ''} onChange={e => update('mailbox', e.target.value)} placeholder="ediscovery-intake@example.edu" />
          <span className="form-help">{fieldHelp.mailbox}</span>
        </label>
        <label>
          Mail folder
          <input className="input" value={config.folder_id || 'inbox'} onChange={e => update('folder_id', e.target.value)} placeholder="inbox" />
          <span className="form-help">{fieldHelp.folder_id}</span>
        </label>
        <label>
          Poll interval (seconds)
          <input className="input" type="number" min="15" max="86400" value={config.poll_interval_seconds ?? 60} onChange={e => update('poll_interval_seconds', Number(e.target.value))} />
          <span className="form-help">How often the scheduler checks the Graph delta feed.</span>
        </label>
        <label>
          Messages per poll
          <input className="input" type="number" min="1" max="500" value={config.max_messages_per_poll ?? 50} onChange={e => update('max_messages_per_poll', Number(e.target.value))} />
          <span className="form-help">Maximum messages processed in one scheduler pass.</span>
        </label>
        <label>
          Sender policy
          <select className="input" value={config.sender_policy || 'any'} onChange={e => update('sender_policy', e.target.value)}>
            <option value="any">Any valid sender</option>
            <option value="organization">Organization domains only</option>
            <option value="allowlist">Configured allowlist only</option>
          </select>
          <span className="form-help">Controls which senders may create a pending request.</span>
        </label>
        {(config.sender_policy || 'any') === 'allowlist' && (
          <>
            <label>
              Allowed senders
              <textarea className="input" rows={3} value={config.allowed_senders || ''} onChange={e => update('allowed_senders', e.target.value)} placeholder="person@example.com" />
              <span className="form-help">One exact email address per line, or separate values with commas.</span>
            </label>
            <label>
              Allowed sender domains
              <textarea className="input" rows={3} value={config.allowed_sender_domains || ''} onChange={e => update('allowed_sender_domains', e.target.value)} placeholder="outside-counsel.com" />
              <span className="form-help">One domain per line without the @ symbol.</span>
            </label>
          </>
        )}
        <label>
          Graph base URL
          <input className="input" value={config.graph_base || 'https://graph.microsoft.com/v1.0'} onChange={e => update('graph_base', e.target.value)} />
          <span className="form-help">Microsoft Graph API root; keep the v1.0 endpoint unless Microsoft directs otherwise.</span>
        </label>
        <label>
          OAuth scope
          <input className="input" value={config.scope || 'https://graph.microsoft.com/.default'} onChange={e => update('scope', e.target.value)} />
          <span className="form-help">Client-credentials scope used to request the application token.</span>
        </label>
        <label>
          Request timeout (seconds)
          <input className="input" type="number" min="5" max="300" value={config.timeout_seconds ?? 30} onChange={e => update('timeout_seconds', Number(e.target.value))} />
          <span className="form-help">Maximum duration of one Microsoft request.</span>
        </label>
        <label>
          Graph retry count
          <input className="input" type="number" min="0" max="10" value={config.retry_count ?? 3} onChange={e => update('retry_count', Number(e.target.value))} />
          <span className="form-help">Retries throttling and temporary Microsoft service failures.</span>
        </label>
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, fontWeight: 600 }}>
        <input type="checkbox" checked={config.requestor_from_sender !== false} onChange={e => update('requestor_from_sender', e.target.checked)} />
        Use the message sender as the matter requestor
      </label>      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontWeight: 600 }}>
        <input type="checkbox" checked={!!config.process_existing_on_first_run} onChange={e => update('process_existing_on_first_run', e.target.checked)} />
        Process messages already in the folder on the first poll
      </label>
      <p className="form-help" style={{ marginTop: 4 }}>
        Leave this off for normal deployment. DiscoveryOne will establish a delta baseline and process only messages that arrive afterward.
      </p>
      <p className="form-help" style={{ marginTop: 4 }}>
        External senders are accepted only through this admin-controlled mailbox path and remain subject to the sender policy above.
      </p>
    </section>
  )
}