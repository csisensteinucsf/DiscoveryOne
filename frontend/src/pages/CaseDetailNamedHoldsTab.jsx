import { useMemo, useState } from 'react'
import { Pencil, Plus, RefreshCw, Search, UsersRound } from 'lucide-react'
import Modal from '../components/Modal.jsx'
import CaseDetailHoldsTab from './CaseDetailHoldsTab.jsx'
import { useCaseDetailNamedHolds } from './useCaseDetailNamedHolds.js'
import {
  CONSENT_STATUS_OPTIONS,
  NTP_STATUS_OPTIONS,
  consentStatusLabel,
  normalizeConsentStatus,
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
  const consent = aggregateWorkflowState(hold.consent_counts, ['received', 'implied', 'awoc', 'na'])
  const search = aggregateWorkflowState(hold.search_counts?.search, ['performed', 'complete', 'completed'])
  const exportState = aggregateWorkflowState(hold.search_counts?.export, ['performed', 'complete', 'completed'])
  const delivery = aggregateWorkflowState(hold.search_counts?.delivery, ['performed', 'complete', 'completed'])
  const labels = [
    ['Hold', hold.status || 'active'],
    ['NTP', ntp],
    ['Consent', consent],
    ['Search', search],
    ['Export', exportState],
    ['Delivery', delivery],
  ]
  return (
    <div className="named-hold-workflow-summary" aria-label={'Workflow status for ' + hold.name}>
      {labels.map(([label, status]) => (
        <StatusBadge key={label} status={status}>{label}: {status === 'active' ? 'complete' : status.replaceAll('_', ' ')}</StatusBadge>
      ))}
    </div>
  )
}

function HoldSearchDetails({ searches = [] }) {
  if (!searches.length) return <p className="muted">No searches are assigned to this hold.</p>
  return (
    <div className="table-scroll named-hold-related-table">
      <table className="table">
        <thead>
          <tr><th>Search</th><th>Search</th><th>Export</th><th>Delivery</th></tr>
        </thead>
        <tbody>
          {searches.map(search => (
            <tr key={search.membership_id || search.search_id}>
              <td><strong>{search.name || 'Unnamed search'}</strong></td>
              <td><StatusBadge status={aggregateWorkflowState({ [search.status_search]: 1 }, ['performed', 'complete', 'completed'])}>{search.status_search}</StatusBadge></td>
              <td><StatusBadge status={aggregateWorkflowState({ [search.status_export]: 1 }, ['performed', 'complete', 'completed'])}>{search.status_export}</StatusBadge></td>
              <td><StatusBadge status={aggregateWorkflowState({ [search.status_delivery]: 1 }, ['performed', 'complete', 'completed'])}>{search.status_delivery}</StatusBadge></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function HoldTicketDetails({ hold, entries = [] }) {
  const memberIds = new Set((hold.custodians || []).map(member => Number(member.custodian_id)))
  const related = (entries || []).filter(entry => {
    const entryHoldId = Number(entry?.case_hold_id || entry?.hold_id)
    if (Number.isFinite(entryHoldId) && entryHoldId > 0) return entryHoldId === Number(hold.id)
    return memberIds.has(Number(entry?.custodian_id))
  })
  if (!related.length) return <p className="muted">No ticket activity is linked to this hold.</p>
  return (
    <div className="table-scroll named-hold-related-table">
      <table className="table">
        <thead>
          <tr><th>Ticket</th><th>Category</th><th>Custodian</th><th>Status</th></tr>
        </thead>
        <tbody>
          {related.map(entry => (
            <tr key={entry.id || entry.ticket || entry.sys_id}>
              <td>{entry.ticket || entry.number || entry.sys_id || '-'}</td>
              <td>{entry.category || '-'}</td>
              <td>{entry.custodian_name || entry.custodian_email || '-'}</td>
              <td>{entry.ticket_status || entry.status || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
  searches,
  isReadOnly,
  showToast,
  requestEntries,
  legacyProps,
}) {
  const holds = useCaseDetailNamedHolds({ apiBase, caseId, showToast })
  const [createOpen, setCreateOpen] = useState(false)
  const [editHold, setEditHold] = useState(null)
  const [memberHold, setMemberHold] = useState(null)
  const [searchHold, setSearchHold] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [selectedCustodians, setSelectedCustodians] = useState([])
  const [selectedSearches, setSelectedSearches] = useState([])

  const custodianById = useMemo(
    () => new Map((custodians || []).map(custodian => [Number(custodian.id), custodian])),
    [custodians],
  )

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

  const openSearches = hold => {
    setSelectedSearches((hold.search_ids || []).map(Number))
    setSearchHold(hold)
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

  const saveSearches = async () => {
    const success = await holds.setNamedHoldSearches(searchHold.id, selectedSearches)
    if (success) setSearchHold(null)
  }

  const updateNtpStatus = async (hold, member, value) => {
    const status = normalizeNtpStatus(value)
    const payload = { ntp_status: status, ntp_not_required_reason: null }
    if (status === 'silent') {
      const reason = window.prompt('Why should this custodian be Silent for NTP?', member.ntp_not_required_reason || '')
      if (reason === null) return
      if (!reason.trim()) {
        showToast('A reason is required for Silent NTP status.', { variant: 'warn' })
        return
      }
      payload.ntp_not_required_reason = reason.trim()
    }
    await holds.updateNamedHoldWorkflow(hold.id, member.custodian_id, payload)
  }

  const updateConsentStatus = async (hold, member, value) => {
    const status = normalizeConsentStatus(value)
    if (status === 'awoc') {
      showToast('AWOC status is set only by uploading an AWOC consent document.', { variant: 'warn' })
      return
    }
    const payload = { consent_status: status, consent_not_required_reason: null }
    if (status === 'implied') {
      const reason = window.prompt('Why is consent Implied for this custodian?', member.consent_not_required_reason || '')
      if (reason === null) return
      if (!reason.trim()) {
        showToast('A reason is required for Implied consent.', { variant: 'warn' })
        return
      }
      payload.consent_not_required_reason = reason.trim()
    }
    await holds.updateNamedHoldWorkflow(hold.id, member.custodian_id, payload)
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

      <div className="named-holds-list">
        {holds.namedHolds.map(hold => (
          <section className="named-hold-section" key={hold.id}>
            <div className="named-hold-section__header">
              <div>
                <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                  <h4>{hold.name}</h4>
                  <StatusBadge status={hold.status}>{hold.status}</StatusBadge>
                  <span className="muted">{hold.custodian_count} custodians</span>
                  <span className="muted">{hold.search_count} searches</span>
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
                  <button type="button" className="icon-button" title="Assign searches" aria-label={'Assign searches to ' + hold.name} onClick={() => openSearches(hold)}>
                    <Search size={17} aria-hidden="true" />
                  </button>
                </div>
              )}
            </div>

            <HoldWorkflowSummary hold={hold} />

            <details className="named-hold-workspace-details" open>
              <summary>Hold workspace details</summary>
              <h5>Preservation</h5>
              <SourceTotals totals={hold.source_totals} />
              <h5>Searches</h5>
              <HoldSearchDetails searches={hold.searches} />
              <h5>Tickets</h5>
              <HoldTicketDetails hold={hold} entries={requestEntries} />
              <h5>Custodians</h5>
              <div className="table-scroll named-hold-members">
              <table className="table">
                <thead>
                  <tr>
                    <th>Custodian</th>
                    <th>NTP</th>
                    <th>Consent</th>
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
                        {isReadOnly ? consentStatusLabel(member.consent_status) : (
                          <select
                            value={normalizeConsentStatus(member.consent_status)}
                            onChange={event => updateConsentStatus(hold, member, event.target.value)}
                            disabled={holds.namedHoldBusy || normalizeConsentStatus(member.consent_status) === 'awoc'}
                            title={normalizeConsentStatus(member.consent_status) === 'awoc' ? 'AWOC is managed by the uploaded AWOC consent document.' : undefined}
                          >
                            {CONSENT_STATUS_OPTIONS.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
                            {normalizeConsentStatus(member.consent_status) === 'awoc' ? <option value="awoc">AWOC (document uploaded)</option> : null}
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
                    <tr><td colSpan={4}>No custodians are assigned to this hold.</td></tr>
                  )}
                </tbody>
              </table>
              </div>
            </details>
          </section>
        ))}
      </div>

      <details className="legacy-hold-details">
        <summary>Legacy preservation timeline and provider events</summary>
        <CaseDetailHoldsTab {...legacyProps} />
      </details>

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

      <Modal
        open={!!searchHold}
        title={searchHold ? 'Searches for ' + searchHold.name : 'Assign Searches'}
        onClose={() => setSearchHold(null)}
        width={620}
        footer={(
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn secondary" onClick={() => setSearchHold(null)}>Cancel</button>
            <button type="button" className="btn" onClick={saveSearches} disabled={holds.namedHoldBusy}>Save Assignments</button>
          </div>
        )}
      >
        <div className="named-hold-checkbox-list">
          {(searches || []).map(searchItem => (
            <label key={searchItem.id}>
              <input
                type="checkbox"
                checked={selectedSearches.includes(Number(searchItem.id))}
                onChange={event => setSelectedSearches(current => (
                  event.target.checked
                    ? [...new Set([...current, Number(searchItem.id)])]
                    : current.filter(id => id !== Number(searchItem.id))
                ))}
              />
              <span>
                <strong>{searchItem.name || 'Unnamed search'}</strong>
                <small>{searchItem.status_search || 'not performed'}</small>
              </span>
            </label>
          ))}
        </div>
      </Modal>
    </section>
  )
}
