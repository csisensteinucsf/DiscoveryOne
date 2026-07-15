export default function CaseDetailTabNav({
  activeTab,
  setActiveTab,
  isTech,
  isRequestor,
  isSysAdmin,
  searchCount,
  requestsFilledCount,
  documentationBadgeCount,
  noteCount,
  requestorNoteCount,
  activeNoteCount,
}) {
  return (
<div className="row" style={{ gap: 8, margin: '12px 0' }}>
            <button
              className={activeTab === 'custodians' ? 'btn' : 'btn secondary'}
              onClick={() => setActiveTab('custodians')}
              aria-pressed={activeTab === 'custodians'}
            >
              Custodians
            </button>
            <button
              className={activeTab === 'holds' ? 'btn' : 'btn secondary'}
              onClick={() => setActiveTab('holds')}
              aria-pressed={activeTab === 'holds'}
            >
              Holds
            </button>
            {!isTech && (
              <button
                className={activeTab === 'searches' ? 'btn' : 'btn secondary'}
                onClick={() => setActiveTab('searches')}
                aria-pressed={activeTab === 'searches'}
                style={{ position: 'relative' }}
                aria-label={`Searches (${searchCount})`}
              >
                Searches
                {searchCount > 0 && (
                  <span
                    style={{
                      position:'absolute',
                      top:-6, right:-8,
                      minWidth:16, height:16, padding:'0 5px',
                      borderRadius:9999,
                      background:'var(--accent,#3b82f6)',
                      color:'#fff',
                      fontSize:11, lineHeight:'16px',
                      fontWeight:600,
                      boxShadow:'0 0 0 2px var(--card,#fff)'
                    }}
                  >
                    {searchCount}
                  </span>
                )}
              </button>
            )}
            <button
              className={activeTab === 'requests' ? 'btn' : 'btn secondary'}
              onClick={() => setActiveTab('requests')}
              aria-pressed={activeTab === 'requests'}
              style={{ position: 'relative' }}
            >
              Tickets
              {requestsFilledCount > 0 && (
                <span
                  style={{
                    position:'absolute',
                    top:-6, right:-8,
                    minWidth:16, height:16, padding:'0 5px',
                    borderRadius:9999,
                    background:'var(--accent,#14b8a6)',
                    color:'#fff',
                    fontSize:11, lineHeight:'16px',
                    fontWeight:600,
                    boxShadow:'0 0 0 2px var(--card,#fff)'
                  }}
                >
                  {requestsFilledCount}
                </span>
              )}
            </button>
            {!isTech && (
              <button
                type="button"
                className={activeTab === 'documentation' ? 'btn' : 'btn secondary'}
                onClick={() => setActiveTab('documentation')}
                aria-pressed={activeTab === 'documentation'}
                style={{ position: 'relative' }}
                aria-label={`Consent (${documentationBadgeCount})`}
              >
                Consent
                {documentationBadgeCount > 0 && (
                  <span
                    style={{
                      position:'absolute',
                      top:-6, right:-8,
                      minWidth:16, height:16, padding:'0 5px',
                      borderRadius:9999,
                      background:'var(--accent,#ef4444)',
                      color:'#fff',
                      fontSize:11, lineHeight:'16px',
                      fontWeight:600,
                      boxShadow:'0 0 0 2px var(--card,#fff)'
                    }}
                  >
                    {documentationBadgeCount}
                  </span>
                )}
              </button>
            )}
            {!isTech && (
              <button
                type="button"
                className={activeTab === 'sla' ? 'btn' : 'btn secondary'}
                onClick={() => setActiveTab('sla')}
                aria-pressed={activeTab === 'sla'}
              >
                SLA
              </button>
            )}
            {!isTech && (
              <button
                className={activeTab === 'notes' ? 'btn' : 'btn secondary'}
                onClick={() => setActiveTab('notes')}
                style={{ position:'relative' }}
                aria-label={`Notes (${isRequestor ? requestorNoteCount : (noteCount + requestorNoteCount)})`}
              >
                Notes
                {(isRequestor ? requestorNoteCount : (noteCount + requestorNoteCount)) > 0 && (
                  <span
                    style={{
                      position:'absolute',
                      top:-6, right:-8,
                      minWidth:16, height:16, padding:'0 5px',
                      borderRadius:9999,
                      background:'var(--accent,#ef4444)',
                      color:'#fff',
                      fontSize:11, lineHeight:'16px',
                      fontWeight:600,
                      boxShadow:'0 0 0 2px var(--card,#fff)'
                    }}
                  >
                    {isRequestor ? requestorNoteCount : (noteCount + requestorNoteCount)}
                  </span>
                )}
              </button>
            )}
            {!isTech && !isRequestor && isSysAdmin && (
              <button
                className={activeTab === 'active' ? 'btn' : 'btn secondary'}
                onClick={() => setActiveTab('active')}
                style={{ position:'relative' }}
                aria-label={`Active (${activeNoteCount})`}
              >
                Active
                {activeNoteCount > 0 && (
                  <span
                    style={{
                      position:'absolute',
                      top:-6, right:-8,
                      minWidth:16, height:16, padding:'0 5px',
                      borderRadius:9999,
                      background:'var(--accent,#ef4444)',
                      color:'#fff',
                      fontSize:11, lineHeight:'16px',
                      fontWeight:600,
                      boxShadow:'0 0 0 2px var(--card,#fff)'
                    }}
                  >
                    {activeNoteCount}
                  </span>
                )}
              </button>
            )}
          </div>
  )
}
