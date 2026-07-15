import Modal from '../components/Modal.jsx'

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
  onClose,
  onSubmit,
  onLegalCaseNameChange,
  formatAnalystName,
}) {
  if (!open) return null
  return (
    <Modal
      open={open}
      title={editingId ? 'Edit Case' : 'New Case'}
      onClose={onClose}
      width={560}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose}>Cancel</button>
          <button type="submit" form="case-modal-form" className="btn">{editingId ? 'Save' : 'Create'}</button>
        </div>
      )}
    >
      <form id="case-modal-form" onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {useLegalCaseNameAsPrimary ? (
          <label>
            Case Name
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
              eDiscovery Name
              <input
                className="input"
                name="name"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                readOnly={!editingId && caseNamingMode !== 'color'}
                required
              />
              {!editingId && caseNamingMode === 'created_date' && (
                <small style={{ color: 'var(--muted,#6b7280)' }}>Generated from the case create date.</small>
              )}
            </label>

            <label>
              {secondaryCaseNameLabel}
              <input className="input" value={form.legal_case_name} onChange={e => onLegalCaseNameChange(e.target.value)} />
            </label>
          </>
        )}

        <label
          style={{
            display: 'flex',
            gap: 10,
            alignItems: 'flex-start',
            padding: '12px 14px',
            border: '2px solid #0f766e',
            borderRadius: 12,
            background: '#f0fdfa',
          }}
        >
          <input
            type="checkbox"
            checked={!!form.is_private}
            onChange={e => setForm(f => ({ ...f, is_private: e.target.checked }))}
            style={{ marginTop: 3 }}
          />
          <span>
            <strong>Make case private</strong>
            <small style={{ display: 'block', color: '#0f766e', marginTop: 3 }}>
              Only requestors on this case, admins, and analysts can see it.
            </small>
          </span>
        </label>

        <label>
          Claimant (optional)
          <input className="input" value={form.claimant} onChange={e => setForm(f => ({ ...f, claimant: e.target.value }))} />
        </label>

        <label>
          Requestor Email (optional)
          <input
            className="input"
            type="email"
            inputMode="email"
            placeholder="requestor@example.com"
            list="requestor-options"
            value={form.requestor}
            onChange={e => setForm(f => ({ ...f, requestor: e.target.value }))}
          />
          <datalist id="requestor-options">
            {requestorOptions.map(r => <option key={r} value={r} />)}
          </datalist>
        </label>

        <label>
          Additional Requestors (comma separated)
          <input
            className="input"
            type="text"
            placeholder="secondary1@example.com, secondary2@example.com"
            value={form.additional_requestors}
            onChange={e => setForm(f => ({ ...f, additional_requestors: e.target.value }))}
          />
          <small style={{ color: 'var(--muted,#6b7280)' }}>
            First requestor listed above is the primary (notifications).<br />
            Others get case access as secondary.
          </small>
        </label>

        <label>
          Analyst
          <select className="input" value={form.analyst_id} onChange={e => setForm(f => ({ ...f, analyst_id: e.target.value }))}>
            <option value="">-- Select analyst --</option>
            {analysts.map(a => <option key={a.id} value={a.id}>{formatAnalystName(a)}</option>)}
          </select>
        </label>

        <label>
          When to send case closure reminders to requestor (days)
          <input
            className="input"
            type="number"
            min={1}
            step={1}
            placeholder="180"
            value={form.closure_nag_days ?? ''}
            onChange={e => {
              const val = e.target.value
              const num = Number(val)
              setForm(f => ({ ...f, closure_nag_days: val === '' ? '' : num }))
            }}
          />
        </label>
      </form>
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