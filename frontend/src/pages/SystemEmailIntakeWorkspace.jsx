import { useCallback, useEffect, useMemo, useState } from 'react'
import { Ban, Eye, Play, Plus, RefreshCw, RotateCcw, Save, TestTube2, Trash2 } from 'lucide-react'
import Modal from '../components/Modal.jsx'

const emptyTemplate = () => ({
  id: null,
  name: '',
  description: '',
  enabled: true,
  priority: 100,
  sender_pattern: '',
  recipient_pattern: '',
  subject_pattern: '',
  body_markers: [],
  field_markers: {
    case_name: 'Case Name:',
    legal_case_name: 'Legal Case Name:',
    claimant: 'Claimant:',
    internal_counsel: 'Internal Counsel:',
    outside_counsel: 'Outside Counsel:',
    matter_number: 'Matter Number:',
    custodians: 'Custodians:',
  },
  default_values: {},
  hold_name: '',
})

const emptySample = () => ({
  sender: 'requestor@example.com',
  recipients: 'ediscovery-intake@example.edu',
  subject: 'New matter request',
  body_content_type: 'text',
  body: 'Case Name: Example Matter\nClaimant: Example Person\nMatter Number: MAT-100\nCustodians: Person One <person.one@example.edu>',
})

const statusColor = status => ({
  pending_request: '#166534',
  failed: '#b91c1c',
  unmatched: '#92400e',
  ignored: '#475569',
  received: '#075985',
}[status] || '#475569')

const labelStatus = status => String(status || 'unknown').replaceAll('_', ' ')

export default function SystemEmailIntakeWorkspace({ apiBase, enabled, showToast, mode = 'all' }) {
  const [status, setStatus] = useState(null)
  const [templates, setTemplates] = useState([])
  const [messages, setMessages] = useState([])
  const [messageTotal, setMessageTotal] = useState(0)
  const [messageFilter, setMessageFilter] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [editor, setEditor] = useState(null)
  const [sample, setSample] = useState(emptySample)
  const [testTemplate, setTestTemplate] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [detail, setDetail] = useState(null)

  const apiRequest = useCallback(async (path, options = {}) => {
    const response = await fetch(`${apiBase}/system/email-intake${path}`, {
      credentials: 'include',
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
    })
    if (!response.ok) {
      let message = `Request failed (${response.status})`
      try {
        const payload = await response.json()
        message = payload?.detail || message
      } catch {
        message = await response.text() || message
      }
      throw new Error(message)
    }
    return response.status === 204 ? null : response.json()
  }, [apiBase])

  const loadWorkspace = useCallback(async () => {
    if (!enabled) return
    setBusy('load')
    setError('')
    try {
      const query = messageFilter ? `?status=${encodeURIComponent(messageFilter)}` : ''
      const [nextStatus, nextTemplates, nextMessages] = await Promise.all([
        apiRequest('/status'),
        apiRequest('/templates'),
        apiRequest(`/messages${query}`),
      ])
      setStatus(nextStatus)
      setTemplates(nextTemplates || [])
      setMessages(nextMessages?.items || [])
      setMessageTotal(Number(nextMessages?.total || 0))
    } catch (err) {
      setError(err?.message || 'Unable to load Email Intake.')
    } finally {
      setBusy('')
    }
  }, [apiRequest, enabled, messageFilter])

  useEffect(() => {
    loadWorkspace()
  }, [loadWorkspace])

  const runAction = async (key, path, options = {}) => {
    setBusy(key)
    setError('')
    try {
      const result = await apiRequest(path, options)
      showToast?.(key === 'poll' ? `Mailbox poll completed: ${result.processed || 0} message(s) processed.` : 'Email Intake action completed.', 'success')
      await loadWorkspace()
      return result
    } catch (err) {
      setError(err?.message || 'Email Intake action failed.')
      showToast?.(err?.message || 'Email Intake action failed.', 'error')
      return null
    } finally {
      setBusy('')
    }
  }

  const saveTemplate = async () => {
    if (!editor) return
    const payload = {
      ...editor,
      body_markers: Array.isArray(editor.body_markers) ? editor.body_markers : [],
      field_markers: Object.fromEntries(Object.entries(editor.field_markers || {}).filter(([, value]) => String(value || '').trim())),
      default_values: Object.fromEntries(Object.entries(editor.default_values || {}).filter(([, value]) => String(value || '').trim())),
    }
    delete payload.id
    delete payload.created_at
    delete payload.updated_at
    setBusy('template-save')
    setError('')
    try {
      await apiRequest(editor.id ? `/templates/${editor.id}` : '/templates', {
        method: editor.id ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      })
      setEditor(null)
      showToast?.('Email Intake template saved.', 'success')
      await loadWorkspace()
    } catch (err) {
      setError(err?.message || 'Unable to save template.')
    } finally {
      setBusy('')
    }
  }

  const deleteTemplate = async template => {
    if (!window.confirm(`Delete Email Intake template "${template.name}"?`)) return
    await runAction('template-delete', `/templates/${template.id}`, { method: 'DELETE' })
  }

  const openTemplateTest = template => {
    setTestTemplate(template)
    setSample(emptySample())
    setTestResult(null)
  }

  const runTemplateTest = async () => {
    if (!testTemplate) return
    setBusy('template-test')
    setError('')
    try {
      const templatePayload = { ...testTemplate }
      delete templatePayload.id
      delete templatePayload.created_at
      delete templatePayload.updated_at
      const result = await apiRequest('/templates/test', {
        method: 'POST',
        body: JSON.stringify({
          ...(testTemplate.id ? { template_id: testTemplate.id } : { template: templatePayload }),
          sample: {
            ...sample,
            recipients: String(sample.recipients || '').split(/[;,\n]+/).map(value => value.trim()).filter(Boolean),
          },
        }),
      })
      setTestResult(result)
    } catch (err) {
      setError(err?.message || 'Unable to test template.')
    } finally {
      setBusy('')
    }
  }

  const viewMessage = async message => {
    setBusy(`message-${message.id}`)
    try {
      setDetail(await apiRequest(`/messages/${message.id}`))
    } catch (err) {
      setError(err?.message || 'Unable to load message details.')
    } finally {
      setBusy('')
    }
  }

  const statusSummary = useMemo(() => {
    if (!status) return []
    return [
      ['Pending requests', status.counts?.pending_request || 0],
      ['Unmatched', status.counts?.unmatched || 0],
      ['Failed', status.counts?.failed || 0],
      ['Ignored', status.counts?.ignored || 0],
    ]
  }, [status])

  const showOperations = mode === 'all' || mode === 'operations'
  const showTemplates = mode === 'all' || mode === 'templates'

  if (!enabled) return <div className="card">Enable and configure Email Intake under System Integrations before managing its templates or mailbox operations.</div>

  return (
    <section style={{ marginTop: 22, paddingTop: 20, borderTop: '1px solid var(--border,#d1d5db)' }}>
      {showOperations && <><div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h3 style={{ margin: '0 0 4px' }}>Email Intake Operations</h3>
          <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>
            {status?.ready ? `Monitoring ${status.mailbox} / ${status.folder_id}` : 'Save a complete Email Intake configuration before testing or polling.'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn secondary" onClick={() => runAction('connection', '/test-connection', { method: 'POST' })} disabled={!!busy} title="Test Microsoft Graph mailbox access"><TestTube2 size={16} /> Test Connection</button>
          <button className="btn secondary" onClick={() => runAction('poll', '/poll', { method: 'POST' })} disabled={!!busy || !status?.ready} title="Run mailbox polling now"><Play size={16} /> Poll Now</button>
          <button className="btn secondary" onClick={loadWorkspace} disabled={!!busy} title="Refresh Email Intake status"><RefreshCw size={16} /> Refresh</button>
        </div>
      </div>

      {error && <div style={{ color: '#b91c1c', marginTop: 10 }}>{error}</div>}
      {status?.last_error && <div style={{ color: '#b91c1c', marginTop: 10 }}>Last poll error: {status.last_error}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginTop: 14 }}>
        {statusSummary.map(([label, value]) => (
          <div key={label} style={{ borderLeft: '3px solid var(--accent,#00598c)', padding: '6px 10px' }}>
            <div style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>{label}</div>
            <strong style={{ fontSize: 20 }}>{value}</strong>
          </div>
        ))}
        <div style={{ borderLeft: '3px solid #64748b', padding: '6px 10px' }}>
          <div style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>Last successful poll</div>
          <strong style={{ fontSize: 13 }}>{status?.last_success_at ? new Date(status.last_success_at).toLocaleString() : 'Not yet'}</strong>
        </div>
      </div></>}

      {showTemplates && <div style={{ marginTop: mode === 'templates' ? 0 : 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <h4 style={{ margin: 0 }}>Templates</h4>
          <button className="btn secondary" onClick={() => setEditor(emptyTemplate())}><Plus size={16} /> New Template</button>
        </div>
        <div style={{ overflowX: 'auto', marginTop: 10 }}>
          <table>
            <thead><tr><th>Name</th><th>Priority</th><th>Match</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {templates.map(template => (
                <tr key={template.id}>
                  <td><strong>{template.name}</strong><div style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>{template.description}</div></td>
                  <td>{template.priority}</td>
                  <td style={{ fontSize: 12 }}>{[template.sender_pattern && `From: ${template.sender_pattern}`, template.recipient_pattern && `To: ${template.recipient_pattern}`, template.subject_pattern && `Subject: ${template.subject_pattern}`].filter(Boolean).join(' | ') || `${template.body_markers?.length || 0} body marker(s)`}</td>
                  <td>{template.enabled ? 'Enabled' : 'Disabled'}</td>
                  <td><div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}><button className="btn secondary" onClick={() => setEditor({ ...template })}>Edit</button><button className="btn secondary" onClick={() => openTemplateTest(template)}><TestTube2 size={15} /> Test</button><button className="btn secondary" onClick={() => deleteTemplate(template)}><Trash2 size={15} /> Delete</button></div></td>
                </tr>
              ))}
              {!templates.length && <tr><td colSpan="5" style={{ color: 'var(--muted,#6b7280)' }}>No templates configured. Messages remain unmatched until an enabled template exists.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>}

      {showOperations && <div style={{ marginTop: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <h4 style={{ margin: 0 }}>Message Review ({messageTotal})</h4>
          <select className="input" style={{ width: 190 }} value={messageFilter} onChange={e => setMessageFilter(e.target.value)}>
            <option value="">All statuses</option><option value="pending_request">Pending request</option><option value="unmatched">Unmatched</option><option value="failed">Failed</option><option value="ignored">Ignored</option>
          </select>
        </div>
        <div style={{ overflowX: 'auto', marginTop: 10 }}>
          <table>
            <thead><tr><th>Received</th><th>Sender</th><th>Subject</th><th>Template</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {messages.map(message => (
                <tr key={message.id}>
                  <td>{message.received_at ? new Date(message.received_at).toLocaleString() : '-'}</td><td>{message.sender || '-'}</td><td>{message.subject || '(no subject)'}</td><td>{message.template_name || '-'}</td>
                  <td><span style={{ color: statusColor(message.status), fontWeight: 700, textTransform: 'capitalize' }}>{labelStatus(message.status)}</span></td>
                  <td><div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}><button className="btn secondary" onClick={() => viewMessage(message)}><Eye size={15} /> View</button>{!message.case_request_id && message.status !== 'ignored' && <button className="btn secondary" onClick={() => runAction('retry', `/messages/${message.id}/retry`, { method: 'POST' })}><RotateCcw size={15} /> Retry</button>}{!message.case_request_id && message.status !== 'ignored' && <button className="btn secondary" onClick={() => runAction('ignore', `/messages/${message.id}/ignore`, { method: 'POST' })}><Ban size={15} /> Ignore</button>}</div></td>
                </tr>
              ))}
              {!messages.length && <tr><td colSpan="6" style={{ color: 'var(--muted,#6b7280)' }}>No messages in this view.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>}

      {showTemplates && editor && (
        <Modal open title={editor.id ? 'Edit Email Intake Template' : 'New Email Intake Template'} onClose={() => setEditor(null)} width={820} bodyStyle={{ maxHeight: '68vh', overflowY: 'auto' }} footer={<><button className="btn secondary" onClick={() => setEditor(null)}>Cancel</button><button className="btn" onClick={saveTemplate} disabled={busy === 'template-save'}><Save size={16} /> Save</button></>}>
          <div className="form-grid">
            <label>Name<input className="input" value={editor.name || ''} onChange={e => setEditor(prev => ({ ...prev, name: e.target.value }))} /></label>
            <label>Priority<input className="input" type="number" min="1" max="10000" value={editor.priority ?? 100} onChange={e => setEditor(prev => ({ ...prev, priority: Number(e.target.value) }))} /></label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}><input type="checkbox" checked={editor.enabled !== false} onChange={e => setEditor(prev => ({ ...prev, enabled: e.target.checked }))} />Enabled</label>
            <label>Named Hold (optional)<input className="input" value={editor.hold_name || ''} onChange={e => setEditor(prev => ({ ...prev, hold_name: e.target.value }))} /><span className="form-help">Leave blank to create the case request and custodians without assigning them to a Hold.</span></label>
            <label style={{ gridColumn: '1 / -1' }}>Description<textarea className="input" rows={2} value={editor.description || ''} onChange={e => setEditor(prev => ({ ...prev, description: e.target.value }))} /></label>
            <label>Sender match<input className="input" value={editor.sender_pattern || ''} onChange={e => setEditor(prev => ({ ...prev, sender_pattern: e.target.value }))} placeholder="*@outside-counsel.com" /></label>
            <label>Recipient match<input className="input" value={editor.recipient_pattern || ''} onChange={e => setEditor(prev => ({ ...prev, recipient_pattern: e.target.value }))} placeholder="ediscovery-intake@example.edu" /></label>
            <label style={{ gridColumn: '1 / -1' }}>Subject match<input className="input" value={editor.subject_pattern || ''} onChange={e => setEditor(prev => ({ ...prev, subject_pattern: e.target.value }))} placeholder="New matter*" /></label>
            <label style={{ gridColumn: '1 / -1' }}>Required body markers<textarea className="input" rows={3} value={(editor.body_markers || []).join('\n')} onChange={e => setEditor(prev => ({ ...prev, body_markers: e.target.value.split('\n').map(value => value.trim()).filter(Boolean) }))} placeholder="One required phrase per line" /></label>
          </div>
          <h4>Field Labels</h4>
          <p className="form-help">Each value is the label that precedes the field in the plain-text message body.</p>
          <div className="form-grid">
            {Object.entries({ case_name: 'Case Name', legal_case_name: 'Legal Case Name', claimant: 'Claimant', internal_counsel: 'Internal Counsel', outside_counsel: 'Outside Counsel', matter_number: 'Matter Number', custodians: 'Custodians', description: 'Additional Notes' }).map(([key, label]) => <label key={key}>{label}<input className="input" value={editor.field_markers?.[key] || ''} onChange={e => setEditor(prev => ({ ...prev, field_markers: { ...(prev.field_markers || {}), [key]: e.target.value } }))} placeholder={`${label}:`} /></label>)}
          </div>
          <h4>Default Values</h4>
          <div className="form-grid">
            {Object.entries({ case_name: 'Case Name', legal_case_name: 'Legal Case Name', claimant: 'Claimant', internal_counsel: 'Internal Counsel', outside_counsel: 'Outside Counsel', matter_number: 'Matter Number', description: 'Additional Notes' }).map(([key, label]) => <label key={key}>{label}<input className="input" value={editor.default_values?.[key] || ''} onChange={e => setEditor(prev => ({ ...prev, default_values: { ...(prev.default_values || {}), [key]: e.target.value } }))} /></label>)}
          </div>
        </Modal>
      )}

      {showTemplates && testTemplate && (
        <Modal open title={`Test Template: ${testTemplate.name || 'Unsaved template'}`} onClose={() => setTestTemplate(null)} width={760} bodyStyle={{ maxHeight: '68vh', overflowY: 'auto' }} footer={<><button className="btn secondary" onClick={() => setTestTemplate(null)}>Close</button><button className="btn" onClick={runTemplateTest} disabled={busy === 'template-test'}><TestTube2 size={16} /> Run Test</button></>}>
          <div className="form-grid"><label>Sender<input className="input" value={sample.sender} onChange={e => setSample(prev => ({ ...prev, sender: e.target.value }))} /></label><label>Recipients<input className="input" value={sample.recipients} onChange={e => setSample(prev => ({ ...prev, recipients: e.target.value }))} /></label><label style={{ gridColumn: '1 / -1' }}>Subject<input className="input" value={sample.subject} onChange={e => setSample(prev => ({ ...prev, subject: e.target.value }))} /></label><label style={{ gridColumn: '1 / -1' }}>Body<textarea className="input" rows={9} value={sample.body} onChange={e => setSample(prev => ({ ...prev, body: e.target.value }))} /></label></div>
          {testResult && <div style={{ marginTop: 14 }}><strong style={{ color: testResult.matched ? '#166534' : '#b91c1c' }}>{testResult.matched ? 'Template matched' : `No match: ${(testResult.failures || []).join(', ')}`}</strong><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: 'var(--muted-bg,#f8fafc)', padding: 10, maxHeight: 260, overflow: 'auto' }}>{JSON.stringify(testResult.extracted, null, 2)}</pre></div>}
        </Modal>
      )}

      {showOperations && detail && (
        <Modal open title={detail.subject || 'Email Intake Message'} onClose={() => setDetail(null)} width={760} bodyStyle={{ maxHeight: '68vh', overflowY: 'auto' }} footer={<button className="btn secondary" onClick={() => setDetail(null)}>Close</button>}>
          <div style={{ display: 'grid', gap: 6, fontSize: 13 }}><div><strong>From:</strong> {detail.sender || '-'}</div><div><strong>To:</strong> {(detail.recipients || []).join(', ') || '-'}</div><div><strong>Status:</strong> {labelStatus(detail.status)}</div><div><strong>Template:</strong> {detail.template_name || '-'}</div><div><strong>Case Request:</strong> {detail.case_request_id || '-'}</div><div><strong>Attachments:</strong> {detail.attachment_count || 0}</div>{detail.last_error && <div style={{ color: '#b91c1c' }}><strong>Error:</strong> {detail.last_error}</div>}</div><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: 'var(--muted-bg,#f8fafc)', padding: 10, marginTop: 14 }}>{detail.body_text || '(empty body)'}</pre>
        </Modal>
      )}
    </section>
  )
}
