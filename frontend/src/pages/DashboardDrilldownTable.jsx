export function DrilldownTable({ kind, items, filter, loading, onOpenCase, onOpenCustodian }) {
  if (loading) return <div style={{ color: 'var(--muted,#64748b)' }}>Loading…</div>
  const q = (filter || '').trim().toLowerCase()
  const filtered = (items || []).filter((it) => {
    if (!q) return true
    const hay = [
      it.case_name,
      it.case_id,
      it.legal_case_name,
      it.requestor,
      it.analyst_username,
      it.custodian_name,
      it.custodian_email,
      it.search_id,
      it.search_name,
      it.status_search,
      it.status_export,
      it.status_delivery,
      it.ticket,
      it.category,
      it.assigned_to_display,
      it.assigned_to_email,
      it.status,
      it.envelope_id,
      it.request_id,
      it.request_type,
      it.requestor_email,
      it.ntp_status,
      it.ntp_sent_at,
      it.ntp_acknowledged_at,
      it.reminder_status,
      it.template_name,
      it.next_send_at,
      it.last_sent_at,
      it.stop_after,
      it.send_count,
      it.interval_days,
    ].map(x => String(x || '').toLowerCase()).join(' ')
    return hay.includes(q)
  })
  if (!filtered.length) return <div className="empty">No matching results.</div>

  if (kind === 'cases_list') {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Analyst</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Requestor</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Created</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={it.case_id}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>
                    ID: {it.case_id}{it.legal_case_name ? ` • ${it.legal_case_name}` : ''}
                  </div>
                </td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{it.case_closed ? 'Closed' : 'Open'}</td>
                <td style={{ padding: '10px 6px' }}>{it.analyst_username || '—'}</td>
                <td style={{ padding: '10px 6px' }}>{it.requestor || '—'}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{String(it.created_at || '').slice(0, 19).replace('T', ' ')}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'holds_list') {
    const summarize = (m) => {
      if (!m || typeof m !== 'object') return ''
      const keys = Object.keys(m).filter(k => m[k])
      return keys.join(', ')
    }
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Custodian</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Active preservation</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Pending preservation</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={`${it.case_id}-${it.custodian_id}`}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>ID: {it.case_id}</div>
                </td>
                <td
                  className="dashboard-custodian-link"
                  style={{ padding: '10px 6px' }}
                  role="button"
                  tabIndex={0}
                  aria-label={`Open custodian ${it.custodian_name || it.custodian_email || ''}`}
                  title="Open custodian"
                  onClick={() => onOpenCustodian?.(it)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      onOpenCustodian?.(it)
                    }
                  }}
                >
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.custodian_name || '—'}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.custodian_email || ''}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>{summarize(it.holds_active) || '—'}</td>
                <td style={{ padding: '10px 6px' }}>{summarize(it.holds_pending) || '—'}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'requests_list') {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Request</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Submitted</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Requestor</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={it.request_id}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>#{it.request_id}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.request_type || '—'}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.case_name || (it.case_id ? `Case #${it.case_id}` : '—')}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.case_id ? `ID: ${it.case_id}` : ''}</div>
                </td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{String(it.created_at || '').slice(0, 19).replace('T', ' ')}</td>
                <td style={{ padding: '10px 6px' }}>{it.requestor_email || '—'}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {it.case_id ? (
                    <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                  ) : (
                    <span style={{ color: 'var(--muted,#64748b)' }}>—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'consent_pending') {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Custodian</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Sent</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Updated</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={`${it.case_id}-${it.consent_id}`}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>ID: {it.case_id}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.custodian_name || '—'}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.custodian_email || ''}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>{it.status || '—'}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{(it.sent_at || '').slice(0, 19).replace('T', ' ')}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{(it.updated_at || '').slice(0, 19).replace('T', ' ')}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'searches_list') {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Search</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Search status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Export status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Delivery status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Custodians</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={`${it.case_id}-${it.search_id}`}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>ID: {it.case_id}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.search_name || `Search #${it.search_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>Search ID: {it.search_id}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>{it.status_search || 'not performed'}</td>
                <td style={{ padding: '10px 6px' }}>
                  <div>{it.status_export || 'not performed'}</div>
                  {it.export_without_consent ? (
                    <div style={{ fontSize: 12, color: '#b91c1c', fontWeight: 600 }}>Exported without consent</div>
                  ) : null}
                </td>
                <td style={{ padding: '10px 6px' }}>{it.status_delivery || 'not performed'}</td>
                <td style={{ padding: '10px 6px' }}>{it.custodian_count ?? 0}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (kind === 'ntp_status_list') {
    const fmt = (val) => String(val || '').slice(0, 19).replace('T', ' ')
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Custodian</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Sent</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Acknowledged</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={`${it.case_id}-${it.custodian_id}`}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>ID: {it.case_id}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.custodian_name || 'n/a'}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.custodian_email || ''}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>{it.ntp_status || 'not sent'}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{fmt(it.ntp_sent_at)}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{fmt(it.ntp_acknowledged_at)}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'ntp_reminders_list') {
    const fmt = (val) => String(val || '').slice(0, 19).replace('T', ' ')
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Custodian</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Template</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Next send</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Stop after</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Last sent</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Count</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Status</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={`${it.case_id}-${it.reminder_id}`}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>ID: {it.case_id}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.custodian_name || 'n/a'}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.custodian_email || ''}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>{it.template_name || 'n/a'}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{fmt(it.next_send_at)}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{fmt(it.stop_after)}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>{fmt(it.last_sent_at)}</td>
                <td style={{ padding: '10px 6px' }}>{it.send_count ?? 0}</td>
                <td style={{ padding: '10px 6px' }}>{it.reminder_status || 'unknown'}</td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (kind === 'tickets_list') {
    return (
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Case</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Category</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Ticket</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Status</th>
              <th style={{ textAlign: 'left', padding: '8px 6px' }}>Assigned</th>
              <th style={{ textAlign: 'right', padding: '8px 6px' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr key={`${it.case_id}-${it.ticket}-${it.entry_id || ''}`}>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 700, color: 'var(--text,#0f172a)' }}>{it.case_name || `Case #${it.case_id}`}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>ID: {it.case_id}</div>
                </td>
                <td style={{ padding: '10px 6px' }}>{(it.category || '').replace(/_/g, ' ') || '—'}</td>
                <td style={{ padding: '10px 6px', whiteSpace: 'nowrap' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text,#0f172a)' }}>{it.ticket || '—'}</div>
                  {it.custodian_name || it.custodian_email ? (
                    <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>
                      {it.custodian_name || ''}{it.custodian_email ? ` (${it.custodian_email})` : ''}
                    </div>
                  ) : null}
                </td>
                <td style={{ padding: '10px 6px' }}>{it.status || 'unknown'}</td>
                <td style={{ padding: '10px 6px' }}>
                  <div>{it.assigned_to_display || '—'}</div>
                  {it.assigned_to_email ? <div style={{ fontSize: 12, color: 'var(--muted,#64748b)' }}>{it.assigned_to_email}</div> : null}
                </td>
                <td style={{ padding: '10px 6px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button type="button" className="btn secondary" onClick={() => onOpenCase?.(it.case_id)}>Open case</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(filtered, null, 2)}</pre>
}
