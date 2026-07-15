import NotesPanel from '../components/NotesPanel.jsx'

export default function CaseDetailTicketNotesTab({
  isTech,
  runTicketSelfHeal,
  ticketSelfHealBusy,
  caseId,
  showToast,
}) {
  return (
<div style={{ marginTop: 12, display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>Ticket Notes</div>
              {!isTech && (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>
                    If you believe you had previously created tickets that are no longer showing, use this tool to review the backend logs and restore old tickets.
                  </div>
                  <div>
                    <button
                      className="btn secondary"
                      type="button"
                      onClick={runTicketSelfHeal}
                      disabled={ticketSelfHealBusy}
                      style={{ padding: '6px 10px', borderRadius: 10, fontSize: 12, width: 'fit-content' }}
                    >
                      {ticketSelfHealBusy ? 'Restoring...' : 'Ticket self heal'}
                    </button>
                  </div>
                </div>
              )}
              <NotesPanel
                caseId={caseId}
                apiSuffix="ticket_notes"
                readOnly={false}
                notify={(msg) => { showToast(msg) }}
              />
            </div>
  )
}
