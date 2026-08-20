import Modal from '../components/Modal.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import { TextInput } from './caseDetailControls.jsx'
import { formatNameRaw, REMINDER_INTERVAL_DEFAULT, REMINDER_DURATION_DEFAULT } from './caseDetailUtils.js'
import NtpHistoryModal from './NtpHistoryModal.jsx'
import NtpReminderModals from './NtpReminderModals.jsx'

export default function CaseDetailNtpModals({
  showSendNtpModal,
  closeSendNtp,
  previewNtpNotice,
  ntpPreview,
  setNtpPreview,
  sendingNtp,
  sendNtpNotices,
  selectedTemplateId,
  setSelectedTemplateId,
  ntpSelection,
  ntpHolds,
  ntpHoldsLoading,
  ntpTemplatesLoading,
  ntpHoldId,
  setNtpHoldId,
  ntpModalScrollStyle,
  ntpFieldLabelStyle,
  ntpSelectStyle,
  ntpTemplates,
  selectedReminderTemplateId,
  setSelectedReminderTemplateId,
  setReminderIntervalDays,
  setReminderDurationDays,
  reminderIntervalDays,
  reminderDurationDays,
  openNtpHistoryModal,
  lastNtpSend,
  copyPreviousNtpData,
  ntpVariables,
  setNtpVariables,
  ntpReasonTouchedRef,
  ntpOutsideCounselHistory,
  reminderSummary,
  ntpSectionCardStyle,
  ntpHelperTextStyle,
  openReminderListModal,
  ntpRemindersLoading,
  ntpSearch,
  setNtpSearch,
  filteredNtpCustodians,
  toggleNtpSelection,
  ntpStatusLabel,
  showNtpHistoryModal,
  setShowNtpHistoryModal,
  ntpHistory,
  ntpHistoryExporting,
  ntpHistoryEmailing,
  exportNtpHistoryCsv,
  emailNtpHistoryReport,
  loadNtpHistory,
  ntpHistoryCustodianRows,
  ntpHistoryEvents,
  formatDateTime,
  showReminderListModal,
  setShowReminderListModal,
  canEditReminders,
  eligibleReminderReactivationCustodianIds,
  reactivateEligibleCancelledNtpReminders,
  reactivatingNtpRemindersBulk,
  reminderGroups,
  reactivatingNtpReminders,
  openReminderEditor,
  reactivateCancelledNtpReminders,
  ntpBlockedModal,
  setNtpBlockedModal,
  reminderEditor,
  closeReminderEditor,
  saveReminderEditor,
  setReminderEditor,
  reminderTemplateNames,
  activeReminderCustodianIds,
  editorPrimaryReminder,
}) {
  return (
    <>
      {showSendNtpModal && (
        <>
        <Modal
          open
          title="Send NTP Notices"
          onClose={closeSendNtp}
          width={860}
          footer={(
            <>
              <button className="btn" onClick={closeSendNtp}>Cancel</button>
              <button
                className="btn secondary"
                type="button"
                onClick={previewNtpNotice}
                disabled={ntpPreview.loading || sendingNtp}
              >
                {ntpPreview.loading ? 'Previewing...' : 'Preview NTP'}
              </button>
              <button
                className="btn primary"
                onClick={sendNtpNotices}
                disabled={sendingNtp || !ntpHoldId || !selectedTemplateId || !ntpSelection.length}
              >
                {sendingNtp ? 'Sending...' : 'Send Notices'}
              </button>
            </>
          )}
        >
          <div style={ntpModalScrollStyle}>
            {!ntpHoldsLoading && !ntpHolds.length && (
              <div className="alert warn">
                No active Holds are available. Create a Hold and assign custodians before sending an NTP.
              </div>
            )}
            {!ntpTemplatesLoading && !ntpTemplates.length && (
              <div className="alert warn">
                No NTP templates are available. Ask a system administrator to create one or grant access.
              </div>
            )}
            <div
              className="form-grid"
              style={{ display:'grid', gap:12, gridTemplateColumns:'repeat(auto-fit, minmax(220px, 1fr))', marginTop:8 }}
            >
              <label style={{ ...ntpFieldLabelStyle, gridColumn: '1 / -1' }}>
                <span>Hold</span>
                <select
                  value={ntpHoldId || ''}
                  onChange={e => setNtpHoldId(Number(e.target.value) || null)}
                  style={ntpSelectStyle}
                  disabled={ntpHoldsLoading}
                >
                  <option value="">Select a hold</option>
                  {ntpHolds.map(hold => (
                    <option key={hold.id} value={hold.id}>{hold.name} ({hold.custodian_count || 0} custodians)</option>
                  ))}
                </select>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                  NTP recipients, reminders, acknowledgments, and history are tracked separately for each hold.
                </div>
              </label>
              <label style={{ ...ntpFieldLabelStyle, gridColumn: '1 / -1' }}>
                <span>Template</span>
                <select
                  value={selectedTemplateId || ''}
                  onChange={e => setSelectedTemplateId(Number(e.target.value) || null)}
                  style={ntpSelectStyle}
                >
                  <option value="">Select a template</option>
                  {ntpTemplates.map(t => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </label>
              <div style={{ gridColumn: '1 / -1', fontSize: 12, color: '#64748b', marginTop: -2 }}>
                Archive copy: <strong>{ntpTemplates.find(t => Number(t?.id) === Number(selectedTemplateId))?.archive_copy_address || 'Not configured'}</strong>. This address will receive a copy of all NTPs for archive purposes when configured.
              </div>
              <label style={{ ...ntpFieldLabelStyle, gridColumn: '1 / -1' }}>
                <span>Reminder Template</span>
                <select
                  value={selectedReminderTemplateId || ''}
                  onChange={e => {
                    const val = Number(e.target.value) || null
                    setSelectedReminderTemplateId(val)
                    if (val) {
                      setReminderIntervalDays(REMINDER_INTERVAL_DEFAULT)
                      setReminderDurationDays(REMINDER_DURATION_DEFAULT)
                    }
                  }}
                  style={ntpSelectStyle}
                >
                  <option value="">Do not send reminders</option>
                  {ntpTemplates.map(t => (
                    <option key={`rem-${t.id}`} value={t.id}>{t.name}</option>
                  ))}
                </select>
                {selectedReminderTemplateId ? (
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 8 }}>
                    <label style={{ ...ntpFieldLabelStyle, margin: 0 }}>
                      <span>Reminder every (days)</span>
                      <input
                        type="number"
                        min="1"
                        value={reminderIntervalDays}
                        onChange={e => setReminderIntervalDays(e.target.value)}
                        style={{ ...ntpSelectStyle, width: '140px' }}
                      />
                    </label>
                    <label style={{ ...ntpFieldLabelStyle, margin: 0 }}>
                      <span>Reminders for (days)</span>
                      <input
                        type="number"
                        min="1"
                        value={reminderDurationDays}
                        onChange={e => setReminderDurationDays(e.target.value)}
                        style={{ ...ntpSelectStyle, width: '140px' }}
                      />
                    </label>
                  </div>
                ) : null}
              </label>
              <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={openNtpHistoryModal}
                  title="View prior NTP sends, reminders, templates, and acknowledgements for this matter"
                >
                  See previous NTPs
                </button>
                {!!(lastNtpSend?.data?.exists) && (
                  <button
                    className="btn secondary"
                    type="button"
                    onClick={copyPreviousNtpData}
                    title={lastNtpSend?.data?.exists ? 'Copy the most recently sent NTP template + variables for this matter' : 'No prior NTP found for this matter'}
                  >
                    Copy previous NTP data
                  </button>
                )}
              </div>
              <label style={ntpFieldLabelStyle}>
                <span>Legal Matter Name</span>
                <TextInput value={ntpVariables.legal_case_name} onChange={e => setNtpVariables(prev => ({ ...prev, legal_case_name: e.target.value }))} />
              </label>
              <label style={ntpFieldLabelStyle}>
                <span>Claimant</span>
                <TextInput value={ntpVariables.claimant} onChange={e => setNtpVariables(prev => ({ ...prev, claimant: e.target.value }))} />
              </label>
              <label style={ntpFieldLabelStyle}>
                <span>Reason</span>
                <TextInput value={ntpVariables.reason} onChange={e => { ntpReasonTouchedRef.current = true; setNtpVariables(prev => ({ ...prev, reason: e.target.value })) }} />
              </label>
              <label style={ntpFieldLabelStyle}>
                <span>Outside Counsel 1</span>
                <TextInput list="ntp-outside-counsel-options" value={ntpVariables.outside_counsel1} onChange={e => setNtpVariables(prev => ({ ...prev, outside_counsel1: e.target.value }))} />
              </label>
              <label style={ntpFieldLabelStyle}>
                <span>Outside Counsel 2</span>
                <TextInput list="ntp-outside-counsel-options" value={ntpVariables.outside_counsel2} onChange={e => setNtpVariables(prev => ({ ...prev, outside_counsel2: e.target.value }))} />
              </label>
              <label style={ntpFieldLabelStyle}>
                <span>Outside Counsel 3</span>
                <TextInput list="ntp-outside-counsel-options" value={ntpVariables.outside_counsel3} onChange={e => setNtpVariables(prev => ({ ...prev, outside_counsel3: e.target.value }))} />
              </label>
              <label style={{ ...ntpFieldLabelStyle, gridColumn: '1 / -1' }}>
                <span>Outside Counsel Firm</span>
                <TextInput list="ntp-outside-counsel-firm-options" value={ntpVariables.outside_counsel_firm} onChange={e => setNtpVariables(prev => ({ ...prev, outside_counsel_firm: e.target.value }))} />
              </label>
              <datalist id="ntp-outside-counsel-options">
                {ntpOutsideCounselHistory.counsel.map((value, idx) => (
                  <option key={`ntp-counsel-${idx}`} value={value} />
                ))}
              </datalist>
              <datalist id="ntp-outside-counsel-firm-options">
                {ntpOutsideCounselHistory.firms.map((value, idx) => (
                  <option key={`ntp-counsel-firm-${idx}`} value={value} />
                ))}
              </datalist>
              <label style={{ ...ntpFieldLabelStyle, gridColumn: '1 / -1' }}>
                <span>CC Recipients (comma separated)</span>
                <TextInput
                  value={ntpVariables.cc_list || ''}
                  onChange={e => setNtpVariables(prev => ({ ...prev, cc_list: e.target.value }))}
                />
              </label>
            </div>
            {reminderSummary.total > 0 && (
              <div style={ntpSectionCardStyle}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>See reminders</div>
                    <div style={ntpHelperTextStyle}>
                      Reminders exist for {reminderSummary.custodians} custodian{reminderSummary.custodians === 1 ? '' : 's'}. Active: {reminderSummary.activeCustodians}.
                    </div>
                  </div>
                  <button
                    className="btn secondary"
                    type="button"
                    onClick={openReminderListModal}
                    disabled={ntpRemindersLoading}
                  >
                    {ntpRemindersLoading ? 'Loading...' : 'See reminders'}
                  </button>
                </div>
              </div>
            )}
            <div style={ntpSectionCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>Select custodians</div>
                  <div style={ntpHelperTextStyle}>Choose which custodians should receive this notice.</div>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                </div>
              </div>
              <div style={{ marginTop: 10 }}>
                <input
                  type="search"
                  placeholder="Search by name or email"
                  value={ntpSearch}
                  onChange={e => setNtpSearch(e.target.value)}
                  style={{ width:'100%', border:'1px solid var(--border, #d1d5db)', borderRadius:10, padding:'8px 12px', fontSize:12, background:'var(--card,#fff)', color:'var(--text,#0f172a)' }}
                />
              </div>
              <div style={{ maxHeight: 320, overflowY: 'auto', marginTop: 12, border: '1px solid var(--border, #e5e7eb)', borderRadius: 10, background: 'var(--card,#fff)' }}>
                {filteredNtpCustodians.filter(c => (c.email || '').trim()).length === 0 ? (
                  <p style={{ color: 'var(--muted,#6b7280)', padding: '16px' }}>No custodians with email addresses.</p>
                ) : (
                  filteredNtpCustodians.filter(c => (c.email || '').trim()).map(c => (
                    <label
                      key={c.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        padding: '6px 14px',
                        borderBottom: '1px solid rgba(15,23,42,0.05)',
                        alignItems: 'center',
                      }}
                    >
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <input
                          type="checkbox"
                          checked={ntpSelection.includes(c.id)}
                          onChange={e => toggleNtpSelection(c.id, e.target.checked)}
                        />
                        <span>
                          <div style={{ fontWeight: 500, color: '#0f172a', fontSize: 12 }}>{c.name}</div>
                          <div style={{ color: '#6b7280', fontSize: 11 }}>{(c.email || '').trim() || '-'}</div>
                        </span>
                      </span>
                      <span style={{ color: '#6b7280', fontSize: 10, letterSpacing: 0.5 }}>{ntpStatusLabel(c)}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          </div>
        </Modal>
        {ntpPreview.data && (
          <Modal
            open
            title="Preview NTP"
            onClose={() => setNtpPreview({ loading: false, error: null, data: null })}
            width={920}
            footer={(
              <button
                className="btn primary"
                type="button"
                onClick={() => setNtpPreview({ loading: false, error: null, data: null })}
              >
                Close Preview
              </button>
            )}
          >
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={ntpSectionCardStyle}>
                <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
                  Previewing the first selected custodian. Sending will use the same template and variables for all {ntpPreview.data.recipient_count || 0} selected custodian{Number(ntpPreview.data.recipient_count || 0) === 1 ? '' : 's'}.
                </div>
                <div style={{ display: 'grid', gap: 6, fontSize: 13, color: '#0f172a' }}>
                  <div><strong>To:</strong> {ntpPreview.data.recipient?.name || 'Unknown'} &lt;{ntpPreview.data.recipient?.email || '-'}&gt;</div>
                  <div><strong>Subject:</strong> {ntpPreview.data.subject || '(no subject)'}</div>
                  <div><strong>Template:</strong> {ntpPreview.data.template_name || '-'}</div>
                  {(ntpPreview.data.cc || []).length ? <div><strong>CC:</strong> {ntpPreview.data.cc.join(', ')}</div> : null}
                  <div><strong>Archive copy:</strong> {ntpPreview.data.archive_copy_address || 'Not configured'}</div>
                </div>
              </div>
              <div style={{ border: '1px solid var(--border,#e2e8f0)', borderRadius: 12, overflow: 'hidden', background: '#fff' }}>
                <div style={{ padding: '10px 12px', borderBottom: '1px solid var(--border,#e2e8f0)', background: '#f8fafc', fontSize: 12, fontWeight: 700, color: '#334155' }}>
                  Email body
                </div>
                <iframe
                  title="NTP email preview"
                  sandbox=""
                  srcDoc={`<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>body{font-family:Arial,sans-serif;font-size:14px;line-height:1.55;color:#111827;margin:0;padding:18px;background:#fff}a{color:#056aa8}</style></head><body>${ntpPreview.data.html_body || ''}</body></html>`}
                  style={{ width: '100%', minHeight: 360, border: 0, display: 'block', background: '#fff' }}
                />
              </div>
            </div>
          </Modal>
        )}
        <LoadingOverlay
          visible={sendingNtp}
          title="Sending notices"
          subtitle="This can take a few seconds. Please do not close the window."
        />
        </>
      )}
      <NtpHistoryModal
        showNtpHistoryModal={showNtpHistoryModal}
        setShowNtpHistoryModal={setShowNtpHistoryModal}
        ntpHistory={ntpHistory}
        ntpHistoryExporting={ntpHistoryExporting}
        ntpHistoryEmailing={ntpHistoryEmailing}
        exportNtpHistoryCsv={exportNtpHistoryCsv}
        emailNtpHistoryReport={emailNtpHistoryReport}
        loadNtpHistory={loadNtpHistory}
        ntpSectionCardStyle={ntpSectionCardStyle}
        ntpHistoryCustodianRows={ntpHistoryCustodianRows}
        ntpHistoryEvents={ntpHistoryEvents}
        formatDateTime={formatDateTime}
      />
      <NtpReminderModals
        showReminderListModal={showReminderListModal}
        setShowReminderListModal={setShowReminderListModal}
        canEditReminders={canEditReminders}
        eligibleReminderReactivationCustodianIds={eligibleReminderReactivationCustodianIds}
        reactivateEligibleCancelledNtpReminders={reactivateEligibleCancelledNtpReminders}
        reactivatingNtpRemindersBulk={reactivatingNtpRemindersBulk}
        ntpRemindersLoading={ntpRemindersLoading}
        reminderGroups={reminderGroups}
        reactivatingNtpReminders={reactivatingNtpReminders}
        openReminderEditor={openReminderEditor}
        reactivateCancelledNtpReminders={reactivateCancelledNtpReminders}
        reminderEditor={reminderEditor}
        closeReminderEditor={closeReminderEditor}
        saveReminderEditor={saveReminderEditor}
        setReminderEditor={setReminderEditor}
        reminderTemplateNames={reminderTemplateNames}
        activeReminderCustodianIds={activeReminderCustodianIds}
        ntpFieldLabelStyle={ntpFieldLabelStyle}
        ntpSelectStyle={ntpSelectStyle}
        editorPrimaryReminder={editorPrimaryReminder}
        formatDateTime={formatDateTime}
      />
      {ntpBlockedModal?.open && (
        <Modal
          open
          title="NTP selection blocked"
          onClose={() => setNtpBlockedModal({ open: false, custodian: null })}
          width={520}
          footer={(
            <button className="btn primary" type="button" onClick={() => setNtpBlockedModal({ open: false, custodian: null })}>
              OK
            </button>
          )}
        >
          <p style={{ margin: 0, color: 'var(--text,#0f172a)', lineHeight: 1.5 }}>
            That custodian is separated or marked Silent for NTPs.
          </p>
          {ntpBlockedModal?.custodian ? (
            <div style={{ marginTop: 10, fontSize: 13, color: 'var(--muted,#64748b)' }}>
              {ntpBlockedModal.custodian.name} {'\u2022'} {(ntpBlockedModal.custodian.email || '').trim() || 'no email'}
            </div>
          ) : null}
        </Modal>
      )}
    </>
  )
}
