import { Minus, Plus } from 'lucide-react'
import FileDropZone from '../components/FileDropZone.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'
import {
  CASE_REQUEST_MAX_MB,
  DEFAULT_LOOKUP_INPUT_PLACEHOLDER,
} from './caseRequestsUtils.js'

export default function CaseRequestIntakeStep({
  useWizard,
  step,
  caseContext,
  isNewCase,
  isSearch,
  isRequestor,
  caseNamingMode,
  form,
  suggesting,
  secondaryCaseNameLabel,
  updateLegalCaseName,
  setForm,
  lookupInputPlaceholder,
  autofillNonce,
  updateCustodian,
  removeCustodianRow,
  addCustodianRow,
  custodianFileBusy,
  loadCustodiansFromUpload,
}) {
  return (
    <>
        {(!useWizard || step === 1) && (
          <>
            <div className="form-section">
              <div className="form-section__title">Matter details</div>
              <div className="form-section__body">
                {caseContext?.name && !isNewCase && (
                  <div className="callout">
                    <strong>Case:</strong> {caseContext.name}
                  </div>
                )}
                {isNewCase && (
                  <div className="form-grid">
                    {!(isRequestor && caseNamingMode === 'legal_case_name') && (
                    <label className="field">
                      <span>eDiscovery Matter Name</span>
                      <input
                        type="text"
                        value={caseNamingMode === 'legal_case_name' ? form.legal_case_name : form.name}
                        placeholder={caseNamingMode === 'created_date' ? 'YYYY-MM-DD' : (caseNamingMode === 'color' ? 'YYYY-Color' : '')}
                        disabled={suggesting}
                        readOnly={caseNamingMode !== 'color' || isRequestor}
                        title={caseNamingMode !== 'color' || isRequestor ? 'This eDiscovery name is generated from the configured naming policy.' : undefined}
                        onChange={(e) => {
                          if (isRequestor || caseNamingMode !== 'color') return
                          setForm((prev) => ({ ...prev, name: e.target.value }))
                        }}
                      />
                      {caseNamingMode !== 'color' || isRequestor ? (
                        <small style={{ color: 'var(--muted,#6b7280)' }}>
                          {caseNamingMode === 'legal_case_name' ? 'Generated from the legal matter name.' : 'Generated from the configured naming policy.'}
                        </small>
                      ) : null}
                    </label>
                    )}
                    <label className="field">
                      <RequiredFieldLabel required={caseNamingMode === 'legal_case_name'}>{secondaryCaseNameLabel}</RequiredFieldLabel>
                      <input type="text" value={form.legal_case_name} onChange={(e) => updateLegalCaseName(e.target.value)} required={caseNamingMode === 'legal_case_name'} />
                    </label>
                    <label className="field">
                      <span>Claimant</span>
                      <input type="text" value={form.claimant} onChange={(e) => setForm((prev) => ({ ...prev, claimant: e.target.value }))} />
                    </label>
                  </div>
                )}
                {!isSearch && (
                  <label className="field field--full">
                    <span>Description / Notes</span>
                    <textarea value={form.description} onChange={(e) => setForm((prev) => ({ ...prev, description: e.target.value }))} rows={3} />
                  </label>
                )}
              </div>
            </div>

            {!isSearch && (
              <div className="form-section">
                <div className="form-section__title">Custodians</div>
                <div className="form-section__body">
                  <p style={{ marginTop: 0, marginBottom: 12, color: '#475569', fontSize: 13 }}>
                    Capture who is involved now. Preservation, NTP, and consent details come on the next step.
                  </p>
                  <div className="field field--full">
                    <span>Custodian Input</span>
                    <div className="radio-row">
                      <label><input type="radio" name="cust-mode" value="manual" checked={form.custodianMode === 'manual'} onChange={() => setForm((prev) => ({ ...prev, custodianMode: 'manual' }))} /> Enter manually</label>
                      <label><input type="radio" name="cust-mode" value="paste" checked={form.custodianMode === 'paste'} onChange={() => setForm((prev) => ({ ...prev, custodianMode: 'paste' }))} /> Paste list</label>
                      <label><input type="radio" name="cust-mode" value="upload" checked={form.custodianMode === 'upload'} onChange={() => setForm((prev) => ({ ...prev, custodianMode: 'upload' }))} /> Upload file</label>
                      <label><input type="radio" name="cust-mode" value="none" checked={form.custodianMode === 'none'} onChange={() => setForm((prev) => ({ ...prev, custodianMode: 'none' }))} /> None yet</label>
                    </div>
                  </div>
                  {form.custodianMode === 'manual' && (
                    <div className="custodian-grid" role="group" aria-label="Manual custodian entries">
                      <p className="request-custodian-help">
                        Enter a full name, email address, or employee ID.
                      </p>
                      {form.custodians.map((c) => (
                        <div key={c.id} className="custodian-card">
                          <div className="custodian-card__header">
                            <div className="custodian-card__grid">
                              <label className="sr-only" htmlFor={`cust-lookup-${c.id}`}>Custodian lookup</label>
                              <input id={`cust-lookup-${c.id}`} type="text" placeholder={lookupInputPlaceholder || DEFAULT_LOOKUP_INPUT_PLACEHOLDER} autoComplete="off" name={`field-${autofillNonce}-${c.id}-lookup`} value={c.name} onChange={(e) => updateCustodian(c.id, { name: e.target.value, email: '' })} required />
                            </div>
                            <div className="request-custodian-row-actions">
                              <button className="icon-button" type="button" onClick={addCustodianRow} title="Add another custodian" aria-label="Add another custodian"><Plus size={17} aria-hidden="true" /></button>
                              <button className="icon-button" type="button" onClick={() => removeCustodianRow(c.id)} disabled={form.custodians.length === 1} title="Remove custodian" aria-label="Remove custodian"><Minus size={17} aria-hidden="true" /></button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {form.custodianMode === 'paste' && (
                    <div className="upload-panel">
                      <label className="sr-only" htmlFor="paste-custodians">Paste custodian list</label>
                      <textarea
                        id="paste-custodians"
                        rows={6}
                        placeholder={'Jane Doe, jane@example.com\nJohn Smith, john@company.com'}
                        value={form.pasteText}
                        onChange={(e) => setForm((prev) => ({ ...prev, pasteText: e.target.value }))}
                        required
                      />
                      <p>Enter one custodian per line with a comma between the name and email, for example: Jane Doe, jane@example.com.</p>
                    </div>
                  )}
                  {form.custodianMode === 'upload' && (
                    <div className="upload-panel">
                      <FileDropZone
                        disabled={custodianFileBusy}
                        onFiles={(files) => {
                          const file = files[0] || null
                          if (!file) return
                          loadCustodiansFromUpload(file)
                        }}
                      >
                      <label className="field field--full">
                        <span>Upload custodian file (CSV/TSV/XLSX)</span>
                        <input
                          type="file"
                          accept=".csv,.tsv,.txt,.xlsx"
                          disabled={custodianFileBusy}
                          required
                          onChange={(e) => {
                            const f = e.target.files?.[0] || null
                            if (!f) {
                              setForm((prev) => ({ ...prev, custodianFile: null, custodians: [] }))
                              return
                            }
                            loadCustodiansFromUpload(f)
                          }} />
                      </label>
                      </FileDropZone>
                      {form.custodianFile && (
                        <div style={{ fontSize: 12, color: '#475569', marginTop: 6 }}>
                          Selected: {form.custodianFile.name} ({Math.max(1, Math.round(form.custodianFile.size / 1024))} KB)
                        </div>
                      )}
                      {custodianFileBusy && (
                        <div style={{ fontSize: 12, color: '#475569', marginTop: 6 }}>
                          Loading custodians from file...
                        </div>
                      )}
                      <p>Upload a CSV/TSV/text file or an .xlsx with name/email/notes columns. Max {CASE_REQUEST_MAX_MB} MB.</p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {isNewCase && isRequestor && (
              <div className="form-section">
                <div className="form-section__body">
                  <div className="case-editor-flags request-intake-flags">
                  <label className="case-editor-flag request-intake-private-flag">
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <input
                        type="checkbox"
                        checked={!!form.is_private}
                        onChange={(e) => setForm((prev) => ({
                          ...prev,
                          is_private: e.target.checked,
                          additional_requestors: e.target.checked ? prev.additional_requestors : '',
                        }))}
                      />
                      <strong style={{ color: '#0f172a' }}>Make case private</strong>
                      <small style={{ color: '#0f766e' }}>
                        Only the listed requestor(s) and system admins can see this matter.
                      </small>
                    </span>
                    {form.is_private && (
                      <span className="field field--full" style={{ margin: 0 }}>
                        <span>Additional requestors</span>
                        <input
                          type="text"
                          value={form.additional_requestors}
                          placeholder="name1@example.edu, name2@example.edu"
                          onChange={(e) => setForm((prev) => ({ ...prev, additional_requestors: e.target.value }))}
                        />
                      </span>
                    )}
                  </label>
                  <label className="case-editor-flag case-editor-flag--test request-intake-test-flag">
                    <input type="checkbox" checked={!!form.is_test_case} onChange={(e) => setForm((prev) => ({ ...prev, is_test_case: e.target.checked }))} />
                    <span>
                      <strong>Test matter</strong>
                      <small>Marks this matter as designated test data.</small>
                    </span>
                  </label>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
    </>
  )
}