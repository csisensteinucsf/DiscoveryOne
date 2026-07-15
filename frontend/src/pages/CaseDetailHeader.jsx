import { Badge } from './caseDetailControls.jsx'

export default function CaseDetailHeader({
  caseData,
  isReadOnly,
  isTech,
  isRequestor,
  analystName,
  formatDate,
  navigate,
  setShowEdit,
  setCustodianModalMode,
  setShowCustodianModal,
  openSendNtp,
  sendingNtp,
  onExportCustodians,
  openPreservationAutomation,
  preservationAutomationEnabled,
  preservationProviderName,
  openCaseSummary,
  toggleClosed,
  ntpButtonDisabled,
  setShowCloseCaseModal,
  useLegalCaseNameAsPrimary = false,
}) {
  const primaryCaseName = useLegalCaseNameAsPrimary ? (caseData?.legal_case_name || caseData?.name) : caseData?.name
  return (
    <>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <h2 style={{ margin: 0, color: 'var(--sidebar-fg)', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span>{caseData ? primaryCaseName : 'Case'}</span>
                {caseData?.is_private ? (
                  <span
                    title="Private Case"
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      minWidth: 18,
                      height: 18,
                      padding: '0 6px',
                      borderRadius: 999,
                      background: '#e0f2fe',
                      border: '1px solid #7dd3fc',
                      color: '#0c4a6e',
                      fontSize: 11,
                      fontWeight: 800,
                      lineHeight: 1,
                    }}
                  >
                    P
                  </span>
                ) : null}
              </h2>
              {caseData?.closed ? <Badge variant="danger">CLOSED</Badge> : null}
            </div>
            {!isReadOnly && (
              <div className="row" style={{ gap: 12, flexWrap: 'wrap' }}>
                <button className="btn secondary" onClick={() => setShowEdit(true)}>Edit Case</button>
                <button
                  className="btn secondary"
                  onClick={() => { setCustodianModalMode('add'); setShowCustodianModal(true) }}
                >
                  Add / Import Custodians
                </button>
                <button className="btn secondary" onClick={openSendNtp} disabled={sendingNtp}>
                  {sendingNtp ? 'Sending...' : 'NTPs'}
                </button>
                <button className="btn secondary" onClick={onExportCustodians}>Export Case to CSV</button>
                {preservationAutomationEnabled && (
                  <button className="btn secondary" onClick={openPreservationAutomation}>
                    {preservationProviderName}
                  </button>
                )}
                <button className="btn secondary" onClick={openCaseSummary}>
                  Case Summary
                </button>
                <button className={caseData?.closed ? 'btn' : 'btn danger'} onClick={toggleClosed}>
                  {caseData?.closed ? 'Reopen Case' : 'Close Case'}
                </button>
              </div>
            )}
          </div>
              <button
                className="btn ghost"
                type="button"
                onClick={() => navigate('/cases')}
                style={{ margin: '12px 0' }}
              >
                {'\u2190'} Back to Cases
              </button>
          {!isTech && !useLegalCaseNameAsPrimary && (
            <p style={{ color: 'var(--text,#0f172a)', opacity: 0.85, fontSize: '0.9rem', marginBottom: 4 }}>
              Legal Case: {caseData?.legal_case_name || '-'}
            </p>
          )}
          {!isTech && (
            <p style={{ color: 'var(--muted,#6b7280)', fontSize: '0.85rem', marginTop: 0, marginBottom: 4 }}>
              Claimant: {caseData?.claimant || '-'}
            </p>
          )}
          <p style={{ color: 'var(--muted,#6b7280)', fontSize: '0.85rem', marginTop: 0, marginBottom: 4 }}>
            Analyst: {analystName || '-'}
          </p>
          <div style={{ color: 'var(--muted,#6b7280)', fontSize: '0.85rem', marginTop: 0, marginBottom: 4 }}>
            Requestors:{' '}
            {Array.isArray(caseData?.requestors) && caseData.requestors.length > 0 ? (
              <span style={{ display: 'inline-flex', gap: 6, flexWrap: 'wrap' }}>
                {caseData.requestors.map((r, idx) => (
                  <span
                    key={`${r.email || idx}`}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '2px 8px',
                      borderRadius: 999,
                      background: r.is_primary ? '#e0f2fe' : '#f3f4f6',
                      color: '#0f172a',
                      fontSize: 12,
                    }}
                  >
                    {r.email || 'unknown'}
                    {r.is_primary && <span style={{ fontWeight: 700, color: '#0f172a' }}>Primary</span>}
                  </span>
                ))}
              </span>
            ) : (
              (caseData?.requestor || '-')
            )}
          </div>
          <p style={{ color: 'var(--muted,#6b7280)', fontSize: '0.85rem', marginTop: 0 }}>
            Created: {caseData?.created_at ? formatDate(caseData.created_at) : '-'}
          </p>
          {caseData?.is_private ? (
            <p style={{ color: '#0c4a6e', fontSize: '0.85rem', marginTop: 0, marginBottom: 0, fontWeight: 700 }}>
              Private Case
            </p>
          ) : null}
          {isRequestor && (
            <div style={{ display:'flex', flexDirection:'column', gap:12, marginTop:12 }}>
              <p style={{ color: '#fbbf24', background:'rgba(251,191,36,.12)', border:'1px solid rgba(251,191,36,.4)', padding:'6px 10px', borderRadius: 8, margin:0 }}>
                Read-only view: requestor accounts cannot modify case data directly.
              </p>
              <div style={{ display:'flex', flexWrap:'wrap', gap:12 }}>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={openSendNtp}
                  disabled={ntpButtonDisabled}
                  style={{ opacity: ntpButtonDisabled ? 0.6 : 1 }}
                >
                  NTPs
                </button>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={openCaseSummary}
                >
                  Case Summary
                </button>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={onExportCustodians}
                >
                  Export Case to CSV
                </button>
                <button
                  className="btn danger"
                  type="button"
                  onClick={() => setShowCloseCaseModal(true)}
                  disabled={caseData?.closed}
                  title={caseData?.closed ? 'Case already closed' : 'Request closure and release of holds'}
                  style={{ opacity: caseData?.closed ? 0.6 : 1 }}
                >
                  Request Case Closure
                </button>
              </div>
            </div>
          )}
          {isTech && (
            <div style={{ display:'flex', flexDirection:'column', gap:12, marginTop:12 }}>
              <p style={{ color: '#1d4ed8', background:'rgba(59,130,246,.1)', border:'1px solid rgba(59,130,246,.35)', padding:'6px 10px', borderRadius: 8, margin:0 }}>
                Ticket-only view: tech accounts can access tickets for their assigned group.
              </p>
            </div>
          )}
    </>
  )
}
