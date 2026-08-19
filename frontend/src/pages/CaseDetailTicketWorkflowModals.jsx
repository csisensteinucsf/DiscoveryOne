import Modal from '../components/Modal.jsx'
import { Badge } from './caseDetailControls.jsx'
import { REQUEST_TICKET_CATEGORY_LOOKUP } from './ticketWorkflowCatalog.js'
import { workflowUsesAccessLogDetailsStatic, entryAccessLogTimeWindows } from './caseDetailUtils.js'

export default function CaseDetailTicketWorkflowModals({
  showBulkRequestModal,
  closeBulkModal,
  bulkCategory,
  bulkSearch,
  setBulkSearch,
  custodians,
  usedCustodianKeysByCategory = new Map(),
  bulkCustodianDisabledReason,
  setBulkSelection,
  bulkSelection,
  toggleBulkCustodian,
  submitBulkRequests,
  requestTicketCategoryLookup = REQUEST_TICKET_CATEGORY_LOOKUP,
  workflowUsesAccessLogDetails = workflowUsesAccessLogDetailsStatic,
  accessLogInfoEntry,
  setAccessLogInfoEntryId,
  employeeIdLabel,
  isRequestor,
  updateRequestEntry,
  addAccessLogTimeWindow,
  updateAccessLogTimeWindow,
  removeAccessLogTimeWindow,
  closeAccessLogInfoModal,
  requestsSaving,
  saveAccessLogInfoModal,
  removeCustodianModal,
  setRemoveCustodianModal,
  removeCustodian,
}) {
  return (
    <>
      {showBulkRequestModal && (
        <Modal
          open
          onClose={closeBulkModal}
          style={{ maxWidth: 620 }}
        >
          {(() => {
            const isAccessLogBulk = workflowUsesAccessLogDetails(bulkCategory)
            const availableCustodians = custodians || []
            const requestKey = bulkCategory
            return (
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            <h3 style={{ margin:0 }}>{isAccessLogBulk ? 'Select custodian' : 'Add custodians in bulk'}</h3>
            <p style={{ margin:0, color:'var(--muted,#475467)' }}>
              {isAccessLogBulk
                ? `Select one custodian to start the ${requestTicketCategoryLookup?.[bulkCategory]?.label || 'access log'} request. You will enter the Employee ID and date/time details in the next step.`
                : `Select custodians to add to ${requestTicketCategoryLookup?.[bulkCategory]?.label || 'this request'}. Custodians already added for this category are greyed out.`}
            </p>
            <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
              <input
                type="text"
                value={bulkSearch}
                onChange={(e) => setBulkSearch(e.target.value)}
                placeholder="Search custodians by name or email"
                style={{ flex:'1 1 220px', padding:'8px 10px', border:'1px solid var(--border,#e5e7eb)', borderRadius:8, fontSize:13, background:'var(--card,#fff)', color:'var(--text,#0f172a)' }}
              />
              {!isAccessLogBulk && (
                <button
                  className="btn secondary"
                  type="button"
                  onClick={() => {
                    const filtered = availableCustodians.filter(c => {
                      const q = (bulkSearch || '').trim().toLowerCase()
                      if (!q) return true
                      return (c.name || '').toLowerCase().includes(q) || (c.email || '').toLowerCase().includes(q)
                    })
                    const usedSet = usedCustodianKeysByCategory.get(requestKey) || new Set()
                    const selectable = filtered
                      .filter(c => {
                        return !bulkCustodianDisabledReason(bulkCategory, c, usedSet)
                      })
                      .map(c => Number(c.id))
                    setBulkSelection(new Set(selectable))
                  }}
                >
                  Select all available
                </button>
              )}
            </div>
            <div style={{ display:'grid', gap:6, gridTemplateColumns:'repeat(auto-fit, minmax(200px, 1fr))', maxHeight: 220, overflowY:'auto', paddingRight:4 }}>
              {availableCustodians.filter(c => {
                const q = (bulkSearch || '').trim().toLowerCase()
                if (!q) return true
                return (c.name || '').toLowerCase().includes(q) || (c.email || '').toLowerCase().includes(q)
              }).map(c => {
                const usedSet = usedCustodianKeysByCategory.get(requestKey) || new Set()
                const disabledReason = bulkCustodianDisabledReason(bulkCategory, c, usedSet)
                const disabled = !!disabledReason
                const checked = bulkSelection.has(Number(c.id))
                return (
                  <label key={`bulk-${c.id}`} style={{ display:'flex', alignItems:'center', gap:6, padding:6, border:'1px solid var(--border, #e5e7eb)', borderRadius:8, background: disabled ? 'var(--table-header-bg,#f8fafc)' : 'var(--card,#fff)', opacity: disabled ? 0.55 : 1 }}>
                    <input
                      type={isAccessLogBulk ? 'radio' : 'checkbox'}
                      name={isAccessLogBulk ? 'access-log-custodian-select' : undefined}
                      disabled={disabled}
                      checked={checked}
                      onChange={() => toggleBulkCustodian(Number(c.id))}
                    />
                    <div style={{ display:'flex', flexDirection:'column', gap:2 }}>
                      <Badge variant="orange" compact>{c.email || 'No email'}</Badge>
                      <span style={{ fontSize:11, color:'var(--muted,#475467)' }}>{c.name || 'Unnamed custodian'}</span>
                      {disabled && <span style={{ fontSize:10, color:'var(--muted,#9ca3af)' }}>{disabledReason}</span>}
                    </div>
                  </label>
                )
              })}
              {!availableCustodians.length && (
                <p style={{ gridColumn:'1 / -1', color:'#9ca3af', fontSize:13 }}>No custodians are assigned to this case.</p>
              )}
            </div>
            <div className="row" style={{ justifyContent:'flex-end', gap:8 }}>
              <button className="btn ghost" type="button" onClick={closeBulkModal}>Cancel</button>
              <button className="btn primary" type="button" onClick={submitBulkRequests} disabled={!bulkSelection.size}>{isAccessLogBulk ? 'Continue' : 'Add selected'}</button>
            </div>
          </div>
            )
          })()}
        </Modal>
      )}
      {accessLogInfoEntry && (
        <Modal
          open
          onClose={() => setAccessLogInfoEntryId(null)}
          style={{ maxWidth: 720 }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <h3 style={{ margin: 0 }}>Access log details</h3>
            <p style={{ margin: 0, color: 'var(--muted,#475467)' }}>
              Review and update the requested audit windows and notes for this ticket.
            </p>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12, color: '#475467' }}>{employeeIdLabel}</span>
              <input
                type="text"
                value={accessLogInfoEntry.access_log_employee_id || ''}
                onChange={(e) => { if (isRequestor) return; updateRequestEntry(accessLogInfoEntry.id, { access_log_employee_id: e.target.value }) }}
                readOnly={isRequestor}
                disabled={isRequestor}
                placeholder="Auto-filled when available"
                style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13, color: '#111827' }}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>
                Pulled from the selected custodian when available, or enter it manually.
              </span>
            </label>
            <div style={{ display: 'grid', gap: 8 }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 12, color: '#475467', fontWeight: 600 }}>Requested dates and times</span>
                {!isRequestor && (
                  <button
                    type="button"
                    className="btn secondary"
                    onClick={() => addAccessLogTimeWindow(accessLogInfoEntry.id)}
                    style={{ padding: '4px 10px', fontSize: 12, borderRadius: 999 }}
                  >
                    + Add date/time
                  </button>
                )}
              </div>
              {entryAccessLogTimeWindows(accessLogInfoEntry).map(window => (
                <div key={window.id} style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr auto', gap: 8, alignItems: 'end' }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span style={{ fontSize: 12, color: '#475467' }}>Date</span>
                    <input
                      type="date"
                      value={window.date || ''}
                      onChange={(e) => { if (isRequestor) return; updateAccessLogTimeWindow(accessLogInfoEntry.id, window.id, { date: e.target.value }) }}
                      readOnly={isRequestor}
                      disabled={isRequestor}
                      style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13, color: '#111827' }}
                    />
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span style={{ fontSize: 12, color: '#475467' }}>Start</span>
                    <input
                      type="time"
                      value={window.start_time || ''}
                      onChange={(e) => { if (isRequestor) return; updateAccessLogTimeWindow(accessLogInfoEntry.id, window.id, { start_time: e.target.value }) }}
                      readOnly={isRequestor}
                      disabled={isRequestor}
                      style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13, color: '#111827' }}
                    />
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span style={{ fontSize: 12, color: '#475467' }}>End</span>
                    <input
                      type="time"
                      value={window.end_time || ''}
                      onChange={(e) => { if (isRequestor) return; updateAccessLogTimeWindow(accessLogInfoEntry.id, window.id, { end_time: e.target.value }) }}
                      readOnly={isRequestor}
                      disabled={isRequestor}
                      style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13, color: '#111827' }}
                    />
                  </label>
                  {!isRequestor && (
                    <button
                      type="button"
                      className="btn ghost"
                      onClick={() => removeAccessLogTimeWindow(accessLogInfoEntry.id, window.id)}
                      style={{ padding: '4px 8px', borderRadius: 8, fontSize: 12, height: 'fit-content' }}
                    >
                      Remove row
                    </button>
                  )}
                </div>
              ))}
            </div>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12, color: '#475467' }}>Request notes</span>
              <textarea
                value={accessLogInfoEntry.access_log_request_notes || ''}
                onChange={(e) => { if (isRequestor) return; updateRequestEntry(accessLogInfoEntry.id, { access_log_request_notes: e.target.value }) }}
                readOnly={isRequestor}
                disabled={isRequestor}
                rows={3}
                placeholder="Add dates, times, or specific request context"
                style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13, color: '#111827', resize: 'vertical' }}
              />
              <span style={{ fontSize: 12, color: '#6b7280' }}>
                Add one row per requested audit window. These rows will be listed in the external ticket description when the workflow uses a ticket provider.
              </span>
            </label>
            <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
              <button className="btn ghost" type="button" onClick={closeAccessLogInfoModal} disabled={requestsSaving}>Close</button>
              {!isRequestor && (
                <button className="btn" type="button" onClick={saveAccessLogInfoModal} disabled={requestsSaving}>
                  {requestsSaving ? 'Saving...' : 'Save'}
                </button>
              )}
            </div>
          </div>
        </Modal>
      )}
      {removeCustodianModal.open && (
        <Modal
          open
          title="Remove custodian"
          onClose={() => setRemoveCustodianModal({ open: false, custodian: null, releaseHolds: true, releaseNtp: true, closeSearches: true, note: '', busy: false })}
        >
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            <p style={{ margin:0, color:'#475467' }}>
              Are you sure you want to delete {removeCustodianModal.custodian?.name || removeCustodianModal.custodian?.email || 'this custodian'} from the case? This will release any Email or OneDrive preservation currently in place.
            </p>
            <label style={{ display:'flex', alignItems:'center', gap:8 }}>
              <input
                type="checkbox"
                checked={removeCustodianModal.releaseHolds}
                onChange={e => setRemoveCustodianModal(m => ({ ...m, releaseHolds: e.target.checked }))}
                disabled={removeCustodianModal.busy}
              />
              <span>Release preservation and NTPs</span>
            </label>
            <label style={{ display:'flex', alignItems:'center', gap:8 }}>
              <input
                type="checkbox"
                checked={removeCustodianModal.closeSearches}
                onChange={e => setRemoveCustodianModal(m => ({ ...m, closeSearches: e.target.checked }))}
                disabled={removeCustodianModal.busy}
              />
              <span>Remove custodian from searches</span>
            </label>
            <label style={{ display:'flex', alignItems:'center', gap:8 }}>
              <input
                type="checkbox"
                checked={removeCustodianModal.releaseNtp}
                onChange={e => setRemoveCustodianModal(m => ({ ...m, releaseNtp: e.target.checked }))}
                disabled={removeCustodianModal.busy}
              />
              <span>Document NTP release (logged)</span>
            </label>
            <label>
              <div style={{ fontSize: 13, color: '#334155', marginBottom: 6 }}>Approval note</div>
              <textarea
                rows={3}
                value={removeCustodianModal.note}
                onChange={e => setRemoveCustodianModal(m => ({ ...m, note: e.target.value }))}
                disabled={removeCustodianModal.busy}
                style={{ width:'100%', border:'1px solid var(--border, #e5e7eb)', borderRadius:10, padding:10, background:'var(--card, #fff)', color:'var(--text, #0f172a)' }}
                placeholder="Add approver, ticket, or rationale"
              />
            </label>
            <div className="row" style={{ justifyContent:'flex-end', gap:8 }}>
              <button className="btn ghost" type="button" disabled={removeCustodianModal.busy} onClick={() => setRemoveCustodianModal({ open: false, custodian: null, releaseHolds: true, releaseNtp: true, closeSearches: true, note: '', busy: false })}>Cancel</button>
              <button className="btn danger" type="button" disabled={removeCustodianModal.busy} onClick={removeCustodian}>
                {removeCustodianModal.busy ? 'Removing...' : 'Remove custodian'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  )
}
