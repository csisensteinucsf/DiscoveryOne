import Modal from '../components/Modal.jsx'
import { Badge } from './caseDetailControls.jsx'

export default function CaseDetailCaseSummaryModal({
  open,
  onClose,
  loadCaseSummary,
  emailCaseSummaryToSelf,
  caseSummary,
  caseSummaryData,
  caseSummarySections,
  caseSummaryAi,
  caseSummaryAiAttention,
  caseSummaryAiActions,
  caseSummaryAiHighlights,
  caseData,
  formatDateTime,
  ntpSectionCardStyle,
}) {
  if (!open) return null
  return (
<Modal
          open
          title="Matter Summary"
          onClose={onClose}
          width={980}
          bodyStyle={{ maxHeight: '78vh', overflowY: 'auto' }}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
              <button
                className="btn secondary"
                type="button"
                onClick={loadCaseSummary}
                disabled={caseSummary.loading || caseSummary.emailing}
              >
                {caseSummary.loading ? 'Refreshing...' : 'Refresh'}
              </button>
              <button
                className="btn secondary"
                type="button"
                onClick={emailCaseSummaryToSelf}
                disabled={caseSummary.loading || caseSummary.emailing || !caseSummaryData}
              >
                {caseSummary.emailing ? 'Emailing...' : 'Email report to self'}
              </button>
              <button
                className="btn"
                type="button"
                onClick={onClose}
                disabled={caseSummary.emailing}
              >
                Close
              </button>
            </div>
          )}
        >
          {caseSummary.loading ? (
            <p style={{ margin: 0, color: '#64748b' }}>Building case summary...</p>
          ) : caseSummary.error ? (
            <p style={{ margin: 0, color: '#b91c1c' }}>{caseSummary.error}</p>
          ) : !caseSummaryData ? (
            <p style={{ margin: 0, color: '#64748b' }}>No summary loaded yet.</p>
          ) : (
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={ntpSectionCardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>{caseSummaryData?.case?.name || caseData?.name || 'Matter'}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>Generated: {formatDateTime(caseSummaryData?.generated_at) || '-'}</div>
                  </div>
                  <Badge variant={caseSummaryAiAttention.length ? 'warn' : 'success'} compact>
                    {caseSummaryAiAttention.length ? `${caseSummaryAiAttention.length} AI attention item(s)` : 'No AI attention items'}
                  </Badge>
                </div>
                <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                  <div><strong>Custodians:</strong> {caseSummarySections?.custodians?.total ?? 0}</div>
                  <div><strong>Missing emails:</strong> {caseSummarySections?.custodians?.missing_email ?? 0}</div>
                  <div><strong>Searches:</strong> {caseSummarySections?.searches?.total ?? 0}</div>
                  <div><strong>Consent requests:</strong> {caseSummarySections?.consent?.envelopes_total ?? 0}</div>
                  <div><strong>Open tickets:</strong> {caseSummarySections?.tickets?.open_or_unclassified ?? 0}</div>
                  <div><strong>AI model:</strong> {caseSummaryAi?.model || '-'}</div>
                  <div><strong>Matter phase:</strong> {caseSummaryAi?.case_phase || '-'}</div>
                  <div><strong>AI risk:</strong> {String(caseSummaryAi?.overall_risk || '-').toUpperCase()}</div>
                  <div><strong>AI confidence:</strong> {typeof caseSummaryAi?.confidence === 'number' ? caseSummaryAi.confidence.toFixed(2) : '-'}</div>
                </div>
              </div>

              <div style={ntpSectionCardStyle}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>Needs attention</div>
                {caseSummaryAiAttention.length ? (
                  <div style={{ display: 'grid', gap: 6 }}>
                    {caseSummaryAiAttention.map((item, idx) => (
                      <div key={`summary-attn-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <Badge variant={'warn'} compact>ATTN</Badge>
                        <span style={{ color: '#1f2937', fontSize: 12 }}>{item || '-'}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ margin: 0, color: '#16a34a', fontSize: 12 }}>No outstanding issues flagged by AI.</p>
                )}
              </div>

              {caseSummaryAiActions.length > 0 && (
                <div style={ntpSectionCardStyle}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>Recommended actions</div>
                  <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>
                    {caseSummaryAiActions.map((item, idx) => (
                      <li key={`summary-action-${idx}`} style={{ color: '#1f2937', fontSize: 12 }}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              {caseSummaryAiHighlights.length > 0 && (
                <div style={ntpSectionCardStyle}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>Progress highlights</div>
                  <ul style={{ margin: 0, paddingLeft: 18, display: 'grid', gap: 6 }}>
                    {caseSummaryAiHighlights.map((item, idx) => (
                      <li key={`summary-highlight-${idx}`} style={{ color: '#1f2937', fontSize: 12 }}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={ntpSectionCardStyle}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>AI narrative</div>
                <pre style={{ margin: 0, whiteSpace: 'pre-wrap', lineHeight: 1.45, fontSize: 12, color: '#0f172a' }}>{caseSummaryData?.report_text || ''}</pre>
              </div>
            </div>
          )}
        </Modal>
  )
}
