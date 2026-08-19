import { useEffect, useMemo, useState } from 'react'
import { Pencil, Plus, RefreshCw, UsersRound } from 'lucide-react'
import Modal from '../components/Modal.jsx'
import CaseDetailHoldSelector from './CaseDetailHoldSelector.jsx'
import CaseDetailStatusReasonModal from './CaseDetailStatusReasonModal.jsx'
import { useCaseDetailNamedHolds } from './useCaseDetailNamedHolds.js'
import {
  NTP_STATUS_OPTIONS,
  normalizeNtpStatus,
  ntpStatusLabel,
} from './custodianStatusCatalog.js'

const emptyForm = () => ({
  name: '',
  description: '',
  status: 'active',
  ntp_template_name: '',
  preservation_template_name: '',
})

const SOURCE_STATUS_OPTIONS = [
  { value: 'not_started', label: 'Not started' },
  { value: 'pending', label: 'Pending' },
  { value: 'active', label: 'Active' },
  { value: 'failed', label: 'Failed' },
  { value: 'released', label: 'Released' },
]

function StatusBadge({ status, children }) {
  const normalized = String(status || 'not_started').toLowerCase()
  return <span className={'hold-status-badge is-' + normalized.replaceAll('_', '-')}>{children || normalized.replaceAll('_', ' ')}</span>
}

function aggregateWorkflowState(counts = {}, completeStatuses = []) {
  const entries = Object.entries(counts || {})
  const total = entries.reduce((sum, [, count]) => sum + Number(count || 0), 0)
  if (!total) return 'not_started'
  const failed = entries.some(([status, count]) => Number(count || 0) > 0 && /fail|error/i.test(status))
  if (failed) return 'failed'
  const complete = entries.reduce(
    (sum, [status, count]) => sum + (completeStatuses.includes(String(status).toLowerCase()) ? Number(count || 0) : 0),
    0,
  )
  if (complete === total) return 'active'
  const started = entries.some(([status, count]) => (
    Number(count || 0) > 0 && !['not sent', 'not performed', 'not_started'].includes(String(status).toLowerCase())
  ))
  return started || complete ? 'pending' : 'not_started'
}

function HoldWorkflowSummary({ hold }) {
  const ntp = aggregateWorkflowState(hold.ntp_counts, ['acknowledged', 'silent', 'na'])
  return (
    <div className="named-hold-workflow-summary" aria-label={'NTP status for ' + hold.name}>
      <StatusBadge status={ntp}>NTP: {ntp === 'active' ? 'complete' : ntp.replaceAll('_', ' ')}</StatusBadge>
    </div>
  )
}

function SourceTotals({ totals = [] }) {
  if (!totals.length) return <span className="muted">No preservation sources</span>
  return (
    <div className="named-hold-source-totals">
      {totals.map(source => {
        const pending = Number(source.pending || 0)
        const active = Number(source.active || 0)
        const failed = Number(source.failed || 0)
        const released = Number(source.released || 0)
        const status = failed ? 'failed' : pending ? 'pending' : active ? 'active' : released ? 'released' : 'not_started'
        const count = failed || pending || active || released || 0
        return <StatusBadge key={source.source_key} status={status}>{source.source_label}: {count}</StatusBadge>
      })}
    </div>
  )
}

export default function CaseDetailNamedHoldsTab({
  apiBase,
  caseId,
  custodians,
  isReadOnly,
  showToast,
  initialHoldId = null,
  onHoldDataChanged,
}) {
  const holds = useCaseDetailNamedHolds({ apiBase, caseId, showToast, onMutationComplete: onHoldDataChanged })
  const [createOpen, setCreateOpen] = useState(false)
  const [editHold, setEditHold] = useState(null)
  const [memberHold, setMemberHold] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [selectedCustodians, setSelectedCustodians] = useState([])
  const [statusReasonRequest, setStatusReasonRequest] = useState(null)
  const [selectedHoldId, setSelectedHoldId] = useState(null)

  useEffect(() => {
    if (initialHoldId) setSelectedHoldId(initialHoldId)
  }, [initialHoldId])

  const custodianById = useMemo(
    () => new Map((custodians || []).map(custodian => [Number(custodian.id), custodian])),
    [custodians],
  )
  const selectedHold = useMemo(
    () => holds.namedHolds.find(hold => String(hold.id) === String(selectedHoldId))
      || holds.namedHolds[0]
      || null,
    [holds.namedHolds, selectedHoldId],
  )
  const visibleNamedHolds = selectedHold ? [selectedHold] : []

  const openCreate = () => {
    setForm(emptyForm())
    setCreateOpen(true)
  }

  const openEdit = hold => {
    setForm({
      name: hold.name || '',
      description: hold.description || '',
      status: hold.status || 'active',
      ntp_template_name: hold.ntp_template_name || '',
      preservation_template_name: hold.preservation_template_name || '',
    })
    setEditHold(hold)
  }

  const openMembers = hold => {
    setSelectedCustodians((hold.custodians || []).map(member => Number(member.custodian_id)))
    setMemberHold(hold)
  }

  const submitCreate = async event => {
    event.preventDefault()
    const success = await holds.createNamedHold({
      name: form.name.trim() || null,
      description: form.description.trim() || null,
      ntp_template_name: form.ntp_template_name.trim() || null,
      preservation_template_name: form.preservation_template_name.trim() || null,
    })
    if (success) setCreateOpen(false)
  }

  const submitEdit = async event => {
    event.preventDefault()
    const success = await holds.updateNamedHold(editHold.id, {
      name: form.name,
      description: form.description || null,
      status: form.status,
      ntp_template_name: form.ntp_template_name || null,
      preservation_template_name: form.preservation_template_name || null,
    })
    if (success) setEditHold(null)
  }

  const saveMembers = async () => {
    const current = new Set((memberHold.custodians || []).map(member => Number(member.custodian_id)))
    const desired = new Set(selectedCustodians.map(Number))
    const additions = [...desired].filter(id => !current.has(id))
    const removals = [...current].filter(id => !desired.has(id))

    let success = true
    if (additions.length) success = await holds.addNamedHoldCustodians(memberHold.id, additions)
    for (const custodianId of removals) {
      if (!success) break
      success = await holds.removeNamedHoldCustodian(memberHold.id, custodianId)
    }
    if (success) setMemberHold(null)
  }

  const updateNtpStatus = async (hold, member, value) => {
    const status = normalizeNtpStatus(value)
    const payload = { ntp_status: status, ntp_not_required_reason: null }
    if (status === 'silent') {
      setStatusReasonRequest({
        kind: 'ntp',
        hold,
        member,
        status,
        title: 'Silent NTP reason',
        question: 'Why should this custodian be Silent for NTP?',
        initialReason: member.ntp_not_required_reason || '',
      })
      return
    }
    await holds.updateNamedHoldWorkflow(hold.id, member.custodian_id, payload)
  }

  const submitStatusReason = async reason => {
    const request = statusReasonRequest
    if (!request || holds.namedHoldBusy) return
    const success = await holds.updateNamedHoldWorkflow(
      request.hold.id,
      request.member.custodian_id,
      { ntp_status: request.status, ntp_not_required_reason: reason },
    )
    if (success) setStatusReasonRequest(null)
  }

  const closeStatusReasonDialog = () => {
    if (!holds.namedHoldBusy) setStatusReasonRequest(null)
  }

  return (
    <section className="card named-holds-shell">
      <div className="named-holds-heading">
        <div>
          <h3>Holds</h3>
          <p>
            {holds.namedHoldTotals.active || 0} active of {holds.namedHoldTotals.holds || 0} total holds.
            Custodians may belong to more than one hold.
          </p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <button
            type="button"
            className="icon-button"
            title="Refresh holds"
            aria-label="Refresh holds"
            onClick={holds.loadNamedHolds}
            disabled={holds.namedHoldsLoading}
          >
            <RefreshCw size={18} aria-hidden="true" />
          </button>
          {!isReadOnly && (
            <button type="button" className="btn" onClick={openCreate}>
              <Plus size={16} aria-hidden="true" /> New Hold
            </button>
          )}
        </div>
      </div>

      {holds.namedHoldsError && <div className="alert error">{holds.namedHoldsError}</div>}
      {holds.namedHoldsLoading && !holds.namedHolds.length && <p>Loading holds...</p>}

      <CaseDetailHoldSelector
        holds={holds.namedHolds}
        selectedHoldId={selectedHold?.id}
        onSelect={setSelectedHoldId}
        ariaLabel="Select Hold workspace"
      />

      <div className="named-holds-list">
        {visibleNamedHolds.map(hold => (
          <section className="named-hold-section" key={hold.id}>
            <div className="named-hold-section__header">
              <div>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  <h4>{hold.name}</h4>
                  <StatusBadge status={hold.status}>{hold.status}</StatusBadge>
                  <span className="muted">{hold.custodian_count} custodians</span>
                </div>
                {hold.description && <p>{hold.description}</p>}
                {(hold.ntp_template_name || hold.preservation_template_name) && (
                  <p className="named-hold-template-line">
                    NTP template: {hold.ntp_template_name || 'Not selected'} | Preservation template: {hold.preservation_template_name || 'Not selected'}
                  </p>
                )}
              </div>
              {!isReadOnly && (
                <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                  <button type="button" className="icon-button" title="Edit hold" aria-label={'Edit ' + hold.name} onClick={() => openEdit(hold)}>
                    <Pencil size={17} aria-hidden="true" />
                  </button>
                  <button type="button" className="icon-button" title="Assign custodians" aria-label={'Assign custodians to ' + hold.name} onClick={() => openMembers(hold)}>
                    <UsersRound size={17} aria-hidden="true" />
                  </button>
                </div>
              )}
            </div>

            <HoldWorkflowSummary hold={hold} />

            <details className="named-hold-workspace-details" open>
              <summary>Hold workspace details</summary>
              <h5>Preservation</h5>
              <SourceTotals totals={hold.source_totals} />
              <h5>Custodians</h5>
              <div className="table-scroll named-hold-members">
              <table className="table">
                <thead>
                  <tr>
                    <th>Custodian</th>
                    <th>NTP</th>
                    <th>Preservation Sources</th>
                  </tr>
                </thead>
                <tbody>
                  {(hold.custodians || []).map(member => (
                    <tr key={member.membership_id}>
                      <td>
                        <strong>{member.name || member.email || 'Unnamed custodian'}</strong>
                        <div className="muted">{member.email || '-'}</div>
                      </td>
                      <td>
                        {isReadOnly ? ntpStatusLabel(member.ntp_status) : (
                          <select
                            value={normalizeNtpStatus(member.ntp_status)}
                            onChange={event => updateNtpStatus(hold, member, event.target.value)}
                            disabled={holds.namedHoldBusy}
                          >
                            {NTP_STATUS_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                          </select>
                        )}
                      </td>
                      <td>
                        <div className="named-hold-source-controls">
                          {(member.preservation_sources || []).map(source => (
                            <label key={source.source_key}>
                              <span>{source.source_label}</span>
                              {isReadOnly ? (
                                <StatusBadge status={source.status}>{source.status.replaceAll('_', ' ')}</StatusBadge>
                              ) : (
                                <select
                                  value={source.status}
                                  onChange={event => holds.updateNamedHoldPreservation(
                                    hold.id,
                                    member.custodian_id,
                                    source.source_key,
                                    event.target.value,
                                  )}
                                  disabled={holds.namedHoldBusy}
                                  className={'preservation-status-select is-' + source.status.replaceAll('_', '-')}
                                >
                                  {SOURCE_STATUS_OPTIONS.map(option => (
                                    <option key={option.value} value={option.value}>{option.label}</option>
                                  ))}
                                </select>
                              )}
                            </label>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {!hold.custodians?.length && (
                    <tr><td colSpan={3}>No custodians are assigned to this hold.</td></tr>
                  )}
                </tbody>
              </table>
              </div>
            </details>
          </section>
        ))}
      </div>

      <Modal
        open={createOpen || !!editHold}
        title={editHold ? 'Edit Hold' : 'New Hold'}
        onClose={() => { setCreateOpen(false); setEditHold(null) }}
        width={540}
        footer={(
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn secondary" onClick={() => { setCreateOpen(false); setEditHold(null) }}>Cancel</button>
            <button type="submit" form="named-hold-form" className="btn" disabled={holds.namedHoldBusy}>Save</button>
          </div>
        )}
      >
        <form id="named-hold-form" onSubmit={editHold ? submitEdit : submitCreate} className="named-hold-form">
          <label>
            Hold Name
            <input className="input" value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} placeholder="Leave blank for Hold A, Hold B, and so on" />
          </label>
          <label>
            Purpose / Description
            <textarea className="input" rows={3} value={form.description} onChange={event => setForm(current => ({ ...current, description: event.target.value }))} />
          </label>
          {editHold && (
            <label>
              Status
              <select className="input" value={form.status} onChange={event => setForm(current => ({ ...current, status: event.target.value }))}>
                <option value="active">Active</option>
                <option value="released">Released</option>
                <option value="closed">Closed</option>
              </select>
            </label>
          )}
          <label>
            NTP Template Name
            <input className="input" value={form.ntp_template_name} onChange={event => setForm(current => ({ ...current, ntp_template_name: event.target.value }))} />
          </label>
          <label>
            Preservation Template Name
            <input className="input" value={form.preservation_template_name} onChange={event => setForm(current => ({ ...current, preservation_template_name: event.target.value }))} />
          </label>
        </form>
      </Modal>

      <CaseDetailStatusReasonModal
        request={statusReasonRequest}
        onClose={closeStatusReasonDialog}
        onSubmit={submitStatusReason}
        busy={holds.namedHoldBusy}
      />

      <Modal
        open={!!memberHold}
        title={memberHold ? 'Custodians for ' + memberHold.name : 'Assign Custodians'}
        onClose={() => setMemberHold(null)}
        width={620}
        footer={(
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn secondary" onClick={() => setMemberHold(null)}>Cancel</button>
            <button type="button" className="btn" onClick={saveMembers} disabled={holds.namedHoldBusy}>Save Assignments</button>
          </div>
        )}
      >
        <div className="named-hold-checkbox-list">
          {(custodians || []).map(custodian => (
            <label key={custodian.id}>
              <input
                type="checkbox"
                checked={selectedCustodians.includes(Number(custodian.id))}
                onChange={event => setSelectedCustodians(current => (
                  event.target.checked
                    ? [...new Set([...current, Number(custodian.id)])]
                    : current.filter(id => id !== Number(custodian.id))
                ))}
              />
              <span>
                <strong>{custodian.name || custodian.email || 'Unnamed custodian'}</strong>
                <small>{custodian.email || custodianById.get(Number(custodian.id))?.email || ''}</small>
              </span>
            </label>
          ))}
        </div>
      </Modal>

    </section>
  )
}
