import { Badge } from './caseDetailControls.jsx'

export default function CaseDetailSlaTab({ slaLoading, slaError, slaStatus }) {
  return (
<section className="card" style={{ padding: 16, width: '100%' }}>
              <h3 style={{ marginTop: 0, marginBottom: 4 }}>SLA</h3>
              {slaLoading ? (
                <p style={{ color: '#6b7280' }}>Loading SLA status...</p>
              ) : slaError ? (
                <p style={{ color: '#b91c1c' }}>{slaError}</p>
              ) : (
                <div style={{ display: 'grid', gap: 8 }}>
                  <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong>NTP acknowledgements</strong>
                      <Badge variant={slaStatus.ntp_overdue.length ? 'warn' : 'success'} compact>
                        {slaStatus.ntp_overdue.length ? `${slaStatus.ntp_overdue.length} overdue` : 'On track'}
                      </Badge>
                    </div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                      SLA: {slaStatus?.config?.ntp_ack_days || 7} day acknowledgement from send.
                    </div>
                    {slaStatus.ntp_overdue.length ? (
                      <ul style={{ margin: '8px 0 0', paddingLeft: 16, color: '#991b1b', fontSize: 13 }}>
                        {slaStatus.ntp_overdue.map(item => (
                          <li key={`ntp-${item.custodian_id}`}> 
                            {item.custodian_name || item.custodian_email || 'Custodian'} - overdue by {item.days_overdue} day(s)
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  <div style={{ border: '1px solid #e5e7eb', borderRadius: 10, padding: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong>Consents</strong>
                      <Badge variant={slaStatus.consent_overdue.length ? 'warn' : 'success'} compact>
                        {slaStatus.consent_overdue.length ? `${slaStatus.consent_overdue.length} overdue` : 'On track'}
                      </Badge>
                    </div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                      SLA: {slaStatus?.config?.consent_received_days || 7} day completion from send.
                    </div>
                    {slaStatus.consent_overdue.length ? (
                      <ul style={{ margin: '8px 0 0', paddingLeft: 16, color: '#92400e', fontSize: 13 }}>
                        {slaStatus.consent_overdue.map(item => (
                          <li key={`consent-${item.consent_id}`}>
                            {item.custodian_name || item.custodian_email || 'Custodian'} - overdue by {item.days_overdue} day(s)
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                </div>
              )}
            </section>
  )
}
