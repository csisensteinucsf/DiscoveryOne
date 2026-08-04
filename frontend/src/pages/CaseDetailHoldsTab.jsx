import { formatNameRaw } from './caseDetailUtils.js'

export default function CaseDetailHoldsTab({
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
  return (
<section className="legacy-hold-timeline">
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <h3 style={{ margin: 0 }}>Preservation Detail</h3>
                  <div style={{ color: '#6b7280', fontSize: 12, marginTop: 2 }}>
                    Custodians: {holdsDetailTotals.custodians || 0} | Timeline events: {holdsDetailTotals.events || 0}
                    {holdsDetail?.data?.generated_at ? ` | Updated: ${formatDateTime(holdsDetail.data.generated_at) || '-'}` : ''}
                  </div>
                </div>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={loadHoldsDetail}
                  disabled={holdsDetail.loading}
                >
                  {holdsDetail.loading ? 'Refreshing...' : 'Refresh'}
                </button>
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

              {!holdsDetail.loading && holdsDetailRows.length === 0 ? (
                <p style={{ color: '#6b7280', marginTop: 10 }}>No custodians found for this case.</p>
              ) : null}

              <div style={{ display: 'grid', gap: 12, marginTop: 10 }}>
                {holdsDetailRows.map((row) => {
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
