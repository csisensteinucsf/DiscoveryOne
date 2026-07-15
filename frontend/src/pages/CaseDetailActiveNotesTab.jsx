import NotesPanel from '../components/NotesPanel.jsx'

export default function CaseDetailActiveNotesTab({
  caseId,
  isActiveCase,
  activeCaseBusy,
  toggleActiveCaseStatus,
  showToast,
  setActiveNoteCount,
}) {
  return (
    <div style={{ display: 'grid', gap: 12, width: '100%' }}>
      <div>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 6 }}>Active Case Notes</div>
        <NotesPanel
          caseId={caseId}
          apiSuffix="active_notes"
          readOnly={false}
          notify={(msg) => { showToast(msg) }}
          onCountChange={setActiveNoteCount}
          draftControlsBeforeAttach={(
            <button
              className="btn secondary"
              type="button"
              onClick={toggleActiveCaseStatus}
              disabled={activeCaseBusy}
            >
              {activeCaseBusy
                ? 'Updating...'
                : (isActiveCase ? 'Remove from Active Cases' : 'Add to Active Cases')}
            </button>
          )}
        />
      </div>
    </div>
  )
}
