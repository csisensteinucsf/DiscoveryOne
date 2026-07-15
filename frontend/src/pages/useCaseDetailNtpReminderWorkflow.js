import { useCallback, useState } from 'react'
import { REMINDER_DURATION_DEFAULT, REMINDER_INTERVAL_DEFAULT, daysFromNow } from './caseDetailUtils.js'

export function useCaseDetailNtpReminderWorkflow({
  apiBase,
  caseId,
  loadNtpReminders,
  pickNextReminder,
  showToast,
}) {
  const [reminderEditor, setReminderEditor] = useState({
    open: false,
    custodian: null,
    reminders: [],
    intervalDays: REMINDER_INTERVAL_DEFAULT,
    durationDays: REMINDER_DURATION_DEFAULT,
    enabled: true,
    applyToAll: false,
    busy: false,
  })
  const [showReminderListModal, setShowReminderListModal] = useState(false)
  const [reactivatingNtpReminders, setReactivatingNtpReminders] = useState({})
  const [reactivatingNtpRemindersBulk, setReactivatingNtpRemindersBulk] = useState(false)

  const resetReminderEditor = useCallback(() => {
    setReminderEditor({
      open: false,
      custodian: null,
      reminders: [],
      intervalDays: REMINDER_INTERVAL_DEFAULT,
      durationDays: REMINDER_DURATION_DEFAULT,
      enabled: true,
      applyToAll: false,
      busy: false,
    })
  }, [])

  const openReminderEditor = useCallback((custodian, reminders) => {
    const active = Array.isArray(reminders) ? reminders.filter(reminder => reminder?.status === 'active') : []
    if (!custodian || active.length === 0) return
    const next = pickNextReminder(active)
    const interval = Math.max(1, Number(next?.interval_days) || REMINDER_INTERVAL_DEFAULT)
    const remaining = daysFromNow(next?.stop_after)
    const duration = remaining && remaining > 0 ? remaining : REMINDER_DURATION_DEFAULT
    setReminderEditor({
      open: true,
      custodian,
      reminders: active,
      intervalDays: interval,
      durationDays: duration,
      enabled: true,
      applyToAll: false,
      busy: false,
    })
  }, [pickNextReminder])

  const closeReminderEditor = useCallback(() => {
    if (reminderEditor.busy) return
    resetReminderEditor()
  }, [reminderEditor.busy, resetReminderEditor])

  const openReminderListModal = useCallback(async () => {
    await loadNtpReminders()
    setShowReminderListModal(true)
  }, [loadNtpReminders])

  const reactivateCancelledNtpReminders = useCallback(async (custodianId, opts = {}) => {
    const id = Number(custodianId)
    if (!caseId || !Number.isFinite(id)) return false
    const { reload = true, toast = true } = opts || {}
    setReactivatingNtpReminders(prev => ({ ...prev, [id]: true }))
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/reminders/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ enabled: true }),
      })
      if (!res.ok) {
        let msg = ''
        try {
          const data = await res.json()
          msg = data?.detail || ''
        } catch {
          msg = await res.text().catch(() => '')
        }
        throw new Error(msg || 'Unable to enable reminders')
      }
      if (toast) showToast('NTP reminders turned on.', { variant: 'success' })
      if (reload) await loadNtpReminders()
      return true
    } catch (err) {
      if (toast) showToast(err?.message || 'Unable to enable reminders.', { variant: 'error' })
      return false
    } finally {
      setReactivatingNtpReminders(prev => {
        const next = { ...prev }
        delete next[id]
        return next
      })
    }
  }, [apiBase, caseId, loadNtpReminders, showToast])

  const reactivateEligibleCancelledNtpReminders = useCallback(async (eligibleReminderReactivationCustodianIds) => {
    const ids = Array.isArray(eligibleReminderReactivationCustodianIds) ? eligibleReminderReactivationCustodianIds : []
    if (!caseId || ids.length === 0) return
    const ok = window.confirm(`Turn NTP reminders back on for ${ids.length} custodian${ids.length === 1 ? '' : 's'} who have not acknowledged the notice?`)
    if (!ok) return
    setReactivatingNtpRemindersBulk(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/reminders`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ custodian_ids: ids, enabled: true }),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) throw new Error(data?.detail || data?.message || 'Unable to enable reminders')
      const successCount = Number.isFinite(Number(data?.updated_count)) ? Number(data.updated_count) : 0
      const failureCount = Number.isFinite(Number(data?.failed_count)) ? Number(data.failed_count) : 0
      await loadNtpReminders()
      if (failureCount > 0) {
        showToast(`Turned on reminders for ${successCount} custodian${successCount === 1 ? '' : 's'}, ${failureCount} failed.`, { variant: 'warn' })
      } else {
        showToast(`Turned on reminders for ${successCount} custodian${successCount === 1 ? '' : 's'}.`, { variant: 'success' })
      }
    } catch (err) {
      showToast(err?.message || 'Unable to enable reminders.', { variant: 'error' })
    } finally {
      setReactivatingNtpRemindersBulk(false)
    }
  }, [apiBase, caseId, loadNtpReminders, showToast])

  const saveReminderEditor = useCallback(async (activeReminderCustodianIds) => {
    if (!caseId || !reminderEditor.custodian) return
    const interval = Math.max(1, Number(reminderEditor.intervalDays) || REMINDER_INTERVAL_DEFAULT)
    const duration = Math.max(1, Number(reminderEditor.durationDays) || REMINDER_DURATION_DEFAULT)
    setReminderEditor(prev => ({ ...prev, busy: true }))
    const updateReminder = async (custodianId) => {
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/reminders/${custodianId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          interval_days: interval,
          duration_days: duration,
          enabled: reminderEditor.enabled,
        }),
      })
      if (!res.ok) throw new Error(await res.text() || 'Unable to update reminders')
      return res.json().catch(() => null)
    }
    try {
      const targetIds = reminderEditor.applyToAll ? activeReminderCustodianIds : [reminderEditor.custodian.id]
      if (reminderEditor.applyToAll && targetIds.length === 0) {
        showToast('No active reminders found to update.', { variant: 'info' })
        setReminderEditor(prev => ({ ...prev, busy: false }))
        return
      }
      let successCount = 0
      let failureCount = 0
      for (const custodianId of targetIds) {
        try {
          await updateReminder(custodianId)
          successCount += 1
        } catch (err) {
          failureCount += 1
          console.error('Reminder update failed', err)
        }
      }
      if (failureCount > 0) {
        showToast(`Updated ${successCount} reminder${successCount === 1 ? '' : 's'}, ${failureCount} failed.`, { variant: 'warn' })
        setReminderEditor(prev => ({ ...prev, busy: false }))
        await loadNtpReminders()
        return
      }
      showToast(reminderEditor.enabled ? 'NTP reminders updated.' : 'NTP reminders disabled.', { variant: 'success' })
      resetReminderEditor()
      await loadNtpReminders()
    } catch (err) {
      showToast(err?.message || 'Unable to update reminders.', { variant: 'error' })
      setReminderEditor(prev => ({ ...prev, busy: false }))
    }
  }, [apiBase, caseId, loadNtpReminders, reminderEditor, resetReminderEditor, showToast])

  return {
    showReminderListModal,
    setShowReminderListModal,
    reactivatingNtpReminders,
    reactivatingNtpRemindersBulk,
    openReminderEditor,
    reactivateCancelledNtpReminders,
    reminderEditor,
    closeReminderEditor,
    saveReminderEditor,
    setReminderEditor,
    openReminderListModal,
    reactivateEligibleCancelledNtpReminders,
  }
}