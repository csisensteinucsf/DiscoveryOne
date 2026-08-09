import { useCallback, useEffect, useState } from 'react'
import { GripVertical, Plus } from 'lucide-react'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'
import { DeleteIconButton, EditIconButton } from '../components/RowActionIconButton.jsx'
import SystemCaseTemplateCustomFields from './SystemCaseTemplateCustomFields.jsx'
import {
  nextCaseTemplateSortOrder,
  mergeSavedCaseTemplate,
  reorderCaseTemplates,
  templateOrderUpdates,
} from './caseTemplateOrder.js'

const TEMPLATE_FIELDS = [
  ['legal_case_name', 'Case name', 'text'],
  ['claimant', 'Claimant', 'text'],
  ['internal_counsel', 'Internal counsel', 'text'],
  ['outside_counsel', 'Outside counsel', 'text'],
  ['matter_number', 'Matter or claim number', 'text'],
  ['requestor', 'Primary requestor email', 'email'],
  ['requestors', 'Additional requestor emails', 'requestors'],
  ['analyst_id', 'Analyst', 'analyst'],
  ['is_private', 'Private case', 'boolean'],
  ['is_test_case', 'Test case', 'boolean'],
  ['description', 'Additional notes / comments', 'textarea'],
  ['start_date', 'Start date', 'date'],
  ['closure_nag_days', 'Case status notification interval', 'number'],
]

const emptyEditor = () => ({
  id: null,
  name: '',
  description: '',
  enabled: true,
  is_default: false,
  defaults: {},
  field_rules: Object.fromEntries(TEMPLATE_FIELDS.map(([key]) => [key, { visible: true, required: false }])),
  custom_fields: [],
})

const normalizeEditor = template => ({
  ...emptyEditor(),
  ...template,
  defaults: { ...(template?.defaults || {}) },
  field_rules: Object.fromEntries(TEMPLATE_FIELDS.map(([key]) => [
    key,
    { visible: true, required: false, ...(template?.field_rules?.[key] || {}) },
  ])),
  custom_fields: (template?.custom_fields || []).map(field => ({
    ...field,
    options: [...(field.options || [])],
  })),
})

const responseError = async response => {
  const payload = await response.json().catch(() => null)
  const detail = payload?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return `${detail.message}${detail.fields?.length ? `: ${detail.fields.join(', ')}` : ''}`
  return `Request failed (${response.status})`
}

const TEMPLATE_SAVE_TIMEOUT_MS = 20000

export default function SystemCaseTemplatesPanel({ apiBase, isSysAdmin, analystOptions = [], titleStyle }) {
  const [templates, setTemplates] = useState([])
  const [editor, setEditor] = useState(null)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [reorderBusy, setReorderBusy] = useState(false)
  const [draggedTemplateId, setDraggedTemplateId] = useState(null)
  const [dropTarget, setDropTarget] = useState(null)

  const load = useCallback(async () => {
    if (!isSysAdmin) return
    const response = await fetch(`${apiBase}/case-templates?include_disabled=true`, { credentials: 'include' })
    if (!response.ok) {
      setStatus(await responseError(response))
      return
    }
    setTemplates(await response.json())
  }, [apiBase, isSysAdmin])

  useEffect(() => { load() }, [load])

  const updateRule = (field, key, value) => {
    setEditor(current => {
      const rule = { ...current.field_rules[field], [key]: value }
      if (key === 'visible' && !value) rule.required = false
      return { ...current, field_rules: { ...current.field_rules, [field]: rule } }
    })
  }

  const updateDefault = (field, value) => {
    setEditor(current => {
      const defaults = { ...current.defaults }
      if (value === '' || value === undefined || value === null) delete defaults[field]
      else defaults[field] = value
      return { ...current, defaults }
    })
  }

  const save = async () => {
    if (!editor?.name.trim()) {
      setStatus('Template name is required.')
      return
    }
    if ((editor.custom_fields || []).some(field => !field.label?.trim())) {
      setStatus('Every custom field needs a label.')
      return
    }
    if ((editor.custom_fields || []).some(field => field.field_type === 'select' && !field.options?.length)) {
      setStatus('Every dropdown custom field needs at least one option.')
      return
    }
    setBusy(true)
    setStatus('')
    const defaults = { ...editor.defaults }
    if (Array.isArray(defaults.requestors)) {
      defaults.requestors = defaults.requestors.filter(item => item?.email)
      if (!defaults.requestors.length) delete defaults.requestors
    }
    const payload = {
      name: editor.name.trim(),
      description: editor.description.trim() || null,
      enabled: !!editor.enabled,
      is_default: !!editor.is_default,
      sort_order: editor.id ? Number(editor.sort_order || 0) : nextCaseTemplateSortOrder(templates),
      defaults,
      field_rules: editor.field_rules,
      custom_fields: (editor.custom_fields || []).map(field => ({
        ...field,
        label: field.label.trim(),
        options: field.field_type === 'select' ? field.options : [],
      })),
    }
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), TEMPLATE_SAVE_TIMEOUT_MS)
    try {
      const response = await fetch(`${apiBase}/case-templates${editor.id ? `/${editor.id}` : ''}`, {
        method: editor.id ? 'PUT' : 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      if (!response.ok) {
        setStatus(await responseError(response))
        return
      }
      const savedTemplate = await response.json()
      setTemplates(current => mergeSavedCaseTemplate(current, savedTemplate))
      setEditor(null)
      setStatus('Case template saved.')
    } catch (error) {
      const requestTimedOut = error?.name === 'AbortError'
      setStatus(
        requestTimedOut
          ? 'Saving timed out. Check the connection, then reopen templates before trying again.'
          : 'Unable to save the case template. Check the connection and try again.',
      )
    } finally {
      window.clearTimeout(timeoutId)
      setBusy(false)
    }
  }

  const remove = async template => {
    if (!window.confirm(`Delete case template "${template.name}"? Templates already used by a case must be disabled instead.`)) return
    setBusy(true)
    const response = await fetch(`${apiBase}/case-templates/${template.id}`, { method: 'DELETE', credentials: 'include' })
    if (!response.ok) setStatus(await responseError(response))
    else {
      setStatus('Case template deleted.')
      await load()
    }
    setBusy(false)
  }

  const clearDragState = () => {
    setDraggedTemplateId(null)
    setDropTarget(null)
  }

  const persistTemplateOrder = async orderedTemplates => {
    const updates = templateOrderUpdates(orderedTemplates)
    setReorderBusy(true)
    setStatus('')
    try {
      for (const update of updates) {
        const response = await fetch(apiBase + '/case-templates/' + update.id, {
          method: 'PUT',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sort_order: update.sort_order }),
        })
        if (!response.ok) throw new Error(await responseError(response))
      }
      setTemplates(orderedTemplates.map((template, index) => ({
        ...template,
        sort_order: updates[index].sort_order,
      })))
      setStatus('Template order saved.')
    } catch (error) {
      setStatus('Failed to save template order: ' + error.message)
      await load()
    } finally {
      setReorderBusy(false)
    }
  }

  const handleTemplateDragStart = (event, templateId) => {
    if (busy || reorderBusy) {
      event.preventDefault()
      return
    }
    const id = String(templateId)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', id)
    setDraggedTemplateId(id)
  }

  const handleTemplateDragOver = (event, templateId) => {
    const targetId = String(templateId)
    if (!draggedTemplateId || draggedTemplateId === targetId) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
    const bounds = event.currentTarget.getBoundingClientRect()
    const placement = event.clientY > bounds.top + bounds.height / 2 ? 'after' : 'before'
    setDropTarget({ id: targetId, placement })
  }

  const handleTemplateDrop = async (event, targetId) => {
    event.preventDefault()
    const sourceId = draggedTemplateId || event.dataTransfer.getData('text/plain')
    const bounds = event.currentTarget.getBoundingClientRect()
    const placement = event.clientY > bounds.top + bounds.height / 2 ? 'after' : 'before'
    const reordered = reorderCaseTemplates(templates, sourceId, targetId, placement)
    clearDragState()
    if (reordered.every((template, index) => String(template.id) === String(templates[index]?.id))) return
    setTemplates(reordered)
    await persistTemplateOrder(reordered)
  }

  const defaultInput = (field, type) => {
    const value = editor.defaults[field]
    if (type === 'boolean') {
      return <select value={value === undefined ? '' : String(!!value)} onChange={event => updateDefault(field, event.target.value === '' ? '' : event.target.value === 'true')}><option value="">No default</option><option value="false">No</option><option value="true">Yes</option></select>
    }
    if (type === 'analyst') {
      return <select value={value ?? ''} onChange={event => updateDefault(field, event.target.value ? Number(event.target.value) : '')}><option value="">No default</option>{analystOptions.map(option => <option key={option.id} value={option.id}>{option.first_name || option.last_name ? `${option.first_name || ''} ${option.last_name || ''}`.trim() : option.username}</option>)}</select>
    }
    if (type === 'requestors') {
      const emails = Array.isArray(value) ? value.map(item => item?.email).filter(Boolean).join(', ') : ''
      return <input value={emails} placeholder="email1@example.edu, email2@example.edu" onChange={event => updateDefault(field, event.target.value.split(',').map(email => ({ email: email.trim(), is_primary: false })).filter(item => item.email))} />
    }
    if (type === 'date') {
      return <select value={editor.defaults.start_date_mode || ''} onChange={event => {
        setEditor(current => {
          const defaults = { ...current.defaults }
          delete defaults.start_date
          if (event.target.value) defaults.start_date_mode = event.target.value
          else delete defaults.start_date_mode
          return { ...current, defaults }
        })
      }}><option value="">No default</option><option value="today">Date created</option></select>
    }
    if (type === 'textarea') return <textarea rows={2} value={value ?? ''} onChange={event => updateDefault(field, event.target.value)} />
    return <input type={type} min={type === 'number' ? 1 : undefined} value={value ?? ''} onChange={event => updateDefault(field, type === 'number' && event.target.value ? Number(event.target.value) : event.target.value)} />
  }

  if (!isSysAdmin) return <div className="card">Only system administrators can manage case templates.</div>

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <div>
          <div style={titleStyle}>New Case Templates</div>
          <p style={{ color: 'var(--muted,#6b7280)', margin: 0 }}>Create choices for the New Case form. Each template can supply default values and decide which fields are visible or required.</p>
        </div>
        <button className="btn" type="button" onClick={() => { setStatus(''); setEditor(emptyEditor()) }} disabled={busy || reorderBusy}><Plus size={16} /> New Template</button>
      </div>
      {status && <div style={{ marginTop: 12, color: status.toLowerCase().includes('failed') || status.toLowerCase().includes('required') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>{status}</div>}
      <div className="table-responsive" style={{ marginTop: 16 }}>
        <table className="table">
          <thead>
            <tr>
              <th className="case-template-order-column" aria-label="Reorder" />
              <th>Name</th>
              <th>Default</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {templates.map(template => {
              const templateId = String(template.id)
              const dragClass = draggedTemplateId === templateId ? ' is-dragging' : ''
              const dropClass = dropTarget?.id === templateId ? ' is-drop-' + dropTarget.placement : ''
              return (
                <tr
                  key={template.id}
                  className={'case-template-order-row' + dragClass + dropClass}
                  onDragOver={event => handleTemplateDragOver(event, template.id)}
                  onDrop={event => handleTemplateDrop(event, template.id)}
                >
                  <td className="case-template-order-column">
                    <button
                      className="case-template-drag-handle"
                      type="button"
                      draggable={!busy && !reorderBusy}
                      disabled={busy || reorderBusy}
                      title="Drag to reorder"
                      aria-label={'Drag ' + template.name + ' to reorder'}
                      onDragStart={event => handleTemplateDragStart(event, template.id)}
                      onDragEnd={clearDragState}
                    >
                      <GripVertical size={18} aria-hidden="true" />
                    </button>
                  </td>
                  <td><strong>{template.name}</strong><div className="form-help">{template.description}</div></td>
                  <td>{template.is_default ? 'Yes' : '-'}</td>
                  <td>{template.enabled ? 'Enabled' : 'Disabled'}</td>
                  <td>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <EditIconButton label={'Edit ' + template.name} onClick={() => { setStatus(''); setEditor(normalizeEditor(template)) }} disabled={busy || reorderBusy} />
                      <DeleteIconButton label={'Delete ' + template.name} onClick={() => remove(template)} disabled={busy || reorderBusy} />
                    </div>
                  </td>
                </tr>
              )
            })}
            {!templates.length && <tr><td colSpan="5">No case templates configured. The standard New Case form remains available.</td></tr>}
          </tbody>
        </table>
      </div>

      {editor && <Modal open title={editor.id ? 'Edit New Case Template' : 'New Case Template'} onClose={() => setEditor(null)} width={900} bodyStyle={{ maxHeight: 'calc(100vh - 170px)', overflowY: 'auto', overscrollBehavior: 'contain' }} footer={<><button type="button" className="btn secondary" onClick={() => setEditor(null)}>Cancel</button><button type="submit" form="case-template-form" className="btn" disabled={busy}>{busy ? 'Saving' : 'Save Template'}</button></>}>
        <form id="case-template-form" onSubmit={event => { event.preventDefault(); save() }}>
        <div className="form-grid">
          <label style={{ gridColumn: '1 / -1' }}>
            <RequiredFieldLabel>Template name</RequiredFieldLabel>
            <input value={editor.name} onChange={event => setEditor(current => ({ ...current, name: event.target.value }))} required />
          </label>
          <label style={{ gridColumn: '1 / -1' }}>Description<textarea rows={2} value={editor.description} onChange={event => setEditor(current => ({ ...current, description: event.target.value }))} /></label>
          <div className="case-template-options" style={{ gridColumn: '1 / -1' }}>
            <label className="case-template-option"><input type="checkbox" checked={editor.enabled} onChange={event => setEditor(current => ({ ...current, enabled: event.target.checked, is_default: event.target.checked ? current.is_default : false }))} /><span>Enabled</span></label>
            <label className="case-template-option"><input type="checkbox" checked={editor.is_default} disabled={!editor.enabled} onChange={event => setEditor(current => ({ ...current, is_default: event.target.checked }))} /><span>Default</span></label>
          </div>
        </div>
        <div className="case-template-fields" style={{ marginTop: 18 }}>
          <div className="case-template-fields__header"><strong>Field</strong><strong>Show</strong><strong>Require</strong><strong>Default value</strong></div>
          {TEMPLATE_FIELDS.map(([field, label, type]) => {
            const rule = editor.field_rules[field]
            return <div className="case-template-fields__row" key={field}><span>{label}</span><input type="checkbox" aria-label={`Show ${label}`} checked={rule.visible} onChange={event => updateRule(field, 'visible', event.target.checked)} /><input type="checkbox" aria-label={`Require ${label}`} checked={rule.required} disabled={!rule.visible} onChange={event => updateRule(field, 'required', event.target.checked)} /><div>{defaultInput(field, type)}</div></div>
          })}
        </div>
        <SystemCaseTemplateCustomFields editor={editor} setEditor={setEditor} />
        {status && (
          <div className="case-template-editor-status" role="alert" aria-live="polite">
            {status}
          </div>
        )}
        </form>
      </Modal>}
    </div>
  )
}
