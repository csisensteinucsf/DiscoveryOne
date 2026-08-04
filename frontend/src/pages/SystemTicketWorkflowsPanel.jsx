import { normalizeTicketProvider, normalizeTicketWorkflowMetadataSchema, ticketProviderLabel } from './ticketWorkflowCatalog.js'

const fieldHelpStyle = { display: 'block', marginTop: 4, color: 'var(--muted,#6b7280)', fontSize: 13, lineHeight: 1.35, fontWeight: 400 }

const statusColor = (message) => String(message || '').toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)'

function WorkflowField({ label, help, children }) {
  return (
    <label style={{ display: 'block', fontWeight: 700 }}>
      {label}
      {children}
      {help && <span style={fieldHelpStyle}>{help}</span>}
    </label>
  )
}

export default function SystemTicketWorkflowsPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  ticketWorkflows,
  updateTicketWorkflow,
  addTicketWorkflow,
  removeTicketWorkflow,
  saveTicketWorkflows,
  ticketWorkflowSaving,
  ticketWorkflowStatus,
  preservationSourcePayload,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can configure ticket workflows.')
  }

  const sourceOptions = (preservationSourcePayload || [])
    .filter(item => item?.key)
    .map(item => ({ key: item.key, label: item.label || item.key }))

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>Ticket Workflow Catalog</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0, lineHeight: 1.5 }}>
        Configure the ticket and handoff workflows DiscoveryOne exposes for preservation work. Manual workflows only track status inside DiscoveryOne; external provider workflows can create or reconcile tickets when that integration is enabled and configured.
      </p>

      <datalist id="ticket-workflow-preservation-sources">
        {sourceOptions.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
      </datalist>

      <div style={{ display: 'grid', gap: 14 }}>
        {(ticketWorkflows || []).map((workflow, index) => {
          const provider = normalizeTicketProvider(workflow.provider)
          const providerName = ticketProviderLabel(provider)
          const providerActionName = ticketProviderLabel(provider, { action: true })
          return (
            <div
              key={`${workflow.key || 'new'}-${index}`}
              style={{
                border: '1px solid var(--border,#d1d5db)',
                borderRadius: 8,
                padding: 14,
                background: workflow.enabled === false ? 'rgba(148,163,184,0.08)' : 'var(--panel,#fff)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700 }}>
                  <input
                    type="checkbox"
                    checked={workflow.enabled !== false}
                    onChange={e => updateTicketWorkflow(index, 'enabled', e.target.checked)}
                  />
                  {workflow.label || 'New workflow'}
                </label>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  {workflow.built_in && <span style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>Built in</span>}
                  <span style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>{providerActionName}</span>
                  {!workflow.built_in && (
                    <button type="button" className="btn subtle" onClick={() => removeTicketWorkflow(index)}>
                      Remove
                    </button>
                  )}
                </div>
              </div>

              <div className="form-grid">
                <WorkflowField label="Workflow label" help="This is the user-facing ticket category shown in case request and case detail workflows.">
                  <input
                    className="input"
                    value={workflow.label || ''}
                    onChange={e => updateTicketWorkflow(index, 'label', e.target.value)}
                    placeholder="Endpoint imaging request"
                  />
                </WorkflowField>
                <WorkflowField label="Workflow key" help="This stable key is used internally for permissions, audit details, and saved ticket entries. Built-in keys cannot be renamed safely.">
                  <input
                    className="input"
                    value={workflow.key || ''}
                    onChange={e => updateTicketWorkflow(index, 'key', e.target.value)}
                    readOnly={!!workflow.built_in}
                    placeholder="endpoint_imaging"
                  />
                </WorkflowField>
                <WorkflowField label="Provider" help="Use manual tracking when no external ticket system should be called; choose an external provider when this workflow should create or reconcile tickets through an integration.">
                  <select
                    className="input"
                    value={provider}
                    onChange={e => updateTicketWorkflow(index, 'provider', e.target.value)}
                  >
                    <option value="manual">Manual tracking</option>
                    <option value="servicenow">{ticketProviderLabel('servicenow', { action: true })}</option>
                  </select>
                </WorkflowField>
                <WorkflowField label="Preservation source" help="This links the workflow to a configured preservation source such as email, box, slack, zoom, or a custom source.">
                  <input
                    className="input"
                    list="ticket-workflow-preservation-sources"
                    value={workflow.preservation_source || ''}
                    onChange={e => updateTicketWorkflow(index, 'preservation_source', e.target.value)}
                    placeholder="email"
                  />
                </WorkflowField>
                <WorkflowField label="Hold field/key" help="Use an existing hold field such as holds_box for built-in source automation, or leave blank for manual/custom workflows.">
                  <input
                    className="input"
                    value={workflow.hold_key || ''}
                    onChange={e => updateTicketWorkflow(index, 'hold_key', e.target.value)}
                    placeholder="holds_box"
                  />
                </WorkflowField>
                <WorkflowField label="Hold operation" help="Choose Hold when this ticket represents applying or maintaining preservation. Choose Release when it represents releasing the linked source.">
                  <select className="input" value={workflow.hold_operation || 'hold'} onChange={e => updateTicketWorkflow(index, 'hold_operation', e.target.value)}>
                    <option value="hold">Apply or maintain hold</option>
                    <option value="release">Release hold</option>
                  </select>
                </WorkflowField>
                <WorkflowField label="Completion satisfies source" help="Optional preservation source to mark held when this external ticket closes. Leave blank when closing the ticket should not satisfy another source.">
                  <input
                    className="input"
                    list="ticket-workflow-preservation-sources"
                    value={workflow.completion_satisfies_source || ''}
                    onChange={e => updateTicketWorkflow(index, 'completion_satisfies_source', e.target.value)}
                    placeholder="email"
                  />
                </WorkflowField>
                <WorkflowField label="Completion hold field/key" help="Advanced optional hold field to mark complete when the ticket closes. Prefer Completion satisfies source for normal configuration.">
                  <input className="input" value={workflow.completion_satisfies_hold_key || ''} onChange={e => updateTicketWorkflow(index, 'completion_satisfies_hold_key', e.target.value)} placeholder="holds_email" />
                </WorkflowField>
                <WorkflowField label="Tech group" help="Tech users assigned to this group can work this workflow. Groups are defined by this catalog and can match any team structure you use.">
                  <input
                    className="input"
                    value={workflow.tech_group || ''}
                    onChange={e => updateTicketWorkflow(index, 'tech_group', e.target.value)}
                    placeholder="endpoint"
                  />
                </WorkflowField>
                <WorkflowField label="Detail fields" help="Access log requests collect one custodian, Employee ID, date/time windows, and request notes before creating or tracking the ticket. Use this for EHR, badge, VPN, application, or other audit-log workflows.">
                  <select
                    className="input"
                    value={normalizeTicketWorkflowMetadataSchema(workflow.metadata_schema || workflow.metadataSchema)}
                    onChange={e => updateTicketWorkflow(index, 'metadata_schema', e.target.value)}
                  >
                    <option value="">Standard ticket metadata</option>
                    <option value="access_log_request">Access log request</option>
                  </select>
                </WorkflowField>
              </div>

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontWeight: 700, marginTop: 12 }}>
                <input
                  type="checkbox"
                  checked={!!workflow.auto_create_on_approval}
                  onChange={e => updateTicketWorkflow(index, 'auto_create_on_approval', e.target.checked)}
                  style={{ marginTop: 3 }}
                />
                <span>
                  Auto-create on case-request approval
                  <span style={fieldHelpStyle}>When enabled, approving a new-case or custodian request creates an external ticket for custodians who require this workflow's linked preservation source.</span>
                </span>
              </label>

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontWeight: 700, marginTop: 12 }}>
                <input
                  type="checkbox"
                  checked={!!workflow.manual_status_tracking}
                  onChange={e => updateTicketWorkflow(index, 'manual_status_tracking', e.target.checked)}
                  style={{ marginTop: 3 }}
                />
                <span>
                  Keep preservation status manual
                  <span style={fieldHelpStyle}>Do not infer the linked preservation status from whether the external ticket is open or closed. Administrators and tech users will update the preservation status manually.</span>
                </span>
              </label>

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontWeight: 700, marginTop: 12 }}>
                <input
                  type="checkbox"
                  checked={!!workflow.requires_matched_email}
                  onChange={e => updateTicketWorkflow(index, 'requires_matched_email', e.target.checked)}
                  style={{ marginTop: 3 }}
                />
                <span>
                  Requires matched email
                  <span style={fieldHelpStyle}>Enable this when the workflow should only be offered for custodians with a verified or selected email address.</span>
                </span>
              </label>

              {provider === 'servicenow' && (
                <div style={{ marginTop: 14 }}>
                  <h4 style={{ margin: '0 0 10px' }}>{providerName} mapping</h4>
                  <div className="form-grid">
                    <WorkflowField label="Assignment group" help="The provider group that receives tickets for this workflow.">
                      <input className="input" value={workflow.assignment_group || ''} onChange={e => updateTicketWorkflow(index, 'assignment_group', e.target.value)} />
                    </WorkflowField>
                    <WorkflowField label="Incident keyword" help="Optional keyword or routing token included in the provider payload.">
                      <input className="input" value={workflow.incident_keyword || ''} onChange={e => updateTicketWorkflow(index, 'incident_keyword', e.target.value)} />
                    </WorkflowField>
                    <WorkflowField label="Short description" help="Default short description used when DiscoveryOne creates the external ticket.">
                      <input className="input" value={workflow.short_description || ''} onChange={e => updateTicketWorkflow(index, 'short_description', e.target.value)} placeholder="Preservation action needed" />
                    </WorkflowField>
                    <WorkflowField label="Symptom" help="Optional provider symptom/category value for this workflow.">
                      <input className="input" value={workflow.symptom || ''} onChange={e => updateTicketWorkflow(index, 'symptom', e.target.value)} placeholder="Inquiry" />
                    </WorkflowField>
                    <WorkflowField label="Request type" help="Optional request type value for import-set or custom provider mappings.">
                      <input className="input" value={workflow.request_type || ''} onChange={e => updateTicketWorkflow(index, 'request_type', e.target.value)} />
                    </WorkflowField>
                    <WorkflowField label="Case link label" help="Text label used for the DiscoveryOne case link in the external ticket payload.">
                      <input className="input" value={workflow.link_label || ''} onChange={e => updateTicketWorkflow(index, 'link_label', e.target.value)} placeholder="Case link" />
                    </WorkflowField>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
        <button type="button" className="btn subtle" onClick={addTicketWorkflow}>Add Workflow</button>
        <button type="button" className="btn secondary" onClick={saveTicketWorkflows} disabled={ticketWorkflowSaving}>
          {ticketWorkflowSaving ? 'Saving' : 'Save Ticket Workflows'}
        </button>
        {ticketWorkflowStatus && <span style={{ color: statusColor(ticketWorkflowStatus) }}>{ticketWorkflowStatus}</span>}
      </div>
    </div>
  )
}
