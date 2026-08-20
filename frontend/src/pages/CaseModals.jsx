import { useEffect, useState } from 'react'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'
import CaseCustomFieldsEditor from './CaseCustomFieldsEditor.jsx'
import { findInvalidFormControls, findMissingRequiredControls } from './casesUtils.js'

export function CaseEditorModal({
  open,
  editingId,
  form,
  setForm,
  analysts,
  requestorOptions,
  caseNamingMode,
  secondaryCaseNameLabel,
  useLegalCaseNameAsPrimary,
  internalCounselLabel = 'Internal Counsel',
  matterTypes = [],
  onClose,
  onSubmit,
  onLegalCaseNameChange,
  formatAnalystName,
  caseTemplates = [],
  selectedTemplate = null,
  onTemplateChange,
}) {
  const [showMissingRequired, setShowMissingRequired] = useState(false)

  useEffect(() => {
    setShowMissingRequired(false)
  }, [open, editingId, form.case_template_id])
  if (!open) return null
  const rules = selectedTemplate?.field_rules || {}
  const fieldRule = (name) => rules[name] || { visible: true, required: false }
  const showField = (name) => editingId || fieldRule(name).visible !== false
  const fieldRequired = (name) => !editingId && !!fieldRule(name).required
  const fieldLabel = (label, required = false) => (
    <RequiredFieldLabel required={required}>
      {label}
    </RequiredFieldLabel>
  )
  const handleSubmit = (event) => {
    const missingControls = findMissingRequiredControls(event.currentTarget)
    if (missingControls.length) {
      event.preventDefault()
      setShowMissingRequired(true)
      missingControls[0]?.focus?.()
      return
    }

    setShowMissingRequired(false)
    const invalidControls = findInvalidFormControls(event.currentTarget)
    if (invalidControls.length) {
      event.preventDefault()
      invalidControls[0]?.focus?.()
      event.currentTarget.reportValidity?.()
      return
    }
    onSubmit(event)
  }
  const handleInput = (event) => {
    if (showMissingRequired && !findMissingRequiredControls(event.currentTarget).length) {
      setShowMissingRequired(false)
    }
  }
  return (
    <Modal
      open={open}
      title={editingId ? 'Edit Matter' : 'New Matter'}
      onClose={onClose}
      width={560}
      bodyStyle={{ maxHeight: 'calc(100vh - 170px)', overflowY: 'auto' }}
      footer={(
        <div className="case-editor-footer">
          {showMissingRequired ? (
            <div className="case-editor-missing-required" role="alert">missing required fields</div>
          ) : null}
          <div className="case-editor-footer__actions">
            <button type="button" className="btn secondary" onClick={onClose}>Cancel</button>
            <button type="submit" form="case-modal-form" className="btn">{editingId ? 'Save' : 'Create'}</button>
          </div>
        </div>
      )}
    >
      <form
        id="case-modal-form"
        className="case-editor-form"
        noValidate
        data-show-missing-required={showMissingRequired || undefined}
        onInput={handleInput}
        onSubmit={handleSubmit}
        style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
      >
        {!editingId && (
          <label>
            New Matter Template
            <select
              className="input"
              value={form.case_template_id || ''}
              onChange={event => onTemplateChange?.(event.target.value)}
            >
              <option value="">Standard matter</option>
              {caseTemplates.map(template => (
                <option key={template.id} value={template.id}>{template.name}</option>
              ))}
            </select>
            <small style={{ color: 'var(--muted,#6b7280)' }}>
              {selectedTemplate?.description || 'Templates apply organization-approved defaults and control which fields are shown or required.'}
            </small>
          </label>
        )}
        {useLegalCaseNameAsPrimary ? (
          showField('legal_case_name') && <label>
            {fieldLabel('Matter Name', true)}
            <input
              className="input"
              name="case_name"
              value={form.legal_case_name || form.name}
              onChange={e => onLegalCaseNameChange(e.target.value)}
              required
            />
          </label>
        ) : (
          <>
            <label>
              {fieldLabel('eDiscovery Name', true)}
              <input
                className="input"
                name="name"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                readOnly={!editingId && caseNamingMode !== 'color'}
                required
              />
              {!editingId && caseNamingMode === 'created_date' && (
                <small style={{ color: 'var(--muted,#6b7280)' }}>Generated from the matter create date.</small>
              )}
            </label>

            {showField('legal_case_name') && <label>
              {fieldLabel(secondaryCaseNameLabel, fieldRequired('legal_case_name'))}
              <input className="input" value={form.legal_case_name} onChange={e => onLegalCaseNameChange(e.target.value)} required={fieldRequired('legal_case_name')} />
            </label>}
          </>
        )}

        <div className="case-editor-flags">
        {showField('is_private') && <label className="case-editor-flag">
          <input
            type="checkbox"
            checked={!!form.is_private}
            onChange={e => setForm(f => ({ ...f, is_private: e.target.checked }))}
            style={{ marginTop: 3 }}
          />
          <span>
            <strong>{fieldLabel('Make case private', fieldRequired('is_private'))}</strong>
            <small style={{ display: 'block', color: '#0f766e', marginTop: 3 }}>
              Only requestors on this matter, admins, and analysts can see it.
            </small>
          </span>
        </label>}
        {showField('is_test_case') && (
          <label className="case-editor-flag case-editor-flag--test">
            <input
              type="checkbox"
              checked={!!form.is_test_case}
              onChange={e => setForm(f => ({ ...f, is_test_case: e.target.checked }))}
            />
            <span>
              <strong>{fieldLabel('Test matter', fieldRequired('is_test_case'))}</strong>
              <small>
                Marks this matter as designated test data.
              </small>
            </span>
          </label>
        )}
        </div>

        <div className="form-grid case-editor-two-column">
          {showField('matter_number') && <label>
            {fieldLabel('Matter or Claim Number', fieldRequired('matter_number'))}
            <input
              className="input"
              value={form.matter_number}
              onChange={e => setForm(f => ({ ...f, matter_number: e.target.value }))}
              required={fieldRequired('matter_number')}
            />
          </label>}
          {showField('start_date') && <label>
            {fieldLabel('Start Date', fieldRequired('start_date'))}
            <input
              className="input"
              type="date"
              value={form.start_date || ''}
              onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))}
              required={fieldRequired('start_date')}
            />
          </label>}
          {showField('campus') && <label>
            {fieldLabel('Campus', fieldRequired('campus'))}
            <input
              className="input"
              value={form.campus || ''}
              onChange={e => setForm(f => ({ ...f, campus: e.target.value }))}
              required={fieldRequired('campus')}
            />
          </label>}
          {showField('matter_type') && <label>
            {fieldLabel('Matter Type', fieldRequired('matter_type'))}
            <select
              className="input"
              value={form.matter_type || ''}
              onChange={e => setForm(f => ({ ...f, matter_type: e.target.value, matter_type_other: e.target.value === 'Other' ? f.matter_type_other : '' }))}
              required={fieldRequired('matter_type')}
            >
              <option value="">-- Select matter type --</option>
              {matterTypes.map(option => <option key={option} value={option}>{option}</option>)}
              <option value="Other">Other</option>
            </select>
          </label>}
          {showField('matter_type') && form.matter_type === 'Other' && <label>
            {fieldLabel('Other Matter Type', fieldRequired('matter_type'))}
            <input
              className="input"
              value={form.matter_type_other || ''}
              onChange={e => setForm(f => ({ ...f, matter_type_other: e.target.value }))}
              required={fieldRequired('matter_type')}
            />
          </label>}
          {showField('internal_counsel') && <label>
            {fieldLabel(internalCounselLabel, fieldRequired('internal_counsel'))}
            <input
              className="input"
              value={form.internal_counsel}
              onChange={e => setForm(f => ({ ...f, internal_counsel: e.target.value }))}
              required={fieldRequired('internal_counsel')}
            />
          </label>}
          {showField('outside_counsel') && <label>
            {fieldLabel('Outside Counsel', fieldRequired('outside_counsel'))}
            <input
              className="input"
              value={form.outside_counsel}
              onChange={e => setForm(f => ({ ...f, outside_counsel: e.target.value }))}
              required={fieldRequired('outside_counsel')}
            />
          </label>}
        </div>

        {showField('claimant') && <label>
          {fieldLabel('Claimant', fieldRequired('claimant'))}
          <input className="input" value={form.claimant} onChange={e => setForm(f => ({ ...f, claimant: e.target.value }))} required={fieldRequired('claimant')} />
        </label>}

        {showField('requestor') && <label>
          {fieldLabel('Requestor Email', fieldRequired('requestor'))}
          <input
            className="input"
            type="email"
            inputMode="email"
            placeholder="requestor@example.com"
            list="requestor-options"
            value={form.requestor}
            onChange={e => setForm(f => ({ ...f, requestor: e.target.value }))}
            required={fieldRequired('requestor')}
          />
          <datalist id="requestor-options">
            {requestorOptions.map(r => <option key={r} value={r} />)}
          </datalist>
        </label>}

        {showField('requestors') && <label>
          {fieldLabel('Additional Requestors (comma separated)', fieldRequired('requestors'))}
          <input
            className="input"
            type="text"
            placeholder="secondary1@example.com, secondary2@example.com"
            value={form.additional_requestors}
            onChange={e => setForm(f => ({ ...f, additional_requestors: e.target.value }))}
            required={fieldRequired('requestors')}
          />
          <small style={{ color: 'var(--muted,#6b7280)' }}>
            First requestor listed above is the primary (notifications).<br />
            Others get case access as secondary.
          </small>
        </label>}

        {showField('analyst_id') && <label>
          {fieldLabel('Analyst', fieldRequired('analyst_id'))}
          <select className="input" value={form.analyst_id} onChange={e => setForm(f => ({ ...f, analyst_id: e.target.value }))} required={fieldRequired('analyst_id')}>
            <option value="">-- Select analyst --</option>
            {analysts.map(a => <option key={a.id} value={a.id}>{formatAnalystName(a)}</option>)}
          </select>
        </label>}
        {showField('description') && <label>
          {fieldLabel('Additional Notes / Comments', fieldRequired('description'))}
          <textarea
            className="input"
            rows={4}
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="Context that should be visible from the Active Matters dashboard."
            required={fieldRequired('description')}
          />
        </label>}

        {showField('closure_nag_days') && <label>
          {fieldLabel('Send matter status notification to requestor every (days)', fieldRequired('closure_nag_days'))}
          <input
            className="input"
            type="number"
            min={1}
            step={1}
            placeholder="180"
            value={form.closure_nag_days ?? ''}
            required={fieldRequired('closure_nag_days')}
            onChange={e => {
              const val = e.target.value
              const num = Number(val)
              setForm(f => ({ ...f, closure_nag_days: val === '' ? '' : num }))
            }}
          />
        </label>}
        <CaseCustomFieldsEditor
          customFields={form.custom_fields}
          onChange={custom_fields => setForm(current => ({ ...current, custom_fields }))}
        />
      </form>
    </Modal>
  )
}

export function CaseClosureModal({ target, readiness, busy, onClose, onConfirm, onOpenHold }) {
  if (!target) return null
  const activeHolds = readiness?.active_holds || []
  const preservationBlockers = readiness?.preservation_blockers || []
  const blocked = readiness && readiness.ready === false

  return (
    <Modal
      open
      title="Close Matter"
      onClose={busy ? undefined : onClose}
      width={blocked ? 620 : 500}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          {!blocked && (
            <button type="button" className="btn" onClick={onConfirm} disabled={busy}>
              {busy ? 'Closing' : 'Close Matter'}
            </button>
          )}
        </div>
      )}
    >
      {blocked ? (
        <div className="alert warning">
          <strong>This matter cannot be closed yet.</strong>
          <p>Close every active Hold and release every active preservation item first. This gate preserves an accurate record and prevents sources from being left on hold after the matter is inactive.</p>
          {activeHolds.length > 0 && (
            <>
              <h4>Active Holds</h4>
              <ul>{activeHolds.map(hold => (
                <li key={hold.hold_id}>
                  <button
                    type="button"
                    className="case-closure-hold-link"
                    onClick={() => onOpenHold?.(hold)}
                  >
                    {hold.hold_name}
                  </button>{' '}
                  ({hold.custodian_count} custodians)
                </li>
              ))}</ul>
            </>
          )}
          {preservationBlockers.length > 0 && (
            <>
              <h4>Preservation items to release</h4>
              <ul>
                {preservationBlockers.map((item, index) => (
                  <li key={`${item.hold_id || 'matter'}-${item.custodian_id}-${item.source_key}-${index}`}>
                    {item.hold_name ? `${item.hold_name}: ` : ''}{item.custodian_name} - {item.source_label} ({item.status})
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <p>Close <strong>{target.legal_case_name || target.name}</strong> and move it to Inactive Matters? Its full history will be retained.</p>
      )}
    </Modal>
  )
}

export function RequestorGroupInviteModal({
  inviteGroupModal,
  inviteGroup,
  inviteNewGroup,
  requestorGroupOptions,
  onClose,
  onConfirm,
  onInviteGroupChange,
  onInviteNewGroupChange,
  formatGroupLabel,
}) {
  if (!inviteGroupModal) return null
  return (
    <Modal
      open
      title="Choose requestor group"
      onClose={onClose}
      width={520}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn" onClick={onConfirm}>Send Invite</button>
        </div>
      )}
    >
      <p style={{ marginTop: 0, color: 'var(--muted,#6b7280)' }}>
        Select the DiscoveryOne group for <strong>{inviteGroupModal.email}</strong> before sending the invite.
      </p>
      <div style={{ display: 'grid', gap: 12 }}>
        <label>
          Existing group
          <select
            className="input"
            value={inviteGroup}
            onChange={e => onInviteGroupChange(e.target.value)}
          >
            <option value="">Select a group</option>
            {requestorGroupOptions.map(group => (
              <option key={group} value={group}>{formatGroupLabel(group)}</option>
            ))}
          </select>
        </label>
        <label>
          Or create a new group
          <input
            className="input"
            value={inviteNewGroup}
            onChange={e => onInviteNewGroupChange(e.target.value)}
            placeholder="Enter department/group"
          />
        </label>
      </div>
    </Modal>
  )
}
export function CaseDeleteModal({
  target,
  warning,
  overrideReason,
  setOverrideReason,
  busy,
  onClose,
  onConfirm,
}) {
  if (!target) return null
  const history = warning?.history || {}
  const requiresOverride = warning?.code === 'case_has_history'

  return (
    <Modal
      open
      title="Permanently Delete Case"
      onClose={busy ? undefined : onClose}
      width={520}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button
            type="button"
            className="btn danger"
            onClick={onConfirm}
            disabled={busy || (requiresOverride && overrideReason.trim().length < 10)}
          >
            {busy ? 'Deleting' : (requiresOverride ? 'Override and Delete' : 'Delete Permanently')}
          </button>
        </div>
      )}
    >
      <p style={{ marginTop: 0 }}>
        Delete <strong>{target.legal_case_name || target.name}</strong> permanently? Closing the matter is the normal way to retain its record.
      </p>
      {requiresOverride && (
        <div className="alert warning">
          <strong>This matter has recorded activity.</strong>
          <ul style={{ marginBottom: 10 }}>
            {Object.entries(history).filter(([, count]) => Number(count) > 0).map(([label, count]) => (
              <li key={label}>{label.replaceAll('_', ' ')}: {count}</li>
            ))}
          </ul>
          <label>
            Override reason
            <textarea
              className="input"
              rows={3}
              value={overrideReason}
              onChange={event => setOverrideReason(event.target.value)}
              placeholder="Explain why the permanent record must be deleted."
              autoFocus
            />
            <small>At least 10 characters are required and the reason is written to the audit log.</small>
          </label>
        </div>
      )}
    </Modal>
  )
}
