import { Badge, Button } from './caseDetailControls.jsx'

export default function CaseDetailDocumentationTab({
  isRequestor,
  custodians,
  setShowConsentModal,
  consentsLoading,
  consentsError,
  consents,
  consentRequestTracker,
  consentActionBusy,
  consentDownloadBusyId,
  formatDateTime,
  resendConsent,
  voidConsent,
  downloadConsent,
  canManageDocs,
  openDocModal,
  docsLoading,
  docsError,
  proofs,
  formatFileSize,
  deletingProofId,
  handleDeleteProof,
  esignDisplayName = 'e-signature provider',
}) {
  return (
<div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 16, alignItems: "start", pointerEvents: isRequestor ? "none" : "auto", opacity: isRequestor ? 0.95 : 1 }}>
              <section className="card" style={{ padding: 16, width: '100%' }}>
                <h3 style={{ marginTop: 0, marginBottom: 4 }}>Request consent</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <p style={{ color: '#475467', fontSize: 14, margin: 0, flex: '1 1 auto' }}>
                    Send consent requests through the configured e-signature provider. Each selected custodian receives a separate request. Completed consents are tracked below.
                  </p>
                  {!isRequestor && (
                    <Button onClick={() => setShowConsentModal(true)} disabled={!custodians.length}>
                      Send consent with {esignDisplayName}
                    </Button>
                  )}
                </div>
                <div style={{ marginTop: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <h4 style={{ margin: 0 }}>Consents sent</h4>
                    {consentsLoading && <span style={{ fontSize: 12, color: '#6b7280' }}>Refreshing...</span>}
                  </div>
                  {!consentsError && consents.length > 0 && (
                    <div style={{ marginTop: 8, padding: '10px 12px', borderRadius: 10, background: '#eff6ff', color: '#1d4ed8', fontSize: 13, fontWeight: 600 }}>
                      {consentRequestTracker.total > 0
                        ? `${consentRequestTracker.completed}/${consentRequestTracker.total} custodians requested consent completed${consentRequestTracker.remaining > 0 ? ` (${consentRequestTracker.remaining} left)` : ' (all completed)'}`
                        : 'No active consent requests remain.'}
                    </div>
                  )}
                  {consentsError ? (
                    <p style={{ color: '#b91c1c' }}>{consentsError}</p>
                  ) : !consents.length ? (
                    <p style={{ color: '#6b7280', marginTop: 8 }}>No e-signature consent requests sent yet.</p>
                  ) : (
                    <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {consents.map((c) => {
                      const requestId = c.request_id || c.envelope_id
                      const custodian = custodians.find(x => Number(x.id) === Number(c.custodian_id))
                      const email = c.custodian_email || custodian?.email || 'Unknown custodian'
                      const rawStatus = (c.status || 'pending')
                      const status = rawStatus.replace(/_/g, ' ')
                      const statusVariant = (() => {
                        const s = rawStatus.toLowerCase()
                        if (s === 'completed' || s === 'received') return 'success'
                        if (s === 'sent') return 'warn'
                        return 'default'
                      })()
                      const disabled = consentActionBusy.id === c.id
                      const isCompleted = ['completed', 'received'].includes(rawStatus.toLowerCase())
                      const proofDownloaded = Boolean(c.proof_downloaded)
                      const isVoided = rawStatus.toLowerCase() === 'voided'
                      const downloadBusy = consentDownloadBusyId === c.id
                      const resentAt = c.last_resent_at ? formatDateTime(c.last_resent_at) : null
                      const displayStatus = proofDownloaded && isCompleted ? 'downloaded' : (status || 'pending')
                      const displayVariant = proofDownloaded && isCompleted ? 'success' : statusVariant
                      return (
                        <div key={c.id || `${email}-${requestId || 'pending'}`} style={{ padding: 12, border: '1px solid var(--border, #e5e7eb)', borderRadius: 10, background: 'var(--card, #fff)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                            <Badge variant="orange" compact>{email}</Badge>
                            <Badge variant={displayVariant} compact>{displayStatus}</Badge>
                          </div>
                          <div style={{ marginTop: 6, fontSize: 12, color: '#475467' }}>
                            Request ID: {requestId || 'Pending'}
                          </div>
                          {resentAt && (
                            <div style={{ marginTop: 4, fontSize: 12, color: '#0f172a' }}>
                              <Badge variant="subtle" compact>Resent {resentAt}</Badge>
                            </div>
                          )}
                          {!isCompleted && !isVoided && (
                            <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                              <Button
                                variant="secondary"
                                disabled={disabled}
                                onClick={() => resendConsent(c)}
                              >
                                {disabled && consentActionBusy.type === 'resend' ? 'Resending?' : 'Resend'}
                              </Button>
                              <Button
                                variant="ghost"
                                disabled={disabled}
                                onClick={() => voidConsent(c)}
                              >
                                {disabled && consentActionBusy.type === 'void' ? 'Voiding?' : 'Void'}
                              </Button>
                            </div>
                          )}
                          {requestId && isCompleted && !proofDownloaded && (
                            <div style={{ marginTop: 10 }}>
                              <Button
                                variant="ghost"
                                disabled={downloadBusy}
                                onClick={() => downloadConsent(c)}
                              >
                                {downloadBusy ? 'Downloading...' : 'Download completed consent'}
                              </Button>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
                </div>
              </section>
              <section className="card" style={{ padding: 16, width: '100%' }}>
                <h3 style={{ marginTop: 0, marginBottom: 4 }}>Consent Proof</h3>
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <p style={{ color: '#475467', fontSize: 14, margin: 0, flex: '1 1 auto' }}>
                    Upload or review consent proof files submitted by custodians. Download files that were submitted through requests or uploaded directly here.
                  </p>
                  {canManageDocs && (
                    <Button onClick={openDocModal}>
                      Upload consent proof
                    </Button>
                  )}
                </div>
                <div style={{ marginTop: 16 }}>
                  {docsLoading ? (
                    <p>Loading documentation...</p>
                  ) : docsError ? (
                    <p style={{ color: '#b91c1c' }}>{docsError}</p>
                  ) : !proofs.length ? (
                    <p>No consent proofs are available for this case yet.</p>
                  ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
                      {proofs.map((proof) => {
                        const metadata = []
                        if (proof.original_filename) metadata.push(proof.original_filename)
                        if (proof.size) metadata.push(formatFileSize(proof.size))
                        if (proof.hold_name) metadata.push(`Hold: ${proof.hold_name}`)
                        const uploader = proof?.uploaded_by?.email || proof?.uploaded_by?.username || ''
                        const timeline = []
                        if (proof.uploaded_at) timeline.push(`Uploaded ${formatDateTime(proof.uploaded_at)}`)
                        if (uploader) timeline.push(`by ${uploader}`)
                        timeline.push(
                          proof.source === 'case_request'
                            ? 'via case request'
                            : (proof.source === 'manual' ? 'uploaded manually' : `downloaded from ${esignDisplayName}`)
                        )
                        const disableDelete = deletingProofId === proof.id
                        return (
                          <li key={proof.id} style={{ padding: 12, border: '1px solid #e5e7eb', borderRadius: 10 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                              <div>
                                <div style={{ fontWeight: 600 }}>
                                  {proof.custodian_name || proof.custodian_email || 'Custodian proof'}
                                  {proof.custodian_email && proof.custodian_name ? (
                                    <span style={{ color: '#6b7280', fontWeight: 400 }}> - {proof.custodian_email}</span>
                                  ) : null}
                                </div>
                                {metadata.length ? (
                                  <div style={{ fontSize: 13, color: '#475467', marginTop: 4 }}>
                                    {metadata.join(' | ')}
                                  </div>
                                ) : null}
                                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                                  {timeline.join(' | ')}
                                </div>
                              </div>
                              <div style={{ display: 'flex', gap: 8 }}>
                                <a
                                  href={proof.url || '#'}
                                  target="_blank"
                                  rel="noreferrer"
                                  style={{ pointerEvents: proof.url ? 'auto' : 'none', opacity: proof.url ? 1 : 0.6 }}
                                >
                                  Download
                                </a>
                                {canManageDocs && !proof.case_request_id && (
                                  <button
                                    className="btn ghost"
                                    type="button"
                                    onClick={() => handleDeleteProof(proof)}
                                    disabled={disableDelete}
                                  >
                                    {disableDelete ? 'Removing...' : 'Remove'}
                                  </button>
                                )}
                              </div>
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              </section>
            </div>
  )
}
