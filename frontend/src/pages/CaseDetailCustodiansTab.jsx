import { Badge } from './caseDetailControls.jsx'
import DataTableHeader from '../components/DataTableHeader.jsx'
import { formatNameRaw } from './caseDetailUtils.js'
import {
  CONSENT_STATUS_OPTIONS,
  NTP_STATUS_OPTIONS,
  isConsentComplete,
  normalizeConsentStatus,
  normalizeNtpStatus,
  consentStatusLabel,
  ntpStatusLabel,
} from './custodianStatusCatalog.js'

const PRESERVATION_FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: 'has', label: 'Has preservation' },
  { value: 'none', label: 'No preservation' },
]

const NTP_FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  ...NTP_STATUS_OPTIONS,
]

const CONSENT_FILTER_OPTIONS = [
  { value: 'all', label: 'All' },
  ...CONSENT_STATUS_OPTIONS,
  { value: 'awoc', label: 'AWOC' },
]

const HEADER_STYLE = {
  textAlign: 'left',
  padding: '8px',
  color: 'var(--text,#e5e7eb)',
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
  setCustodianModalMode,
  setShowCustodianModal,
  openSendNtp,
  sendingNtp,
  ntpButtonDisabled,
}) {
  const {
    custodianCount,
    custFilters,
    setCustFilters,
    custSort,
    toggleSort,
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
                    {!isReadOnly && !isTech && (
                      <button
                        className="btn secondary"
                        type="button"
                        onClick={() => { setCustodianModalMode('add'); setShowCustodianModal(true) }}
                      >
                        Add / Import Custodians
                      </button>
                    )}
                    {!isTech && (
                      <button className="btn secondary" type="button" onClick={openSendNtp} disabled={sendingNtp || ntpButtonDisabled}>
                        {sendingNtp ? 'Sending...' : 'NTPs'}
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
              <p className="muted" style={{ margin: '8px 0 0' }}>
                Preservation and NTP values are read only here and are managed within each Hold.
              </p>
              <table style={{ width: '100%', maxWidth: '100%', borderCollapse: 'collapse', marginTop: 8, minWidth: 1000 }}>
                <thead style={{ background: 'rgba(0,0,0,.04)', color: 'var(--text,#e5e7eb)' }}>
                  <tr>
                    <DataTableHeader
                      label="Name"
                      sortKey="name"
                      sort={custSort}
                      onSort={toggleSort}
                      filterValue={custFilters.name}
                      onFilterChange={value => setCustFilters(filters => ({ ...filters, name: value }))}
                      filterPlaceholder="Filter name..."
                      style={HEADER_STYLE}
                    />
                    <DataTableHeader
                      label="Email"
                      sortKey="email"
                      sort={custSort}
                      onSort={toggleSort}
                      filterValue={custFilters.email}
                      onFilterChange={value => setCustFilters(filters => ({ ...filters, email: value }))}
                      filterPlaceholder="Filter email..."
                      style={HEADER_STYLE}
                    />
                    <DataTableHeader
                      label="Preservation"
                      sortKey="holds"
                      sort={custSort}
                      onSort={toggleSort}
                      filterValue={custFilters.holds}
                      onFilterChange={value => setCustFilters(filters => ({ ...filters, holds: value }))}
                      filterOptions={PRESERVATION_FILTER_OPTIONS}
                      filterClearValue="all"
                      style={HEADER_STYLE}
                    />
                    {!isTech && (
                      <DataTableHeader
                        label="NTP"
                        sortKey="ntp"
                        sort={custSort}
                        onSort={toggleSort}
                        filterValue={custFilters.ntp}
                        onFilterChange={value => setCustFilters(filters => ({ ...filters, ntp: value }))}
                        filterOptions={NTP_FILTER_OPTIONS}
                        filterClearValue="all"
                        style={HEADER_STYLE}
                      />
                    )}
                    {!isTech && (
                      <DataTableHeader
                        label="Consent"
                        sortKey="consent"
                        sort={custSort}
                        onSort={toggleSort}
                        filterValue={custFilters.consent}
                        onFilterChange={value => setCustFilters(filters => ({ ...filters, consent: value }))}
                        filterOptions={CONSENT_FILTER_OPTIONS}
                        filterClearValue="all"
                        style={HEADER_STYLE}
                      />
                    )}
                    {!isTech && (
                      <th style={{ textAlign: 'left', padding: '8px', color: 'var(--text,#e5e7eb)' }}>Status</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {visibleCustodians && visibleCustodians.length > 0 ? (
                    visibleCustodians.map(c => {
                      const hasHold = hasAnyHold(c)
                      const hasHoldPending = holdMetaForView.some(({ key }) => {
                        const state = holdState(c, key)
                        return !!(state.pending || state.failed)
                      })
                      const ntpStatus = normalizeNtpStatus(c.ntp_status)
                      const ntpHalf = ntpStatus === 'sent'
                      const ntpFull = ntpStatus === 'acknowledged'
                      const consent = normalizeConsentStatus(c.consent_status)
                      const consentHalf = consent === 'sent'
                      const consentFull = isConsentComplete(consent)
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
                                <Badge variant="warn" compact title={c.name_email_review_reason || 'Name/email mismatch suspected. Review this custodian before applying preservation.'}>NAME/EMAIL REVIEW</Badge>
                              ) : null}
                              {isUnmatched ? (
                                <Badge variant="danger" compact title="Person lookup was not matched for this custodian.">UNMATCHED</Badge>
                              ) : null}
                            </div>
                          </td>
                          {/* Preservation */}
                          <td style={{ padding: '5px', verticalAlign: 'top' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, max-content)', gap: 2 }}>
                              {holdMetaForView.map(({ key, label }) => {
                                const state = holdState(c, key)
                                const symbol = state.failed ? 'X' : (state.pending ? 'P' : (state.active ? '\u2713' : (state.released ? 'R' : '')))
                                const title = state.failed ? 'requested but could not be completed' : (state.pending ? 'pending' : (state.active ? 'completed' : (state.released ? 'released' : 'off')))
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
                                    disabled
                                    aria-pressed={state.active || state.pending || state.failed || state.released}
                                    aria-label={`${label} preservation ${title}`}
                                    style={{
                                      display: 'flex',
                                      alignItems: 'center',
                                      gap: 6,
                                      background: 'var(--card,#0f172a)',
                                      border: '1px solid var(--border,#E5E7EB)',
                                      padding: '2px 6px',
                                      borderRadius: 8,
                                      boxShadow:'inset 0 1px 0 rgba(255,255,255,0.04)',
                                      cursor: 'default'
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
                              <strong>{ntpStatusLabel(normalizeNtpStatus(c.ntp_status))}</strong>
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
                              {consentStatusLabel(normalizeConsentStatus(c.consent_status))}
                            </td>
                          )}
                          {/* Status badges */}
                          {!isTech && (
                            <td style={{ padding: '5px', verticalAlign: 'top' }}>
                              <div style={{ display:'grid', gridTemplateColumns:'repeat(2, max-content)', gap:2 }}>
                                {hasHold ? (
                                  hasHoldPending
                                    ? <Badge variant="warn" onClick={() => onBadgeClick("HOLD")}>PRESERVATION</Badge>
                                    : <Badge variant="success" onClick={() => onBadgeClick("HOLD")}>PRESERVATION</Badge>
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
                        </tr>
                      )
                    })
                  ) : (
                    <tr>
                      <td style={{ padding: '8px' }} colSpan={isTech ? 3 : 6}>-</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </section>
  )
}
