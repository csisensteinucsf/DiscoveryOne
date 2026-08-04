import Modal from '../components/Modal.jsx'
import { Field, Button, InlineSpinner, Badge } from './caseDetailControls.jsx'

export default function CaseDetailSearchStatusModals({
  searchExportModal,
  closeSearchExportModal,
  searchExportProviderName,
  searchQueryLabel,
  detailsSearch,
  setDetailsSearch,
  detailsSearchParsed,
  detailValueStyle,
  custodians,
  blockedConsent,
  setBlockedConsent,
}) {
  return (
    <>
      {searchExportModal.open && (
        <Modal
          open
          title={`Push Search to ${searchExportProviderName}`}
          onClose={closeSearchExportModal}
          width={520}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', width: '100%' }}>
              <Button variant="ghost" onClick={closeSearchExportModal} disabled={searchExportModal.busy}>Close</Button>
            </div>
          )}
        >
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              {searchExportModal.busy ? <InlineSpinner size={18} color="#0284c7" /> : <span style={{ fontSize: 18 }}>{searchExportModal.error ? '!' : 'OK'}</span>}
              <div style={{ fontWeight: 600 }}>{searchExportModal.searchName || 'Search'}</div>
            </div>
            <div style={{ fontSize: 13, color: '#475467' }}>{searchExportModal.message || 'Preparing push request...'}</div>
            {searchExportModal.busy && (
              <div className="btn-pulse" style={{ height: 8, borderRadius: 999, border: '1px solid #bfdbfe', backgroundColor: '#dbeafe' }} />
            )}
            {searchExportModal.error ? (
              <div style={{ fontSize: 13, color: '#b91c1c', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, padding: '8px 10px' }}>
                {searchExportModal.error}
              </div>
            ) : null}
            {!searchExportModal.busy && !searchExportModal.error && searchExportModal.result && (
              <div style={{ fontSize: 12, color: '#334155', display: 'grid', gap: 4 }}>
                <div><strong>{searchExportProviderName} Case ID:</strong> {searchExportModal.result.provider_case_id || searchExportModal.result.purview_case_id || '-'}</div>
                <div><strong>{searchExportProviderName} Search ID:</strong> {searchExportModal.result.provider_search_id || searchExportModal.result.purview_search_id || '-'}</div>
              </div>
            )}
          </div>
        </Modal>
      )}

      {detailsSearch && (
        <Modal
          open
          title={detailsSearch.name + ' - Details'}
          onClose={() => setDetailsSearch(null)}
          width={720}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Button onClick={() => setDetailsSearch(null)}>Close</Button>
            </div>
          )}
        >
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
            <Field label="Keywords"><div style={detailValueStyle}>{detailsSearch.keywords || <em>-</em>}</div></Field>
            <Field label="Search overview"><div style={detailValueStyle}>{detailsSearchParsed.searchOverview || <em>-</em>}</div></Field>
            <Field label="Senders"><div style={detailValueStyle}>{detailsSearch.senders || <em>-</em>}</div></Field>
            <Field label="Recipients"><div style={detailValueStyle}>{detailsSearch.recipients || <em>-</em>}</div></Field>
            <Field label="Date From"><div style={detailValueStyle}>{detailsSearch.dateFrom || <em>-</em>}</div></Field>
            <Field label="Date To"><div style={detailValueStyle}>{detailsSearch.dateTo || <em>-</em>}</div></Field>
            <Field label={searchQueryLabel}><div style={{ ...detailValueStyle, fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>{detailsSearchParsed.providerQuery || <em>-</em>}</div></Field>
            <Field label="Assigned custodians">
              <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                {custodians.filter(c => detailsSearch.custodianIds.includes(c.id)).map(c => (
                  <Badge key={c.id} variant="orange" compact>{c.email || '-'}</Badge>
                ))}
              </div>
            </Field>
          </div>
        </Modal>
      )}

      {blockedConsent && (
        <Modal
          open
          title="Consent required"
          onClose={() => setBlockedConsent(null)}
          width={520}
          footer={(
            <div style={{ display:'flex', justifyContent:'flex-end' }}>
              <Button onClick={() => setBlockedConsent(null)}>Close</Button>
            </div>
          )}
        >
          <p style={{ color: '#475467' }}>
            Consent not received from some custodians for <strong>{blockedConsent.searchName}</strong>.
            Collect consent from everyone assigned to this search, mark consent as Implied with a reason, or upload an AWOC consent document before marking {blockedConsent.field} as performed.
          </p>
          <ul style={{ margin: 0, paddingLeft: 18, color: '#1f2937' }}>
            {blockedConsent.custodians.map(person => (
              <li key={person.id} style={{ marginBottom: 4 }}>
                <strong>{person.name || person.email || 'Unnamed custodian'}</strong>
                {person.email ? ` (${person.email})` : ''} - status: {(person.consent || 'not sent').toLowerCase()}
              </li>
            ))}
          </ul>
        </Modal>
      )}
    </>
  )
}
