import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  NTP_VARIABLE_DEFAULTS,
  readNtpOutsideCounselHistory,
  mergeNtpOutsideCounselHistory,
  writeNtpOutsideCounselHistory,
  REMINDER_INTERVAL_DEFAULT,
  REMINDER_DURATION_DEFAULT,
} from './caseDetailUtils.js'
import {
  buildNtpPayloadVariablesFromForm,
  isNtpBlockedCustodianRecord,
  isNtpEmailEligibleCustodian,
  ntpAutoNaReasonForCustodian,
  ntpNaReasonForCustodian,
  ntpStatusLabelForCustodian,
  pickNextNtpReminder,
  rememberedNtpReason,
} from './caseDetailNtpUtils.js'
import { useCaseDetailNtpHistory } from './useCaseDetailNtpHistory.js'
import { useCaseDetailNtpReminderWorkflow } from './useCaseDetailNtpReminderWorkflow.js'

export function useCaseDetailNtpWorkflow({
  apiBase,
  caseId,
  caseData,
  custodians,
  setCustodians,
  isRequestor,
  isTech,
  showToast,
}) {
  const [ntpTemplates, setNtpTemplates] = useState([])
  const [ntpTemplatesLoading, setNtpTemplatesLoading] = useState(false)
  const [ntpReminders, setNtpReminders] = useState([])
  const [ntpRemindersLoading, setNtpRemindersLoading] = useState(false)
  const [showSendNtpModal, setShowSendNtpModal] = useState(false)
  const [ntpSelection, setNtpSelection] = useState([])
  const [selectedTemplateId, setSelectedTemplateId] = useState(null)
  const [selectedReminderTemplateId, setSelectedReminderTemplateId] = useState(null)
  const [reminderIntervalDays, setReminderIntervalDays] = useState(REMINDER_INTERVAL_DEFAULT)
  const [reminderDurationDays, setReminderDurationDays] = useState(REMINDER_DURATION_DEFAULT)
  const [ntpVariables, setNtpVariables] = useState(() => ({ ...NTP_VARIABLE_DEFAULTS }))
  const [sendingNtp, setSendingNtp] = useState(false)
  const [ntpOutsideCounselHistory, setNtpOutsideCounselHistory] = useState(() => readNtpOutsideCounselHistory())
  const [ntpSearch, setNtpSearch] = useState('')
  const [ntpBlockedModal, setNtpBlockedModal] = useState({ open: false, custodian: null })
  const [lastNtpSend, setLastNtpSend] = useState({ loading: false, error: null, data: null })
  const [ntpPreview, setNtpPreview] = useState({ loading: false, error: null, data: null })
  const ntpReasonTouchedRef = useRef(false)
  const [ntpHolds, setNtpHolds] = useState([])
  const [ntpHoldsLoading, setNtpHoldsLoading] = useState(false)
  const [ntpHoldId, setNtpHoldId] = useState(null)

  const loadNtpHolds = useCallback(async () => {
    if (!caseId) return []
    setNtpHoldsLoading(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/holds`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text().catch(() => '') || 'Unable to load holds')
      const data = await res.json()
      const holds = (Array.isArray(data?.holds) ? data.holds : []).filter(hold => hold?.status === 'active')
      setNtpHolds(holds)
      setNtpHoldId(current => holds.some(hold => Number(hold.id) === Number(current)) ? current : null)
      return holds
    } catch (err) {
      setNtpHolds([])
      setNtpHoldId(null)
      showToast(err?.message || 'Unable to load named holds.', { variant: 'error' })
      return []
    } finally {
      setNtpHoldsLoading(false)
    }
  }, [apiBase, caseId, showToast])

  const selectedNtpHold = useMemo(
    () => ntpHolds.find(hold => Number(hold?.id) === Number(ntpHoldId)) || null,
    [ntpHoldId, ntpHolds],
  )

  const ntpCustodians = useMemo(() => {
    if (!selectedNtpHold) return []
    const baseById = new Map(custodians.map(custodian => [Number(custodian.id), custodian]))
    return (selectedNtpHold.custodians || []).map(member => ({
      ...(baseById.get(Number(member.custodian_id)) || {}),
      ...member,
      id: Number(member.custodian_id),
      hold_custodian_id: member.membership_id,
    }))
  }, [custodians, selectedNtpHold])

  const loadNtpTemplates = useCallback(async () => {
    setNtpTemplatesLoading(true)
    try {
      const res = await fetch(`${apiBase}/ntp/templates`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setNtpTemplates(Array.isArray(data) ? data : [])
    } catch {
      setNtpTemplates([])
    } finally {
      setNtpTemplatesLoading(false)
    }
  }, [apiBase])

  const loadNtpReminders = useCallback(async () => {
    if (!caseId || isTech) return
    setNtpRemindersLoading(true)
    try {
      const params = new URLSearchParams({ include_inactive: 'true' })
      if (ntpHoldId) params.set('case_hold_id', String(ntpHoldId))
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/reminders?${params.toString()}`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text() || 'Unable to load reminders')
      const data = await res.json()
      setNtpReminders(Array.isArray(data) ? data : [])
    } catch {
      setNtpReminders([])
    } finally {
      setNtpRemindersLoading(false)
    }
  }, [apiBase, caseId, isTech, ntpHoldId])

  const ntpButtonDisabled = ntpTemplatesLoading || ntpHoldsLoading || !ntpTemplates.length

  const isNtpBlockedCustodian = useCallback(isNtpBlockedCustodianRecord, [])

  const ntpAutoNaReason = useCallback((custodian) => ntpAutoNaReasonForCustodian(caseData?.claimant, custodian), [caseData?.claimant])

  const ntpNaReason = useCallback((custodian) => ntpNaReasonForCustodian(custodian, ntpAutoNaReason(custodian)), [ntpAutoNaReason])

  const ntpStatusLabel = useCallback((custodian) => ntpStatusLabelForCustodian(custodian, ntpAutoNaReason(custodian)), [ntpAutoNaReason])

  const isNtpEmailEligible = useCallback(isNtpEmailEligibleCustodian, [])

  useEffect(() => {
    loadNtpHolds()
    if (!isTech) loadNtpTemplates()
  }, [loadNtpHolds, loadNtpTemplates, isTech])

  useEffect(() => {
    if (!showSendNtpModal || !caseId) return
    let cancelled = false
    setLastNtpSend({ loading: true, error: null, data: null })
    ;(async () => {
      try {
        const query = ntpHoldId ? `?case_hold_id=${encodeURIComponent(ntpHoldId)}` : ''
        const res = await fetch(`${apiBase}/cases/${caseId}/ntp/last_send${query}`, { credentials: 'include' })
        if (!res.ok) throw new Error(await res.text().catch(() => '') || 'Unable to load last NTP settings')
        const data = await res.json()
        if (!cancelled) setLastNtpSend({ loading: false, error: null, data })
      } catch (err) {
        if (!cancelled) setLastNtpSend({ loading: false, error: err?.message || 'Unable to load last NTP settings', data: null })
      }
    })()
    return () => { cancelled = true }
  }, [showSendNtpModal, caseId, apiBase, ntpHoldId])

  useEffect(() => {
    if (!showSendNtpModal) return
    if (ntpReasonTouchedRef.current) return
    setNtpVariables(prev => {
      const nextReason = rememberedNtpReason(lastNtpSend?.data)
      if (prev.reason === nextReason) return prev
      return { ...prev, reason: nextReason }
    })
  }, [showSendNtpModal, lastNtpSend, rememberedNtpReason])

  useEffect(() => {
    if (!showSendNtpModal || !selectedNtpHold) return
    const eligible = ntpCustodians.filter(c => isNtpEmailEligible(c))
    const unsentEligible = eligible.filter(c => ((c.ntp_status || '').toLowerCase() === 'not sent'))
    setNtpSelection(unsentEligible.map(c => c.id))
    setNtpPreview({ loading: false, error: null, data: null })
  }, [isNtpEmailEligible, ntpCustodians, selectedNtpHold, showSendNtpModal])

  useEffect(() => {
    if (!showSendNtpModal || isTech || !ntpHoldId) return
    loadNtpReminders()
  }, [showSendNtpModal, isTech, loadNtpReminders, ntpHoldId])

  const {
    showNtpHistoryModal,
    setShowNtpHistoryModal,
    ntpHistory,
    ntpHistoryExporting,
    ntpHistoryEmailing,
    openNtpHistoryModal,
    loadNtpHistory,
    exportNtpHistoryCsv,
    emailNtpHistoryReport,
  } = useCaseDetailNtpHistory({ apiBase, caseId, caseHoldId: ntpHoldId, loadNtpReminders, showToast })

  const openSendNtp = useCallback(() => {
    if (!ntpTemplates.length) {
      const message = isRequestor
        ? 'No NTP templates are assigned to your group. Ask an administrator to grant access.'
        : 'No NTP templates available. Ask an administrator to create one.'
      showToast(message, { variant: 'warn' })
      return
    }
    if (!ntpHolds.length) {
      showToast('Create an active Hold and assign custodians before sending an NTP.', { variant: 'warn' })
      return
    }
    const defaultTemplateId = ntpTemplates.find(t => t.is_default)?.id || ntpTemplates[0]?.id || null
    const defaultReminderTemplateId =
      ntpTemplates.find(t => t.is_default_reminder)?.id ||
      (ntpTemplates.find(t => String(t?.name || '').toLowerCase().includes('reminder'))?.id || null)

    setSelectedTemplateId(defaultTemplateId)
    setSelectedReminderTemplateId(defaultReminderTemplateId)
    setReminderIntervalDays(REMINDER_INTERVAL_DEFAULT)
    setReminderDurationDays(REMINDER_DURATION_DEFAULT)
    ntpReasonTouchedRef.current = false
    setNtpVariables({
      ...NTP_VARIABLE_DEFAULTS,
      legal_case_name: caseData?.legal_case_name || '',
      claimant: caseData?.claimant || '',
      reason: rememberedNtpReason(lastNtpSend?.data),
    })
    setNtpPreview({ loading: false, error: null, data: null })
    setShowSendNtpModal(true)
  }, [caseData, isRequestor, lastNtpSend?.data, ntpHolds.length, ntpTemplates, rememberedNtpReason, showToast])

  const closeSendNtp = useCallback(() => {
    setShowSendNtpModal(false)
    setNtpPreview({ loading: false, error: null, data: null })
  }, [])

  const copyPreviousNtpData = useCallback(() => {
    const payload = lastNtpSend?.data
    if (!payload?.exists) return
    const vars = payload?.variables && typeof payload.variables === 'object' ? payload.variables : {}
    const templateId = Number(payload.template_id) || null
    const reminderId = Number(payload.reminder_template_id) || null
    if (templateId) {
      const exists = ntpTemplates.some(t => Number(t?.id) === templateId)
      if (exists) setSelectedTemplateId(templateId)
      else showToast('Previous NTP template is no longer available for your account.', { variant: 'warn' })
    }
    if (reminderId) {
      const exists = ntpTemplates.some(t => Number(t?.id) === reminderId)
      if (exists) setSelectedReminderTemplateId(reminderId)
      else setSelectedReminderTemplateId(null)
    } else {
      setSelectedReminderTemplateId(null)
    }
    setReminderIntervalDays(REMINDER_INTERVAL_DEFAULT)
    setReminderDurationDays(REMINDER_DURATION_DEFAULT)
    setNtpVariables(prev => ({
      ...prev,
      legal_case_name: typeof vars.legal_case_name === 'string' ? vars.legal_case_name : prev.legal_case_name,
      claimant: typeof vars.claimant === 'string' ? vars.claimant : prev.claimant,
      reason: typeof vars.reason === 'string' ? vars.reason : prev.reason,
      outside_counsel1: typeof vars.outside_counsel1 === 'string' ? vars.outside_counsel1 : prev.outside_counsel1,
      outside_counsel2: typeof vars.outside_counsel2 === 'string' ? vars.outside_counsel2 : prev.outside_counsel2,
      outside_counsel3: typeof vars.outside_counsel3 === 'string' ? vars.outside_counsel3 : prev.outside_counsel3,
      outside_counsel_firm: typeof vars.outside_counsel_firm === 'string' ? vars.outside_counsel_firm : prev.outside_counsel_firm,
      cc_list: typeof vars.cc === 'string' ? vars.cc : (typeof vars.cc_list === 'string' ? vars.cc_list : prev.cc_list),
    }))
    showToast('Previous NTP settings copied. Review and then click Send Notices.', { variant: 'success' })
  }, [lastNtpSend?.data, ntpTemplates, showToast])

  const toggleNtpSelection = useCallback((id, checked) => {
    if (checked) {
      const target = ntpCustodians.find(c => c.id === id)
      if (target && isNtpBlockedCustodian(target)) {
        setNtpBlockedModal({ open: true, custodian: target })
        return
      }
    }
    setNtpSelection(prev => {
      const set = new Set(prev)
      if (checked) set.add(id)
      else set.delete(id)
      return Array.from(set)
    })
  }, [isNtpBlockedCustodian, ntpCustodians])

  const buildNtpPayloadVariables = useCallback(() => buildNtpPayloadVariablesFromForm(ntpVariables), [ntpVariables])

  const previewNtpNotice = useCallback(async () => {
    if (!ntpHoldId) {
      showToast('Select the Hold for this NTP.', { variant: 'warn' })
      return
    }
    if (!selectedTemplateId) {
      showToast('Select a template.', { variant: 'warn' })
      return
    }
    if (!ntpSelection.length) {
      showToast('Please select at least 1 custodian to see the preview.', { variant: 'warn' })
      return
    }
    setNtpPreview({ loading: true, error: null, data: null })
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          template_id: selectedTemplateId,
          case_hold_id: ntpHoldId,
          custodian_ids: ntpSelection,
          variables: buildNtpPayloadVariables(),
        }),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) throw new Error(data?.detail || 'Unable to preview NTP.')
      setNtpPreview({ loading: false, error: null, data })
    } catch (err) {
      const message = err?.message || 'Unable to preview NTP.'
      setNtpPreview({ loading: false, error: message, data: null })
      showToast(message, { variant: 'error' })
    }
  }, [apiBase, buildNtpPayloadVariables, caseId, ntpHoldId, ntpSelection, selectedTemplateId, showToast])

  const sendNtpNotices = useCallback(async () => {
    if (!selectedTemplateId) {
      showToast('Select a template.', { variant: 'warn' })
      return
    }
    if (!ntpSelection.length) {
      showToast('Select at least one custodian.', { variant: 'warn' })
      return
    }
    setSendingNtp(true)
    try {
      const payloadVariables = buildNtpPayloadVariables()
      const nextOutsideCounselHistory = mergeNtpOutsideCounselHistory(ntpOutsideCounselHistory, payloadVariables)
      const reminderInterval = selectedReminderTemplateId ? Math.max(1, Number(reminderIntervalDays) || REMINDER_INTERVAL_DEFAULT) : null
      const reminderDuration = selectedReminderTemplateId ? Math.max(1, Number(reminderDurationDays) || REMINDER_DURATION_DEFAULT) : null
      const res = await fetch(`${apiBase}/cases/${caseId}/ntp/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          template_id: selectedTemplateId,
          case_hold_id: ntpHoldId,
          reminder_template_id: selectedReminderTemplateId || null,
          custodian_ids: ntpSelection,
          variables: payloadVariables,
          reminder_interval_days: reminderInterval,
          reminder_duration_days: reminderDuration,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const selectedTemplateName = (ntpTemplates.find(t => Number(t?.id) === Number(selectedTemplateId))?.name || '').trim()
      setCustodians(prev => prev.map(c => ntpSelection.includes(c.id)
        ? { ...c, ntp_status: 'sent', ntp_template_name: selectedTemplateName || c.ntp_template_name || null }
        : c
      ))
      await Promise.all([loadNtpReminders(), loadNtpHolds()])
      setNtpOutsideCounselHistory(nextOutsideCounselHistory)
      writeNtpOutsideCounselHistory(nextOutsideCounselHistory)
      showToast('NTP notices sent.', { variant: 'success' })
      closeSendNtp()
    } catch (err) {
      const msg = String(err?.message || 'Failed to send notices.')
      if (msg.toLowerCase().includes('separated or listed as na for ntps') || msg.toLowerCase().includes('listed as silent for ntps')) {
        setNtpBlockedModal({ open: true, custodian: null })
      } else {
        showToast(msg, { variant: 'error' })
      }
    } finally {
      setSendingNtp(false)
    }
  }, [apiBase, buildNtpPayloadVariables, caseId, closeSendNtp, loadNtpHolds, loadNtpReminders, ntpHoldId, ntpOutsideCounselHistory, ntpSelection, ntpTemplates, reminderDurationDays, reminderIntervalDays, selectedReminderTemplateId, selectedTemplateId, setCustodians, showToast])

  const pickNextReminder = useCallback(pickNextNtpReminder, [])

  const {
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
  } = useCaseDetailNtpReminderWorkflow({
    apiBase,
    caseId,
    caseHoldId: ntpHoldId,
    loadNtpReminders,
    pickNextReminder,
    showToast,
  })

  return {
    ntpTemplates,
    ntpTemplatesLoading,
    ntpHolds,
    ntpHoldsLoading,
    loadNtpHolds,
    ntpHoldId,
    setNtpHoldId,
    ntpCustodians,
    ntpReminders,
    ntpRemindersLoading,
    ntpButtonDisabled,
    showSendNtpModal,
    closeSendNtp,
    previewNtpNotice,
    ntpPreview,
    setNtpPreview,
    sendingNtp,
    sendNtpNotices,
    selectedTemplateId,
    setSelectedTemplateId,
    ntpSelection,
    selectedReminderTemplateId,
    setSelectedReminderTemplateId,
    setReminderIntervalDays,
    setReminderDurationDays,
    reminderIntervalDays,
    reminderDurationDays,
    openNtpHistoryModal,
    lastNtpSend,
    copyPreviousNtpData,
    ntpVariables,
    setNtpVariables,
    ntpReasonTouchedRef,
    ntpOutsideCounselHistory,
    ntpSearch,
    setNtpSearch,
    toggleNtpSelection,
    ntpAutoNaReason,
    ntpStatusLabel,
    showNtpHistoryModal,
    setShowNtpHistoryModal,
    ntpHistory,
    ntpHistoryExporting,
    ntpHistoryEmailing,
    exportNtpHistoryCsv,
    emailNtpHistoryReport,
    loadNtpHistory,
    showReminderListModal,
    setShowReminderListModal,
    reactivateEligibleCancelledNtpReminders,
    reactivatingNtpRemindersBulk,
    reactivatingNtpReminders,
    openReminderEditor,
    reactivateCancelledNtpReminders,
    ntpBlockedModal,
    setNtpBlockedModal,
    reminderEditor,
    closeReminderEditor,
    saveReminderEditor,
    setReminderEditor,
    openReminderListModal,
    openSendNtp,
    pickNextReminder,
  }
}
