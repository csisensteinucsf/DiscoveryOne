import { CASE_REQUEST_CONSENT_MAX_MB, lookupPersonName, lookupPersonId } from './caseRequestsUtils.js'

export default function CaseRequestPreservationStep({
  useWizard,
  isSearch,
  step,
  lookupStatus,
  lookupError,
  form,
  displayedCustodians,
  configuredRequestHoldOptions,
  normalizeHolds,
  holdOpen,
  setHoldOpen,
  lookupMatches,
  selectedMatchFor,
  badgesForMatch,
  lookupSelection,
  handleSelectMatch,
  endDateStyle,
  updateCustodian,
  removeCustodianRow,
  toggleLookupOverride,
  handleNtpUpdate,
  handleProofFile,
  handleHoldChange,
  applyHoldsToAll,
  applyNtpToAll,
  custodianProofFiles,
  missingProofs,
}) {
  return (
    <>
        {useWizard && !isSearch && step === 2 && (
          <div className="form-section">
            <div className="form-section__title">Preservation, NTP, and consent</div>
            <div className="form-section__body">
              <p style={{ marginTop: 0, marginBottom: 12, color: '#475569', fontSize: 13 }}>
                Review each custodian and add the right preservation, NTP, or consent details before moving on.
              </p>
              {(lookupStatus === 'loading' && useWizard) && (
                <div className="lookup-status" role="status">Pulling person info about custodians...</div>
              )}
              {lookupStatus === 'error' && (
                <div className="error">Lookup failed: {lookupError}</div>
              )}
              {form.custodianMode === 'upload' && !displayedCustodians.length ? (
                <div className="callout">
                  Custodians from the uploaded file cannot be previewed here. Attach the file on the previous step and continue.
                </div>
              ) : form.custodianMode === 'none' ? (
                <div className="callout">
                  No custodians were provided for this request.
                </div>
              ) : !displayedCustodians.length ? (
                <div className="callout">
                  Add custodians on the first step to set preservation, NTP, or consent details.
                </div>
              ) : (
                <div className="custodian-grid" role="group" aria-label="Custodian preservation and notice choices">
                  {displayedCustodians.map((c) => {
                    const currentHolds = normalizeHolds(c.holds)
                    const holdsOpen = holdOpen[c.id] || configuredRequestHoldOptions.some(([field]) => currentHolds[field])
                    const entry = lookupMatches[String(c.id)] || lookupMatches[c.id] || {}
                    const selectedMatch = selectedMatchFor(c.id)
                    const badges = badgesForMatch(selectedMatch)
                    const noMatches = Array.isArray(entry.matches) && entry.matches.length === 0 && !entry.error
                    return (
                      <div
                        key={c.id}
                        className="custodian-card"
                        style={noMatches && !c.override_lookup ? { background: '#fee2e2', borderColor: '#fca5a5' } : undefined}
                      >
                        <div className="custodian-card__header" style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                              <div style={{ minWidth: 0 }}>
                                <div style={{ fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                  {c.name || c.email}
                                  {badges.map((b, idx) => (
                                    <span
                                      key={`${c.id}-badge-${idx}`}
                                      className="mini-badge"
                                      title={b.title}
                                  style={b.variant === 'danger'
                                    ? { background: '#fee2e2', color: '#991b1b', borderColor: '#fecdd3' }
                                    : { background: '#fef3c7', color: '#92400e', borderColor: '#fde68a' }}
                                >{b.label}</span>
                              ))}
                                </div>
                                {c.email ? <div style={{ fontSize: 13, color: '#475569', wordBreak: 'break-word' }}>{c.email}</div> : null}
                              </div>
                              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                                <button className="btn ghost" type="button" onClick={() => removeCustodianRow(c.id)} disabled={displayedCustodians.length === 1 && form.custodianMode === 'manual'}>
                                  Remove
                                </button>
                                <button
                                  className="btn secondary"
                                  type="button"
                                  onClick={() => toggleLookupOverride(c)}
                                >
                                  {c.override_lookup ? 'Disable override' : 'Override lookup'}
                                </button>
                              </div>
                            </div>
                            {selectedMatch && !c.override_lookup && (
                              <div className="lookup-panel lookup-panel--small">
                                <div className="lookup-panel__title">
                                  {lookupPersonName(selectedMatch)}{lookupPersonId(selectedMatch) ? ' (' + lookupPersonId(selectedMatch) + ')' : ''}
                                </div>
                                <div className="lookup-panel__meta">
                                  {selectedMatch.email ? `Email: ${selectedMatch.email}` : 'Email not found'}
                                  {selectedMatch.department_name ? ` | Dept: ${selectedMatch.department_name}` : null}
                                  {selectedMatch.employee_end_date ? (
                                    <span style={endDateStyle(selectedMatch)}>{` | End: ${selectedMatch.employee_end_date}`}</span>
                                  ) : null}
                                </div>
                              </div>
                            )}
                            {entry.error && !c.override_lookup && (
                              <div className="error" style={{ marginTop: 6 }}>
                                Lookup error: {entry.error}
                              </div>
                            )}
                            {noMatches && !entry.error && !c.override_lookup && (
                              <div style={{ marginTop: 6, fontSize: 12, color: '#92400e' }}>
                                No person lookup match found for this custodian.
                              </div>
                            )}
                          </div>
                        </div>
{c.override_lookup && (
                          <div style={{ marginTop: 8 }}>
                            <div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>
                              Person lookup overridden. Enter the final name/email to include with this request.
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                              <label className="field">
                                <span>Name</span>
                                <input
                                  type="text"
                                  name={`override-name-${c.id}`}
                                  value={c.name}
                                  onChange={(e) => updateCustodian(c.id, { name: e.target.value })}
                                  autoComplete="off"
                                />
                              </label>
                              <label className="field">
                                <span>Email</span>
                                <input
                                  type="email"
                                  name={`override-email-${c.id}`}
                                  value={c.email}
                                  onChange={(e) => updateCustodian(c.id, { email: e.target.value })}
                                  autoComplete="off"
                                />
                              </label>
                            </div>
                          </div>
                        )}
                        {!c.override_lookup && Array.isArray(entry.matches) && entry.matches.length > 1 && (
                          <div className="lookup-panel">
                            <div className="lookup-panel__title">Multiple matches found. Select the correct custodian.</div>
                            <div className="lookup-options">
                              {entry.matches.map((m, idx) => (
                                <label key={`${c.id}-opt-${idx}`} className="lookup-option">
                                  <input type="radio" name={`lookup-${c.id}`} checked={lookupSelection[String(c.id)] === idx} onChange={() => handleSelectMatch(c.id, idx)} />
                                  <div>
                                    <div style={{ fontWeight: 600 }}>
                                      {lookupPersonName(m)}{lookupPersonId(m) ? ' (' + lookupPersonId(m) + ')' : ''}
                                    </div>
                                    <div className="lookup-option__meta">
                                      {m.department_name ? `Dept: ${m.department_name}` : 'Dept: Unknown'}
                                      {m.employee_end_date ? <span style={endDateStyle(m)}>{` | End: ${m.employee_end_date}`}</span> : ''}
                                      {m.email ? ` | Email: ${m.email}` : ''}
                                    </div>
                                  </div>
                                </label>
                              ))}
                            </div>
                          </div>
                        )}

                        <div className="action-chip-row">
                          <button
                            type="button"
                            className={`action-chip ${holdsOpen ? 'is-active' : ''}`}
                            onClick={() => setHoldOpen((prev) => ({ ...prev, [c.id]: !holdsOpen }))}
                            aria-pressed={holdsOpen}
                          >
                            Add preservation request
                          </button>
                          <button
                            type="button"
                            className={`action-chip ${c.ntp_sent ? 'is-active' : ''}`}
                            onClick={() => handleNtpUpdate(c.id, !c.ntp_sent, false)}
                            aria-pressed={!!c.ntp_sent}
                          >
                            NTP already sent
                          </button>
                          <button
                            type="button"
                            className={`action-chip ${c.consent_received ? 'is-active' : ''}`}
                            onClick={() => {
                              const next = !c.consent_received
                              updateCustodian(c.id, { consent_received: next })
                              if (!next) handleProofFile(c.id, null)
                            }}
                            aria-pressed={!!c.consent_received}
                          >
                            Consent already received
                          </button>
                        </div>

                        {holdsOpen && (
                          <div className="holds">
                            <div className="holds-heading">What do you need preserved at this time?</div>
                            {configuredRequestHoldOptions.map(([field, label]) => (
                              <label key={field}>
                                <input
                                  type="checkbox"
                                  checked={!!currentHolds[field]}
                                  onChange={(e) => handleHoldChange(c.id, field, e.target.checked)}
                                /> {label}
                              </label>
                            ))}
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                              <button className="btn ghost" type="button" onClick={() => applyHoldsToAll({})}>
                                Clear all
                              </button>
                              <button className="btn secondary" type="button" onClick={() => applyHoldsToAll(currentHolds)}>
                                Apply to all
                              </button>
                            </div>
                          </div>
                        )}

                        {c.ntp_sent && (
                          <div className="custodian-card__status">
                            <label>
                              <input
                                type="radio"
                                name={`ntp-${c.id}`}
                                checked={c.ntp_sent && !c.ntp_ack}
                                onChange={() => handleNtpUpdate(c.id, true, false)}
                              />
                              Sent but not yet acknowledged
                            </label>
                            <label>
                              <input
                                type="radio"
                                name={`ntp-${c.id}`}
                                checked={!!c.ntp_ack}
                                onChange={() => handleNtpUpdate(c.id, true, true)}
                              />
                              Sent and acknowledged
                            </label>
                            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
                              <button className="btn ghost" type="button" onClick={() => handleNtpUpdate(c.id, false, false)}>
                                Clear
                              </button>
                              <button className="btn secondary" type="button" onClick={() => applyNtpToAll(true, !!c.ntp_ack)}>
                                Apply to all
                              </button>
                            </div>
                          </div>
                        )}

                        {c.consent_received && (
                          <label className="field field--full custodian-card__proof">
                            <span>Attach consent proof (MSG/EML or PDF)</span>
                            <input
                              type="file"
                              accept=".msg,.eml,.pdf"
                              onChange={(e) => handleProofFile(c.id, e.target.files?.[0] || null)}
                            />
                            <p style={{ margin: '4px 0', color: '#475467', fontSize: 12 }}>
                              Max {CASE_REQUEST_CONSENT_MAX_MB} MB per file.
                            </p>
                            {custodianProofFiles[c.id] && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                                <small>{custodianProofFiles[c.id].name}</small>
                                <button className="btn ghost" type="button" onClick={() => handleProofFile(c.id, null)}>Remove</button>
                              </div>
                            )}
                            {missingProofs && !custodianProofFiles[c.id] && (
                              <p style={{ margin: 0, color: '#b91c1c', fontSize: 12 }}>Proof required for this custodian.</p>
                            )}
                          </label>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        )}
    </>
  )
}

