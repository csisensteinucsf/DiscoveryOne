import Modal from '../components/Modal.jsx'
import { formatNameRaw } from './caseDetailUtils.js'

export default function NtpHistoryModal({
  showNtpHistoryModal,
  setShowNtpHistoryModal,
  ntpHistory,
  ntpHistoryExporting,
  ntpHistoryEmailing,
  exportNtpHistoryCsv,
  emailNtpHistoryReport,
  loadNtpHistory,
  ntpSectionCardStyle,
  ntpHistoryCustodianRows,
  ntpHistoryEvents,
  formatDateTime,
}) {
  return (
    <>
      {showNtpHistoryModal && (
        <Modal
          open
          title="Previous NTPs"
          onClose={() => setShowNtpHistoryModal(false)}
          width={980}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
              <button
                className="btn secondary"
                type="button"
                onClick={exportNtpHistoryCsv}
                disabled={ntpHistory.loading || ntpHistoryExporting || ntpHistoryEmailing}
              >
                {ntpHistoryExporting ? 'Exporting...' : 'Export to CSV'}
              </button>
              <button
                className="btn secondary"
                type="button"
                onClick={emailNtpHistoryReport}
                disabled={ntpHistory.loading || ntpHistoryExporting || ntpHistoryEmailing}
              >
                {ntpHistoryEmailing ? 'Emailing...' : 'Email Report'}
              </button>
              <button
                className="btn secondary"
                type="button"
                onClick={loadNtpHistory}
                disabled={ntpHistory.loading || ntpHistoryExporting || ntpHistoryEmailing}
              >
                {ntpHistory.loading ? 'Refreshing...' : 'Refresh'}
              </button>
              <button
                className="btn"
                type="button"
                onClick={() => setShowNtpHistoryModal(false)}
                disabled={ntpHistory.loading || ntpHistoryExporting || ntpHistoryEmailing}
              >
                Close
              </button>
            </div>
          )}
        >
          {ntpHistory.loading ? (
            <p style={{ color: '#6b7280', margin: 0 }}>Loading previous NTP activity...</p>
          ) : ntpHistory.error ? (
            <p style={{ color: '#b91c1c', margin: 0 }}>{ntpHistory.error}</p>
          ) : (
            <div style={{ display: 'grid', gap: 12, maxHeight: '76vh', overflowY: 'auto', paddingRight: 4 }}>
              <div style={ntpSectionCardStyle}>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>Custodian NTP summary</div>
                {ntpHistoryCustodianRows.length ? (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead style={{ background: 'rgba(15,23,42,0.04)' }}>
                        <tr>
                          <th style={{ textAlign: 'left', padding: 6 }}>Custodian</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Template(s)</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Sent</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>ACK</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Reminder status</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Next reminder</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Last reminder sent</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ntpHistoryCustodianRows.map(row => (
                          <tr key={`ntp-history-custodian-${row.id}`}>
                            <td style={{ padding: 6 }}>
                              <div style={{ fontWeight: 600, color: '#0f172a' }}>{formatNameRaw(row.name || '') || row.email || '-'}</div>
                              <div style={{ color: '#64748b' }}>{row.email || '-'}</div>
                            </td>
                            <td style={{ padding: 6 }}>{row.ntp_template_name || '-'}</td>
                            <td style={{ padding: 6 }}>{formatDateTime(row.ntp_sent_at) || '-'}</td>
                            <td style={{ padding: 6 }}>{formatDateTime(row.ntp_acknowledged_at) || '-'}</td>
                            <td style={{ padding: 6 }}>{row.reminders_summary || (row.reminders_total ? `${row.reminders_total} total` : '-')}</td>
                            <td style={{ padding: 6 }}>{formatDateTime(row.next_reminder_at) || '-'}</td>
                            <td style={{ padding: 6 }}>{formatDateTime(row.last_reminder_sent_at) || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p style={{ color: '#6b7280', margin: 0 }}>No NTP activity found for custodians in this case.</p>
                )}
              </div>

              <div style={ntpSectionCardStyle}>
                <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a', marginBottom: 8 }}>NTP event timeline</div>
                {ntpHistoryEvents.length ? (
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead style={{ background: 'rgba(15,23,42,0.04)' }}>
                        <tr>
                          <th style={{ textAlign: 'left', padding: 6 }}>Date</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Event</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Custodian</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Template</th>
                          <th style={{ textAlign: 'left', padding: 6 }}>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ntpHistoryEvents.map((event, idx) => {
                          const detailBits = []
                          if (event?.reminder_id) detailBits.push(`Reminder #${event.reminder_id}`)
                          if (event?.token_id) detailBits.push(`Token #${event.token_id}`)
                          return (
                            <tr key={`ntp-history-event-${event?.id || idx}`}> 
                              <td style={{ padding: 6 }}>{formatDateTime(event?.created_at) || '-'}</td>
                              <td style={{ padding: 6 }}>{event?.event_type || event?.action || '-'}</td>
                              <td style={{ padding: 6 }}>
                                <div>{formatNameRaw(event?.custodian_name || '') || event?.custodian_email || '-'}</div>
                                {event?.custodian_email && <div style={{ color: '#64748b' }}>{event.custodian_email}</div>}
                              </td>
                              <td style={{ padding: 6 }}>{event?.template_name || '-'}</td>
                              <td style={{ padding: 6 }}>{detailBits.length ? detailBits.join(' | ') : '-'}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p style={{ color: '#6b7280', margin: 0 }}>No NTP audit events found for this case.</p>
                )}
              </div>
            </div>
          )}
        </Modal>
      )}
    </>
  )
}