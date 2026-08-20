import { Badge } from './caseDetailControls.jsx'
import { primaryCustodian, workflowUsesAccessLogDetailsStatic } from './caseDetailUtils.js'
import { ticketProviderLabel } from './ticketWorkflowCatalog.js'

export default function CaseDetailTicketsTab({
  isRequestor,
  isTech,
  isReadOnly,
  custodianOptions,
  namedHolds = [],
  visibleTicketCategories,
  requestEntries,
  openBulkRequestModal,
  entryHasUnmatchedSnowCustodian,
  matchedEmailWorkflowWarning,
  handleRequestEntryCustodianChange,
  updateRequestEntry,
  formatDateTime,
  externalTicketBusy,
  externalTicketStatuses,
  externalTicketEmailBusy,
  externalTicketEmailSent,
  sendCustodianDetailsToAssignee,
  copyEntryCustodians,
  setAccessLogInfoEntryId,
  workflowUsesAccessLogDetails = workflowUsesAccessLogDetailsStatic,
  createExternalTicket,
  removeRequestEntry,
  requestsSaving,
  requestsDirty,
}) {
  return (
<section className="card" style={{ padding: 16, pointerEvents: isRequestor ? "none" : "auto", opacity: isRequestor ? 0.95 : 1 }}>
              <h3 style={{ marginTop: 0, marginBottom: 4 }}>Tickets</h3>
              <p style={{ color: '#475467', fontSize: 14, marginTop: 0 }}>
                Track configured ticket and handoff work, including manual tasks and external ticket-provider workflows.
              </p>
              <datalist id="custodian-request-options">
                {custodianOptions.map(opt => (
                  <option key={`custodian-option-${opt.id}`} value={opt.label} />
                ))}
              </datalist>
              {isTech && visibleTicketCategories.length === 0 && (
                <p style={{ color: '#b45309', fontSize: 13, marginTop: 8 }}>
                  This tech account needs a configured ticket workflow group to see ticket categories.
                </p>
              )}
              {!custodianOptions.length && (
                <p style={{ color: '#9ca3af', fontSize: 12, marginTop: 8 }}>
                  Add custodians to the matter to enable lookup suggestions in the search box.
                </p>
              )}
              <div style={{ display: 'grid', gap: 16, gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', marginTop: 16 }}>
                {visibleTicketCategories.map(category => {
                  const entriesForCategory = (requestEntries || []).filter(entry => entry.category === category.key)
                  const categoryProviderLabel = ticketProviderLabel(category.provider || ((category.externalTicketEnabled ?? category.serviceNowEnabled) === false ? 'manual' : 'servicenow'), { action: true })
                  return (
                    <div key={category.key} style={{
                      border: '1px solid var(--border, #e5e7eb)',
                      borderRadius: 12,
                      padding: 12,
                      background: 'var(--card, #f8fafc)'
                    }}>
                        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                          <span style={{ fontWeight: 600 }}>{category.label}</span>
                          {!isReadOnly && (
                            <div className="row" style={{ gap:8 }}>
                              <button
                                type="button"
                                className="btn secondary"
                                onClick={() => openBulkRequestModal(category.key)}
                                style={{ padding: '4px 10px', fontSize: 13, borderRadius: 999 }}
                              >
                                + Add
                              </button>
                            </div>
                          )}
                        </div>
                      {!entriesForCategory.length ? (
                        <p style={{ color: '#6b7280', fontSize: 13, marginTop: 4, marginBottom: 0 }}>
                          No tickets yet. Use the + button to create one.
                        </p>
                      ) : entriesForCategory.map(entry => {
                        const primary = primaryCustodian(entry)
                        const displayValue = primary.email || primary.name || ''
                        const selectedHold = (namedHolds || []).find(hold => Number(hold.id) === Number(entry.case_hold_id))
                        const selectableHolds = (namedHolds || []).filter(hold => hold?.status === 'active' || Number(hold.id) === Number(entry.case_hold_id))
                        const linkageText = Array.isArray(entry.bulk_custodians) && entry.bulk_custodians.length > 1
                          ? `${entry.bulk_custodians.length} custodians selected`
                          : ''
                        const hasCustodian = !!(displayValue || '').trim()
                        const creatingExternalTicket = !!externalTicketBusy?.[entry.id]
                        const statusInfo = externalTicketStatuses?.[entry.id] || (entry.ticket ? externalTicketStatuses?.[entry.ticket] : null)
                        const statusColor = statusInfo ? (statusInfo.is_closed ? "#b91c1c" : "#15803d") : "#6b7280"
                        const ticketLink = statusInfo?.link || null
                        const assignedEmail = (statusInfo?.assigned_to_email || entry.assigned_to_email || '').trim()
                        const assignedDisplay = (statusInfo?.assigned_to_display || entry.assigned_to_display || '').trim()
                        const custodianKey = entry.custodian_id
                          ? `id:${entry.custodian_id}`
                          : (entry.custodian_email ? `email:${entry.custodian_email.toLowerCase()}` : null)
                        const hasTicketForCustodian = !!(
                          (entry.ticket || "").trim()
                          || (custodianKey && (requestEntries || []).some(other => {
                            if (!other || other.id === entry.id || other.category !== entry.category) return false
                            const otherKey = other.custodian_id
                              ? `id:${other.custodian_id}`
                              : (other.custodian_email ? `email:${(other.custodian_email || "").toLowerCase()}` : null)
                            return otherKey === custodianKey && (other.ticket || "").trim()
                          }))
                        )
                        const hasUnmatchedSnowCustodian = entryHasUnmatchedSnowCustodian(entry)
                        const allowCreateExternalTicket = !isTech && (category.externalTicketEnabled ?? category.serviceNowEnabled) !== false && hasCustodian && !creatingExternalTicket && !hasTicketForCustodian && !hasUnmatchedSnowCustodian
                        const ticketStatus = (entry.ticket_status || entry.status || statusInfo?.status || "").trim()
                        const assigneeName = (entry.assigned_to || assignedDisplay || "").trim()
                        const assigneeEmail = assignedEmail
                        const hasAssignee = !!(assigneeName || assigneeEmail)
                        const isClosed = !!(statusInfo?.is_closed)
                        const hasTicketNumber = !!(entry.ticket || "").trim()
                        const normalizedStatus = (ticketStatus || '').toLowerCase()
                        const closedKeywords = ['closed', 'resolved', 'complete', 'completed', 'canceled', 'cancelled', 'retired', 'done']
                        let badgeState = 'Open'
                        if (isClosed || closedKeywords.some(k => normalizedStatus.includes(k))) {
                          badgeState = 'Closed'
                        } else if (hasAssignee || normalizedStatus.includes('assign') || normalizedStatus.includes('work in progress') || normalizedStatus.includes('in progress')) {
                          badgeState = 'Assigned'
                        } else if (normalizedStatus === 'new') {
                          badgeState = 'Open'
                        }
                        const statusBadgeText = badgeState === 'Closed' ? 'Ticket Closed' : (badgeState === 'Assigned' ? 'Ticket Assigned' : 'Ticket Opened')
                        const statusBadgeColors = (() => {
                          if (badgeState === 'Closed') return { bg: '#fee2e2', fg: '#991b1b' }
                          if (badgeState === 'Assigned') return { bg: '#dcfce7', fg: '#166534' }
                          return { bg: '#fef3c7', fg: '#92400e' } // Open
                        })()
                        const statusTitle = (hasAssignee && !isRequestor) ? `Assigned to ${assigneeName || assigneeEmail || 'unknown'}` : ''
                        const showStatusBadge = hasTicketNumber
                        return (
                        <div key={entry.id} style={{ background: 'var(--card, #fff)', border: '1px solid var(--border, #e5e7eb)', borderRadius: 10, padding: 10, display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                              <span style={{ fontSize: 12, color: '#475467' }}>Named Hold</span>
                              {isReadOnly ? (
                                <strong>{selectedHold?.name || 'Not assigned'}</strong>
                              ) : (
                                <select
                                  className="input"
                                  value={entry.case_hold_id || ''}
                                  onChange={event => updateRequestEntry(entry.id, { case_hold_id: event.target.value ? Number(event.target.value) : null })}
                                  disabled={!!entry.ticket}
                                >
                                  <option value="">Select a hold</option>
                                  {selectableHolds.map(hold => <option key={hold.id} value={hold.id}>{hold.name}</option>)}
                                </select>
                              )}
                            </label>
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                              <span style={{ fontSize: 12, color: '#475467' }}>Custodians</span>
                              {hasCustodian ? (
                                <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                                  {Array.isArray(entry.bulk_custodians) && entry.bulk_custodians.length
                                    ? entry.bulk_custodians.map((c, idx) => (
                                        <Badge key={`${entry.id}-bulk-${idx}`} variant="orange" compact>
                                          {c.email || 'No email'}
                                        </Badge>
                                      ))
                                    : (
                                      <Badge variant="orange" compact>{primary.email || 'No email'}</Badge>
                                    )
                                  }
                                </div>
                              ) : (
                                <input
                                  type="text"
                                  list="custodian-request-options"
                                  value={displayValue}
                                  placeholder="Start typing a name or email"
                                  onChange={(e) => handleRequestEntryCustodianChange(entry.id, e.target.value)}
                                  style={{ border: '1px solid #d1d5db', borderRadius: 8, padding: '8px 10px', fontSize: 13 }}
                                />
                              )}
                            </label>
                            {hasUnmatchedSnowCustodian && (
                              <div style={{ fontSize: 12, color: '#b45309' }}>
                                {matchedEmailWorkflowWarning || 'Unmatched or missing email custodians cannot be used for this configured ticket workflow.'}
                              </div>
                            )}
                            <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                              <span style={{ fontSize: 12, color: '#475467' }}>Ticket #</span>
                              <input
                                type="text"
                                value={isRequestor ? "Hidden" : entry.ticket}
                                onChange={(e) => { if (isRequestor) return; updateRequestEntry(entry.id, { ticket: e.target.value }) }}
                                maxLength={64} readOnly={isRequestor} disabled={isRequestor}
                                style={{
                                  border: '1px solid #d1d5db',
                                  borderRadius: 8,
                                  padding: '8px 10px',
                                  fontSize: 13,
                                  color: '#111827',
                                }}
                              />
                              <span style={{ fontSize: 12, color: '#6b7280' }}>
                                Created: {isRequestor ? 'Hidden' : (formatDateTime(entry.created_at) || '-')}
                              </span>
                            </label>
                            {showStatusBadge && (
                              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                                  {ticketLink && !isRequestor ? (
                                    <a href={ticketLink} target="_blank" rel="noreferrer" style={{ textDecoration:'none' }}>
                                      <span
                                        title={statusTitle}
                                        style={{ fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 999, background: statusBadgeColors.bg, color: statusBadgeColors.fg, display:'inline-block' }}
                                      >
                                        {statusBadgeText}
                                      </span>
                                    </a>
                                  ) : (
                                    <span
                                      title={isRequestor ? 'Ticket number hidden' : statusTitle}
                                      style={{ fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 999, background: statusBadgeColors.bg, color: statusBadgeColors.fg }}
                                    >
                                      {statusBadgeText}
                                    </span>
                                  )}
                                </div>
                                {assigneeEmail && hasCustodian && badgeState === 'Assigned' && !entry.assignment_email_sent && !isRequestor && (
                                  <button
                                    className="btn primary"
                                    type="button"
                                    disabled={!!externalTicketEmailBusy[entry.id]}
                                    onClick={() => sendCustodianDetailsToAssignee(entry)}
                                    style={{ padding: '4px 10px', borderRadius: 8, fontSize: 12 }}
                                  >
                                    {externalTicketEmailBusy[entry.id]
                                      ? 'Sending...'
                                      : (externalTicketEmailSent[entry.id] ? 'Sent' : 'Send custodian details')}
                                  </button>
                                )}
                                {!isRequestor && entry.assignment_email_sent && (
                                  <span style={{ fontSize: 12, fontWeight: 600, padding: '3px 10px', borderRadius: 999, background: '#dcfce7', color: '#166534' }}>
                                    Sent
                                  </span>
                                )}
                              </div>
                            )}
                              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                <span style={{ fontSize: 12, color: '#6b7280' }}>{linkageText}</span>
                                {!isRequestor && (
                                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                    <button
                                      type="button"
                                      className="btn secondary"
                                      onClick={() => copyEntryCustodians(entry)}
                                      style={{ padding: '4px 10px', borderRadius: 8, fontSize: 12 }}
                                    >
                                      Copy custodians
                                    </button>
                                    {workflowUsesAccessLogDetails(entry) && (
                                      <button
                                        type="button"
                                        className="btn secondary"
                                        onClick={() => setAccessLogInfoEntryId(entry.id)}
                                        style={{ padding: '4px 10px', borderRadius: 8, fontSize: 12 }}
                                      >
                                        More info
                                      </button>
                                    )}
                                    {allowCreateExternalTicket && (
                                      <button
                                        type="button"
                                        className="btn"
                                        onClick={() => createExternalTicket(entry)}
                                        disabled={creatingExternalTicket}
                                        style={{ padding: '4px 10px', borderRadius: 8, fontSize: 12 }}
                                      >
                                        {creatingExternalTicket ? 'Creating...' : `+ ${categoryProviderLabel}`}
                                      </button>
                                    )}
                                    {!isTech && (
                                      <button
                                        className="btn ghost"
                                        type="button"
                                        onClick={() => removeRequestEntry(entry.id)}
                                        style={{ padding: '4px 8px', borderRadius: 8, fontSize: 12 }}
                                      >
                                        Remove
                                      </button>
                                    )}
                                  </div>
                                )}
                              </div>
                          </div>
                        )
                      })}
                    </div>
                  )
                })}
              </div>
              <div className="row" style={{ justifyContent: 'flex-start', alignItems: 'center', marginTop: 20, flexWrap: 'wrap', gap: 12 }}>
                <span style={{ color: '#6b7280', fontSize: 13 }}>
                  {requestsSaving
                    ? 'Saving...'
                    : requestsDirty
                      ? 'Saving your changes...'
                      : 'All changes saved.'}
                </span>
              </div>
            </section>
  )
}
