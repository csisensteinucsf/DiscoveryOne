import { Link } from 'react-router-dom'

function PreservationCountBadge({ count }) {
  const total = Number(count || 0)
  const title = total === 1
    ? '1 custodian with active preservation'
    : `${total} custodians with active preservation`
  return (
    <span
      className={total > 0 ? 'case-hold-count is-active' : 'case-hold-count'}
      title={title}
    >
      {total}
    </span>
  )
}

export const tableStyles = {
  table: {
    width: '100%',
    minWidth: 1350,
    borderCollapse: 'collapse',
    fontSize: 14,
    tableLayout: 'fixed',
  },
  headerCell: {
    whiteSpace: 'nowrap',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    color: 'var(--muted,#475467)',
    padding: '8px 10px',
    background: '#eef2f6',
    borderBottom: '1px solid #e5e7eb',
  },
  row: { borderBottom: '1px solid var(--border,#1f2937)' },
  cell: { padding: '10px', verticalAlign: 'middle' },
  caseNameCell: { width: 160 },
  legalCaseCell: { width: 180 },
  matterCell: { width: 120 },
  counselCell: { width: 145 },
  analystCell: { width: 95 },
  requestorCell: { width: 145 },
  stateCell: { width: 90, textAlign: 'center' },
  statusCell: { width: 95, textAlign: 'center' },
  notesCell: { width: 220 },
  actionsCell: {
    padding: '10px',
    width: 235,
    whiteSpace: 'nowrap',
    textAlign: 'right',
  },
  actionsInner: {
    display: 'inline-flex',
    justifyContent: 'flex-end',
    gap: '0.4rem',
    alignItems: 'center',
  },
}

export function CasesTableRow({
  c,
  stats,
  showSecondaryCaseNameColumn,
  visibleColumns = [],
  useLegalCaseNameAsPrimary,
  analystFirstName,
  requestorDisplayName,
  isReadOnly,
  canDelete,
  onEdit,
  onToggleClosed,
  onDelete,
}) {
  const columnVisible = key => visibleColumns.includes(key)
  const caseStats = stats[c.id] || stats[String(c.id)] || {}
  const preservationCount = caseStats.hold ?? 0
  const primaryCaseName = useLegalCaseNameAsPrimary
    ? (c.legal_case_name || c.name || '')
    : (c.name || c.legal_case_name || '')
  const extraRequestorCount = Array.isArray(c.requestors)
    ? c.requestors.filter(requestor => !requestor?.is_primary).length
    : 0
  const notes = (c.description || '').trim()

  return (
    <tr style={tableStyles.row}>
      <td style={{ ...tableStyles.cell, ...tableStyles.caseNameCell }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <Link to={'/cases/' + c.id} style={{ textDecoration: 'none', color: 'inherit' }}>{primaryCaseName}</Link>
          {c.is_private ? <span className="case-private-badge" title="Private case">P</span> : null}
        </span>
      </td>
      {showSecondaryCaseNameColumn && (
        <td style={{ ...tableStyles.cell, ...tableStyles.legalCaseCell }}>{c.legal_case_name || ''}</td>
      )}
      {columnVisible('matter_number') && <td style={{ ...tableStyles.cell, ...tableStyles.matterCell }}>{c.matter_number || c.servicenow_inc_number || '-'}</td>}
      {columnVisible('internal_counsel') && <td style={{ ...tableStyles.cell, ...tableStyles.counselCell }}>{c.internal_counsel || '-'}</td>}
      {columnVisible('analyst') && <td style={{ ...tableStyles.cell, ...tableStyles.analystCell }}>{analystFirstName(c.analyst_id)}</td>}
      {columnVisible('requestor') && <td style={{ ...tableStyles.cell, ...tableStyles.requestorCell }}>
        {requestorDisplayName(c.requestor)}
        {extraRequestorCount > 0 && (
          <span style={{ color: 'var(--muted,#6b7280)', marginLeft: 6 }}>+{extraRequestorCount} more</span>
        )}
      </td>}
      {columnVisible('state') && <td style={{ ...tableStyles.cell, ...tableStyles.stateCell }}>
        <span className={'hold-status-badge ' + (c.closed ? 'is-closed' : 'is-active')}>
          {c.closed ? 'Inactive' : 'Active'}
        </span>
      </td>}
      {columnVisible('holds') && <td style={{ ...tableStyles.cell, ...tableStyles.statusCell }}>
        <PreservationCountBadge count={preservationCount} />
      </td>}
      {columnVisible('notes') && <td style={{ ...tableStyles.cell, ...tableStyles.notesCell }}>
        <span className="case-notes-preview" title={notes}>{notes || '-'}</span>
      </td>}
      <td style={tableStyles.actionsCell}>
        <div style={tableStyles.actionsInner}>
          {isReadOnly ? (
            <span style={{ color: 'var(--muted,#6b7280)' }}>Read only</span>
          ) : (
            <>
              <button className="btn secondary compact" type="button" onClick={() => onEdit(c)}>Edit</button>
              <button className="btn secondary compact" type="button" onClick={() => onToggleClosed(c)}>
                {c.closed ? 'Reopen' : 'Close'}
              </button>
              {canDelete && (
                <button className="btn danger compact" type="button" onClick={() => onDelete(c)}>Delete</button>
              )}
            </>
          )}
        </div>
      </td>
    </tr>
  )
}
