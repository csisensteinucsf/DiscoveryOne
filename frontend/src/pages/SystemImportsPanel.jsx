import Modal from '../components/Modal.jsx'
import FileDropZone from '../components/FileDropZone.jsx'

export default function SystemImportsPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  importInputRef,
  importFolderInputRef,
  importFiles,
  importing,
  importStatus,
  importResult,
  importLog,
  importCaseDetails,
  importFinalizeIdx,
  currentFinalizeCase,
  analystOptions,
  onSelectImportFiles,
  onSelectImportFolder,
  clearImportSelection,
  runImport,
  setImportFinalizeIdx,
  updateImportCaseField,
  handleFinalizeAdvance,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can run imports.')
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>Matter Spreadsheet Import</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginBottom: 12 }}>
        Upload individual eDiscovery matter workbooks or select an entire folder. Supported files must be .xlsx or a .zip that contains spreadsheets.
        A detailed report is written to the server for every import.
      </p>
      <FileDropZone
        multiple
        disabled={importing}
        onFiles={(files) => onSelectImportFiles({ target: { files } })}
        prompt="Drag and drop case workbooks here"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <button type="button" className="btn secondary" onClick={() => importInputRef.current && importInputRef.current.click()}>
            Choose file
          </button>
          <button type="button" className="btn secondary" onClick={() => importFolderInputRef.current && importFolderInputRef.current.click()}>
            Choose folder
          </button>
          <input
            type="file"
            accept=".xlsx"
            ref={importInputRef}
            style={{ display: 'none' }}
            onChange={onSelectImportFiles}
          />
          <input
            type="file"
            multiple
            ref={importFolderInputRef}
            style={{ display: 'none' }}
            onChange={onSelectImportFolder}
            webkitdirectory="true"
            directory=""
          />
          <span style={{ color: 'var(--muted,#6b7280)' }}>
            {importFiles.length
              ? `${importFiles.length} item${importFiles.length === 1 ? '' : 's'} selected`
              : 'No files selected'}
          </span>
          {importFiles.length > 0 && (
            <button className="btn" onClick={clearImportSelection}>Clear Selection</button>
          )}
        </div>
      </FileDropZone>
      <div style={{ marginTop: 12 }}>
        <button className="btn secondary" onClick={runImport} disabled={!importFiles.length || importing}>
          {importing ? 'Importing...' : 'Import Selected'}
        </button>
      </div>
      {importStatus && (
        <div style={{ marginTop: 8, color: 'var(--muted,#6b7280)' }}>{importStatus}</div>
      )}
      {importResult && (
        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 14, color: 'var(--muted,#6b7280)', marginBottom: 8 }}>
            Report directory: <code>{importResult.report_dir}</code>
          </div>
          {importResult.log_path && (
            <div style={{ fontSize: 13, color: 'var(--muted,#6b7280)', marginBottom: 8 }}>
              Log file: <code>{importResult.log_path}</code>
            </div>
          )}
          {importResult.report_warnings?.length ? (
            <div style={{ color: '#b45309', background: '#fffbeb', border: '1px solid #fef3c7', padding: 8, borderRadius: 8, marginBottom: 12 }}>
              <strong>Report warnings:</strong>
              <ul style={{ margin: '4px 0 0 16px' }}>
                {importResult.report_warnings.map((warn, idx) => (
                  <li key={`warn-${idx}`}>{warn}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {importLog && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Import status</div>
              <textarea
                readOnly
                value={importLog}
                style={{ width: '100%', minHeight: 160, fontFamily: 'monospace', fontSize: 12, background: 'var(--card,#0f172a)', color: 'var(--text,#e5e7eb)', border: '1px solid var(--border,#e5e7eb)', borderRadius: 8 }}
              />
            </div>
          )}

          {importCaseDetails.length > 0 && (
            <div style={{ marginTop: 16, padding: 16, border: '1px solid var(--border,#e5e7eb)', borderRadius: 12, background: '#f8fafc' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <div style={{ fontWeight: 800, fontSize: 16, color: '#0f172a' }}>Finalize new matters</div>
                <span style={{ color: '#475569', fontSize: 12 }}>{importCaseDetails.length} case{importCaseDetails.length === 1 ? '' : 's'} ready</span>
              </div>
              <p style={{ marginTop: 8, marginBottom: 12, color: '#475569' }}>
                Add missing details before teams start using these imported matters.
              </p>
              <button type="button" className="btn secondary" onClick={() => setImportFinalizeIdx(0)}>
                Review cases
              </button>
            </div>
          )}

          {currentFinalizeCase && (
            <Modal
              open
              title={`Finalize imported case (${(importFinalizeIdx || 0) + 1} of ${importCaseDetails.length})`}
              onClose={() => setImportFinalizeIdx(null)}
              width={520}
              footer={(
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, width: '100%' }}>
                  <button className="btn ghost compact" type="button" onClick={() => setImportFinalizeIdx(null)}>
                    Close
                  </button>
                  <button
                    className="btn"
                    type="button"
                    onClick={handleFinalizeAdvance}
                    disabled={currentFinalizeCase.saving}
                  >
                    {importFinalizeIdx >= importCaseDetails.length - 1 ? (currentFinalizeCase.saving ? 'Submitting...' : 'Submit') : (currentFinalizeCase.saving ? 'Saving...' : 'Save & Next')}
                  </button>
                </div>
              )}
            >
              <div style={{ display: 'grid', gap: 12 }}>
                <div style={{ fontWeight: 700, fontSize: 16 }}>{currentFinalizeCase.name}</div>
                <label className="field field--full">
                  <span>Legal matter name</span>
                  <input
                    value={currentFinalizeCase.legal_case_name}
                    onChange={(e) => updateImportCaseField(currentFinalizeCase.id, 'legal_case_name', e.target.value)}
                    placeholder="e.g., Doe v. Acme"
                  />
                </label>
                <label className="field field--full">
                  <span>Requestor email</span>
                  <input
                    type="email"
                    value={currentFinalizeCase.requestor_email}
                    onChange={(e) => updateImportCaseField(currentFinalizeCase.id, 'requestor_email', e.target.value)}
                    placeholder="requestor@company.com"
                  />
                </label>
                <label className="field field--full">
                  <span>Analyst</span>
                  <select
                    value={currentFinalizeCase.analyst_id || ''}
                    onChange={(e) => updateImportCaseField(currentFinalizeCase.id, 'analyst_id', e.target.value ? Number(e.target.value) : null)}
                  >
                    <option value="">Select analyst</option>
                    {analystOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </label>
                <label className="field field--full">
                  <span>Claimant</span>
                  <input
                    value={currentFinalizeCase.claimant}
                    onChange={(e) => updateImportCaseField(currentFinalizeCase.id, 'claimant', e.target.value)}
                    placeholder="Claimant"
                  />
                </label>
                {currentFinalizeCase.status && (
                  <div style={{ fontSize: 12, color: currentFinalizeCase.status === 'Saved' ? '#16a34a' : '#475569' }}>
                    {currentFinalizeCase.status}
                  </div>
                )}
              </div>
            </Modal>
          )}

          <div className="table-responsive">
            <table className="table users-table">
              <thead>
                <tr>
                  <th>File</th>
                  <th>Matter</th>
                  <th>Status</th>
                  <th>Custodians</th>
                  <th>Searches</th>
                </tr>
              </thead>
              <tbody>
                {importResult.files?.map((item, idx) => (
                  <tr key={`${item.filename}-${idx}`}>
                    <td className="users-table__actions">{item.filename}</td>
                    <td>{item.case_name || ''}</td>
                    <td style={{ textTransform: 'capitalize' }}>{item.status}</td>
                    <td>
                      +{item.custodians_created || 0} / upd {item.custodians_updated || 0} / skip {item.custodians_skipped || 0}
                    </td>
                    <td>
                      +{item.searches_created || 0} / upd {item.searches_updated || 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {importResult.files?.map((item, idx) => {
            const hasDetails = (item.warnings?.length || item.errors?.length || item.unmapped_fields?.length)
            if (!hasDetails) return null
            return (
              <div key={`details-${idx}`} style={{ marginTop: 8, borderTop: '1px solid var(--border,#e5e7eb)', paddingTop: 8 }}>
                {item.warnings?.length ? (
                  <div style={{ color: '#b45309' }}>
                    <strong>Warnings:</strong>
                    <ul>
                      {item.warnings.map((warn, i) => <li key={`warn-${idx}-${i}`}>{warn}</li>)}
                    </ul>
                  </div>
                ) : null}
                {item.errors?.length ? (
                  <div style={{ color: '#b91c1c' }}>
                    <strong>Errors:</strong>
                    <ul>
                      {item.errors.map((err, i) => <li key={`err-${idx}-${i}`}>{err}</li>)}
                    </ul>
                  </div>
                ) : null}
                {item.unmapped_fields?.length ? (
                  <div style={{ color: 'var(--muted,#6b7280)' }}>
                    <strong>Unmapped fields:</strong> {item.unmapped_fields.join(', ')}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
