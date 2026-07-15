import { formatDateTime } from './systemUtils.js'

export default function SystemClamavPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  clamavMonitor,
  clamavLoading,
  clamavStatus,
  loadClamavMonitor,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can view ClamAV monitoring.')
  }

  return (
    <div className="card" style={{ marginBottom: 16, display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <div style={titleStyle}>ClamAV Monitor</div>
          <p style={{ color: 'var(--muted,#6b7280)', margin: '4px 0 0' }}>
            Shows scanner health and upload scan activity for the past {clamavMonitor?.days || 30} days.
          </p>
          <p style={{ color: 'var(--muted,#6b7280)', margin: '4px 0 0', fontSize: 13 }}>
            Processed-file counts are tracked from the scan audit rollout forward; malicious detections include existing alert history.
          </p>
        </div>
        <button className="btn ghost" onClick={loadClamavMonitor} disabled={clamavLoading}>
          {clamavLoading ? 'Refreshing' : 'Refresh'}
        </button>
      </div>
      {clamavStatus && <div style={{ color: '#b91c1c', fontWeight: 600 }}>{clamavStatus}</div>}
      {clamavLoading && !clamavMonitor ? (
        <div>Loading ClamAV monitor</div>
      ) : (
        <>
          <ScannerStatus scanner={clamavMonitor?.scanner || {}} />
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            {[
              ['Files Processed', clamavMonitor?.summary?.processed ?? 0],
              ['Clean', clamavMonitor?.summary?.clean ?? 0],
              ['Malicious Found', clamavMonitor?.summary?.malicious ?? 0],
              ['Blocked', clamavMonitor?.summary?.blocked ?? 0],
            ].map(([label, value]) => (
              <div key={label} style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12 }}>
                <div style={{ color: 'var(--muted,#6b7280)', fontSize: 12, fontWeight: 700, textTransform: 'uppercase' }}>{label}</div>
                <div style={{ fontSize: 28, fontWeight: 800, marginTop: 4 }}>{Number(value || 0).toLocaleString()}</div>
              </div>
            ))}
          </div>
          {clamavMonitor?.summary?.upload_events > 0 && clamavMonitor?.summary?.scan_events === 0 && (
            <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>
              Processed count is using upload-success audit records because dedicated scan events have not been recorded in this 30-day window.
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
            <DailyActivityTable daily={clamavMonitor?.daily || []} />
            <RecentDetectionsTable detections={clamavMonitor?.recent_detections || []} />
          </div>
        </>
      )}
    </div>
  )
}

function ScannerStatus({ scanner }) {
  const isCurrent = scanner.definitions_current
  const statusColor = scanner.ready && isCurrent !== false ? '#047857' : '#b91c1c'
  return (
    <div style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12 }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginBottom: 8 }}>
        <span style={{ fontWeight: 700 }}>Scanner Status</span>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center',
          borderRadius: 999,
          padding: '2px 8px',
          fontSize: 12,
          fontWeight: 700,
          color: statusColor,
          background: scanner.ready && isCurrent !== false ? 'rgba(5,150,105,0.14)' : 'rgba(185,28,28,0.12)',
        }}>
          {scanner.ready ? (isCurrent === false ? 'Definitions stale' : 'Ready') : 'Unavailable'}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
        <div><strong>Engine</strong><div>{scanner.engine || 'Unknown'}</div></div>
        <div><strong>Current Def Date</strong><div>{scanner.signature_date || 'Unknown'}</div></div>
        <div><strong>Def Version</strong><div>{scanner.signature_version ?? 'Unknown'}</div></div>
        <div><strong>Def Age</strong><div>{scanner.signature_age_hours != null ? `${scanner.signature_age_hours} hours` : 'Unknown'}</div></div>
      </div>
      {scanner.error && <div style={{ color: '#b91c1c', marginTop: 8 }}>{scanner.error}</div>}
    </div>
  )
}

function DailyActivityTable({ daily }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Daily Activity</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%' }}>
          <thead>
            <tr><th>Date</th><th>Processed</th><th>Malicious</th></tr>
          </thead>
          <tbody>
            {daily.length ? daily.map(row => (
              <tr key={row.date}>
                <td>{row.date}</td>
                <td>{Number(row.processed || 0).toLocaleString()}</td>
                <td>{Number(row.malicious || 0).toLocaleString()}</td>
              </tr>
            )) : (
              <tr><td colSpan={3} style={{ color: 'var(--muted,#6b7280)' }}>No scan activity recorded yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function RecentDetectionsTable({ detections }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>Recent Malicious Detections</div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%' }}>
          <thead>
            <tr><th>When</th><th>File</th><th>User</th></tr>
          </thead>
          <tbody>
            {detections.length ? detections.map((row, idx) => (
              <tr key={`${row.created_at || 'detection'}-${idx}`}>
                <td>{formatDateTime(row.created_at)}</td>
                <td title={row.scanner_detail || ''}>{row.filename || 'Unknown'}</td>
                <td>{row.actor_name || row.request_ip || 'Unknown'}</td>
              </tr>
            )) : (
              <tr><td colSpan={3} style={{ color: 'var(--muted,#6b7280)' }}>No malicious files detected in the last 30 days.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
