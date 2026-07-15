import Badge from './CaseRequestBadge.jsx'
import { TYPE_LABELS, ISODate, hasSearchDetails } from './caseRequestsUtils.js'

const employmentBadgesFromPayload = (cust) => {
  const badges = []
  const status = String(cust?.separation_status || '').toLowerCase()
  const date = cust?.separation_date
  if (status === 'separated') badges.push({ label: 'Separated', variant: 'danger', title: date ? `Separated ${date}` : 'Separated employee' })
  else if (status === 'separating') badges.push({ label: 'Separating', variant: 'warn', title: date ? `Separation date ${date}` : 'Upcoming separation' })
  else if (date) badges.push({ label: `Sep ${date}`, variant: 'warn', title: `Separation date ${date}` })
  return badges
}
export default function CaseRequestCards({ items, emptyLabel, apiBase, caseLookup, isRequestor, onApprove, onDecline }) {
    if (!items.length) return <div className="empty">{emptyLabel}</div>
  return (
      <div className="request-grid">
        {items.map((req) => {
          const payload = req.payload || {}
          const searches = (() => {
            if (Array.isArray(payload.searches)) return payload.searches
            if (payload.search) return [payload.search]
            if (req.request_type === 'search') return [payload.search || payload]
            return []
          })().filter((s) => s && typeof s === 'object')
          const versaRequirements = String(payload.versa_search_requirements || payload.search_requirements || '').trim()
          const custodians = (payload.custodians || [])
          const created = ISODate(req.created_at)
          const caseName = req.case_name || (req.case_id && caseLookup[req.case_id]?.name)
          return (
            <div className="request-card" key={req.id}>
              <div className="request-card__header">
                <div>
                  <div className="label">{TYPE_LABELS[req.request_type] || req.request_type}</div>
                  <h3>{caseName || 'Pending case'}</h3>
                  {payload.legal_case_name && (
                    <div style={{ fontSize: 12, color: '#475569' }}>
                      <strong>Legal Case:</strong> {payload.legal_case_name}
                    </div>
                  )}
                  {payload.claimant && (
                    <div style={{ fontSize: 12, color: '#475569' }}>
                      <strong>Claimant:</strong> {payload.claimant}
                    </div>
                  )}
                </div>
                <Badge status={req.status} />
              </div>
              <div className="request-card__body">
                <div><strong>Submitted:</strong> {created}</div>
                <div><strong>Requestor:</strong> {req.requestor?.email || req.requestor?.username || ''}</div>
                {payload.claimant ? <div><strong>Claimant:</strong> {payload.claimant}</div> : null}
                {req.request_type === 'close_case' && (
                  <div style={{ padding:'8px 10px', borderRadius:8, background:'#FEF3C7', border:'1px solid #FDE68A', color:'#92400E' }}>
                    Request to close the case and release all existing holds/preservation.
                  </div>
                )}
                {req.ntp_all_sent ? <div><strong>NTPs:</strong> Mark as sent</div> : null}
                {custodians.length ? (
                  <div>
                    <strong>Custodians:</strong>
                    <ul style={{ paddingLeft: 16, marginTop: 6 }}>
                      {custodians.map((c, idx) => {
                        const badges = employmentBadgesFromPayload(c)
                        const holds = c.holds || {}
                        const holdsList = []
                        if (holds.email) holdsList.push('Email')
                        if (holds.box) holdsList.push('Box')
                        if (holds.onedrive) holdsList.push('OneDrive')
                        if (holds.slack) holdsList.push('Slack')
                        return (
                          <li key={`${req.id}-c-${idx}`} style={{ marginBottom: 4 }}>
                            {c.name}{c.email ? ` (${c.email})` : ''}
                            {c.lookup_override ? (
                              <span
                                className="mini-badge"
                                style={{ background: '#e0f2fe', color: '#075985', borderColor: '#bae6fd', marginLeft: 6 }}
                                title="Lookup override"
                              >
                                O
                              </span>
                            ) : null}
                            {badges.map((b, i) => (
                              <span
                                key={`${req.id}-c-${idx}-badge-${i}`}
                                className="mini-badge"
                                style={b.variant === 'danger'
                                  ? { background: '#fee2e2', color: '#991b1b', borderColor: '#fecdd3', marginLeft: 6 }
                                  : { background: '#fef3c7', color: '#92400e', borderColor: '#fde68a', marginLeft: 6 }}
                                title={b.title || b.label}
                              >
                                {b.label}
                              </span>
                            ))}
                            {holdsList.length ? (
                              <div style={{ fontSize: 12, color: '#475569', marginTop: 2 }}>
                                Holds: {holdsList.join(', ')}
                              </div>
                            ) : null}
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ) : null}
                {Array.isArray(payload.consent_proofs) && payload.consent_proofs.length > 0 && (
                  <div>
                    <strong>Consent proofs</strong>
                    <ul>
                      {payload.consent_proofs.map((proof) => (
                        <li key={`proof-${proof.id}`}>
                          {proof.custodian_name || proof.custodian_email || 'Unnamed custodian'} 
                          <a
                            className="btn secondary"
                            href={`${apiBase}/case_requests/${req.id}/consent_proofs/${proof.id}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ marginLeft: 8 }}
                          >
                            Download {proof.original_filename || 'proof'}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {req.attachment_name && (
                  <div>
                    <a className="btn secondary" href={`${apiBase}/case_requests/${req.id}/attachment`} target="_blank" rel="noreferrer">Download uploaded list</a>
                  </div>
                )}
                {versaRequirements ? (
                  <div>
                    <strong>Versa search requirements</strong>
                    <div style={{ whiteSpace: 'pre-wrap', marginTop: 6 }}>{versaRequirements}</div>
                  </div>
                ) : null}
                {Array.isArray(payload.consents) && payload.consents.length > 0 && (
                  <div>
                    <strong>Consents reported:</strong>
                    <ul>
                      {payload.consents.map((consent, idx) => (
                        <li key={`${req.id}-consent-${idx}`}>
                          {consent.name || consent.email ? (
                            <>
                              {consent.name || ''}
                              {consent.email ? ` (${consent.email})` : ''}
                            </>
                          ) : 'Unnamed custodian'}
                          {consent.notes ? `  ${consent.notes}` : ''}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {req.consent_attachment_name && (
                  <div>
                    <a className="btn secondary" href={`${apiBase}/case_requests/${req.id}/consent_attachment`} target="_blank" rel="noreferrer">Download consent documentation</a>
                  </div>
                )}
                {searches.some(hasSearchDetails) ? (
                  <div>
                    <strong>Search details</strong>
                    {searches.filter(hasSearchDetails).map((search, idx) => (
                      <div key={`${req.id}-search-${idx}`} style={{ marginTop: idx === 0 ? 8 : 12 }}>
                        {searches.filter(hasSearchDetails).length > 1 && (
                          <div style={{ fontWeight: 700, marginBottom: 4 }}>Search request {idx + 1}</div>
                        )}
                        <dl>
                          {search.keywords ? <><dt>Keywords</dt><dd>{search.keywords}</dd></> : null}
                          {search.senders ? <><dt>Senders</dt><dd>{search.senders}</dd></> : null}
                          {search.recipients ? <><dt>Recipients</dt><dd>{search.recipients}</dd></> : null}
                          {(search.date_from || search.date_to) ? <><dt>Date Range</dt><dd>{[search.date_from, search.date_to].filter(Boolean).join('  ')}</dd></> : null}
                          {search.additional ? <><dt>Notes</dt><dd>{search.additional}</dd></> : null}
                        </dl>
                      </div>
                    ))}
                  </div>
                ) : null}
                {req.decline_reason && <div className="error">Declined: {req.decline_reason}</div>}
              </div>
              {!isRequestor && req.status === 'pending' && (
                <div className="request-card__actions">
                  <button className="btn" onClick={() => onApprove(req.id)}>Approve</button>
                  <button className="btn danger" onClick={() => onDecline(req.id)}>Decline</button>
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }
