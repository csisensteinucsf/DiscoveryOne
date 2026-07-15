import { Link } from 'react-router-dom'

function ProgressBadge({ label, percent = 0, variant = 'default', half = false, title }) {
  const readVar = (name, fallback) => {
    if (typeof document === 'undefined') return fallback
    const value = getComputedStyle(document.documentElement).getPropertyValue(name)
    return value && value.trim() ? value.trim() : fallback
  }
  const p = Math.max(0, Math.min(100, Math.round(percent)))
  const colors = {
    default: {
      fg: readVar('--badge-default-fg', '#334155'),
      br: readVar('--badge-default-br', '#e5e7eb'),
      track: readVar('--badge-default-track', '#f8fafc'),
      fill: readVar('--badge-default-fill', '#94a3b8'),
    },
    success: {
      fg: readVar('--badge-success-fg', '#166534'),
      br: readVar('--badge-success-br', '#bbf7d0'),
      track: readVar('--badge-success-track', '#f0fdf4'),
      fill: readVar('--badge-success-fill', '#22c55e'),
    },
    warn: {
      fg: readVar('--badge-warn-fg', '#92400e'),
      br: readVar('--badge-warn-br', '#fde68a'),
      track: readVar('--badge-warn-track', '#fffbeb'),
      fill: readVar('--badge-warn-fill', '#f59e0b'),
    },
  }
  const c = colors[variant] || colors.default
  const fillStop = half ? Math.max(0, Math.min(100, Math.round(p / 2))) : p

  return (
    <span
      title={title || `${label}: ${p}%`}
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        fontSize: 11,
        fontWeight: 700,
        padding: '3px 8px',
        borderRadius: 999,
        border: `1px solid ${c.br}`,
        color: c.fg,
        background: c.track,
        lineHeight: 1,
        letterSpacing: .25,
        userSelect: 'none',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: `${fillStop}%`,
          minWidth: fillStop > 0 ? 3 : 0,
          background: c.fill,
          opacity: 0.55,
        }}
      />
      <span style={{ position: 'relative', zIndex: 1 }}>{label}</span>
    </span>
  )
}

export const tableStyles = {
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 14, tableLayout: 'fixed' },
  headerCell: {
    whiteSpace: 'nowrap',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    color: 'var(--muted,#475467)',
    padding: '10px 12px',
    background: '#eef2f6',
    borderBottom: '1px solid #e5e7eb',
  },
  row: { borderBottom: '1px solid var(--border,#1f2937)' },
  cell: { padding: '10px 12px', verticalAlign: 'middle' },
  statusCell: { padding: '10px 12px', verticalAlign: 'middle', width: '18%' },
  actionsCell: {
    padding: '10px 12px',
    width: '12%',
    whiteSpace: 'nowrap',
    textAlign: 'right',
  },
  actionsInner: {
    display: 'inline-flex',
    justifyContent: 'flex-end',
    gap: '0.5rem',
    alignItems: 'center',
  },
  caseNameCell: { width: '13%' },
  legalCaseCell: { width: '28%' },
  analystCell: { width: '10%' },
  requestorCell: { width: '12%' },
}

export function CasesTableRow({
  c,
  stats,
  showSecondaryCaseNameColumn,
  useLegalCaseNameAsPrimary,
  analystFirstName,
  requestorDisplayName,
  isReadOnly,
  onEdit,
  onDelete,
}) {
  const st = stats[c.id] || { total: 0, searchTotal: 0, search: 0, export: 0, delivered: 0 }
  const total = st.total || 0
  const pctCust = (n) => total > 0 ? (n / total) * 100 : 0
  const ntpSentPercent = pctCust(st.ntpSent || 0)
  const ntpAckPercent = pctCust(st.ntpAck || 0)
  const hasNtpSent = (st.ntpSent || 0) > 0
  const hasNtpAck = (st.ntpAck || 0) > 0
  const searchTotal = st.searchTotal ?? (Array.isArray(c.searches) ? c.searches.length : 0)
  const pctSearch = (n) => searchTotal > 0 ? (n / searchTotal) * 100 : 0
  const primaryCaseName = useLegalCaseNameAsPrimary ? (c.legal_case_name || c.name || '') : (c.name || '')
  const extraRequestorCount = Array.isArray(c.requestors)
    ? c.requestors.filter(r => !r?.is_primary).length
    : 0

  return (
    <tr style={tableStyles.row}>
      <td style={{ ...tableStyles.cell, ...tableStyles.caseNameCell }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Link to={`/cases/${c.id}`} style={{ textDecoration: 'none', color: 'inherit' }}>{c.name}</Link>
          {c.is_private ? (
            <span
              title="Private Case"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: 18,
                height: 18,
                padding: '0 6px',
                borderRadius: 999,
                background: '#e0f2fe',
                border: '1px solid #7dd3fc',
                color: '#0c4a6e',
                fontSize: 11,
                fontWeight: 800,
                lineHeight: 1,
              }}
            >
              P
            </span>
          ) : null}
        </span>
      </td>
      {showSecondaryCaseNameColumn && <td style={{ ...tableStyles.cell, ...tableStyles.legalCaseCell }}>{c.legal_case_name || ''}</td>}
      <td style={{ ...tableStyles.cell, ...tableStyles.analystCell }}>{analystFirstName(c.analyst_id)}</td>
      <td style={{ ...tableStyles.cell, ...tableStyles.requestorCell }}>
        {requestorDisplayName(c.requestor)}
        {extraRequestorCount > 0 && (
          <span style={{ color: 'var(--muted,#6b7280)', marginLeft: 6 }}>+{extraRequestorCount} more</span>
        )}
      </td>
      <td style={tableStyles.statusCell}>
        <div className="status-grid" style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'flex-start' }}>
          {st.hold > 0 && <ProgressBadge label="HOLD" variant="success" percent={pctCust(st.hold)} />}
          {hasNtpSent && <ProgressBadge label="NTP" variant="warn" percent={ntpSentPercent} />}
          {hasNtpAck && <ProgressBadge label="NTP ACK" variant="success" percent={ntpAckPercent} />}
          {(total > 0 && st.consentReceived > 0) && <ProgressBadge label="CONSENT" variant="success" percent={pctCust(st.consentReceived || 0)} />}
          {searchTotal > 0 && (
            <>
              <ProgressBadge label="SEARCH" variant={st.search > 0 ? 'success' : 'default'} percent={pctSearch(st.search || 0)} title={`${st.search || 0}/${searchTotal} searches`} />
              <ProgressBadge label="EXPORT" variant={st.export > 0 ? 'success' : 'default'} percent={pctSearch(st.export || 0)} title={`${st.export || 0}/${searchTotal} searches`} />
              <ProgressBadge label="DELIVERED" variant={st.delivered > 0 ? 'success' : 'default'} percent={pctSearch(st.delivered || 0)} title={`${st.delivered || 0}/${searchTotal} searches`} />
            </>
          )}
          {!(st.hold > 0 || hasNtpSent || hasNtpAck || st.consentReceived > 0 || searchTotal > 0) && '-'}
        </div>
      </td>
      <td style={tableStyles.actionsCell}>
        <div style={tableStyles.actionsInner}>
          {isReadOnly ? (
            <span style={{ color: 'var(--muted,#6b7280)' }}>Read only</span>
          ) : (
            <>
              <button className="btn secondary" onClick={() => onEdit(c)}>Edit</button>
              <button className="btn danger" onClick={() => onDelete(c.id)}>Delete</button>
            </>
          )}
        </div>
      </td>
    </tr>
  )
}