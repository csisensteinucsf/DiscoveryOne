import Modal from '../components/Modal.jsx'
import { formatNameRaw } from './caseDetailUtils.js'

export default function NtpReminderModals({
  showReminderListModal,
  setShowReminderListModal,
  canEditReminders,
  eligibleReminderReactivationCustodianIds,
  reactivateEligibleCancelledNtpReminders,
  reactivatingNtpRemindersBulk,
  ntpRemindersLoading,
  reminderGroups,
  reactivatingNtpReminders,
  openReminderEditor,
  reactivateCancelledNtpReminders,
  reminderEditor,
  closeReminderEditor,
  saveReminderEditor,
  setReminderEditor,
  reminderTemplateNames,
  activeReminderCustodianIds,
  ntpFieldLabelStyle,
  ntpSelectStyle,
  editorPrimaryReminder,
  formatDateTime,
}) {
  return (
    <>
      {showReminderListModal && (
        <Modal
          open
          title="NTP Reminders"
          onClose={() => setShowReminderListModal(false)}
          width={760}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
              {canEditReminders && eligibleReminderReactivationCustodianIds.length > 0 && (
                <button
                  className="btn secondary"
                  type="button"
                  onClick={reactivateEligibleCancelledNtpReminders}
                  disabled={reactivatingNtpRemindersBulk || ntpRemindersLoading}
                >
                  {reactivatingNtpRemindersBulk ? 'Turning on?' : `Turn reminders on (${eligibleReminderReactivationCustodianIds.length})`}
                </button>
              )}
              <button
                className="btn"
                type="button"
                onClick={() => setShowReminderListModal(false)}
                disabled={reactivatingNtpRemindersBulk}
              >
                Close
              </button>
            </div>
          )}
        >
          {ntpRemindersLoading ? (
            <p style={{ color: '#6b7280', margin: 0 }}>Loading reminders...</p>
          ) : reminderGroups.length ? (
            <div style={{ display: 'grid', gap: 12, maxHeight: '70vh', overflowY: 'auto', paddingRight: 4 }}>
              {reminderGroups.map(group => {
                const custodianLabel = formatNameRaw(group.custodian?.name || '') || group.custodian?.email || `Custodian ${group.custodianId}`
                const custodianEmail = (group.custodian?.email || '').trim()
                const acknowledged = String(group.custodian?.ntp_status || '').trim().toLowerCase() === 'acknowledged'
                const hasCancelled = (group.reminders || []).some(reminder => (reminder?.status || '').toLowerCase() === 'cancelled')
                const turningOn = !!reactivatingNtpReminders[group.custodianId] || reactivatingNtpRemindersBulk
                return (
                  <div
                    key={`reminder-${group.custodianId}`}
                    style={{ border: '1px solid var(--border,#e2e8f0)', borderRadius: 12, padding: 12, background: 'var(--card,#fff)' }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                      <div>
                        <div style={{ fontWeight: 600, color: '#0f172a' }}>{custodianLabel}</div>
                        {custodianEmail && custodianEmail !== custodianLabel && (
                          <div style={{ fontSize: 12, color: '#6b7280' }}>{custodianEmail}</div>
                        )}
                      </div>
                      {canEditReminders ? (
                        group.activeReminders.length > 0 ? (
                          <button
                            className="btn ghost"
                            type="button"
                            onClick={() => {
                              setShowReminderListModal(false)
                              openReminderEditor(group.custodian, group.activeReminders)
                            }}
                          >
                            Edit reminder
                          </button>
                        ) : (hasCancelled && !acknowledged ? (
                          <button
                            className="btn ghost"
                            type="button"
                            onClick={() => reactivateCancelledNtpReminders(group.custodianId)}
                            disabled={turningOn || ntpRemindersLoading}
                          >
                            {turningOn ? 'Turning on?' : 'Turn reminders on'}
                          </button>
                        ) : (
                          <span style={{ fontSize: 12, color: '#94a3b8' }}>
                            {acknowledged ? 'Acknowledged' : (hasCancelled ? 'Reminders cancelled' : 'No active reminders')}
                          </span>
                        ))
                      ) : (
                        <span style={{ fontSize: 12, color: '#94a3b8' }}>
                          {group.activeReminders.length ? 'Read only' : 'No active reminders'}
                        </span>
                      )}
                    </div>
                    <div style={{ marginTop: 10, overflowX: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead style={{ background: 'rgba(15,23,42,0.04)' }}>
                          <tr>
                            <th style={{ textAlign: 'left', padding: 6 }}>Template</th>
                            <th style={{ textAlign: 'left', padding: 6 }}>Status</th>
                            <th style={{ textAlign: 'right', padding: 6 }}>Every (days)</th>
                            <th style={{ textAlign: 'left', padding: 6 }}>Next send</th>
                            <th style={{ textAlign: 'left', padding: 6 }}>Ends</th>
                            <th style={{ textAlign: 'left', padding: 6 }}>Last sent</th>
                            <th style={{ textAlign: 'right', padding: 6 }}>Sent</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.reminders.map(reminder => (
                            <tr key={reminder.id}>
                              <td style={{ padding: 6 }}>{reminder.template_name || '-'}</td>
                              <td style={{ padding: 6 }}>{(reminder.status || 'active').toUpperCase()}</td>
                              <td style={{ padding: 6, textAlign: 'right' }}>{reminder.interval_days || '-'}</td>
                              <td style={{ padding: 6 }}>{formatDateTime(reminder.next_send_at) || '-'}</td>
                              <td style={{ padding: 6 }}>{formatDateTime(reminder.stop_after) || '-'}</td>
                              <td style={{ padding: 6 }}>{formatDateTime(reminder.last_sent_at) || '-'}</td>
                              <td style={{ padding: 6, textAlign: 'right' }}>{Number(reminder.send_count || 0)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <p style={{ color: '#6b7280', margin: 0 }}>No reminder schedules found for this case.</p>
          )}
        </Modal>
      )}
      {reminderEditor.open && (
        <Modal
          open
          title={`Edit NTP reminders${reminderEditor.custodian ? ` - ${formatNameRaw(reminderEditor.custodian.name || reminderEditor.custodian.email || '')}` : ''}`}
          onClose={closeReminderEditor}
          width={520}
          footer={(
            <>
              <button className="btn" type="button" onClick={closeReminderEditor} disabled={reminderEditor.busy}>
                Cancel
              </button>
              <button className="btn secondary" type="button" onClick={saveReminderEditor} disabled={reminderEditor.busy}>
                {reminderEditor.busy ? 'Saving...' : 'Save'}
              </button>
            </>
          )}
        >
          <div style={{ display: 'grid', gap: 12 }}>
            {reminderEditor.reminders.length > 1 && (
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                Multiple active reminders found; updates apply to all of them.
              </div>
            )}
            {reminderTemplateNames.length > 0 && (
              <div style={{ fontSize: 12, color: '#475467' }}>
                Template: {reminderTemplateNames.join(', ')}
              </div>
            )}
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
              <input
                type="checkbox"
                checked={reminderEditor.enabled}
                onChange={(e) => setReminderEditor(prev => ({ ...prev, enabled: e.target.checked }))}
                disabled={reminderEditor.busy}
              />
              Reminders enabled
            </label>
            {activeReminderCustodianIds.length > 1 && (
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={reminderEditor.applyToAll}
                  onChange={(e) => setReminderEditor(prev => ({ ...prev, applyToAll: e.target.checked }))}
                  disabled={reminderEditor.busy}
                />
                Apply to all custodians with active reminders ({activeReminderCustodianIds.length})
              </label>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              <label style={ntpFieldLabelStyle}>
                <span>Reminder every (days)</span>
                <input
                  type="number"
                  min="1"
                  value={reminderEditor.intervalDays}
                  onChange={e => setReminderEditor(prev => ({ ...prev, intervalDays: e.target.value }))}
                  style={ntpSelectStyle}
                  disabled={reminderEditor.busy || !reminderEditor.enabled}
                />
              </label>
              <label style={ntpFieldLabelStyle}>
                <span>Reminders for (days)</span>
                <input
                  type="number"
                  min="1"
                  value={reminderEditor.durationDays}
                  onChange={e => setReminderEditor(prev => ({ ...prev, durationDays: e.target.value }))}
                  style={ntpSelectStyle}
                  disabled={reminderEditor.busy || !reminderEditor.enabled}
                />
              </label>
            </div>
            {editorPrimaryReminder ? (
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                <div>Next send: {formatDateTime(editorPrimaryReminder.next_send_at) || 'TBD'}</div>
                <div>Ends: {formatDateTime(editorPrimaryReminder.stop_after) || 'TBD'}</div>
                <div>Already sent: {Number(editorPrimaryReminder.send_count || 0)}</div>
              </div>
            ) : null}
          </div>
        </Modal>
      )}
    </>
  )
}