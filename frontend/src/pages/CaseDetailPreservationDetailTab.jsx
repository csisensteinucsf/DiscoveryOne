import { useState } from 'react'
import { formatNameRaw } from './caseDetailUtils.js'
import CaseDetailHoldSelector from './CaseDetailHoldSelector.jsx'
import { useCaseDetailNamedHolds } from './useCaseDetailNamedHolds.js'

function PreservationStateBadge({ status }) {
  const normalized = String(status || 'not_started').toLowerCase().replaceAll(' ', '_')
  return (
    <span className={'hold-status-badge is-' + normalized.replaceAll('_', '-')}>
      {normalized.replaceAll('_', ' ')}
    </span>
  )
}

export default function CaseDetailPreservationDetailTab({
  apiBase,
  caseId,
  showToast,
  holdsDetail,
  holdsDetailTotals,
  holdsDetailRows,
  formatDateTime,
  loadHoldsDetail,
  isTech,
  techHoldKeySet,
  holdDetailStateStyle,
  holdDetailStateLabel,
  formatActionLabel,
}) {
  const namedHolds = useCaseDetailNamedHolds({ apiBase, caseId, showToast })
  const [selectedHoldId, setSelectedHoldId] = useState(null)
  const selectedHold = namedHolds.namedHolds.find(
    hold => String(hold.id) === String(selectedHoldId),
  ) || namedHolds.namedHolds[0] || null
  const visibleNamedHolds = selectedHold ? [selectedHold] : []
  const selectedCustodianIds = new Set(
    (selectedHold?.custodians || []).map(member => String(member.custodian_id)),
  )
  const visibleHoldsDetailRows = selectedHold
    ? holdsDetailRows.filter(row => selectedCustodianIds.has(String(row?.id)))
    : holdsDetailRows
  const visibleCustodianCount = selectedHold
    ? selectedCustodianIds.size
    : (holdsDetailTotals.custodians || 0)
  const visibleTimelineEventCount = selectedHold
    ? visibleHoldsDetailRows.reduce(
      (total, row) => total + (Array.isArray(row?.timeline) ? row.timeline.length : 0),
      0,
    )
    : (holdsDetailTotals.events || 0)
  const refreshAll = () => {
    loadHoldsDetail()
    namedHolds.loadNamedHolds()
  }

  return (
<section className="card preservation-detail-tab">
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <h3 style={{ margin: 0 }}>Preservation Detail</h3>
                  <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>
                    Custodians: {visibleCustodianCount} | Timeline events: {visibleTimelineEventCount}
                    {holdsDetail?.data?.generated_at ? ` | Updated: ${formatDateTime(holdsDetail.data.generated_at) || '-'}` : ''}
                  </div>
                </div>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={refreshAll}
                  disabled={holdsDetail.loading || namedHolds.namedHoldsLoading}
                >
                  {holdsDetail.loading || namedHolds.namedHoldsLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>

              <p className="preservation-detail-intro">
                Preservation sources and provider history are grouped by Hold. Use the Hold buttons to view each workspace separately.
              </p>

              <CaseDetailHoldSelector
                holds={namedHolds.namedHolds}
                selectedHoldId={selectedHold?.id}
                onSelect={setSelectedHoldId}
                ariaLabel="Select Hold preservation detail"
              />

              <section className="preservation-detail-holds" aria-labelledby="preservation-detail-holds-heading">
                <div className="preservation-detail-section-heading">
                  <div>
                    <h4 id="preservation-detail-holds-heading">Hold preservation status</h4>
                    <p>
                      Holds: {namedHolds.namedHoldTotals.holds || 0} | Custodian assignments: {namedHolds.namedHoldTotals.custodian_memberships || 0}
                    </p>
                  </div>
                </div>

                {namedHolds.namedHoldsError ? <div className="alert error">{namedHolds.namedHoldsError}</div> : null}
                {namedHolds.namedHoldsLoading && !namedHolds.namedHolds.length ? <p className="muted">Loading Hold preservation...</p> : null}
                {!namedHolds.namedHoldsLoading && !namedHolds.namedHolds.length ? <p className="muted">No Holds have been created for this case.</p> : null}

                <div className="preservation-detail-hold-list">
                  {visibleNamedHolds.map(hold => (
                    <section className="preservation-detail-hold" key={hold.id}>
                      <div className="preservation-detail-hold-heading">
                        <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                          <h5>{hold.name}</h5>
                          <PreservationStateBadge status={hold.status} />
                        </div>
                        <span className="muted">{hold.custodian_count || 0} custodians</span>
                      </div>

                      {(hold.custodians || []).length ? (
                        <div className="table-scroll">
                          <table className="table preservation-detail-table">
                            <thead>
                              <tr><th>Custodian</th><th>Preservation sources</th></tr>
                            </thead>
                            <tbody>
                              {(hold.custodians || []).map(member => (
                                <tr key={member.membership_id || `${hold.id}-${member.custodian_id}`}>
                                  <td>
                                    <strong>{formatNameRaw(member.name || '') || member.email || 'Unnamed custodian'}</strong>
                                    <div className="muted">{member.email || '-'}</div>
                                  </td>
                                  <td>
                                    {(member.preservation_sources || []).length ? (
                                      <div className="preservation-detail-source-list">
                                        {(member.preservation_sources || []).map(source => (
                                          <div className="preservation-detail-source" key={source.id || source.source_key}>
                                            <div className="preservation-detail-source-heading">
                                              <strong>{source.source_label || source.source_key || 'Preservation source'}</strong>
                                              <PreservationStateBadge status={source.status} />
                                            </div>
                                            <div className="preservation-detail-source-meta">
                                              <span>Automation: {source.automation_ready ? 'Ready' : 'Manual'}</span>
                                              <span>Provider reference: {source.provider_reference || '-'}</span>
                                              <span>Updated: {formatDateTime(source.updated_at) || '-'}</span>
                                            </div>
                                            {source.last_error ? <div className="preservation-detail-source-error">{source.last_error}</div> : null}
                                          </div>
                                        ))}
                                      </div>
                                    ) : <span className="muted">No preservation sources configured for this custodian.</span>}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : <p className="muted">No custodians are assigned to this Hold.</p>}
                    </section>
                  ))}
                </div>
              </section>

              <div className="preservation-detail-section-heading preservation-detail-events-heading">
                <div>
                  <h4>Provider events and preservation timeline</h4>
                  <p>
                    {selectedHold
                      ? 'Provider states and event history for custodians assigned to ' + selectedHold.name + '.'
                      : 'Case-wide provider states and event history for every custodian.'}
                  </p>
                </div>
              </div>

              {holdsDetail.error && !holdsDetail.data ? (
                <p style={{ color: '#b91c1c', marginTop: 10 }}>{holdsDetail.error}</p>
              ) : null}

              {holdsDetail.error && holdsDetail.data ? (
                <p style={{ color: '#92400e', marginTop: 10 }}>
                  Showing last loaded data. Refresh failed: {holdsDetail.error}
                </p>
              ) : null}

              {holdsDetail.loading && !holdsDetail.data ? (
                <p style={{ color: '#6b7280', marginTop: 10 }}>Loading preservation details...</p>
              ) : null}

              {!holdsDetail.loading && visibleHoldsDetailRows.length === 0 ? (
                <p style={{ color: '#6b7280', marginTop: 10 }}>
                  {selectedHold ? 'No custodians are assigned to this Hold.' : 'No custodians found for this case.'}
                </p>
              ) : null}

              <div style={{ display: 'grid', gap: 12, marginTop: 10 }}>
                {visibleHoldsDetailRows.map((row) => {
                  const currentRows = (Array.isArray(row?.current_holds) ? row.current_holds : []).filter(item => !isTech || techHoldKeySet.has(item?.key))
                  const timelineRows = (Array.isArray(row?.timeline) ? row.timeline : []).filter(item => !isTech || techHoldKeySet.has(item?.hold_key))
                  return (
                    <div key={`holds-detail-${row?.id}`} style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 10, background: 'var(--card,#fff)' }}>
                      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                        <div>
                          <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)', fontSize: 13 }}>{formatNameRaw(row?.name || '') || row?.email || '-'}</div>
                          <div style={{ color: '#64748b', fontSize: 12 }}>{row?.email || '-'}</div>
                        </div>
                        <div style={{ display: 'grid', gap: 2, textAlign: 'right' }}>
                          <div style={{ color: '#334155', fontSize: 12, fontWeight: 600 }}>Events: {timelineRows.length}</div>
                          <div style={{ color: '#64748b', fontSize: 11 }}>Last activity: {formatDateTime(row?.last_activity_at) || '-'}</div>
                        </div>
                      </div>

                      <div style={{ marginTop: 10, overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                          <thead style={{ background: 'rgba(15,23,42,0.04)' }}>
                            <tr>
                              <th style={{ textAlign: 'left', padding: 6 }}>Source</th>
                              <th style={{ textAlign: 'left', padding: 6 }}>State</th>
                              <th style={{ textAlign: 'left', padding: 6 }}>Flags</th>
                              <th style={{ textAlign: 'left', padding: 6 }}>Last update</th>
                              <th style={{ textAlign: 'left', padding: 6 }}>Last actor</th>
                              <th style={{ textAlign: 'left', padding: 6 }}>Last event</th>
                            </tr>
                          </thead>
                          <tbody>
                            {currentRows.map((hold) => (
                              <tr key={`hold-current-${row?.id}-${hold?.key}`}>
                                <td style={{ padding: 6 }}>{hold?.label || hold?.key || '-'}</td>
                                <td style={{ padding: 6 }}>
                                  <span style={{ display: 'inline-flex', alignItems: 'center', borderRadius: 999, padding: '2px 8px', fontSize: 11, fontWeight: 700, ...holdDetailStateStyle(hold?.state) }}>
                                    {holdDetailStateLabel(hold?.state)}
                                  </span>
                                </td>
                                <td style={{ padding: 6, color: '#475569' }}>
                                  Active:{hold?.active ? 'Yes' : 'No'} | Pending:{hold?.pending ? 'Yes' : 'No'} | Failed:{hold?.failed ? 'Yes' : 'No'} | Released:{hold?.released ? 'Yes' : 'No'}
                                </td>
                                <td style={{ padding: 6 }}>{formatDateTime(hold?.last_event_at) || '-'}</td>
                                <td style={{ padding: 6 }}>{hold?.last_event_actor || '-'}</td>
                                <td style={{ padding: 6 }}>{formatActionLabel(hold?.last_event_action)}</td>
                              </tr>
                            ))}
                            {!currentRows.length && (
                              <tr>
                                <td style={{ padding: 6, color: '#6b7280' }} colSpan={6}>No preservation sources available for this account.</td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: '#334155', marginBottom: 6 }}>Preservation event timeline</div>
                        {timelineRows.length ? (
                          <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                              <thead style={{ background: 'rgba(15,23,42,0.04)' }}>
                                <tr>
                                  <th style={{ textAlign: 'left', padding: 6 }}>Date</th>
                                  <th style={{ textAlign: 'left', padding: 6 }}>Source</th>
                                  <th style={{ textAlign: 'left', padding: 6 }}>State</th>
                                  <th style={{ textAlign: 'left', padding: 6 }}>Action</th>
                                  <th style={{ textAlign: 'left', padding: 6 }}>Actor</th>
                                  <th style={{ textAlign: 'left', padding: 6 }}>Details</th>
                                </tr>
                              </thead>
                              <tbody>
                                {timelineRows.map((event, idx) => (
                                  <tr key={`hold-event-${row?.id}-${event?.id || idx}-${event?.hold_key || 'hold'}`}>
                                    <td style={{ padding: 6 }}>{formatDateTime(event?.created_at) || '-'}</td>
                                    <td style={{ padding: 6 }}>{event?.hold_label || '-'}</td>
                                    <td style={{ padding: 6 }}>
                                      <span style={{ display: 'inline-flex', alignItems: 'center', borderRadius: 999, padding: '2px 8px', fontSize: 11, fontWeight: 700, ...holdDetailStateStyle(event?.state) }}>
                                        {holdDetailStateLabel(event?.state)}
                                      </span>
                                    </td>
                                    <td style={{ padding: 6 }}>{formatActionLabel(event?.action)}</td>
                                    <td style={{ padding: 6 }}>{event?.actor || '-'}</td>
                                    <td style={{ padding: 6 }}>
                                      <div style={{ color: '#0f172a' }}>{event?.summary || '-'}</div>
                                      {event?.message ? <div style={{ color: '#64748b', marginTop: 2 }}>{event.message}</div> : null}
                                      {event?.details ? (
                                        <details style={{ marginTop: 4 }}>
                                          <summary style={{ cursor: 'pointer', color: '#475569', fontSize: 11 }}>Raw details</summary>
                                          <pre style={{ margin: '6px 0 0', padding: 8, background: '#0f172a', color: '#e2e8f0', borderRadius: 8, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 220, overflowY: 'auto' }}>
                                            {JSON.stringify(event.details, null, 2)}
                                          </pre>
                                        </details>
                                      ) : null}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <p style={{ color: '#6b7280', margin: 0 }}>No preservation timeline events found for this custodian.</p>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </section>
  )
}
