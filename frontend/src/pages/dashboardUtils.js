const PRESERVATION_WIDGET_TYPE = 'hold_status'

export function dashboardWidgetTitle(widget) {
  const title = String(widget?.title || '').trim()
  if (widget?.type === PRESERVATION_WIDGET_TYPE && (!title || /^holds?$/i.test(title))) {
    return 'Preservation'
  }
  return title || String(widget?.type || 'Widget').trim()
}

export function dashboardWidgetTypeLabel(type) {
  if (type === PRESERVATION_WIDGET_TYPE) return 'preservation status'
  return String(type || '').replace(/_/g, ' ')
}

export function mergePreservationDrilldownItems(...groups) {
  const merged = new Map()
  groups.flat().forEach((item) => {
    if (!item || typeof item !== 'object') return
    const key = [item.case_id, item.hold_id, item.custodian_id].join(':')
    const current = merged.get(key)
    if (!current) {
      merged.set(key, {
        ...item,
        holds_active: { ...(item.holds_active || {}) },
        holds_pending: { ...(item.holds_pending || {}) },
      })
      return
    }
    merged.set(key, {
      ...current,
      ...item,
      holds_active: { ...(current.holds_active || {}), ...(item.holds_active || {}) },
      holds_pending: { ...(current.holds_pending || {}), ...(item.holds_pending || {}) },
    })
  })
  return [...merged.values()]
}

export function dashboardDrilldownWidth(kind, itemCount) {
  if (!itemCount) return 480
  const widths = {
    cases_list: 900,
    holds_list: 880,
    requests_list: 840,
    consent_pending: 920,
    searches_list: 1080,
    ntp_status_list: 920,
    ntp_reminders_list: 1120,
    tickets_list: 980,
  }
  return widths[kind] || 760
}

export function custodianDetailPath(item) {
  const params = new URLSearchParams()
  const email = String(item?.custodian_email || '').trim()
  const name = String(item?.custodian_name || '').trim()
  if (email) params.set('email', email)
  else if (name) params.set('name', name)
  const query = params.toString()
  return query ? `/custodians/detail?${query}` : ''
}
