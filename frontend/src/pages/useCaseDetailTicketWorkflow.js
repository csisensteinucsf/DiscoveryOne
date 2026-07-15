import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ADMIN_USERNAME,
  blankAccessLogTimeWindow,
  caseCache,
  deriveRequestEntriesFromCase,
  entryAccessLogTimeWindows,
  isSnowUnmatchedCustodian,
  prepareEntriesForSave,
  primaryCustodian,
  uuid,
} from './caseDetailUtils.js'
import { requiresMatchedEmailForTicketWorkflow, ticketProviderLabel, ticketWorkflowUsesAccessLogDetails } from './ticketWorkflowCatalog.js'
import { personLookupExternalId } from './caseDetailPersonLookupFields.js'

export function useCaseDetailTicketWorkflow({
  apiBase,
  caseId,
  caseData,
  setCaseData,
  updateCase,
  isRequestor,
  isTech,
  user,
  userRole,
  employeeIdLabel,
  custodians,
  custodianOptionLookup,
  techTicketCategorySet,
  ticketCategories,
  requestTicketCategoryLookup,
  entryHasUnmatchedSnowCustodian,
  confirmDialog,
  showToast,
}) {
  const [requestEntries, setRequestEntries] = useState([])
  const [requestsDirty, setRequestsDirty] = useState(false)
  const [requestsSaving, setRequestsSaving] = useState(false)
  const requestEntriesRef = useRef(requestEntries)
  const lastSavedRequestEntries = useRef('[]')
  const saveTicketsTimeout = useRef(null)
  const [externalTicketBusy, setExternalTicketBusy] = useState({})
  const [externalTicketStatuses, setExternalTicketStatuses] = useState({})
  const [externalTicketStatusLoading, setExternalTicketStatusLoading] = useState(false)
  const [externalTicketEmailBusy, setExternalTicketEmailBusy] = useState({})
  const [externalTicketEmailSent, setExternalTicketEmailSent] = useState({})
  const [ticketSelfHealBusy, setTicketSelfHealBusy] = useState(false)
  const [showBulkRequestModal, setShowBulkRequestModal] = useState(false)
  const [bulkCategory, setBulkCategory] = useState(null)
  const [bulkSelection, setBulkSelection] = useState(new Set())
  const [bulkSearch, setBulkSearch] = useState('')
  const [accessLogInfoEntryId, setAccessLogInfoEntryId] = useState(null)

  const accessLogInfoEntry = useMemo(
    () => (requestEntries || []).find(entry => entry.id === accessLogInfoEntryId) || null,
    [requestEntries, accessLogInfoEntryId]
  )

  const matchedEmailWorkflowLabel = useMemo(() => {
    const labels = (Array.isArray(ticketCategories) ? ticketCategories : [])
      .filter(category => category?.requiresMatchedEmail)
      .map(category => String(category?.label || category?.key || '').trim())
      .filter(Boolean)
    if (!labels.length) return 'this workflow'
    if (labels.length === 1) return labels[0]
    return `${labels.slice(0, -1).join(', ')} or ${labels[labels.length - 1]}`
  }, [ticketCategories])
  const matchedEmailWorkflowWarning = `Custodians with unmatched or missing emails cannot be selected for ${matchedEmailWorkflowLabel} tickets.`

  const workflowUsesAccessLogDetails = (entryOrCategory) => {
    const categoryKey = typeof entryOrCategory === 'string'
      ? entryOrCategory
      : String(entryOrCategory?.category || '')
    const workflow = requestTicketCategoryLookup?.[categoryKey] || entryOrCategory
    return ticketWorkflowUsesAccessLogDetails(workflow)
  }


  const ticketProviderActionLabelForEntry = (entry) => {
    const category = requestTicketCategoryLookup?.[entry?.category] || null
    return ticketProviderLabel(category?.provider || ((category?.externalTicketEnabled ?? category?.serviceNowEnabled) !== false ? 'servicenow' : 'manual'), { action: true })
  }

  const requestsFilledCount = useMemo(
    () => (requestEntries || []).reduce(
      (count, entry) => count + (((entry.ticket || '').trim()) ? 1 : 0),
      0
    ),
    [requestEntries]
  )

  const servicenowTicketSignature = useMemo(
    () => JSON.stringify((requestEntries || []).map(e => `${e.id}:${e.ticket || ''}`)),
    [requestEntries]
  )

  const usedCustodianKeysByCategory = useMemo(() => {
    const map = new Map()
    ;(requestEntries || []).forEach(entry => {
      if (!entry || !entry.category) return
      const bucket = map.get(entry.category) || new Set()
      const addKey = (cust) => {
        if (!cust) return
        const key = cust.id
          ? `id:${cust.id}`
          : (cust.email ? `email:${String(cust.email).toLowerCase()}` : null)
        if (key) bucket.add(key)
      }
      addKey({ id: entry.custodian_id, email: entry.custodian_email })
      if (Array.isArray(entry.bulk_custodians)) {
        entry.bulk_custodians.forEach(c => addKey({ id: c?.id, email: c?.email }))
      }
      if (bucket.size) map.set(entry.category, bucket)
    })
    return map
  }, [requestEntries])

  const techCustodianKeys = useMemo(() => {
    if (!isTech) return null
    const keys = new Set()
    const addKey = (id, email) => {
      if (Number.isFinite(Number(id))) {
        keys.add(`id:${Number(id)}`)
      }
      const emailKey = (email || '').trim().toLowerCase()
      if (emailKey) {
        keys.add(`email:${emailKey}`)
      }
    }
    ;(requestEntries || []).forEach(entry => {
      if (!entry || !techTicketCategorySet.has(entry.category)) return
      addKey(entry.custodian_id, entry.custodian_email)
      const bulk = Array.isArray(entry.bulk_custodians) ? entry.bulk_custodians : []
      bulk.forEach(item => {
        if (!item) return
        addKey(item.id, item.email)
      })
    })
    return keys
  }, [isTech, requestEntries, techTicketCategorySet])

  const updateRequestEntriesState = (nextValue, opts = {}) => {
    const prev = requestEntriesRef.current
    const resolved = typeof nextValue === 'function' ? nextValue(Array.isArray(prev) ? prev : []) : nextValue
    const normalized = Array.isArray(resolved) ? resolved : []
    requestEntriesRef.current = normalized
    setRequestEntries(normalized)
    if (opts.skipDirty || isRequestor) return
    setRequestsDirty(true)
    if (saveTicketsTimeout.current) {
      clearTimeout(saveTicketsTimeout.current)
    }
    saveTicketsTimeout.current = setTimeout(() => {
      commitRequestTicketSave()
    }, 600)
  }

  const updateRequestEntry = (entryId, patch) => {
    if (isRequestor) return
    updateRequestEntriesState((prev = []) => (Array.isArray(prev) ? prev : []).map(entry => (
      entry.id === entryId ? { ...entry, ...patch } : entry
    )))
  }

  const sendAssigneeEmail = async (entryId) => {
    if (!caseId) return
    setExternalTicketEmailBusy(prev => ({ ...prev, [entryId]: true }))
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/external_ticket_email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ entry_id: entryId }),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || 'Failed to send assignment email.')
      }
      showToast('Email sent to assigned user.', { variant: 'success' })
      updateRequestEntry(entryId, { assignment_email_sent: true })
      setExternalTicketEmailSent(prev => ({ ...prev, [entryId]: true }))
    } catch (err) {
      showToast(err?.message || 'Failed to send assignment email.', { variant: 'error' })
    } finally {
      setExternalTicketEmailBusy(prev => ({ ...prev, [entryId]: false }))
    }
  }

  useEffect(() => {
    return () => {
      if (saveTicketsTimeout.current) {
        clearTimeout(saveTicketsTimeout.current)
      }
    }
  }, [])

  useEffect(() => {
    const map = {}
    ;(requestEntries || []).forEach(e => {
      if (e && e.assignment_email_sent) {
        map[e.id] = true
      }
    })
    setExternalTicketEmailSent(map)
  }, [requestEntries])

  useEffect(() => {
    if (isRequestor || !caseId) return
    const tickets = (requestEntriesRef.current || []).map(e => (e.ticket || '').trim()).filter(Boolean)
    if (!tickets.length) {
      setExternalTicketStatuses({})
      setExternalTicketStatusLoading(false)
      return
    }
    let cancelled = false
    const timeoutId = setTimeout(() => {
      if (cancelled) return
      setExternalTicketStatusLoading(true)
      ;(async () => {
        try {
          const res = await fetch(`${apiBase}/cases/${caseId}/external_ticket_statuses`, { credentials: 'include' })
          const data = await res.json().catch(() => null)
          if (cancelled) return
          if (Array.isArray(data)) {
            const map = {}
            data.forEach(item => {
              const key = item?.entry_id || item?.ticket
              if (key) map[key] = item
            })
            setExternalTicketStatuses(map)
          } else {
            setExternalTicketStatuses({})
          }
        } catch {
          if (!cancelled) setExternalTicketStatuses({})
        } finally {
          if (!cancelled) setExternalTicketStatusLoading(false)
        }
      })()
    }, 500)
    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [apiBase, caseId, isRequestor, servicenowTicketSignature])

  const addRequestEntry = (categoryKey) => {
    if (isRequestor) return
    if (isTech && !techTicketCategorySet.has(categoryKey)) return
    const category = requestTicketCategoryLookup?.[categoryKey] ? categoryKey : (ticketCategories?.[0]?.key || categoryKey)
    const usesAccessLogDetails = workflowUsesAccessLogDetails(category)
    updateRequestEntriesState((prev = []) => [
      ...(Array.isArray(prev) ? prev : []),
      {
        id: uuid(),
        category,
        ticket: '',
        custodian_id: null,
        custodian_name: '',
        custodian_email: '',
        sys_id: '',
        status: '',
        access_log_employee_id: '',
        access_log_time_windows: usesAccessLogDetails ? [blankAccessLogTimeWindow()] : [],
        access_log_request_notes: '',
        ...(usesAccessLogDetails ? { bulk_custodians: null } : {}),
      },
    ])
  }

  const openBulkRequestModal = (categoryKey) => {
    if (isRequestor) return
    if (isTech && !techTicketCategorySet.has(categoryKey)) return
    setBulkCategory(categoryKey)
    setBulkSelection(new Set())
    setShowBulkRequestModal(true)
  }

  const bulkCustodianDisabledReason = (categoryKey, custodian, usedSet = new Set()) => {
    const key = custodian?.id ? `id:${custodian.id}` : (custodian?.email ? `email:${custodian.email.toLowerCase()}` : null)
    if (key && usedSet.has(key)) return 'Already added for this request'
    if (requiresMatchedEmailForTicketWorkflow(categoryKey, ticketCategories) && isSnowUnmatchedCustodian(custodian)) return 'Unmatched or missing email'
    return ''
  }

  const toggleBulkCustodian = (custodianId) => {
    const singleSelect = workflowUsesAccessLogDetails(bulkCategory)
    const custodian = (custodians || []).find(c => Number(c.id) === Number(custodianId))
    const reason = bulkCustodianDisabledReason(bulkCategory, custodian, usedCustodianKeysByCategory.get(bulkCategory) || new Set())
    if (reason) {
      showToast(reason === 'Unmatched or missing email'
        ? matchedEmailWorkflowWarning
        : reason,
        { variant: 'warn' }
      )
      return
    }
    setBulkSelection(prev => {
      const next = new Set(prev)
      if (next.has(custodianId)) {
        next.delete(custodianId)
      } else {
        if (singleSelect) next.clear()
        next.add(custodianId)
      }
      return next
    })
  }

  const submitBulkRequests = () => {
    if (!bulkCategory) {
      setShowBulkRequestModal(false)
      return
    }
    const selectedIds = Array.from(bulkSelection || []).map(Number).filter(Number.isFinite)
    if (!selectedIds.length) {
      showToast('Select at least one custodian to add.', { variant: 'error' })
      return
    }
    const usedKeys = usedCustodianKeysByCategory.get(bulkCategory) || new Set()
    const invalidSelected = (custodians || [])
      .filter(c => selectedIds.includes(Number(c.id)))
      .some(c => requiresMatchedEmailForTicketWorkflow(bulkCategory, ticketCategories) && isSnowUnmatchedCustodian(c))
    const selectedCustodians = (custodians || [])
      .filter(c => selectedIds.includes(Number(c.id)))
      .filter(c => {
        return !bulkCustodianDisabledReason(bulkCategory, c, usedKeys)
      })
      .map(c => ({
        id: Number.isFinite(Number(c.id)) ? Number(c.id) : null,
        name: c.name || '',
        email: c.email || '',
      }))
    if (!selectedCustodians.length) {
      showToast(
        invalidSelected
          ? matchedEmailWorkflowWarning
          : 'All selected custodians already have tickets for this request.',
        { variant: invalidSelected ? 'warn' : 'info' }
      )
      return
    }
    if (workflowUsesAccessLogDetails(bulkCategory) && selectedCustodians.length > 1) {
      showToast('Select one custodian for this access log request.', { variant: 'warn' })
      return
    }
    const primary = selectedCustodians[0] || {}
    const newEntry = {
      id: uuid(),
      category: bulkCategory,
      ticket: '',
      custodian_id: primary.id,
      custodian_name: primary.name || '',
      custodian_email: primary.email || '',
      bulk_custodians: selectedCustodians,
      sys_id: '',
      status: '',
      access_log_employee_id: workflowUsesAccessLogDetails(bulkCategory) ? (personLookupExternalId(custodians.find(c => Number(c.id) === Number(primary.id))) || '') : '',
      access_log_time_windows: workflowUsesAccessLogDetails(bulkCategory) ? [blankAccessLogTimeWindow()] : [],
      access_log_request_notes: workflowUsesAccessLogDetails(bulkCategory) ? '' : undefined,
    }
    updateRequestEntriesState((prev = []) => (Array.isArray(prev) ? prev : []).concat([newEntry]))
    setShowBulkRequestModal(false)
    setBulkCategory(null)
    setBulkSelection(new Set())
  }

  const closeBulkModal = () => {
    setShowBulkRequestModal(false)
    setBulkCategory(null)
    setBulkSelection(new Set())
    setBulkSearch('')
  }

  const updateAccessLogTimeWindow = (entryId, windowId, patch) => {
    if (isRequestor) return
    updateRequestEntriesState((prev = []) => (Array.isArray(prev) ? prev : []).map(entry => {
      if (entry.id !== entryId) return entry
      const windows = entryAccessLogTimeWindows(entry).map(window => (
        window.id === windowId ? { ...window, ...patch } : window
      ))
      return { ...entry, access_log_time_windows: windows }
    }))
  }

  const addAccessLogTimeWindow = (entryId) => {
    if (isRequestor) return
    updateRequestEntriesState((prev = []) => (Array.isArray(prev) ? prev : []).map(entry => (
      entry.id === entryId
        ? { ...entry, access_log_time_windows: [...entryAccessLogTimeWindows(entry), blankAccessLogTimeWindow()] }
        : entry
    )))
  }

  const removeAccessLogTimeWindow = (entryId, windowId) => {
    if (isRequestor) return
    updateRequestEntriesState((prev = []) => (Array.isArray(prev) ? prev : []).map(entry => {
      if (entry.id !== entryId) return entry
      const remaining = entryAccessLogTimeWindows(entry).filter(window => window.id !== windowId)
      return { ...entry, access_log_time_windows: remaining.length ? remaining : [blankAccessLogTimeWindow()] }
    }))
  }

  const closeAccessLogInfoModal = () => {
    setAccessLogInfoEntryId(null)
  }

  const saveAccessLogInfoModal = async () => {
    const saved = await commitRequestTicketSave()
    if (saved) {
      setAccessLogInfoEntryId(null)
      showToast('Access log request details saved.', { variant: 'success' })
    }
  }

  const removeRequestEntry = (entryId) => {
    if (isRequestor) return
    confirmDialog({
      title: 'Remove request?',
      description: 'Are you sure you want to remove this request?',
      confirmLabel: 'Remove',
      destructive: true,
    }).then(ok => {
      if (!ok) return
      if (accessLogInfoEntryId === entryId) setAccessLogInfoEntryId(null)
      updateRequestEntriesState((prev = []) => (Array.isArray(prev) ? prev : []).filter(entry => entry.id !== entryId))
    })
  }

  const setExternalTicketBusyFlag = (entryId, value) => {
    setExternalTicketBusy(prev => ({ ...prev, [entryId]: value }))
  }

  const createExternalTicket = async (entry) => {
    if (!entry || isRequestor || !caseId) return
    const ticketActionLabel = ticketProviderActionLabelForEntry(entry)
    const primary = primaryCustodian(entry)
    const custodianText = (primary.name || primary.email || '').trim()
    if (!custodianText) {
      showToast(`Add a custodian before creating a ${ticketActionLabel}.`, { variant: 'error' })
      return
    }
    if (entryHasUnmatchedSnowCustodian(entry)) {
      showToast('Custodians with unmatched or missing emails cannot be used for this configured ticket workflow.', { variant: 'error' })
      return
    }
    if (workflowUsesAccessLogDetails(entry)) {
      const eid = String(entry.access_log_employee_id || '').trim()
      const windows = entryAccessLogTimeWindows(entry)
      const populatedWindows = windows.filter(window => window.date || window.start_time || window.end_time)
      if (!eid) {
        showToast(`Enter the custodian ${employeeIdLabel} before creating this access log request.`, { variant: 'error' })
        return
      }
      if (!populatedWindows.length) {
        showToast('Enter at least one requested date and time window before creating this access log request.', { variant: 'error' })
        return
      }
      const invalidWindow = populatedWindows.find(window => !(window.date && window.start_time && window.end_time))
      if (invalidWindow) {
        showToast('Each access log date/time row needs a date, start time, and end time.', { variant: 'error' })
        return
      }
    }
    const requiresEmployeeId = (userRole === 'analyst' || userRole === 'sys_admin') && ((user?.username || '').toLowerCase() !== ADMIN_USERNAME)
    if (requiresEmployeeId && !(user?.employee_id || '').trim()) {
      showToast(`Missing ${employeeIdLabel}; it is needed for ${ticketActionLabel} creation. Update it in System.`, { variant: 'error' })
      return
    }
    setExternalTicketBusyFlag(entry.id, true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/external_ticket`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          category: entry.category,
          entry_id: entry.id,
          custodian_name: primary.name || primary.email || '',
          custodian_email: primary.email || '',
          custodian_id: entry.custodian_id ?? null,
          bulk_custodians: Array.isArray(entry.bulk_custodians) ? entry.bulk_custodians : null,
          access_log_employee_id: entry.access_log_employee_id || '',
          access_log_request_notes: entry.access_log_request_notes || '',
          access_log_time_windows: workflowUsesAccessLogDetails(entry) ? entryAccessLogTimeWindows(entry) : null,
        }),
      })
      let data = null
      try {
        data = await res.json()
      } catch {}
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || `Failed to create ${ticketActionLabel}.`)
      }
      const rawTicket = [data?.ticket_number, data?.ticket, data?.number].find(v => v !== undefined && v !== null)
      const ticketNumber = (rawTicket !== undefined && rawTicket !== null) ? String(rawTicket).trim() : ''
      if (!ticketNumber) {
        throw new Error(`${ticketActionLabel} provider did not return a ticket number.`)
      }
      const sysId = data?.sys_id ? String(data.sys_id).trim() : ''
      const savedEntryId = data?.entry_id ? String(data.entry_id) : entry.id
      updateRequestEntry(entry.id, { id: savedEntryId, ticket: ticketNumber, sys_id: sysId })
      await commitRequestTicketSave()
      showToast(`${ticketActionLabel} ${ticketNumber} created.`, { variant: 'success' })
    } catch (err) {
      showToast(err?.message || `Unable to create ${ticketActionLabel}.`, { variant: 'error' })
    } finally {
      setExternalTicketBusyFlag(entry.id, false)
    }
  }

  const sendCustodianDetailsToAssignee = async (entry) => {
    if (!entry || isRequestor) return
    const email = (entry.assigned_to_email || '').trim()
    if (!email) {
      showToast('No ticket assignee email is available yet.', { variant: 'error' })
      return
    }
    const primary = primaryCustodian(entry)
    const custodianLabel = (primary.name || primary.email || '').trim()
    if (!custodianLabel) {
      showToast('Add a custodian before emailing the assignee.', { variant: 'error' })
      return
    }
    if (externalTicketEmailBusy[entry.id]) return
    await sendAssigneeEmail(entry.id)
  }

  const handleRequestEntryCustodianChange = (entryId, value) => {
    if (isRequestor) return
    const currentEntry = (requestEntriesRef.current || []).find(entry => entry.id === entryId)
    const usesAccessLogDetails = workflowUsesAccessLogDetails(currentEntry)
    const match = custodianOptionLookup.get(value)
    if (match) {
      if (requiresMatchedEmailForTicketWorkflow(currentEntry?.category, ticketCategories) && match.snow_unmatched) {
        showToast(matchedEmailWorkflowWarning, { variant: 'warn' })
        return
      }
      updateRequestEntry(entryId, {
        custodian_id: Number.isFinite(match.id) ? match.id : null,
        custodian_name: match.name || '',
        custodian_email: match.email || '',
        ...(usesAccessLogDetails ? { access_log_employee_id: personLookupExternalId(match) || '' } : {}),
      })
    } else {
      updateRequestEntry(entryId, {
        custodian_id: null,
        custodian_name: value || '',
        custodian_email: '',
        ...(usesAccessLogDetails ? { access_log_employee_id: '' } : {}),
      })
    }
  }

  async function commitRequestTicketSave(snapshot) {
    if (isRequestor) return
    if (!caseData) return false
    if (saveTicketsTimeout.current) {
      clearTimeout(saveTicketsTimeout.current)
      saveTicketsTimeout.current = null
    }
    const current = Array.isArray(snapshot) ? snapshot : requestEntriesRef.current
    const payload = prepareEntriesForSave(current || [])
    const serialized = JSON.stringify(payload)
    if (serialized === lastSavedRequestEntries.current) {
      setRequestsDirty(false)
      return true
    }
    setRequestsSaving(true)
    try {
      const saved = await updateCase({ request_ticket_entries: payload })
      setCaseData(prev => {
        if (saved) {
          return { ...saved, request_ticket_entries: payload }
        }
        if (!prev) return prev
        return { ...prev, request_ticket_entries: payload }
      })
      lastSavedRequestEntries.current = serialized
      setRequestsDirty(false)
      return true
    } catch (err) {
      showToast(err?.message || 'Failed to save request tickets.', { variant: 'error' })
      return false
    } finally {
      setRequestsSaving(false)
    }
  }

  const runTicketSelfHeal = async () => {
    if (ticketSelfHealBusy || isRequestor || isTech) return
    setTicketSelfHealBusy(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/tickets/self_heal`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        throw new Error(txt || `HTTP ${res.status}`)
      }
      const data = await res.json().catch(() => ({}))
      const added = Number(data?.added_count || 0)
      if (added > 0) {
        showToast(`Restored ${added} ticket${added === 1 ? '' : 's'}.`, { variant: 'success' })
      } else {
        showToast('No missing tickets found to restore.', { variant: 'info' })
      }
      const r1 = await fetch(`${apiBase}/cases/${caseId}`, { credentials: 'include' })
      if (r1.ok) {
        const refreshed = await r1.json()
        setCaseData(refreshed)
        caseCache.set(caseId, refreshed)
      }
    } catch (err) {
      showToast(err?.message || 'Unable to run ticket self heal', { variant: 'error', duration: 12000 })
    } finally {
      setTicketSelfHealBusy(false)
    }
  }

  useEffect(() => {
    let next = deriveRequestEntriesFromCase(caseData)
    if (isTech) {
      if (techTicketCategorySet.size) {
        next = next.filter(entry => techTicketCategorySet.has(entry.category))
      } else {
        next = []
      }
    }
    updateRequestEntriesState(next, { skipDirty: true })
    lastSavedRequestEntries.current = JSON.stringify(prepareEntriesForSave(next))
    setRequestsDirty(false)
    if (saveTicketsTimeout.current) {
      clearTimeout(saveTicketsTimeout.current)
      saveTicketsTimeout.current = null
    }
  }, [
    caseData?.request_ticket_entries,
    caseData?.rubrik_restore_ticket,
    caseData?.box_hold_ticket,
    isTech,
    techTicketCategorySet,
  ])

  return {
    requestEntries,
    requestsDirty,
    requestsSaving,
    requestsFilledCount,
    matchedEmailWorkflowWarning,
    usedCustodianKeysByCategory,
    externalTicketBusy,
    externalTicketStatuses,
    externalTicketStatusLoading,
    externalTicketEmailBusy,
    externalTicketEmailSent,
    ticketSelfHealBusy,
    showBulkRequestModal,
    bulkCategory,
    bulkSelection,
    bulkSearch,
    setBulkSearch,
    setBulkSelection,
    accessLogInfoEntryId,
    setAccessLogInfoEntryId,
    accessLogInfoEntry,
    workflowUsesAccessLogDetails,
    techCustodianKeys,
    addRequestEntry,
    openBulkRequestModal,
    bulkCustodianDisabledReason,
    toggleBulkCustodian,
    submitBulkRequests,
    closeBulkModal,
    updateRequestEntry,
    updateAccessLogTimeWindow,
    addAccessLogTimeWindow,
    removeAccessLogTimeWindow,
    closeAccessLogInfoModal,
    saveAccessLogInfoModal,
    removeRequestEntry,
    createExternalTicket,
    sendCustodianDetailsToAssignee,
    handleRequestEntryCustodianChange,
    commitRequestTicketSave,
    runTicketSelfHeal,
  }
}
