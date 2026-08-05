import { useEffect, useState } from 'react'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'
import { Field, TextInput, Select, Button } from './caseDetailControls.jsx'
import { displayUserName } from './caseDetailUtils.js'
import CaseCustomFieldsEditor from './CaseCustomFieldsEditor.jsx'
import { findInvalidFormControls, findMissingRequiredControls } from './casesUtils.js'
export function EditCaseModal({ initial, analysts, requestorOptions, onClose, onSave, useLegalCaseNameAsPrimary = false, internalCounselLabel = 'Internal Counsel' }) {
  const [form, setForm] = useState({ ...initial, additional_requestors: '' })
  const [showMissingRequired, setShowMissingRequired] = useState(false)
  useEffect(() => {
    const primary = (initial.requestor || '').trim().toLowerCase()
    const extras = Array.isArray(initial.requestors)
      ? initial.requestors.filter(r => !r?.is_primary && (r.email || '').trim().toLowerCase() !== primary)
      : []
    setForm({
      ...initial,
      additional_requestors: extras.map(r => r.email).filter(Boolean).join(', '),
    })
    setShowMissingRequired(false)
  }, [initial])
  const caseNameValue = useLegalCaseNameAsPrimary ? (form.legal_case_name || form.name || '') : (form.name || '')
  const updatePrimaryCaseName = (value) => {
    if (useLegalCaseNameAsPrimary) {
      setForm({ ...form, name: value, legal_case_name: value })
    } else {
      setForm({ ...form, name: value })
    }
  }
  const fieldLabel = (label, required = false) => (
    <RequiredFieldLabel required={required}>
      {label}
    </RequiredFieldLabel>
  )
  const handleSubmit = (event) => {
    event.preventDefault()
    const missingControls = findMissingRequiredControls(event.currentTarget)
    if (missingControls.length) {
      setShowMissingRequired(true)
      missingControls[0]?.focus?.()
      return
    }
    setShowMissingRequired(false)
    const invalidControls = findInvalidFormControls(event.currentTarget)
    if (invalidControls.length) {
      invalidControls[0]?.focus?.()
      event.currentTarget.reportValidity?.()
      return
    }
    onSave(form)
  }
  const handleInput = (event) => {
    if (showMissingRequired && !findMissingRequiredControls(event.currentTarget).length) {
      setShowMissingRequired(false)
    }
  }
  return (
    <Modal
      open
      title="Edit Case"
      onClose={onClose}
      width={720}
      footer={(
        <div className="case-editor-footer">
          {showMissingRequired ? (
            <div className="case-editor-missing-required" role="alert">Missing required fields</div>
          ) : null}
          <div className="case-editor-footer__actions">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button type="submit" form="edit-case-form">Save Changes</Button>
          </div>
        </div>
      )}
    >
      <form
        id="edit-case-form"
        className="case-editor-form"
        noValidate
        data-show-missing-required={showMissingRequired || undefined}
        onInput={handleInput}
        onSubmit={handleSubmit}
      >
      <Field label={fieldLabel(useLegalCaseNameAsPrimary ? 'Case Name' : 'eDiscovery Case Name', true)}>
        <TextInput value={caseNameValue} onChange={e => updatePrimaryCaseName(e.target.value)} required />
      </Field>
      {!useLegalCaseNameAsPrimary && (
        <Field label="Legal Case Name">
          <TextInput value={form.legal_case_name} onChange={e => setForm({ ...form, legal_case_name: e.target.value })} />
        </Field>
      )}
      <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '12px 14px', border: '2px solid #0f766e', borderRadius: 12, background: '#f0fdfa', marginBottom: 8, color: '#0f172a', fontSize: 14 }}>
        <input
          type="checkbox"
          checked={!!form.is_private}
          onChange={e => setForm({ ...form, is_private: e.target.checked })}
          style={{ marginTop: 3 }}
        />
        <span>
          <strong>Make case private</strong>
          <small style={{ display: 'block', color: '#0f766e', marginTop: 3 }}>
            Only requestors on this case, admins, and analysts can see it.
          </small>
        </span>
      </label>
      <Field label="Claimant">
        <TextInput value={form.claimant || ''} onChange={e => setForm({ ...form, claimant: e.target.value })} />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Matter or Claim Number">
          <TextInput value={form.matter_number || ''} onChange={e => setForm({ ...form, matter_number: e.target.value })} />
        </Field>
        <Field label="Start Date">
          <TextInput type="date" value={form.start_date || ''} onChange={e => setForm({ ...form, start_date: e.target.value })} />
        </Field>
        <Field label={internalCounselLabel}>
          <TextInput value={form.internal_counsel || ''} onChange={e => setForm({ ...form, internal_counsel: e.target.value })} />
        </Field>
        <Field label="Outside Counsel">
          <TextInput value={form.outside_counsel || ''} onChange={e => setForm({ ...form, outside_counsel: e.target.value })} />
        </Field>
      </div>
      <Field label="Additional Notes / Comments">
        <textarea
          className="input"
          rows={4}
          value={form.description || ''}
          onChange={e => setForm({ ...form, description: e.target.value })}
        />
      </Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Analyst">
          <Select
            value={form.analyst_id ?? ''}
            onChange={e => setForm({ ...form, analyst_id: e.target.value ? Number(e.target.value) : null })}
          >
            <option value="">Unassigned</option>
            {analysts.map(u => (<option key={u.id} value={u.id}>{displayUserName(u)}</option>))}
          </Select>
        </Field>
        <Field label="Requestor Email">
          <div>
            <TextInput
              type="email"
              inputMode="email"
              list="requestor_suggestions"
              value={form.requestor || ''}
              onChange={e => setForm({ ...form, requestor: e.target.value })}
              placeholder="requestor@example.com"
            />
            <datalist id="requestor_suggestions">
              {requestorOptions.map((r, i) => <option value={r} key={i} />)}
            </datalist>
          </div>
        </Field>
        <Field label="Additional Requestors (comma separated)">
          <TextInput
            type="text"
            value={form.additional_requestors || ''}
            onChange={e => setForm({ ...form, additional_requestors: e.target.value })}
            placeholder="secondary1@example.com, secondary2@example.com"
          />
          <div style={{ color: '#6b7280', fontSize: 12, marginTop: 4 }}>
            Primary gets notifications; others can access the case.
          </div>
        </Field>
      </div>
      <Field label="Send case status notification to requestor every (days)">
        <TextInput
          type="number"
          min={1}
          step={1}
          value={form.closure_nag_days ?? ''}
          onChange={e => {
            const val = e.target.value
            const num = Number(val)
            setForm({ ...form, closure_nag_days: val === '' ? '' : num })
          }}
          placeholder="180"
        />
      </Field>
      <CaseCustomFieldsEditor
        customFields={form.custom_fields}
        onChange={custom_fields => setForm({ ...form, custom_fields })}
      />
      </form>
    </Modal>
  )
}
