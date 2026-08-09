import Badge from './CaseRequestBadge.jsx'
import { TYPE_LABELS, ISODate, hasSearchDetails } from './caseRequestsUtils.js'

const employmentBadgesFromPayload = (cust) => {
  const end = cust?.employment_end_date
  if (!end) return []
  const ts = Date.parse(end)
  if (Number.isNaN(ts) || ts > Date.now()) return []
  const days = (Date.now() - ts) / (1000 * 60 * 60 * 24)
  if (days < 90) return [{ label: 'S', title: 'Separated (< 3 months)', variant: 'success' }]
  if (days >= 365) return [{ label: 'S', title: 'Separated (over 1 year)', variant: 'danger' }]
  return [{ label: 'S', title: 'Separated (< 1 year)', variant: 'warn' }]
}

const holdLabelsForCustodian = (cust) => {
  const holds = cust?.holds || {}
  const labels = []
  if (holds.email) labels.push('Email')
  if (holds.onedrive) labels.push('OneDrive')
  if (holds.box) labels.push('Box')
  if (holds.slack) labels.push('Slack')
  if (holds.rubrik_restore) labels.push('Rubrik restore')
  return labels
}

const searchesForRequest = (req) => {
  const payload = req?.payload || {}
  return (() => {
    if (Array.isArray(payload.searches)) return payload.searches
    if (payload.search) return [payload.search]
    if (req?.request_type === 'search') return [payload.search || payload]
    return []
  })().filter((s) => s && typeof s === 'object')
}

const requestCaseName = (req, caseLookup) => {
  const payload = req?.payload || {}
  return req?.case_name || payload.name || (req?.case_id && caseLookup[req.case_id]?.name) || 'Pending case'
}

const requestorLabel = (req) => req?.requestor?.email || req?.requestor?.username || ''

export default function CaseRequestDetailBody({ request: req, apiBase, caseLookup }) {
  if (!req) return null
  const payload = req.payload || {}
  const searches = searchesForRequest(req)
  const visibleSearches = searches.filter(hasSearchDetails)
  const custodians = Array.isArray(payload.custodians) ? payload.custodians : []
  const versaRequirements = String(payload.versa_search_requirements || payload.search_requirements || '').trim()
  const consentProofs = Array.isArray(req.consent_proofs)
    ? req.consent_proofs
    : (Array.isArray(payload.consent_proofs) ? payload.consent_proofs : [])
  const eDiscoveryName = requestCaseName(req, caseLookup)
  const legalCaseName = String(payload.legal_case_name || '').trim()
  const showEDiscoveryName = !legalCaseName || eDiscoveryName.trim().toLocaleLowerCase() !== legalCaseName.toLocaleLowerCase()

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, padding: 12, border: '1px solid var(--border,#e5e7eb)', borderRadius: 12, background: 'var(--card,#f8fafc)' }}>
        {showEDiscoveryName ? <div><strong>eDiscovery Name:</strong><br />{eDiscoveryName}</div> : null}
        <div><strong>Requestor:</strong><br />{requestorLabel(req) || '-'}</div>
        <div><strong>Submitted:</strong><br />{ISODate(req.created_at) || '-'}</div>
        <div><strong>Status:</strong><br /><Badge status={req.status} /></div>
        <div><strong>Request Type:</strong><br />{TYPE_LABELS[req.request_type] || req.request_type}</div>
        {req.reviewed_at ? <div><strong>Reviewed:</strong><br />{ISODate(req.reviewed_at)}</div> : null}
      </div>

      {(payload.legal_case_name || payload.claimant || payload.description || req.note || req.decline_reason) && (
        <div style={{ display: 'grid', gap: 6 }}>
          {legalCaseName ? <div><strong>Legal Case Name:</strong> {legalCaseName}</div> : null}
          {payload.claimant ? <div><strong>Claimant:</strong> {payload.claimant}</div> : null}
          {payload.description ? <div><strong>Description:</strong> <span style={{ whiteSpace: 'pre-wrap' }}>{payload.description}</span></div> : null}
          {req.note ? <div><strong>Note:</strong> <span style={{ whiteSpace: 'pre-wrap' }}>{req.note}</span></div> : null}
          {req.decline_reason ? <div className="error">Declined: {req.decline_reason}</div> : null}
        </div>
      )}

      {req.request_type === 'close_case' && (
        <div style={{ padding: '8px 10px', borderRadius: 8, background: '#FEF3C7', border: '1px solid #FDE68A', color: '#92400E' }}>
          Request to close the case and release all existing holds/preservation.
        </div>
      )}

      <div>
        <h3 style={{ margin: '0 0 8px' }}>Custodians and Preservation</h3>
        {custodians.length ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead style={{ background: 'rgba(15,23,42,0.05)' }}>
                <tr>
                  <th style={{ textAlign: 'left', padding: 8 }}>Custodian</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>Email</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>Preservation Requested</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>NTP</th>
                  <th style={{ textAlign: 'left', padding: 8 }}>Consent</th>
                </tr>
              </thead>
              <tbody>
                {custodians.map((cust, idx) => {
                  const holds = holdLabelsForCustodian(cust)
                  const badges = employmentBadgesFromPayload(cust)
                  return (
                    <tr key={`${req.id}-detail-cust-${idx}`} style={{ borderTop: '1px solid var(--border,#e5e7eb)' }}>
                      <td style={{ padding: 8 }}>
                        {cust.name || 'Unnamed custodian'}
                        {cust.lookup_override ? (
                          <span className="mini-badge" style={{ background: '#e0f2fe', color: '#075985', borderColor: '#bae6fd', marginLeft: 6 }} title="Lookup override">O</span>
                        ) : null}
                        {badges.map((b, i) => (
                          <span
                            key={`${req.id}-detail-cust-${idx}-badge-${i}`}
                            className="mini-badge"
                            style={b.variant === 'danger'
                              ? { background: '#fee2e2', color: '#991b1b', borderColor: '#fecdd3', marginLeft: 6 }
                              : { background: '#fef3c7', color: '#92400e', borderColor: '#fde68a', marginLeft: 6 }}
                            title={b.title || b.label}
                          >
                            {b.label}
                          </span>
                        ))}
                        {cust.notes ? <div style={{ color: '#64748b', fontSize: 12, marginTop: 3 }}>{cust.notes}</div> : null}
                      </td>
                      <td style={{ padding: 8 }}>{cust.email || '-'}</td>
                      <td style={{ padding: 8 }}>{holds.length ? holds.join(', ') : '-'}</td>
                      <td style={{ padding: 8 }}>
                        {cust.ntp_ack ? 'Acknowledged' : (cust.ntp_sent || req.ntp_all_sent ? 'Sent' : '-')}
                      </td>
                      <td style={{ padding: 8 }}>{cust.consent_received ? 'Received' : '-'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ margin: 0, color: '#64748b' }}>No custodians were included in this request.</p>
        )}
      </div>

      {consentProofs.length > 0 && (
        <div>
          <h3 style={{ margin: '0 0 8px' }}>Consent Proofs</h3>
          <ul style={{ marginTop: 0 }}>
            {consentProofs.map((proof) => (
              <li key={`proof-${proof.id}`}>
                {proof.custodian_name || proof.custodian_email || 'Unnamed custodian'}
                <a className="btn secondary" href={`${apiBase}/case_requests/${req.id}/consent_proofs/${proof.id}`} target="_blank" rel="noreferrer" style={{ marginLeft: 8 }}>
                  Download {proof.original_filename || 'proof'}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(req.attachment_name || req.consent_attachment_name) && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {req.attachment_name ? <a className="btn secondary" href={`${apiBase}/case_requests/${req.id}/attachment`} target="_blank" rel="noreferrer">Download uploaded list</a> : null}
          {req.consent_attachment_name ? <a className="btn secondary" href={`${apiBase}/case_requests/${req.id}/consent_attachment`} target="_blank" rel="noreferrer">Download consent documentation</a> : null}
        </div>
      )}

      {versaRequirements ? (
        <div>
          <h3 style={{ margin: '0 0 8px' }}>AI Search Requirements</h3>
          <div style={{ whiteSpace: 'pre-wrap' }}>{versaRequirements}</div>
        </div>
      ) : null}

      {visibleSearches.length ? (
        <div>
          <h3 style={{ margin: '0 0 8px' }}>Search Details</h3>
          {visibleSearches.map((search, idx) => (
            <div key={`${req.id}-detail-search-${idx}`} style={{ marginTop: idx === 0 ? 0 : 12, padding: 10, border: '1px solid var(--border,#e5e7eb)', borderRadius: 10 }}>
              {visibleSearches.length > 1 && <div style={{ fontWeight: 700, marginBottom: 4 }}>Search request {idx + 1}</div>}
              <dl>
                {search.keywords ? <><dt>Keywords</dt><dd>{search.keywords}</dd></> : null}
                {search.senders ? <><dt>Senders</dt><dd>{search.senders}</dd></> : null}
                {search.recipients ? <><dt>Recipients</dt><dd>{search.recipients}</dd></> : null}
                {(search.date_from || search.date_to) ? <><dt>Date Range</dt><dd>{[search.date_from, search.date_to].filter(Boolean).join(' to ')}</dd></> : null}
                {search.additional ? <><dt>Notes</dt><dd>{search.additional}</dd></> : null}
              </dl>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
