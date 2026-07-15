import NotesPanel from '../components/NotesPanel.jsx'

export default function CaseDetailNotesTab({ caseId, isRequestor, showToast, setNoteCount, setRequestorNoteCount }) {
  return (
<div style={{ display: 'grid', gap: 12, width: '100%' }}>
              {!isRequestor && (
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>Internal Notes</div>
                  <NotesPanel
                    caseId={caseId}
                    apiSuffix="notes"
                    readOnly={false}
                    notify={(msg) => { showToast(msg) }}
                    onCountChange={setNoteCount}
                  />
                </div>
              )}
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>Requestor Notes</div>
                <NotesPanel
                  caseId={caseId}
                  apiSuffix="requestor_notes"
                  readOnly={false}
                  notify={(msg) => { showToast(msg) }}
                  onCountChange={setRequestorNoteCount}
                />
              </div>
            </div>
  )
}
