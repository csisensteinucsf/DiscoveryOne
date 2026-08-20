import { Badge } from './caseDetailControls.jsx'
import { formatCustomFieldValue } from './caseCustomFields.js'

function SummaryItem({ label, children, wide = false }) {
  return (
    <div className={`case-detail-summary__item${wide ? ' case-detail-summary__item--wide' : ''}`}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function RequestorSummary({ caseData }) {
  if (!Array.isArray(caseData?.requestors) || caseData.requestors.length === 0) {
    return caseData?.requestor || '-'
  }

  return (
    <span className="case-detail-summary__requestors">
      {caseData.requestors.map((requestor, index) => (
        <span
          className={`case-detail-summary__requestor${requestor.is_primary ? ' is-primary' : ''}`}
          key={`${requestor.email || index}`}
        >
          {requestor.email || 'unknown'}
          {requestor.is_primary && <span className="case-detail-summary__primary-label">Primary</span>}
        </span>
      ))}
    </span>
  )
}

export default function CaseDetailHeader({
  caseData,
  isReadOnly,
  isTech,
  isRequestor,
  analystName,
  formatDate,
  navigate,
  setShowEdit,
  onExportCustodians,
  openPreservationAutomation,
  preservationAutomationEnabled,
  preservationProviderName,
  openCaseSummary,
  toggleClosed,
  setShowCloseCaseModal,
  useLegalCaseNameAsPrimary = false,
  internalCounselLabel = 'Internal Counsel',
  activeTab,
  onOpenTickets,
  requestsFilledCount = 0,
}) {
  const primaryCaseName = useLegalCaseNameAsPrimary ? (caseData?.legal_case_name || caseData?.name) : caseData?.name
  const customFields = Object.entries(caseData?.custom_fields || {})
  return (
    <>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <h2 style={{ margin: 0, color: 'var(--sidebar-fg)', display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span>{caseData ? primaryCaseName : 'Matter'}</span>
                {caseData?.is_private ? <span className="case-private-badge" title="Private matter">P</span> : null}
                {caseData?.is_test_case ? <span className="case-test-badge" title="Test matter">TEST</span> : null}
              </h2>
              {caseData?.closed ? <Badge variant="danger">INACTIVE</Badge> : <Badge variant="success">ACTIVE</Badge>}
            </div>
            <div className="row case-detail-header__actions" style={{ gap: 12, flexWrap: 'wrap' }}>
              <button
                type="button"
                className={`${activeTab === 'requests' ? 'btn' : 'btn secondary'} case-detail-header__tickets`}
                onClick={onOpenTickets}
                aria-pressed={activeTab === 'requests'}
              >
                Tickets
                {requestsFilledCount > 0 && <span className="case-detail-header__ticket-count">{requestsFilledCount}</span>}
              </button>
              {!isReadOnly && (
                <>
                  <button className="btn secondary" onClick={() => setShowEdit(true)}>Edit Matter</button>
                  <button className="btn secondary" onClick={onExportCustodians}>Export Matter to CSV</button>
                  {preservationAutomationEnabled && (
                    <button className="btn secondary" onClick={openPreservationAutomation}>
                      {preservationProviderName}
                    </button>
                  )}
                  <button className="btn secondary" onClick={openCaseSummary}>
                    Matter Summary
                  </button>
                  <button className={caseData?.closed ? 'btn' : 'btn danger'} onClick={toggleClosed}>
                    {caseData?.closed ? 'Reopen Matter' : 'Close Matter'}
                  </button>
                </>
              )}
            </div>
          </div>
              <button
                className="btn ghost"
                type="button"
                onClick={() => navigate('/cases')}
                style={{ margin: '12px 0' }}
              >
                {'\u2190'} Back to Matters
              </button>
          {!isTech && (
            <section className="case-detail-summary" aria-label="Matter summary">
              <div className="case-detail-summary__group">
                <h3>Matter details</h3>
                <dl className="case-detail-summary__list">
                  {!useLegalCaseNameAsPrimary && (
                    <SummaryItem label="Legal matter">{caseData?.legal_case_name || '-'}</SummaryItem>
                  )}
                  <SummaryItem label="Matter / Claim number">{caseData?.matter_number || '-'}</SummaryItem>
                  <SummaryItem label="Matter type">{caseData?.matter_type || '-'}</SummaryItem>
                  <SummaryItem label="Campus">{caseData?.campus || '-'}</SummaryItem>
                  <SummaryItem label="Start date">{caseData?.start_date ? formatDate(caseData.start_date) : '-'}</SummaryItem>
                  <SummaryItem label="Created">{caseData?.created_at ? formatDate(caseData.created_at) : '-'}</SummaryItem>
                  <SummaryItem label="Last updated">{caseData?.updated_at ? formatDate(caseData.updated_at) : '-'}</SummaryItem>
                </dl>
              </div>

              <div className="case-detail-summary__group">
                <h3>People &amp; access</h3>
                <dl className="case-detail-summary__list">
                  <SummaryItem label="Claimant">{caseData?.claimant || '-'}</SummaryItem>
                  <SummaryItem label={internalCounselLabel}>{caseData?.internal_counsel || '-'}</SummaryItem>
                  <SummaryItem label="Outside counsel">{caseData?.outside_counsel || '-'}</SummaryItem>
                  <SummaryItem label="Analyst">{analystName || '-'}</SummaryItem>
                  <SummaryItem label="Requestors" wide><RequestorSummary caseData={caseData} /></SummaryItem>
                  {caseData?.is_private && <SummaryItem label="Visibility">Private matter</SummaryItem>}
                  {caseData?.is_test_case && <SummaryItem label="Data designation">Test matter</SummaryItem>}
                </dl>
              </div>

              {customFields.length > 0 && (
                <div className="case-detail-summary__group case-detail-summary__group--wide">
                  <h3>Additional information</h3>
                  <dl className="case-detail-summary__list case-detail-summary__list--custom">
                    {customFields.map(([key, field]) => (
                      <SummaryItem label={field?.label || key.replaceAll('_', ' ')} key={key}>
                        {formatCustomFieldValue(field)}
                      </SummaryItem>
                    ))}
                  </dl>
                </div>
              )}

              {caseData?.description ? (
                <div className="case-detail-summary__group case-detail-summary__group--wide">
                  <h3>Additional notes / comments</h3>
                  <p className="case-detail-summary__notes">{caseData.description}</p>
                </div>
              ) : null}
            </section>
          )}
          {isTech && (
            <section className="case-detail-summary case-detail-summary--compact" aria-label="Matter summary">
              <div className="case-detail-summary__group">
                <h3>Matter information</h3>
                <dl className="case-detail-summary__list">
                  <SummaryItem label="Analyst">{analystName || '-'}</SummaryItem>
                  <SummaryItem label="Created">{caseData?.created_at ? formatDate(caseData.created_at) : '-'}</SummaryItem>
                  <SummaryItem label="Requestors" wide><RequestorSummary caseData={caseData} /></SummaryItem>
                </dl>
              </div>
            </section>
          )}
          {isRequestor && (
            <div style={{ display:'flex', flexDirection:'column', gap:12, marginTop:12 }}>
              <p style={{ color: '#fbbf24', background:'rgba(251,191,36,.12)', border:'1px solid rgba(251,191,36,.4)', padding:'6px 10px', borderRadius: 8, margin:0 }}>
                Read-only view: requestor accounts cannot modify matter data directly.
              </p>
              <div style={{ display:'flex', flexWrap:'wrap', gap:12 }}>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={openCaseSummary}
                >
                  Matter Summary
                </button>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={onExportCustodians}
                >
                  Export Matter to CSV
                </button>
                <button
                  className="btn danger"
                  type="button"
                  onClick={() => setShowCloseCaseModal(true)}
                  disabled={caseData?.closed}
                  title={caseData?.closed ? 'Matter already inactive' : 'Request closure and release of holds'}
                  style={{ opacity: caseData?.closed ? 0.6 : 1 }}
                >
                  Request Matter Closure
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
