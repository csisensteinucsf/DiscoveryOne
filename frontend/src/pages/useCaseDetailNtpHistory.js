import { useCallback, useState } from 'react'

export function useCaseDetailNtpHistory({ apiBase, caseId, caseHoldId, loadNtpReminders, showToast }) {
  const [showNtpHistoryModal, setShowNtpHistoryModal] = useState(false)
  const [ntpHistory, setNtpHistory] = useState({ loading: false, error: null, events: [] })
  const [ntpHistoryExporting, setNtpHistoryExporting] = useState(false)
  const [ntpHistoryEmailing, setNtpHistoryEmailing] = useState(false)

  const loadNtpHistory = useCallback(async () => {
    if (!caseId) return
    setNtpHistory({ loading: true, error: null, events: [] })
    try {
      const query = caseHoldId ? `?case_hold_id=${encodeURIComponent(caseHoldId)}` : ''
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/history${query}`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text().catch(() => '') || 'Unable to load NTP history')
      const data = await res.json()
      const events = Array.isArray(data?.events) ? data.events : []
      setNtpHistory({ loading: false, error: null, events })
    } catch (err) {
      setNtpHistory({ loading: false, error: err?.message || 'Unable to load NTP history', events: [] })
    }
  }, [caseHoldId, caseId, apiBase])

  const exportNtpHistoryCsv = useCallback(async () => {
    if (!caseId) return
    setNtpHistoryExporting(true)
    try {
      const query = caseHoldId ? `?case_hold_id=${encodeURIComponent(caseHoldId)}` : ''
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/history/export${query}`, { credentials: 'include' })
      if (!res.ok) {
        let message = 'Unable to export NTP history.'
        try {
          const data = await res.json()
          if (data?.detail) message = String(data.detail)
        } catch {
          const raw = await res.text().catch(() => '')
          if (raw) message = raw
        }
        throw new Error(message)
      }
      const blob = await res.blob()
      const disposition = res.headers.get('content-disposition') || ''
      const match = disposition.match(/filename="?([^";]+)"?/i)
      const filename = (match?.[1] || `case_${caseId}_ntp_history.csv`).trim()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
      showToast('NTP history CSV exported.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Unable to export NTP history.', { variant: 'error' })
    } finally {
      setNtpHistoryExporting(false)
    }
  }, [apiBase, caseHoldId, caseId, showToast])

  const emailNtpHistoryReport = useCallback(async () => {
    if (!caseId) return
    setNtpHistoryEmailing(true)
    try {
      const query = caseHoldId ? `?case_hold_id=${encodeURIComponent(caseHoldId)}` : ''
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/history/email${query}`, {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) throw new Error(data?.detail || 'Unable to email NTP history report.')
      const recipient = String(data?.recipient || '').trim()
      showToast(recipient ? `NTP history emailed to ${recipient}.` : 'NTP history emailed to your account.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Unable to email NTP history report.', { variant: 'error' })
    } finally {
      setNtpHistoryEmailing(false)
    }
  }, [apiBase, caseHoldId, caseId, showToast])

  const openNtpHistoryModal = useCallback(async () => {
    setShowNtpHistoryModal(true)
    await Promise.all([loadNtpReminders(), loadNtpHistory()])
  }, [loadNtpReminders, loadNtpHistory])

  return {
    showNtpHistoryModal,
    setShowNtpHistoryModal,
    ntpHistory,
    ntpHistoryExporting,
    ntpHistoryEmailing,
    openNtpHistoryModal,
    loadNtpHistory,
    exportNtpHistoryCsv,
    emailNtpHistoryReport,
  }
}