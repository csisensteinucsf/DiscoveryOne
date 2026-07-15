import Modal from '../components/Modal.jsx'
import { Button, Field, Select, TextInput } from './caseDetailControls.jsx'

export function CaseDetailAddDocModal({
  open,
  closeDocModal,
  submitConsentDocument,
  docForm,
  handleDocCustodianSelect,
  handleDocFieldChange,
  custodianOptions,
  setDocFile,
  docFile,
  docUploading,
  docUploadError,
}) {
  if (!open) return null
  return (
<Modal
          open
          title="Upload consent proof"
          onClose={closeDocModal}
        >
          <form onSubmit={submitConsentDocument}>
            <Field
              label="Custodian (optional)"
              hint="Select a custodian to pre-fill their details."
            >
              <Select
                value={docForm.custodianId}
                onChange={(e) => handleDocCustodianSelect(e.target.value)}
                disabled={docUploading}
              >
                <option value="">Select a custodian</option>
                {custodianOptions.map(opt => (
                  <option key={opt.id} value={opt.id}>{opt.label}</option>
                ))}
              </Select>
            </Field>
            <Field label="Custodian name">
              <TextInput
                value={docForm.custodianName}
                onChange={(e) => handleDocFieldChange('custodianName', e.target.value)}
                placeholder="Full name"
                disabled={docUploading}
              />
            </Field>
            <Field label="Custodian email">
              <TextInput
                type="email"
                value={docForm.custodianEmail}
                onChange={(e) => handleDocFieldChange('custodianEmail', e.target.value)}
                placeholder="name@example.com"
                disabled={docUploading}
              />
            </Field>
            <Field
              label="Consent document"
              hint="Accepted file types: PDF, MSG, or EML (5 MB max)."
            >
              <input
                type="file"
                accept=".pdf,.msg,.eml"
                onChange={(e) => setDocFile(e.target.files?.[0] || null)}
                disabled={docUploading}
              />
              {docFile ? (
                <div style={{ fontSize: 12, color: '#475467', marginTop: 4 }}>
                  Selected file: {docFile.name}
                </div>
              ) : null}
            </Field>
            {docUploadError && (
              <p style={{ color: '#b91c1c', fontSize: 13 }}>{docUploadError}</p>
            )}
            <div className="row" style={{ justifyContent: 'flex-end', gap: 12, marginTop: 16 }}>
              <Button type="submit" disabled={docUploading}>
                {docUploading ? 'Uploading...' : 'Upload proof'}
              </Button>
              <Button type="button" variant="ghost" onClick={closeDocModal} disabled={docUploading}>
                Cancel
              </Button>
            </div>
          </form>
        </Modal>
  )
}

export function CaseDetailCloseCaseModal({
  open,
  closeCaseBusy,
  setShowCloseCaseModal,
  setCloseCaseNote,
  closeCaseNote,
  submitCloseCaseRequest,
  caseId,
}) {
  if (!open) return null
  return (
<Modal
          open
          title="Request Case Closure"
          onClose={() => { if (closeCaseBusy) return; setShowCloseCaseModal(false); setCloseCaseNote('') }}
          width={540}
          dismissOnBackdrop={false}
          footer={(
            <div style={{ display:'flex', justifyContent:'flex-end', gap:8 }}>
              <button className="btn ghost" type="button" onClick={() => { if (closeCaseBusy) return; setShowCloseCaseModal(false); setCloseCaseNote('') }} disabled={closeCaseBusy}>Cancel</button>
              <button className="btn danger" type="button" onClick={submitCloseCaseRequest} disabled={closeCaseBusy || !caseId}>
                {closeCaseBusy ? 'Submitting...' : 'Submit Request'}
              </button>
            </div>
          )}
        >
          <p style={{ marginTop:0, color:'#475467' }}>
            This will request the eDiscovery team to close the case and release all current holds and preservation. Analysts will review before completing the action.
          </p>
          <label style={{ display:'block', fontSize:13, color:'#475467', marginBottom:6 }}>Optional message to the eDiscovery team</label>
          <textarea
            rows={4}
            value={closeCaseNote}
            onChange={e => setCloseCaseNote(e.target.value)}
            placeholder="Provide any additional context..."
            style={{ width:'100%', border:'1px solid #d1d5db', borderRadius:10, padding:10, fontFamily:'inherit' }}
            disabled={closeCaseBusy}
          />
        </Modal>
  )
}
