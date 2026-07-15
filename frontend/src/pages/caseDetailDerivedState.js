import { useMemo } from 'react'

export function useCaseDetailDerivedState({
  searches,
  custodians,
  ntpSearch,
  ntpReminders,
  ntpHistory,
  reminderEditor,
  pickNextReminder,
}) {
  const filteredNtpCustodians = useMemo(() => {
    const needle = (ntpSearch || '').trim().toLowerCase()
    if (!needle) return custodians
    return custodians.filter(c => {
      const name = (c.name || '').toLowerCase()
      const email = (c.email || '').toLowerCase()
      return name.includes(needle) || email.includes(needle)
    })
  }, [custodians, ntpSearch])

  const reminderMap = useMemo(() => {
    const map = new Map()
    ;(ntpReminders || []).forEach(reminder => {
      const cid = Number(reminder?.custodian_id)
      if (!Number.isFinite(cid)) return
      const bucket = map.get(cid) || []
      bucket.push(reminder)
      map.set(cid, bucket)
    })
    return map
  }, [ntpReminders])

  const custodianById = useMemo(() => {
    const map = new Map()
    ;(custodians || []).forEach(c => {
      const id = Number(c?.id)
      if (Number.isFinite(id)) map.set(id, c)
    })
    return map
  }, [custodians])

  const reminderSummary = useMemo(() => {
    const custodianIds = new Set()
    const activeCustodianIds = new Set()
    let activeCount = 0
    ;(ntpReminders || []).forEach(reminder => {
      const cid = Number(reminder?.custodian_id)
      if (!Number.isFinite(cid)) return
      custodianIds.add(cid)
      if ((reminder?.status || '').toLowerCase() === 'active') {
        activeCustodianIds.add(cid)
        activeCount += 1
      }
    })
    return {
      total: (ntpReminders || []).length,
      custodians: custodianIds.size,
      activeCustodians: activeCustodianIds.size,
      activeReminders: activeCount,
      activeCustodianIds: Array.from(activeCustodianIds),
    }
  }, [ntpReminders])

  const activeReminderCustodianIds = reminderSummary.activeCustodianIds

  const reminderGroups = useMemo(() => {
    const groups = []
    reminderMap.forEach((reminders, custodianId) => {
      const custodian = custodianById.get(custodianId) || { id: custodianId }
      const sorted = [...reminders].sort((a, b) => {
        const aTime = Date.parse(a?.next_send_at || '')
        const bTime = Date.parse(b?.next_send_at || '')
        if (!Number.isFinite(aTime) && !Number.isFinite(bTime)) return 0
        if (!Number.isFinite(aTime)) return 1
        if (!Number.isFinite(bTime)) return -1
        return aTime - bTime
      })
      const activeReminders = sorted.filter(reminder => (reminder?.status || '').toLowerCase() === 'active')
      groups.push({ custodianId, custodian, reminders: sorted, activeReminders })
    })
    groups.sort((a, b) => {
      const aName = (a.custodian?.name || a.custodian?.email || '').toLowerCase()
      const bName = (b.custodian?.name || b.custodian?.email || '').toLowerCase()
      return aName.localeCompare(bName)
    })
    return groups
  }, [reminderMap, custodianById])

  const ntpHistoryEvents = useMemo(() => (
    Array.isArray(ntpHistory?.events) ? ntpHistory.events : []
  ), [ntpHistory])

  const ntpHistoryCustodianRows = useMemo(() => {
    const rows = []
    ;(custodians || []).forEach(c => {
      const custodianId = Number(c?.id)
      const reminders = Number.isFinite(custodianId) ? (reminderMap.get(custodianId) || []) : []
      const sortedReminders = [...reminders].sort((a, b) => {
        const aNext = Date.parse(a?.next_send_at || '')
        const bNext = Date.parse(b?.next_send_at || '')
        if (!Number.isFinite(aNext) && !Number.isFinite(bNext)) return 0
        if (!Number.isFinite(aNext)) return 1
        if (!Number.isFinite(bNext)) return -1
        return aNext - bNext
      })
      const nextReminder = sortedReminders.find(r => String(r?.status || '').toLowerCase() === 'active') || null
      const lastReminder = [...sortedReminders].sort((a, b) => {
        const aLast = Date.parse(a?.last_sent_at || '')
        const bLast = Date.parse(b?.last_sent_at || '')
        if (!Number.isFinite(aLast) && !Number.isFinite(bLast)) return 0
        if (!Number.isFinite(aLast)) return 1
        if (!Number.isFinite(bLast)) return -1
        return bLast - aLast
      })[0] || null
      const statusCounts = sortedReminders.reduce((acc, reminder) => {
        const key = String(reminder?.status || 'active').trim().toLowerCase() || 'active'
        acc[key] = (acc[key] || 0) + 1
        return acc
      }, {})
      const templateNames = new Set()
      if ((c?.ntp_template_name || '').trim()) templateNames.add(String(c.ntp_template_name).trim())
      sortedReminders.forEach(reminder => {
        const templateName = (reminder?.template_name || '').trim()
        if (templateName) templateNames.add(templateName)
      })
      const hasNtpActivity = !!(
        c?.ntp_sent_at
        || c?.ntp_acknowledged_at
        || templateNames.size
        || sortedReminders.length
        || String(c?.ntp_status || '').toLowerCase() === 'sent'
        || String(c?.ntp_status || '').toLowerCase() === 'acknowledged'
      )
      if (!hasNtpActivity) return
      const reminderSummaryText = Object.entries(statusCounts)
        .map(([status, count]) => `${status}: ${count}`)
        .join(' | ')
      rows.push({
        id: c?.id,
        name: c?.name || '',
        email: c?.email || '',
        ntp_status: c?.ntp_status || 'not sent',
        ntp_template_name: Array.from(templateNames).join(', '),
        ntp_sent_at: c?.ntp_sent_at || null,
        ntp_acknowledged_at: c?.ntp_acknowledged_at || null,
        reminders_total: sortedReminders.length,
        reminders_summary: reminderSummaryText,
        next_reminder_at: nextReminder?.next_send_at || null,
        last_reminder_sent_at: lastReminder?.last_sent_at || null,
      })
    })
    rows.sort((a, b) => {
      const aName = String(a?.name || a?.email || '').toLowerCase()
      const bName = String(b?.name || b?.email || '').toLowerCase()
      return aName.localeCompare(bName)
    })
    return rows
  }, [custodians, reminderMap])

  const eligibleReminderReactivationCustodianIds = useMemo(() => (
    (reminderGroups || [])
      .filter(group => {
        const acknowledged = String(group?.custodian?.ntp_status || '').trim().toLowerCase() === 'acknowledged'
        if (acknowledged) return false
        if ((group?.activeReminders || []).length > 0) return false
        return (group?.reminders || []).some(r => (r?.status || '').toLowerCase() === 'cancelled')
      })
      .map(group => Number(group?.custodianId))
      .filter(id => Number.isFinite(id))
  ), [reminderGroups])

  const reminderTemplateNames = useMemo(() => {
    const names = new Set()
    ;(reminderEditor.reminders || []).forEach(reminder => {
      const name = (reminder?.template_name || '').trim()
      if (name) names.add(name)
    })
    return Array.from(names)
  }, [reminderEditor.reminders])

  const editorPrimaryReminder = useMemo(
    () => pickNextReminder(reminderEditor.reminders || []),
    [pickNextReminder, reminderEditor.reminders]
  )

  return {
    searchCount: searches.length,
    detailValueStyle: { whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowWrap: 'anywhere' },
    ntpFieldLabelStyle: { display: 'flex', flexDirection: 'column', gap: 4, color: '#475467', fontSize: 12 },
    ntpSelectStyle: {
      border: '1px solid var(--border, #d1d5db)',
      borderRadius: 10,
      padding: '8px 10px',
      fontSize: 13,
      background: 'var(--card, #fff)',
      color: 'var(--text, #0f172a)',
      width: '100%',
      boxShadow: '0 1px 0 rgba(15,23,42,0.06)',
    },
    ntpHintStyle: { fontSize: 11, color: '#6b7280', marginTop: 4 },
    ntpHelperTextStyle: { fontSize: 12, color: '#64748b' },
    ntpSectionCardStyle: { margin: '12px 0', padding: '12px', border: '1px solid var(--border,#e2e8f0)', borderRadius: 12, background: 'var(--card,#f8fafc)' },
    ntpModalScrollStyle: { maxHeight: '78vh', overflowY: 'auto', paddingRight: 4 },
    filteredNtpCustodians,
    reminderSummary,
    activeReminderCustodianIds,
    reminderGroups,
    ntpHistoryEvents,
    ntpHistoryCustodianRows,
    eligibleReminderReactivationCustodianIds,
    reminderTemplateNames,
    editorPrimaryReminder,
  }
}
