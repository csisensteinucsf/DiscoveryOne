import { useCallback, useEffect, useMemo, useState } from 'react'
import { consentCache } from './caseDetailUtils.js'
import { isConsentUnavailableForRequest, normalizeConsentStatus } from './custodianStatusCatalog.js'

const emptyConsentForm = { recordType: '', dateFrom: '', dateTo: '', message: '' }
const consentRequestId = consent => String(consent?.request_id || consent?.envelope_id || '').trim()

export function useCaseDetailConsents({
  apiBase,
  caseId,
  caseData,
  custodians,
  searches,
  showToast,
  confirmDialog,
  loadSlaStatus,
  setCaseData,
  esignDisplayName = 'e-signature provider',
}) {
  const [showConsentModal, setShowConsentModal] = useState(false)
  const [consentSelection, setConsentSelection] = useState(new Set())
  const [consentFormInline, setConsentFormInline] = useState(emptyConsentForm)
  const [consentSendBusy, setConsentSendBusy] = useState(false)
  const [consentSearch, setConsentSearch] = useState('')
  const [consentAutoSearchId, setConsentAutoSearchId] = useState('')
  const [consents, setConsents] = useState(() => consentCache.get(caseId) || [])
  const [consentsLoading, setConsentsLoading] = useState(false)
  const [consentsError, setConsentsError] = useState(null)
  const [consentActionBusy, setConsentActionBusy] = useState({ id: null, type: null })
  const [consentDownloadBusyId, setConsentDownloadBusyId] = useState(null)



  const consentCustodians = useMemo(() => custodians || [], [custodians])

  const loadConsents = useCallback(async () => {
    if (!caseId) return
    setConsentsLoading(true)
    setConsentsError(null)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/consents`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text() || 'Unable to load consents')
      const data = await res.json()
      const next = Array.isArray(data) ? data : []
      setConsents(next)
      consentCache.set(caseId, next)
      setCaseData(prev => prev ? { ...prev, consent_envelope_count: next.length } : prev)
    } catch (err) {
      setConsentsError(err?.message || 'Unable to load consents')
    } finally {
      setConsentsLoading(false)
    }
  }, [apiBase, caseId, setCaseData])

  const consentReceivedIds = useMemo(() => {
    const ids = new Set()
    ;(consents || []).forEach(c => {
      const status = String(c?.status || '').trim().toLowerCase()
      if (!['completed', 'received'].includes(status)) return
      const id = Number(c?.custodian_id)
      if (Number.isFinite(id)) ids.add(id)
    })
    ;(consentCustodians || []).forEach(c => {
      const id = Number(c?.id)
      const status = String(c?.consent_status || '').trim().toLowerCase()
      if (Number.isFinite(id) && isConsentUnavailableForRequest(status)) ids.add(id)
    })
    return ids
  }, [consentCustodians, consents])

  const consentReceivedEmails = useMemo(() => {
    const emails = new Set()
    ;(consents || []).forEach(c => {
      const status = String(c?.status || '').trim().toLowerCase()
      if (!['completed', 'received'].includes(status)) return
      const email = (c?.custodian_email || '').trim().toLowerCase()
      if (email) emails.add(email)
    })
    ;(consentCustodians || []).forEach(c => {
      const status = String(c?.consent_status || '').trim().toLowerCase()
      const email = (c?.email || '').trim().toLowerCase()
      if (isConsentUnavailableForRequest(status) && email) emails.add(email)
    })
    return emails
  }, [consentCustodians, consents])

  const consentRequestTracker = useMemo(() => {
    const byCustodian = new Map()
    ;(consents || []).forEach(c => {
      const id = Number(c?.custodian_id)
      const email = (c?.custodian_email || '').trim().toLowerCase()
      const requestId = consentRequestId(c)
      const key = Number.isFinite(id)
        ? `id:${id}`
        : (email ? `email:${email}` : (requestId ? `request:${requestId}` : ''))
      if (!key) return
      const status = String(c?.status || 'pending').trim().toLowerCase()
      const next = byCustodian.get(key) || { active: false, completed: false }
      if (status !== 'voided') next.active = true
      if (['completed', 'received'].includes(status)) {
        next.active = true
        next.completed = true
      }
      byCustodian.set(key, next)
    })
    let total = 0
    let completed = 0
    byCustodian.forEach(entry => {
      if (!entry.active) return
      total += 1
      if (entry.completed) completed += 1
    })
    return {
      total,
      completed,
      remaining: Math.max(0, total - completed),
    }
  }, [consents])

  const custodiansById = useMemo(() => {
    const byId = new Map()
    ;(consentCustodians || []).forEach(c => {
      const id = Number(c?.id)
      if (Number.isFinite(id)) byId.set(id, c)
    })
    return byId
  }, [consentCustodians])

  const isConsentUnavailable = useCallback((custodian) => {
    if (!custodian) return true
    const id = Number(custodian?.id)
    const status = normalizeConsentStatus(custodian?.consent_status)
    const email = (custodian?.email || '').trim().toLowerCase()
    if (!Number.isFinite(id)) return true
    if (isConsentUnavailableForRequest(status)) return true
    if (consentReceivedIds.has(id)) return true
    if (email && consentReceivedEmails.has(email)) return true
    return false
  }, [consentReceivedEmails, consentReceivedIds])

  const consentAutoSearches = useMemo(() => {
    return (searches || []).map(s => {
      const ids = (s?.custodianIds ?? s?.custodian_ids ?? []).map(Number).filter(Number.isFinite)
      const unique = Array.from(new Set(ids))
      const eligible = unique.filter(id => {
        const custodian = custodiansById.get(id)
        return custodian && !isConsentUnavailable(custodian)
      })
      return {
        id: String(s?.id ?? ''),
        name: String(s?.name || '').trim() || `Search ${s?.id ?? ''}`,
        custodianIds: unique,
        eligibleCount: eligible.length,
      }
    }).filter(s => s.custodianIds.length > 0)
  }, [searches, custodiansById, isConsentUnavailable])

  const filteredConsentCustodians = useMemo(() => {
    const list = Array.isArray(consentCustodians) ? consentCustodians : []
    const q = (consentSearch || '').trim().toLowerCase()
    if (!q) return list
    return list.filter(c => (c.name || '').toLowerCase().includes(q) || (c.email || '').toLowerCase().includes(q))
  }, [consentCustodians, consentSearch])

  const consentSelectedRecipients = useMemo(() => {
    const rows = Array.from(consentSelection || [])
      .map(Number)
      .filter(Number.isFinite)
      .map(id => custodiansById.get(id))
      .filter(c => c && !isConsentUnavailable(c))
    rows.sort((a, b) => {
      const ak = String(a?.email || a?.name || '').toLowerCase()
      const bk = String(b?.email || b?.name || '').toLowerCase()
      return ak.localeCompare(bk)
    })
    return rows
  }, [consentSelection, custodiansById, isConsentUnavailable])

  const addAllAvailableConsents = () => {
    const next = new Set(consentSelection || [])
    let added = 0
    let skipped = 0
    ;(filteredConsentCustodians || []).forEach(c => {
      const id = Number(c?.id)
      if (!Number.isFinite(id) || isConsentUnavailable(c)) {
        skipped += 1
        return
      }
      if (!next.has(id)) {
        next.add(id)
        added += 1
      }
    })
    setConsentSelection(next)
    showToast(
      `All available custodians: added ${added}, skipped ${skipped}.`,
      { variant: added > 0 ? 'success' : 'info' }
    )
  }

  const autoAddConsentFromSearch = (searchId) => {
    const selectedSearch = consentAutoSearches.find(s => String(s.id) === String(searchId || consentAutoSearchId))
    if (!selectedSearch) {
      showToast('Choose a search to auto add custodians from.', { variant: 'warn' })
      return
    }
    const next = new Set(consentSelection || [])
    let added = 0
    let skipped = 0
    selectedSearch.custodianIds.forEach(id => {
      const custodian = custodiansById.get(Number(id))
      if (!custodian || isConsentUnavailable(custodian)) {
        skipped += 1
        return
      }
      if (!next.has(Number(id))) {
        next.add(Number(id))
        added += 1
      }
    })
    setConsentSelection(next)
    showToast(
      `Auto add from ${selectedSearch.name}: added ${added}, skipped ${skipped}.`,
      { variant: added > 0 ? 'success' : 'info' }
    )
  }

  const sendSelectedConsents = async () => {
    if (!caseId) return
    const selectedIds = Array.from(consentSelection || []).map(Number).filter(Number.isFinite)
    const allowedSelectedIds = selectedIds.filter(id => {
      const custodian = custodiansById.get(id)
      return custodian && !isConsentUnavailable(custodian)
    })
    if (!allowedSelectedIds.length) {
      showToast('Select at least one eligible custodian.', { variant: 'error' })
      return
    }
    const recordType = (consentFormInline.recordType || '').trim()
    if (!recordType) {
      showToast('Record type is required.', { variant: 'error' })
      return
    }
    const legalCaseName = (caseData?.legal_case_name || '').trim()
    if (!legalCaseName) {
      let ok = true
      if (confirmDialog) {
        ok = await confirmDialog({
          title: 'Send without legal case name?',
          description: 'Are you sure you want to send e-signature consent requests without a legal case name?',
          confirmLabel: 'Send anyway',
        })
      } else {
        ok = window.confirm('Are you sure you want to send e-signature consent requests without a legal case name?')
      }
      if (!ok) return
    }
    const payload = {
      record_type: recordType,
      date_from: (consentFormInline.dateFrom || '').trim() || 'NA',
      date_to: (consentFormInline.dateTo || '').trim() || 'NA',
      message: (consentFormInline.message || '').trim() || undefined,
      custodians: allowedSelectedIds.map(id => ({ custodian_id: id })),
    }
    setConsentSendBusy(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/consents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || `Unable to send ${esignDisplayName} request.`)
      }
      showToast(`Consent requests sent via ${esignDisplayName}.`, { variant: 'success' })
      setConsentSelection(new Set())
      setConsentFormInline(emptyConsentForm)
      setShowConsentModal(false)
      await loadConsents()
      await loadSlaStatus()
    } catch (err) {
      showToast(err?.message || `Unable to send ${esignDisplayName} request.`, { variant: 'error' })
    } finally {
      setConsentSendBusy(false)
    }
  }

  const resendConsent = async (consent) => {
    if (!consent?.id) return
    setConsentActionBusy({ id: consent.id, type: 'resend' })
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/consents/${consent.id}/resend`, {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || 'Unable to resend request.')
      showToast(`Consent email resent via ${esignDisplayName}.`, { variant: 'success' })
      await loadConsents()
    } catch (err) {
      showToast(err?.message || 'Unable to resend request.', { variant: 'error' })
    } finally {
      setConsentActionBusy({ id: null, type: null })
    }
  }

  const downloadConsent = async (consent) => {
    const requestId = consentRequestId(consent)
    if (!consent?.id || !requestId) return
    setConsentDownloadBusyId(consent.id)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/consents/${consent.id}/download`, {
        credentials: 'include',
      })
      if (!res.ok) {
        const data = await res.json().catch(() => null)
        throw new Error(data?.detail || 'Unable to download consent.')
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      const safeName = requestId ? `consent-${requestId}.pdf` : `consent-${consent.id}.pdf`
      link.download = safeName
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      showToast(err?.message || 'Unable to download consent.', { variant: 'error' })
    } finally {
      setConsentDownloadBusyId(null)
    }
  }

  const voidConsent = async (consent) => {
    if (!consent?.id) return
    const reason = window.prompt('Enter a reason for voiding this request:', 'Cancelled') ?? null
    setConsentActionBusy({ id: consent.id, type: 'void' })
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/consents/${consent.id}/void`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ reason }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data?.detail || 'Unable to void request.')
      showToast('Consent request voided.', { variant: 'success' })
      await loadConsents()
    } catch (err) {
      showToast(err?.message || 'Unable to void request.', { variant: 'error' })
    } finally {
      setConsentActionBusy({ id: null, type: null })
    }
  }

  useEffect(() => {
    setConsentSelection(prev => {
      const next = new Set()
      prev.forEach(id => {
        const num = Number(id)
        const custodian = custodiansById.get(num)
        if (custodian && !isConsentUnavailable(custodian)) next.add(num)
      })
      return next
    })
  }, [custodiansById, isConsentUnavailable])

  useEffect(() => {
    if (!showConsentModal) return
    const options = consentAutoSearches || []
    if (!options.length) {
      if (consentAutoSearchId) setConsentAutoSearchId('')
      return
    }
    const hasCurrent = options.some(s => String(s.id) === String(consentAutoSearchId))
    if (!hasCurrent) setConsentAutoSearchId(String(options[0].id))
  }, [showConsentModal, consentAutoSearches, consentAutoSearchId])

  return {
    showConsentModal,
    setShowConsentModal,
    consentCustodians,
    consentSelection,
    setConsentSelection,
    consentFormInline,
    setConsentFormInline,
    consentSendBusy,
    consentSearch,
    setConsentSearch,
    consentAutoSearchId,
    setConsentAutoSearchId,
    consents,
    consentsLoading,
    consentsError,
    consentActionBusy,
    consentDownloadBusyId,
    loadConsents,
    consentReceivedIds,
    consentReceivedEmails,
    consentRequestTracker,
    consentAutoSearches,
    filteredConsentCustodians,
    consentSelectedRecipients,
    addAllAvailableConsents,
    autoAddConsentFromSearch,
    sendSelectedConsents,
    resendConsent,
    downloadConsent,
    voidConsent,
  }
}
