import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { dashboardWidgetTitle, dashboardWidgetTypeLabel } from './dashboardUtils.js'

export function WidgetCard({ widget, idx, total, data, loading, onMoveUp, onMoveDown, onRemove, onDrilldown }) {
  const title = dashboardWidgetTitle(widget)
  const body = renderWidgetBody(widget, data, loading, onDrilldown)
  return (
    <div className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text,#0f172a)' }}>{title}</div>
          <div style={{ fontSize: 12, color: 'var(--muted,#64748b)', marginTop: 2 }}>{dashboardWidgetTypeLabel(widget?.type)}</div>
        </div>
        <div className="dashboard-widget-actions">
          <button type="button" className="dashboard-icon-button" onClick={onMoveUp} disabled={idx === 0} title="Move up" aria-label="Move widget up">
            <ArrowUp size={17} aria-hidden="true" />
          </button>
          <button type="button" className="dashboard-icon-button" onClick={onMoveDown} disabled={idx === total - 1} title="Move down" aria-label="Move widget down">
            <ArrowDown size={17} aria-hidden="true" />
          </button>
          <button
            type="button"
            className="dashboard-icon-button is-danger"
            onClick={onRemove}
            title="Remove widget"
            aria-label={`Remove ${title} widget`}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
      <div style={{ marginTop: 12 }}>
        {body}
      </div>
    </div>
  )
}

function renderWidgetBody(widget, data, loading, onDrilldown) {
  if (loading) return <div style={{ color: 'var(--muted,#64748b)' }}>Loading…</div>
  if (!data) return <div style={{ color: 'var(--muted,#64748b)' }}>No data.</div>
  if (data?.error) return <div style={{ color: '#b91c1c' }}>Error: {String(data.error)}</div>

  if (widget.type === 'case_counts') {
    return (
      <div className="dashboard-stat-grid">
        <Stat
          label="Open"
          value={data.open}
          tone="success"
          onClick={() => onDrilldown?.({ kind: 'cases_list', title: 'Active cases', config: { closed: false } })}
        />
        <Stat
          label="Closed"
          value={data.closed}
          tone="neutral"
          onClick={() => onDrilldown?.({ kind: 'cases_list', title: 'Inactive cases', config: { closed: true } })}
        />
        <Stat
          label="Total"
          value={data.total}
          tone="info"
          onClick={() => onDrilldown?.({ kind: 'cases_list', title: 'All matters', config: {} })}
        />
        <div style={{ gridColumn: '1 / -1', color: 'var(--muted,#64748b)', fontSize: 13 }}>
          Created last {data.created_last_days} days:{' '}
          <span
            role="button"
            tabIndex={0}
            onClick={() => onDrilldown?.({ kind: 'cases_list', title: `Matters created in last ${data.created_last_days} days`, config: { created_last_days: data.created_last_days } })}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onDrilldown?.({ kind: 'cases_list', title: `Matters created in last ${data.created_last_days} days`, config: { created_last_days: data.created_last_days } }) }}
            style={{ color: 'var(--text,#0f172a)', fontWeight: 800, cursor: 'pointer', textDecoration: 'underline' }}
            title="Click for details"
          >
            {data.created_recent}
          </span>
        </div>
      </div>
    )
  }

  if (widget.type === 'consent_status') {
    const by = data.by_status || {}
    const rows = Object.entries(by).sort((a, b) => b[1] - a[1])
    return (
      <div>
        <div className="dashboard-stat-grid">
          <Stat
            label="Pending"
            value={data.pending}
            tone="warning"
            onClick={() => onDrilldown?.({
              kind: 'consent_pending',
              title: 'Pending consents (Sent/Delivered)',
              config: widget.config || {},
            })}
          />
          <Stat
            label="Sent"
            value={by.sent || 0}
            tone="info"
            onClick={() => onDrilldown?.({
              kind: 'consent_pending',
              title: 'Consents in status: sent',
              config: { ...(widget.config || {}), status_filter: 'sent' },
            })}
          />
          <Stat
            label="Delivered"
            value={by.delivered || 0}
            tone="warning"
            onClick={() => onDrilldown?.({
              kind: 'consent_pending',
              title: 'Consents in status: delivered',
              config: { ...(widget.config || {}), status_filter: 'delivered' },
            })}
          />
        </div>
        {rows.length > 0 && (
          <div style={{ marginTop: 10, fontSize: 13, color: 'var(--muted,#64748b)' }}>
            {rows.map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span>{k}</span>
                <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (widget.type === 'search_status') {
    const bySearch = data.by_search || {}
    const byExport = data.by_export || {}
    const byDelivery = data.by_delivery || {}
    const rows = [
      { label: 'Search status', value: bySearch },
      { label: 'Export status', value: byExport },
      { label: 'Delivery status', value: byDelivery },
    ]
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="dashboard-stat-grid">
          <Stat
            label="Total"
            value={data.total || 0}
            tone="info"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'All searches', config: { ...(widget.config || {}), metric: 'all' } })}
          />
          <Stat
            label="Search done"
            value={data.search_performed || 0}
            tone="success"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Searches performed', config: { ...(widget.config || {}), metric: 'search_performed' } })}
          />
          <Stat
            label="Search pending"
            value={data.search_not_performed || 0}
            tone="warning"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Searches not performed', config: { ...(widget.config || {}), metric: 'search_not_performed' } })}
          />
          <Stat
            label="Exported"
            value={data.export_performed || 0}
            tone="success"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Searches exported', config: { ...(widget.config || {}), metric: 'export_performed' } })}
          />
          <Stat
            label="Delivery pending"
            value={data.delivery_pending || 0}
            tone="warning"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Exported searches pending delivery', config: { ...(widget.config || {}), metric: 'delivery_pending' } })}
          />
          <Stat
            label="Delivered"
            value={data.delivery_performed || 0}
            tone="success"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Searches marked delivered', config: { ...(widget.config || {}), metric: 'delivery_performed' } })}
          />
          <Stat
            label="Delivery N/R"
            value={data.delivery_not_required || 0}
            tone="neutral"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Searches with delivery not required', config: { ...(widget.config || {}), metric: 'delivery_not_required' } })}
          />
          <Stat
            label="Exported no consent"
            value={data.exported_without_consent || 0}
            tone="danger"
            onClick={() => onDrilldown?.({ kind: 'searches_list', title: 'Searches exported without consent', config: { ...(widget.config || {}), metric: 'export_without_consent' } })}
          />
        </div>
        <div style={{ fontSize: 13, color: 'var(--muted,#64748b)', display: 'grid', gap: 8 }}>
          {rows.map((section) => {
            const entries = Object.entries(section.value || {}).sort((a, b) => b[1] - a[1])
            if (!entries.length) return null
            return (
              <div key={section.label}>
                <div style={{ color: 'var(--text,#0f172a)', fontWeight: 700 }}>{section.label}</div>
                {entries.map(([k, v]) => (
                  <div key={`${section.label}-${k}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <span>{k}</span>
                    <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{v}</span>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
      </div>
    )
  }
  if (widget.type === 'ntp_status') {
    const by = data.by_status || {}
    const rows = Object.entries(by).sort((a, b) => b[1] - a[1])
    return (
      <div>
        <div className="dashboard-stat-grid">
          <Stat
            label="Not sent"
            value={by['not sent'] || 0}
            tone="warning"
            onClick={() => onDrilldown?.({
              kind: 'ntp_status_list',
              title: 'NTP status: not sent',
              config: { ...(widget.config || {}), status_filter: 'not sent' },
            })}
          />
          <Stat
            label="Sent"
            value={by.sent || 0}
            tone="info"
            onClick={() => onDrilldown?.({
              kind: 'ntp_status_list',
              title: 'NTP status: sent',
              config: { ...(widget.config || {}), status_filter: 'sent' },
            })}
          />
          <Stat
            label="Acknowledged"
            value={by.acknowledged || 0}
            tone="success"
            onClick={() => onDrilldown?.({
              kind: 'ntp_status_list',
              title: 'NTP status: acknowledged',
              config: { ...(widget.config || {}), status_filter: 'acknowledged' },
            })}
          />
          <Stat
            label="Silent"
            value={(by.silent || 0) + (by.na || 0)}
            tone="neutral"
            onClick={() => onDrilldown?.({
              kind: 'ntp_status_list',
              title: 'NTP status: silent',
              config: { ...(widget.config || {}), status_filter: 'silent' },
            })}
          />
        </div>
        <div style={{ marginTop: 10, fontSize: 13, color: 'var(--muted,#64748b)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <span>Total</span>
            <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{data.total ?? 0}</span>
          </div>
          {rows.map(([k, v]) => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
              <span>{k}</span>
              <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{v}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (widget.type === 'ntp_reminders') {
    const daysAhead = data.days_ahead || widget?.config?.days_ahead || 7
    const nextDue = data.next_due_at ? String(data.next_due_at).slice(0, 19).replace('T', ' ') : 'None scheduled'
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="dashboard-stat-grid">
          <Stat
            label="Due now"
            value={data.due_now || 0}
            tone="danger"
            onClick={() => onDrilldown?.({
              kind: 'ntp_reminders_list',
              title: 'NTP reminders due now',
              config: { ...(widget.config || {}), mode: 'due_now' },
            })}
          />
          <Stat
            label={`Due next ${daysAhead}d`}
            value={data.due_soon || 0}
            tone="warning"
            onClick={() => onDrilldown?.({
              kind: 'ntp_reminders_list',
              title: `NTP reminders due in next ${daysAhead} days`,
              config: { ...(widget.config || {}), mode: 'due_soon', days_ahead: daysAhead },
            })}
          />
          <Stat
            label="Active"
            value={data.active || 0}
            tone="info"
            onClick={() => onDrilldown?.({
              kind: 'ntp_reminders_list',
              title: 'Active NTP reminders',
              config: { ...(widget.config || {}), mode: 'active' },
            })}
          />
        </div>
        <div style={{ fontSize: 13, color: 'var(--muted,#64748b)' }}>
          Next scheduled: <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{nextDue}</span>
        </div>
      </div>
    )
  }

  if (widget.type === 'hold_status') {
    return (
      <div className="dashboard-stat-grid">
        <Stat
          label="Custodians"
          value={data.custodians}
          tone="info"
          onClick={() => onDrilldown?.({ kind: 'holds_list', title: 'Preservation custodians', config: { ...(widget.config || {}), mode: 'all' } })}
        />
        <Stat
          label="Active preservation"
          value={data.active_any}
          tone="success"
          onClick={() => onDrilldown?.({ kind: 'holds_list', title: 'Custodians with active preservation', config: { ...(widget.config || {}), mode: 'active' } })}
        />
        <Stat
          label="Pending preservation"
          value={data.pending_any}
          tone="warning"
          onClick={() => onDrilldown?.({ kind: 'holds_list', title: 'Custodians with pending preservation', config: { ...(widget.config || {}), mode: 'pending' } })}
        />
        <div style={{ gridColumn: '1 / -1', fontSize: 13, color: 'var(--muted,#64748b)' }}>
          Pending by source:
          <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6 }}>
            {Object.entries(data.pending_by_type || {}).map(([k, v]) => (
              <div
                key={k}
                role="button"
                tabIndex={0}
                onClick={() => onDrilldown?.({ kind: 'holds_list', title: `Pending preservation: ${k}`, config: { ...(widget.config || {}), mode: 'pending', hold_type: k } })}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onDrilldown?.({ kind: 'holds_list', title: `Pending preservation: ${k}`, config: { ...(widget.config || {}), mode: 'pending', hold_type: k } }) }}
                style={{ display: 'flex', justifyContent: 'space-between', gap: 10, cursor: 'pointer' }}
                title="Click for details"
              >
                <span style={{ textDecoration: 'underline' }}>{k}</span>
                <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (widget.type === 'requests_sla') {
    const by = data.by_type || {}
    const age = data.age_buckets || {}
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="dashboard-stat-grid">
          <Stat
            label="Pending"
            value={data.pending}
            tone="warning"
            onClick={() => onDrilldown?.({ kind: 'requests_list', title: 'Pending requests', config: { status: 'pending' } })}
          />
          <Stat
            label="<24h"
            value={age.lt_24h || 0}
            tone="info"
            onClick={() => onDrilldown?.({ kind: 'requests_list', title: 'Pending requests (<24h)', config: { status: 'pending', age_bucket: 'lt_24h' } })}
          />
          <Stat
            label="1–3d"
            value={age.d1_3 || 0}
            tone="warning"
            onClick={() => onDrilldown?.({ kind: 'requests_list', title: 'Pending requests (1–3 days)', config: { status: 'pending', age_bucket: 'd1_3' } })}
          />
          <Stat
            label=">3d"
            value={age.gt_3d || 0}
            tone="danger"
            onClick={() => onDrilldown?.({ kind: 'requests_list', title: 'Pending requests (>3 days)', config: { status: 'pending', age_bucket: 'gt_3d' } })}
          />
        </div>
        <div style={{ fontSize: 13, color: 'var(--muted,#64748b)' }}>
          {Object.entries(by).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
            <div
              key={k}
              role="button"
              tabIndex={0}
              onClick={() => onDrilldown?.({ kind: 'requests_list', title: `Pending requests: ${k}`, config: { status: 'pending', request_type: k } })}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onDrilldown?.({ kind: 'requests_list', title: `Pending requests: ${k}`, config: { status: 'pending', request_type: k } }) }}
              style={{ display: 'flex', justifyContent: 'space-between', gap: 12, cursor: 'pointer' }}
              title="Click for details"
            >
              <span style={{ textDecoration: 'underline' }}>{k}</span>
              <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{v}</span>
            </div>
          ))}
        </div>
        {(data.oldest || []).length > 0 && (
          <div style={{ marginTop: 6 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text,#0f172a)' }}>Oldest</div>
            <div style={{ marginTop: 6, fontSize: 13, color: 'var(--muted,#64748b)' }}>
              {(data.oldest || []).map((r) => (
                <div key={r.id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                  <span>#{r.id} {r.request_type} {r.case_name ? `• ${r.case_name}` : ''}</span>
                  <span>{String(r.created_at || '').slice(0, 10)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  if (widget.type === 'open_tickets') {
    const byCat = data.by_category || {}
    const categories = Object.entries(byCat).sort((a, b) => b[1] - a[1])
    const top = categories.slice(0, 4)
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="dashboard-stat-grid">
          <Stat
            label="Open"
            value={data.open}
            tone="success"
            onClick={() => onDrilldown?.({ kind: 'tickets_list', title: 'Open tickets', config: { ...(widget.config || {}), open_only: true } })}
          />
          {top.map(([cat, count]) => (
            <Stat
              key={cat}
              label={cat.replace(/_/g, ' ')}
              value={count}
              tone="info"
              onClick={() => onDrilldown?.({ kind: 'tickets_list', title: `Open tickets: ${cat}`, config: { ...(widget.config || {}), open_only: true, category: cat } })}
            />
          ))}
        </div>
        {categories.length > 0 && (
          <div style={{ fontSize: 13, color: 'var(--muted,#64748b)' }}>
            {categories.map(([k, v]) => (
              <div
                key={k}
                role="button"
                tabIndex={0}
                onClick={() => onDrilldown?.({ kind: 'tickets_list', title: `Open tickets: ${k}`, config: { ...(widget.config || {}), open_only: true, category: k } })}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onDrilldown?.({ kind: 'tickets_list', title: `Open tickets: ${k}`, config: { ...(widget.config || {}), open_only: true, category: k } }) }}
                style={{ display: 'flex', justifyContent: 'space-between', gap: 12, cursor: 'pointer' }}
                title="Click for details"
              >
                <span style={{ textDecoration: 'underline' }}>{k}</span>
                <span style={{ color: 'var(--text,#0f172a)', fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        )}
        {data.truncated ? (
          <div style={{ marginTop: 6, fontSize: 12, color: '#b45309' }}>
            Showing live status for up to {data.max_tickets} tickets.
          </div>
        ) : null}
      </div>
    )
  }

  return <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{JSON.stringify(data, null, 2)}</pre>
}

function Stat({ label, value, onClick, tone = 'neutral' }) {
  const clickable = typeof onClick === 'function'
  return (
    <div
      className={`dashboard-stat dashboard-stat--${tone}${clickable ? ' is-clickable' : ''}`}
      onClick={clickable ? onClick : undefined}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onKeyDown={clickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick() } : undefined}
      title={clickable ? 'Click for details' : undefined}
    >
      <div className="dashboard-stat__label">{label}</div>
      <div className="dashboard-stat__value">
        {value ?? '—'}
      </div>
    </div>
  )
}
