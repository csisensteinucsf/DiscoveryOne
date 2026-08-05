import { useEffect, useMemo, useState } from 'react'
import Modal from '../components/Modal.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import { useConfirm } from '../components/ConfirmProvider.jsx'
import { useAuth } from '../auth.jsx'
import { useNavigate } from 'react-router-dom'
import { WidgetCard } from './DashboardWidgets.jsx'
import { DrilldownTable } from './DashboardDrilldownTable.jsx'
import {
  custodianDetailPath,
  dashboardDrilldownWidth,
  mergePreservationDrilldownItems,
  shouldCompactDashboardDrilldown,
} from './dashboardUtils.js'

function makeId(prefix = 'id') {
  try {
    const c = globalThis?.crypto
    if (c?.randomUUID) return `${prefix}-${c.randomUUID()}`
  } catch { /* ignore */ }
  return `${prefix}-${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`
}

const WIDGET_CATALOG = [
  {
    type: 'case_counts',
    title: 'Cases',
    description: 'Active vs inactive cases, plus recently created.',
    defaultConfig: { created_last_days: 7 },
  },
  {
    type: 'consent_status',
    title: 'Consents',
    description: 'E-signature consent status counts (includes pending).',
    defaultConfig: { open_only: true },
  },
  {
    type: 'search_status',
    title: 'Searches',
    description: 'Search pipeline status: performed, exported, and delivered.',
    defaultConfig: { open_only: true },
  },
  {
    type: 'ntp_status',
    title: 'NTP Status',
    description: 'Custodian NTP status counts.',
    defaultConfig: { open_only: true },
  },
  {
    type: 'ntp_reminders',
    title: 'NTP Reminders',
    description: 'Upcoming NTP reminders and schedules.',
    defaultConfig: { open_only: true, days_ahead: 7 },
  },
  {
    type: 'hold_status',
    title: 'Preservation',
    description: 'Custodians with active and pending preservation sources.',
    defaultConfig: { open_only: true },
  },
  {
    type: 'requests_sla',
    title: 'Requests',
    description: 'Pending intake requests and age buckets.',
    defaultConfig: { oldest_limit: 5 },
  },
  {
    type: 'open_tickets',
    title: 'Open Tickets',
    description: 'Non-completed external tickets attached to cases.',
    defaultConfig: { open_only: true, refresh_live: true },
  },
]

const DEFAULT_WIDGET_ORDER = ['case_counts', 'consent_status', 'search_status', 'hold_status', 'requests_sla', 'open_tickets']
const DEFAULT_WIDGET_IDS = {
  case_counts: 'cases',
  consent_status: 'consents',
  search_status: 'searches',
  hold_status: 'holds',
  requests_sla: 'requests',
  open_tickets: 'tickets',
}

function defaultConfig() {
  const defaultWidgets = DEFAULT_WIDGET_ORDER.map((type, idx) => {
    const meta = WIDGET_CATALOG.find(w => w.type === type)
    return {
      id: DEFAULT_WIDGET_IDS[type] || makeId(`widget-${idx}`),
      type: meta?.type || type,
      title: meta?.title || 'Widget',
      config: meta?.defaultConfig || {},
    }
  })
  return {
    version: 1,
    active_dashboard_id: 'default',
    dashboards: [
      {
        id: 'default',
        name: 'My Dashboard',
        widgets: defaultWidgets,
      },
      {
        id: 'ntp',
        name: 'NTPs',
        widgets: [
          { id: 'ntp-status', type: 'ntp_status', title: 'NTP Status', config: { open_only: true } },
          { id: 'ntp-reminders', type: 'ntp_reminders', title: 'NTP Reminders', config: { open_only: true, days_ahead: 7 } },
        ],
      },
    ],
  }
}

function activeDashboard(cfg) {
  const dashboards = cfg?.dashboards || []
  const activeId = cfg?.active_dashboard_id
  return dashboards.find(d => d.id === activeId) || dashboards[0] || null
}

export default function Dashboards({ apiBase = '/api' }) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const confirm = useConfirm()
  const navigate = useNavigate()

  const [cfg, setCfg] = useState(null)
  const [loading, setLoading] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  const [widgetData, setWidgetData] = useState({})
  const [widgetLoading, setWidgetLoading] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  const [addOpen, setAddOpen] = useState(false)
  const [addType, setAddType] = useState(WIDGET_CATALOG[0]?.type || 'case_counts')
  const [addTitle, setAddTitle] = useState('')

  const [renameOpen, setRenameOpen] = useState(false)
  const [renameValue, setRenameValue] = useState('')

  const [newDashOpen, setNewDashOpen] = useState(false)
  const [newDashName, setNewDashName] = useState('')

  const [drillOpen, setDrillOpen] = useState(false)
  const [drillTitle, setDrillTitle] = useState('')
  const [drillKind, setDrillKind] = useState('')
  const [drillConfig, setDrillConfig] = useState({})
  const [drillItems, setDrillItems] = useState([])
  const [drillLoading, setDrillLoading] = useState(false)
  const [drillFilter, setDrillFilter] = useState('')

  const active = useMemo(() => activeDashboard(cfg || {}), [cfg])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetch(`${apiBase}/dashboards`, { credentials: 'include' })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (!cancelled) {
          setCfg(data)
          setDirty(false)
        }
      } catch {
        if (!cancelled) {
          setCfg(defaultConfig())
          setDirty(true)
          showToast('Dashboards loaded with defaults (server config not available yet).', { variant: 'warn' })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [apiBase, showToast])

  useEffect(() => {
    if (!cfg || !active) return
    const widgets = Array.isArray(active.widgets) ? active.widgets : []
    const payload = { widgets: widgets.map(w => ({ id: w.id, type: w.type, config: w.config || {} })) }
    let cancelled = false
    const timer = window.setTimeout(async () => {
      setWidgetLoading(true)
      try {
        const res = await fetch(`${apiBase}/dashboards/resolve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(payload),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        if (!cancelled) setWidgetData(data?.results || {})
      } catch {
        if (!cancelled) setWidgetData({})
      } finally {
        if (!cancelled) setWidgetLoading(false)
      }
    }, 250)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [apiBase, cfg, active?.id, active?.widgets, refreshKey])

  const setActiveDashboardId = (dashboardId) => {
    setCfg(prev => {
      const next = { ...(prev || defaultConfig()), active_dashboard_id: dashboardId }
      return next
    })
    setDirty(true)
  }

  const updateActiveDashboard = (mutator) => {
    setCfg(prev => {
      const current = prev || defaultConfig()
      const dashboards = Array.isArray(current.dashboards) ? [...current.dashboards] : []
      const idx = dashboards.findIndex(d => d.id === current.active_dashboard_id)
      if (idx === -1) return current
      const updated = mutator({ ...dashboards[idx] })
      dashboards[idx] = updated
      return { ...current, dashboards }
    })
    setDirty(true)
  }

  const save = async () => {
    if (!cfg) return
    setSaving(true)
    try {
      const res = await fetch(`${apiBase}/dashboards`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(cfg),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setDirty(false)
      showToast('Dashboard saved.', { variant: 'success' })
    } catch {
      showToast('Failed to save dashboard.', { variant: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const openAddWidget = () => {
    setAddType(WIDGET_CATALOG[0]?.type || 'case_counts')
    setAddTitle('')
    setAddOpen(true)
  }

  const addWidget = () => {
    const meta = WIDGET_CATALOG.find(w => w.type === addType) || WIDGET_CATALOG[0]
    const title = (addTitle || meta?.title || 'Widget').trim()
    updateActiveDashboard(d => {
      const widgets = Array.isArray(d.widgets) ? [...d.widgets] : []
      widgets.push({
        id: makeId('widget'),
        type: addType,
        title,
        config: meta?.defaultConfig || {},
      })
      return { ...d, widgets }
    })
    setAddOpen(false)
  }

  const removeWidget = async (widgetId) => {
    const ok = await confirm({ title: 'Remove widget?', description: 'This will remove it from your dashboard.', destructive: true, confirmLabel: 'Remove' })
    if (!ok) return
    updateActiveDashboard(d => {
      const widgets = (d.widgets || []).filter(w => w.id !== widgetId)
      return { ...d, widgets }
    })
  }

  const moveWidget = (widgetId, dir) => {
    updateActiveDashboard(d => {
      const widgets = Array.isArray(d.widgets) ? [...d.widgets] : []
      const idx = widgets.findIndex(w => w.id === widgetId)
      if (idx === -1) return d
      const next = idx + dir
      if (next < 0 || next >= widgets.length) return d
      const tmp = widgets[idx]
      widgets[idx] = widgets[next]
      widgets[next] = tmp
      return { ...d, widgets }
    })
  }

  const openRename = () => {
    setRenameValue(active?.name || '')
    setRenameOpen(true)
  }

  const doRename = () => {
    const name = (renameValue || '').trim()
    if (!name) return
    updateActiveDashboard(d => ({ ...d, name }))
    setRenameOpen(false)
  }

  const openNewDashboard = () => {
    setNewDashName('')
    setNewDashOpen(true)
  }

  const createDashboard = () => {
    const name = (newDashName || '').trim() || 'New Dashboard'
    const id = makeId('dash')
    setCfg(prev => {
      const current = prev || defaultConfig()
      const dashboards = Array.isArray(current.dashboards) ? [...current.dashboards] : []
      dashboards.push({ id, name, widgets: [] })
      return { ...current, dashboards, active_dashboard_id: id }
    })
    setDirty(true)
    setNewDashOpen(false)
  }

  const deleteDashboard = async () => {
    const dashboards = cfg?.dashboards || []
    if (!active || dashboards.length <= 1) return
    const ok = await confirm({
      title: 'Delete dashboard?',
      description: `Delete "${active.name}"? This cannot be undone.`,
      destructive: true,
      confirmLabel: 'Delete',
    })
    if (!ok) return
    setCfg(prev => {
      const current = prev || defaultConfig()
      const nextDashboards = (current.dashboards || []).filter(d => d.id !== active.id)
      const nextActive = nextDashboards[0]?.id || 'default'
      return { ...current, dashboards: nextDashboards, active_dashboard_id: nextActive }
    })
    setDirty(true)
  }

  const refresh = () => {
    setRefreshKey(k => k + 1)
  }

  useEffect(() => {
    if (!drillOpen || !drillKind) return
    let cancelled = false
    const run = async () => {
      setDrillLoading(true)
      setDrillItems([])
      try {
        const requestItems = async (config) => {
          const res = await fetch(`${apiBase}/dashboards/drilldown`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({ kind: drillKind, config }),
          })
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          const data = await res.json()
          return Array.isArray(data?.items) ? data.items : []
        }

        let items
        if (drillKind === 'holds_list' && drillConfig?.mode === 'all') {
          const baseConfig = { ...(drillConfig || {}) }
          delete baseConfig.mode
          const [activeItems, pendingItems] = await Promise.all([
            requestItems({ ...baseConfig, mode: 'active' }),
            requestItems({ ...baseConfig, mode: 'pending' }),
          ])
          items = mergePreservationDrilldownItems(activeItems, pendingItems)
        } else {
          items = await requestItems(drillConfig)
        }
        if (!cancelled) setDrillItems(items)
      } catch {
        if (!cancelled) setDrillItems([])
      } finally {
        if (!cancelled) setDrillLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [apiBase, drillOpen, drillKind, drillConfig])

  const openDrilldown = ({ kind, title, config }) => {
    setDrillTitle(title || 'Details')
    setDrillKind(kind)
    setDrillConfig(config || {})
    setDrillFilter('')
    setDrillOpen(true)
  }

  const compactDrilldown = shouldCompactDashboardDrilldown(drillLoading, drillItems.length)

  if (loading) return <div className="card" style={{ marginTop: 24 }}>Loading…</div>

  const dashboards = cfg?.dashboards || []

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: '4px 0 0', color: 'var(--sidebar-fg)' }}>Dashboards</h2>
          <div style={{ color: 'var(--muted,#64748b)', marginTop: 6, lineHeight: 1.4 }}>
            Build a personal dashboard to track consent progress, search status, preservation, requests, and other case health signals.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <button type="button" className="btn secondary" onClick={refresh} disabled={widgetLoading}>Refresh</button>
          <button type="button" className="btn secondary" onClick={openNewDashboard}>New dashboard</button>
          <button type="button" className="btn secondary" onClick={openRename} disabled={!active}>Rename</button>
          <button type="button" className="btn" onClick={openAddWidget} disabled={!active}>Add widget</button>
          <button type="button" className="btn danger" onClick={deleteDashboard} disabled={!active || dashboards.length <= 1}>Delete</button>
          <button type="button" className="btn primary" onClick={save} disabled={!dirty || saving}>
            {saving ? 'Saving…' : (dirty ? 'Save changes' : 'Saved')}
          </button>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16, display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ minWidth: 240, flex: '0 0 auto' }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: 'var(--muted,#64748b)' }}>Dashboard</label>
          <select
            value={cfg?.active_dashboard_id || ''}
            onChange={(e) => setActiveDashboardId(e.target.value)}
            style={{ marginTop: 6 }}
          >
            {dashboards.map(d => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>
        <div style={{ color: 'var(--muted,#64748b)', fontSize: 13 }}>
          Signed in as <span style={{ fontWeight: 600 }}>{user?.username || 'user'}</span>
        </div>
      </div>

      {!active ? (
        <div className="empty" style={{ marginTop: 16 }}>No dashboard selected.</div>
      ) : (
        <div style={{ marginTop: 16, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
          {(active.widgets || []).map((w, idx) => (
            <WidgetCard
              key={w.id}
              widget={w}
              idx={idx}
              total={(active.widgets || []).length}
              data={widgetData?.[w.id]}
              loading={widgetLoading}
              onMoveUp={() => moveWidget(w.id, -1)}
              onMoveDown={() => moveWidget(w.id, 1)}
              onRemove={() => removeWidget(w.id)}
              onDrilldown={openDrilldown}
            />
          ))}
          {(active.widgets || []).length === 0 && (
            <div className="empty" style={{ gridColumn: '1 / -1' }}>
              No widgets yet. Click “Add widget” to start.
            </div>
          )}
        </div>
      )}

      {addOpen && (
        <Modal
          title="Add widget"
          onClose={() => setAddOpen(false)}
          width={480}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="btn ghost" onClick={() => setAddOpen(false)}>Cancel</button>
              <button type="button" className="btn primary" onClick={addWidget}>Add</button>
            </div>
          )}
        >
          <div className="field">
            <label>Widget type</label>
            <select value={addType} onChange={(e) => setAddType(e.target.value)}>
              {WIDGET_CATALOG.map(w => (
                <option key={w.type} value={w.type}>{w.title}</option>
              ))}
            </select>
            <div style={{ fontSize: 13, color: 'var(--muted,#64748b)' }}>
              {WIDGET_CATALOG.find(w => w.type === addType)?.description || ''}
            </div>
          </div>
          <div className="field">
            <label>Title</label>
            <input value={addTitle} onChange={(e) => setAddTitle(e.target.value)} placeholder="e.g., Consent pipeline" />
          </div>
        </Modal>
      )}

      {renameOpen && (
        <Modal
          title="Rename dashboard"
          onClose={() => setRenameOpen(false)}
          width={420}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="btn ghost" onClick={() => setRenameOpen(false)}>Cancel</button>
              <button type="button" className="btn primary" onClick={doRename} disabled={!renameValue.trim()}>Save</button>
            </div>
          )}
        >
          <div className="field">
            <label>Name</label>
            <input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} />
          </div>
        </Modal>
      )}

      {newDashOpen && (
        <Modal
          title="New dashboard"
          onClose={() => setNewDashOpen(false)}
          width={420}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="btn ghost" onClick={() => setNewDashOpen(false)}>Cancel</button>
              <button type="button" className="btn primary" onClick={createDashboard}>Create</button>
            </div>
          )}
        >
          <div className="field">
            <label>Name</label>
            <input value={newDashName} onChange={(e) => setNewDashName(e.target.value)} placeholder="e.g., Weekly triage" />
          </div>
        </Modal>
      )}

      {drillOpen && (
        <Modal
          title={drillTitle || 'Details'}
          onClose={() => setDrillOpen(false)}
          width={dashboardDrilldownWidth(drillKind, drillItems.length)}
          bodyStyle={compactDrilldown ? { paddingBlock: 12, flex: '0 1 auto' } : undefined}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, width: '100%' }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: 'var(--muted,#64748b)' }}>{drillItems.length} item(s)</span>
              </div>
              <button type="button" className="btn secondary" onClick={() => setDrillOpen(false)}>Close</button>
            </div>
          )}
        >
          {!compactDrilldown && (
          <div className="field">
            <label>Filter</label>
            <input value={drillFilter} onChange={(e) => setDrillFilter(e.target.value)} placeholder="Search case, custodian, status…" />
          </div>
          )}
          <DrilldownTable
            kind={drillKind}
            items={drillItems}
            filter={drillFilter}
            loading={drillLoading}
            onOpenCase={(caseId) => {
              if (!caseId) return
              setDrillOpen(false)
              navigate(`/cases/${caseId}`)
            }}
            onOpenCustodian={(item) => {
              const target = custodianDetailPath(item)
              if (!target) return
              setDrillOpen(false)
              navigate(target)
            }}
          />
        </Modal>
      )}
    </div>
  )
}
