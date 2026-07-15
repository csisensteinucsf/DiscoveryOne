import { Badge, Button, InlineSpinner, Select } from './caseDetailControls.jsx'
import { formatNameRaw } from './caseDetailUtils.js'

function SortLabel({ label, col, custSort, onSort }) {
  const isActive = custSort.key === col
  const arrow = isActive ? (custSort.dir === 'asc' ? '\u25B2' : '\u25BC') : '\u21C5'
  return (
    <button
      type="button"
      onClick={() => onSort(col)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        padding: 0,
        fontWeight: 600,
        color: 'var(--text,#e5e7eb)',
      }}
      title={'Sort by ' + label}
    >
      <span>{label}</span>
      <span style={{ opacity: isActive ? 1 : 0.5 }}>{arrow}</span>
    </button>
  )
}

export default function CaseDetailCustodiansTab({
  custodianTable,
  isTech,
  isReadOnly,
  isRequestor,
  setAllTechPendingCompleted,
  techHoldsApplying,
  custodians,
  applyTechHoldChanges,
  holdsDirty,
  releaseAllHolds,
  releasingHolds,
  navigate,
  caseId,
  bulk,
  setBulk,
  hasAnyHold,
  holdMetaForView,
  normalizeEmail,
  custodianMatchesClaimant,
  caseData,
  employmentBadges,
  techHoldKeySet,
  holdState,
  onToggleHold,
  onChangeNtp,
  onChangeConsent,
  formatDateTime,
  formatDate,
  onEditCustodian,
  openRemoveCustodian,
}) {
  const {
    custodianCount,
    showCustFilters,
    setShowCustFilters,
    custFilters,
    setCustFilters,
    custSort,
    toggleSort,
    resetFilters,
    visibleCustodians,
    progressFor,
    onBadgeClick,
    custodianColumnCount,
  } = custodianTable

  return (
    <section className="card" style={{ padding: 12, overflowX: 'auto' }}>
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                <h3 style={{ margin: 0 }}>
                  Custodians {custodianCount ? <span style={{ fontWeight: 600 }}>({custodianCount})</span> : null}
                </h3>
                {(isTech || !isReadOnly || isRequestor) && (
                  <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap', gap: 8, marginLeft: 'auto' }}>
                    {isTech && (
                      <>
                        <button
                          className="btn secondary"
                          type="button"
                          onClick={setAllTechPendingCompleted}
                          disabled={techHoldsApplying || !custodians.length}
                        >
                          Set all to completed
                        </button>
                        <button
                          className="btn"
                          type="button"
                          onClick={applyTechHoldChanges}
                          disabled={techHoldsApplying || !holdsDirty}
                        >
                          {techHoldsApplying ? 'Applying...' : 'Apply'}
                        </button>
                      </>
                    )}
                    {!isReadOnly && (
                      <button
                        className="btn"
                        type="button"
                        onClick={() => releaseAllHolds()}
                        disabled={releasingHolds}
                        aria-busy={releasingHolds}
                        style={{
                          background: 'var(--brand,#0f172a)',
                          color: 'var(--brand-contrast,#fff)',
                          border: '1px solid transparent',
                          borderRadius: 999,
                          padding: '8px 18px',
                          fontWeight: 600,
                          boxShadow: '0 4px 12px rgba(0,0,0,0.25)',
                          opacity: releasingHolds ? 0.7 : 1,
                        }}
                      >
                        {releasingHolds ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                            <InlineSpinner size={12} color="rgba(255,255,255,0.95)" />
                            Releasing Holds...
                          </span>
                        ) : 'Release All Holds'}
                      </button>
                    )}
                    {isRequestor && (
                      <button
                        className="btn secondary"
                        type="button"
                        onClick={() => navigate(`/requests?type=custodian&caseId=${caseId}`)}
                      >
                        Request to add custodians
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginTop: 12, flexWrap:'wrap', gap:12 }}>
                <div style={{ display:'flex', alignItems:'center', gap:12, flexWrap:'wrap' }}>
                  <div style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>Sort & Filter custodians</div>
                  {!isReadOnly && (
                    <div className="row" style={{ gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>Apply to all:</span>
                      <Button variant={bulk.holds ? 'primary' : 'subtle'} onClick={() => setBulk(b => ({ ...b, holds: !b.holds }))}>Holds</Button>
                      {!isTech && (
                        <Button variant={bulk.ntp ? 'primary' : 'subtle'} onClick={() => setBulk(b => ({ ...b, ntp: !b.ntp }))}>NTP</Button>
                      )}
                      {!isTech && (
                        <Button variant={bulk.consent ? 'primary' : 'subtle'} onClick={() => setBulk(b => ({ ...b, consent: !b.consent }))}>Consent</Button>
                      )}
                    </div>
                  )}
                </div>
                <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                  <button className="btn subtle" type="button" onClick={() => setShowCustFilters(v => !v)}>
                    {showCustFilters ? 'Hide Filters' : 'Show Filters'}
                  </button>
                  <button className="btn subtle" type="button" onClick={resetFilters}>
                    Reset
                  </button>
                </div>
              </div>
              <table style={{ width: '100%', maxWidth: '100%', borderCollapse: 'collapse', marginTop: 8, minWidth: 1000 }}>
                <thead style={{ background: 'rgba(0,0,0,.04)', color: 'var(--text,#e5e7eb)' }}>
                  <tr>
                    <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}><SortLabel label="Name" col="name" custSort={custSort} onSort={toggleSort} /></th>
                    <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}><SortLabel label="Email" col="email" custSort={custSort} onSort={toggleSort} /></th>
                    <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}><SortLabel label="Holds" col="holds" custSort={custSort} onSort={toggleSort} /></th>
                    {!isTech && (
                      <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}><SortLabel label="NTP" col="ntp" custSort={custSort} onSort={toggleSort} /></th>
                    )}
                    {!isTech && (
                      <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}><SortLabel label="Consent" col="consent" custSort={custSort} onSort={toggleSort} /></th>
                    )}
                    {!isTech && (
                      <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}>Status</th>
                    )}
                    {!isTech && (
                      <th style={{ textAlign: 'right', padding: '8px', color: 'var(--text,#e5e7eb)' }}>Actions</th>
                    )}
                  </tr>
                  {showCustFilters && (
                    <tr>
                      {/* Name filter */}
                      <th style={{ padding: 6 }}>
                        <input
                          type="text"
                          value={custFilters.name}
                          onChange={e => setCustFilters(f => ({ ...f, name: e.target.value }))}
                          placeholder="Filter name..."
                          style={{ width:'100%', padding:'6px 8px', border:'1px solid #d1d5db', borderRadius: 8 }}
                        />
                      </th>
                      {/* Email filter */}
                      <th style={{ padding: 6 }}>
                        <input
                          type="text"
                          value={custFilters.email}
                          onChange={e => setCustFilters(f => ({ ...f, email: e.target.value }))}
                          placeholder="Filter email..."
                          style={{ width:'100%', padding:'6px 8px', border:'1px solid #d1d5db', borderRadius: 8 }}
                        />
                      </th>
                      {/* Holds filter */}
                      <th style={{ padding: 6 }}>
                        <select
                          value={custFilters.holds}
                          onChange={e => setCustFilters(f => ({ ...f, holds: e.target.value }))}
                          style={{ width:'100%', padding:'6px 8px', border:'1px solid #d1d5db', borderRadius: 8, background:'white' }}
                        >
                          <option value="all">All</option>
                          <option value="has">Has any hold</option>
                          <option value="none">No holds</option>
                        </select>
                      </th>
                      {!isTech && (
                        <>
                          {/* NTP filter */}
                          <th style={{ padding: 6 }}>
                            <select
                              value={custFilters.ntp}
                              onChange={e => setCustFilters(f => ({ ...f, ntp: e.target.value }))}
                              style={{ width:'100%', padding:'6px 8px', border:'1px solid #d1d5db', borderRadius: 8, background:'white' }}
                            >
                              <option value="all">All</option>
                              <option value="not sent">Not sent</option>
                              <option value="na">NA</option>
                              <option value="sent">Sent</option>
                              <option value="acknowledged">ACK</option>
                            </select>
                          </th>
                          {/* Consent filter */}
                          <th style={{ padding: 6 }}>
                            <select
                              value={custFilters.consent}
                              onChange={e => setCustFilters(f => ({ ...f, consent: e.target.value }))}
                              style={{ width:'100%', padding:'6px 8px', border:'1px solid #d1d5db', borderRadius: 8, background:'white' }}
                            >
                              <option value="all">All</option>
                              <option value="not sent">Not sent</option>
                              <option value="na">NA</option>
                              <option value="sent">Sent</option>
                              <option value="received">Received</option>
                            </select>
                          </th>
                          {/* keep column alignment */}
                          <th />
                          <th />
                        </>
                      )}
  </tr>
)}
</thead>
                <tbody>
                  {visibleCustodians && visibleCustodians.length > 0 ? (
                    visibleCustodians.map(c => {
                      const hasHold = hasAnyHold(c)
                      const hasHoldPending = holdMetaForView.some(({ key }) => {
                        const state = holdState(c, key)
                        return !!(state.pending || state.failed)
                      })
                      const ntpStatus = (c.ntp_status || 'not sent')
                      const ntpHalf = ntpStatus === 'sent'
                      const ntpFull = ntpStatus === 'acknowledged'
                      const consent = (c.consent_status || 'not sent')
                      const consentHalf = consent === 'sent'
                      const consentFull = consent === 'received'
                      const emailKey = normalizeEmail(c.email)
                      const isUnmatched = !!c.person_lookup_overridden || !emailKey || emailKey === 'noemail' || emailKey === 'unmatched'
                      const needsNameEmailReview = !!c.name_email_review_required
                      const isClaimant = custodianMatchesClaimant(caseData?.claimant, c)
                      const pSearch   = progressFor(c.id, 'search');
                      const pExport   = progressFor(c.id, 'export');
                      const pDelivery = progressFor(c.id, 'delivery');
                      return (
                        <tr key={c.id} data-id={c.id} style={isUnmatched ? { background: 'rgba(239, 68, 68, 0.06)' } : (needsNameEmailReview ? { background: 'rgba(245, 158, 11, 0.08)' } : undefined)}>
                          <td style={{ padding: '5px', verticalAlign: 'top' }}><span title={formatNameRaw(c.name) || '-'} style={{fontSize:12,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis',display:'block'}}>{formatNameRaw(c.name) || '-'}</span></td>
                          <td style={{ padding: '5px', verticalAlign: 'top' }}>
                            <span title={c.email || '-'} style={{fontSize:12,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis',display:'block'}}>{c.email || '-'}</span>
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 4 }}>
                              {employmentBadges(c).map((b, idx) => (
                                <Badge key={`emp-${c.id}-${idx}`} variant={b.variant} compact title={b.title}>{b.label}</Badge>
                              ))}
                              {c.person_lookup_overridden ? (
                                <Badge variant="warn" compact title="Person lookup was overridden for this custodian.">OVERRIDE</Badge>
                              ) : null}
                              {isClaimant ? (
                                <Badge variant="info" compact title="Claimant">C</Badge>
                              ) : null}
                              {needsNameEmailReview ? (
                                <Badge variant="warn" compact title={c.name_email_review_reason || 'Name/email mismatch suspected. Review this custodian before placing holds.'}>NAME/EMAIL REVIEW</Badge>
                              ) : null}
                              {isUnmatched ? (
                                <Badge variant="danger" compact title="Person lookup was not matched for this custodian.">UNMATCHED</Badge>
                              ) : null}
                            </div>
                          </td>
                          {/* Holds */}
                          <td style={{ padding: '5px', verticalAlign: 'top' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, max-content)', gap: 2 }}>
                              {holdMetaForView.map(({ key, label }) => {
                                const state = holdState(c, key)
                                const nextState = state.pending ? 'active' : (state.active ? 'failed' : (state.failed ? 'released' : (state.released ? 'off' : 'pending')))
                                const symbol = state.failed ? 'X' : (state.pending ? 'P' : (state.active ? '\u2713' : (state.released ? 'R' : '')))
                                const title = state.failed ? 'requested but could not be completed' : (state.pending ? 'pending' : (state.active ? 'completed' : (state.released ? 'released' : 'off')))
                                const isHoldEditable = !isRequestor && (!isTech || techHoldKeySet.has(key))
                                const boxStyle = state.failed
                                  ? { background:'#fee2e2', color:'#b91c1c', borderColor:'#fca5a5' }
                                  : state.pending
                                    ? { background:'#fef9c3', color:'#92400e', borderColor:'#facc15' }
                                    : state.active
                                      ? { background:'#dcfce7', color:'#166534', borderColor:'#86efac' }
                                      : state.released
                                        ? { background:'#ede9fe', color:'#6d28d9', borderColor:'#c4b5fd' }
                                        : { background:'var(--card,#0f172a)', color:'var(--text,#e5e7eb)', borderColor:'var(--border,#E5E7EB)' }
                                return (
                                  <button
                                    key={key}
                                    type="button"
                                    onClick={() => onToggleHold(c, key, nextState)}
                                    disabled={!isHoldEditable}
                                    aria-pressed={state.active || state.pending || state.failed || state.released}
                                    aria-label={`${label} hold ${title}`}
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 6,
                                      background: 'var(--card,#0f172a)',
                                      border: '1px solid var(--border,#E5E7EB)',
                                      padding: '2px 6px',
                                      borderRadius: 8,
                                      boxShadow:'inset 0 1px 0 rgba(255,255,255,0.04)',
                                      cursor: isHoldEditable ? 'pointer' : 'not-allowed'
                                    }}
                                  >
                                    <span
                                      role="presentation"
                                      title={state.failed ? 'requested but could not be completed' : (state.pending ? 'pending' : (state.released ? 'released' : undefined))}
                                      style={{
                                        width: 16,
                                        height: 16,
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        borderRadius: 4,
                                        border: `1px solid ${boxStyle.borderColor}`,
                                        background: boxStyle.background,
                                        color: boxStyle.color,
                                        fontSize: 11,
                                        fontWeight: 700,
                                        lineHeight: 1,
                                        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
                                      }}
                                    >
                                      {symbol}
                                    </span>
                                    <span style={{ fontSize: 11, color: 'var(--text,#e5e7eb)' }}>{label}</span>
                                  </button>
                                )
                              })}
                            </div>
                          </td>
                          {/* NTP */}
                          {!isTech && (
                            <td style={{ padding: '5px', verticalAlign: 'top' }}>
                              <Select value={c.ntp_status || 'not sent'} onChange={e => onChangeNtp(c, e.target.value)} disabled={isTech}>
                                <option value="na">NA</option>
                                <option value="not sent">Not sent</option>
                                <option value="sent">Sent</option>
                                <option value="acknowledged">ACK</option>
                              </Select>
                              {c.ntp_sent_at && ['sent', 'acknowledged'].includes(String(c.ntp_status || '').toLowerCase()) && (
                                <div style={{ fontSize: 11, color: 'var(--muted,#6b7280)', marginTop: 4 }}>
                                  Sent: {formatDateTime(c.ntp_sent_at)}
                                </div>
                              )}
                              {c.ntp_acknowledged_at && String(c.ntp_status || '').toLowerCase() === 'acknowledged' && (
                                <div style={{ fontSize: 11, color: 'var(--muted,#6b7280)', marginTop: 2 }}>
                                  ACK: {formatDateTime(c.ntp_acknowledged_at)}
                                </div>
                              )}
                              {c.ntp_template_name && ['sent', 'acknowledged'].includes(String(c.ntp_status || '').toLowerCase()) && (
                                <div style={{ fontSize: 11, color: 'var(--muted,#6b7280)', marginTop: 2 }}>
                                  Template: {c.ntp_template_name}
                                </div>
                              )}
                            </td>
                          )}
                          {/* Consent */}
                          {!isTech && (
                            <td style={{ padding: '5px', verticalAlign: 'top' }}>
                              <Select value={c.consent_status || 'not sent'} onChange={e => onChangeConsent(c, e.target.value)} disabled={isTech}>
                                <option value="na">NA</option>
                                <option value="not sent">Not sent</option>
                                <option value="sent">Sent</option>
                                <option value="received">Received</option>
                              </Select>
                            </td>
                          )}
                          {/* Status badges */}
                          {!isTech && (
                            <td style={{ padding: '5px', verticalAlign: 'top' }}>
                              <div style={{ display:'grid', gridTemplateColumns:'repeat(2, max-content)', gap:2 }}>
                                {hasHold ? (
                                  hasHoldPending
                                    ? <Badge variant="warn" onClick={() => onBadgeClick("HOLD")}>HOLD</Badge>
                                    : <Badge variant="success" onClick={() => onBadgeClick("HOLD")}>HOLD</Badge>
                                ) : null}
                                {ntpHalf ? <Badge variant="warn" half onClick={() => onBadgeClick("NTP")}>NTP</Badge> : null}
                                {ntpFull ? <Badge variant="success" onClick={() => onBadgeClick("NTP")}>NTP ACK</Badge> : null}
                                {consentHalf ? <Badge variant="warn" half onClick={() => onBadgeClick("CONSENT")}>CONSENT</Badge> : null}
                                {consentFull ? <Badge variant="success" onClick={() => onBadgeClick("CONSENT")}>CONSENT</Badge> : null}
                                {pSearch.total > 0 && (
                                  pSearch.pct === 1
                                    ? <Badge variant="success" onClick={() => onBadgeClick("SEARCH")}>SEARCH</Badge>
                                    : <Badge variant="warn" fillPct={pSearch.pct} onClick={() => onBadgeClick("SEARCH")}>SEARCH</Badge>
                                )}
                                {pExport.total > 0 && (
                                  pExport.pct === 1
                                    ? <Badge variant="success" onClick={() => onBadgeClick("EXPORT")}>EXPORT</Badge>
                                    : <Badge variant="warn" fillPct={pExport.pct} onClick={() => onBadgeClick("EXPORT")}>EXPORT</Badge>
                                )}
                                {pDelivery.total > 0 && (
                                  pDelivery.pct === 1
                                    ? <Badge variant="success" onClick={() => onBadgeClick("DELIVERED")}>DELIVERED</Badge>
                                    : <Badge variant="warn" fillPct={pDelivery.pct} onClick={() => onBadgeClick("DELIVERED")}>DELIVERED</Badge>
                                )}
                                {(!hasHold && !ntpHalf && !ntpFull && !consentHalf && !consentFull &&
                                  pSearch.total===0 && pExport.total===0 && pDelivery.total===0) ? <span>-</span> : null}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 11, color: 'var(--muted,#6b7280)' }}>
                                added: {formatDate(c.added_at) || 'unknown'}
                              </div>
                            </td>
                          )}
                          {/* Actions */}
                          {!isTech && (
                            <td style={{ padding: '5px', textAlign: 'right', verticalAlign: 'top' }}>
                              {isRequestor ? (
                                <span style={{ color:'#6b7280' }}>Read only</span>
                              ) : (
                                <div className="row" style={{ justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
                                  <button className="btn secondary" onClick={() => onEditCustodian(c)} style={{padding:'4px 8px',borderRadius:10,fontSize:12}}>Edit</button>
                                  <button className="btn danger" onClick={() => openRemoveCustodian(c)} style={{padding:'4px 8px',borderRadius:10,fontSize:12}}>Remove</button>
                                </div>
                              )}
                            </td>
                          )}
                        </tr>
                      )
                    })
                  ) : (
                    <tr>
                      <td style={{ padding: '8px' }} colSpan={custodianColumnCount}>-</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </section>
  )
}
