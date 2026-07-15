import { useCallback, useEffect, useRef, useState } from 'react'
import { lookupPersonName } from './caseRequestsUtils.js'

export function useCaseRequestCustodianLookup({
  apiBase,
  useWizard,
  step,
  form,
  setForm,
  displayedCustodians,
  updateCustodian,
}) {
  const [lookupStatus, setLookupStatus] = useState('idle')
  const [lookupError, setLookupError] = useState('')
  const [lookupMatches, setLookupMatches] = useState({})
  const [lookupSelection, setLookupSelection] = useState({})
  const [lookupCompletedFor, setLookupCompletedFor] = useState(new Set())
  const [unmatchedCount, setUnmatchedCount] = useState(0)
  const [unmatchedModalOpenState, setUnmatchedModalOpenState] = useState(false)
  const unmatchedModalOpen = !!unmatchedModalOpenState
  const setUnmatchedModalOpen = (val) => setUnmatchedModalOpenState(!!val)
  const setShowUnmatchedNotice = setUnmatchedModalOpen
  const [custodianLookupOptOut, setCustodianLookupOptOut] = useState(new Set())
  const lookupSignatureRef = useRef({})
  const lookupProgrammaticIdsRef = useRef(new Set())

  const resetLookupState = useCallback(() => {
    setLookupStatus('idle')
    setLookupError('')
    setLookupMatches({})
    setLookupSelection({})
    setUnmatchedCount(0)
    setUnmatchedModalOpen(false)
    setCustodianLookupOptOut(new Set())
    setLookupCompletedFor(new Set())
    lookupSignatureRef.current = {}
    lookupProgrammaticIdsRef.current = new Set()
  }, [])

  const resetLookupResults = useCallback(() => {
    setLookupStatus('idle')
    setLookupError('')
    setLookupMatches({})
    setLookupSelection({})
    setLookupCompletedFor(new Set())
    setUnmatchedCount(0)
    setUnmatchedModalOpen(false)
  }, [])

  useEffect(() => {
    const nextSignature = {}
    const changedIds = new Set()
    ;(form.custodians || []).forEach((cust) => {
      const key = String(cust.id)
      const signature = `${(cust.name || '').trim()}|${(cust.email || '').trim()}|${!!cust.override_lookup}`
      nextSignature[key] = signature
      if (lookupSignatureRef.current[key] !== undefined && lookupSignatureRef.current[key] !== signature) {
        if (lookupProgrammaticIdsRef.current.has(key)) {
          lookupProgrammaticIdsRef.current.delete(key)
        } else {
          changedIds.add(key)
        }
      } else if (lookupProgrammaticIdsRef.current.has(key)) {
        lookupProgrammaticIdsRef.current.delete(key)
      }
    })
    lookupSignatureRef.current = nextSignature
    if (!changedIds.size) return
    setLookupMatches((prev) => {
      const next = { ...prev }
      changedIds.forEach((id) => { delete next[id] })
      return next
    })
    setLookupSelection((prev) => {
      const next = { ...prev }
      changedIds.forEach((id) => { delete next[id] })
      return next
    })
    setLookupCompletedFor((prev) => {
      const next = new Set(prev)
      changedIds.forEach((id) => next.delete(id))
      return next
    })
    setUnmatchedCount(0)
    setShowUnmatchedNotice(false)
  }, [form.custodians])

  useEffect(() => {
    const allowed = new Set((form.custodians || []).map((c) => String(c.id)))
    setLookupMatches((prev) => {
      const next = {}
      let changed = false
      Object.entries(prev || {}).forEach(([id, val]) => {
        if (allowed.has(String(id))) {
          next[id] = val
        } else {
          changed = true
        }
      })
      return changed ? next : prev
    })
    setLookupSelection((prev) => {
      const next = {}
      let changed = false
      Object.entries(prev || {}).forEach(([id, val]) => {
        if (allowed.has(String(id))) {
          next[id] = val
        } else {
          changed = true
        }
      })
      return changed ? next : prev
    })
    setLookupCompletedFor((prev) => {
      const allowedIds = allowed
      let changed = false
      const next = new Set()
      prev.forEach((id) => {
        if (allowedIds.has(String(id))) {
          next.add(String(id))
        } else {
          changed = true
        }
      })
      return changed ? next : prev
    })
  }, [form.custodians])

  const applyMatchFields = useCallback((custId, match, { overwrite = false, clearIfMissing = false } = {}) => {
    const target = displayedCustodians.find(c => String(c.id) === String(custId))
    if (target?.override_lookup) return
    lookupProgrammaticIdsRef.current.add(String(custId))
    const matchedEmail = (match?.email || '').trim()
    const matchedName = lookupPersonName(match)
      || (match?.display_name || '').trim()
      || (match?.name || '').trim()
    setForm((prev) => ({
      ...prev,
      custodians: prev.custodians.map((c) => {
        if (String(c.id) !== String(custId)) return c
        const next = { ...c }
        const existingEmail = (c.email || '').trim()
        const existingName = (c.name || '').trim()
        const shouldApplyEmail = overwrite || !existingEmail
        if (matchedEmail || (clearIfMissing && overwrite)) {
          if (shouldApplyEmail) next.email = matchedEmail || ''
        }
        if (matchedName && (overwrite || !existingName || existingName.toLowerCase() !== matchedName.toLowerCase())) {
          next.name = matchedName
        }
        return next
      }),
    }))
  }, [displayedCustodians, setForm])

  const selectedMatchFor = useCallback((custId) => {
    const entry = lookupMatches[String(custId)] || lookupMatches[custId]
    if (!entry || !Array.isArray(entry.matches)) return null
    const idx = lookupSelection[String(custId)] ?? lookupSelection[custId]
    if (Number.isInteger(idx)) {
      return entry.matches[idx] || null
    }
    if (entry.matches.length === 1) return entry.matches[0]
    return null
  }, [lookupMatches, lookupSelection])

  const runCustodianLookup = useCallback(async (rosterOverride) => {
    if (!useWizard) return
    if (form.custodianMode === 'none' || (form.custodianMode === 'upload' && !(form.custodians || []).length)) {
      resetLookupResults()
      return
    }
    const roster = (rosterOverride && rosterOverride.length ? rosterOverride : displayedCustodians)
      .map((c) => ({ id: String(c.id), name: c.name || '', email: c.email || '' }))
      .filter((c) => (c.name || '').trim() && !custodianLookupOptOut.has(String(c.id)))
    const pendingRoster = roster.filter((c) => !lookupCompletedFor.has(String(c.id)))
    if (!pendingRoster.length) return
    setLookupStatus('loading')
    setLookupError('')
    try {
      const res = await fetch(`${apiBase}/case_requests/custodian_lookup`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custodians: pendingRoster }),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Lookup failed.')
      }
      const data = await res.json()
      const matchesById = { ...lookupMatches }
      const selectionById = { ...lookupSelection }
      for (const item of data.results || []) {
        const key = String(item.id || item.name || '')
        const matches = Array.isArray(item.matches) ? item.matches.filter(Boolean) : []
        matchesById[key] = { matches, error: item.error || '' }
        if (matches.length === 1) {
          selectionById[key] = 0
        }
      }
      setLookupMatches(matchesById)
      setLookupSelection(selectionById)
      Object.entries(selectionById).forEach(([key, idx]) => {
        const match = matchesById[key]?.matches?.[idx]
        if (match) {
          applyMatchFields(key, match, { overwrite: true, clearIfMissing: true })
        }
      })
      setLookupCompletedFor((prev) => {
        const next = new Set(prev)
        pendingRoster.forEach((c) => next.add(String(c.id)))
        return next
      })
      const unmatched = Object.entries(matchesById)
        .filter(([id, entry]) => {
          const matchTarget = displayedCustodians.find((c) => String(c.id) === String(id))
          if (matchTarget?.override_lookup) return false
          if (custodianLookupOptOut.has(String(id))) return false
          return Array.isArray(entry.matches) && entry.matches.length === 0 && !entry.error
        }).length
      setUnmatchedCount(unmatched)
      setShowUnmatchedNotice(unmatched > 0)
      setLookupStatus('success')
    } catch (err) {
      console.error(err)
      setLookupStatus('error')
      setLookupError(err?.message || 'Lookup failed.')
      setUnmatchedCount(0)
      setShowUnmatchedNotice(false)
    }
  }, [apiBase, applyMatchFields, custodianLookupOptOut, displayedCustodians, form.custodianMode, form.custodians, lookupCompletedFor, lookupMatches, lookupSelection, resetLookupResults, useWizard])

  useEffect(() => {
    if (!useWizard) return
    if (step !== 2) return
    if (!['manual', 'paste'].includes(form.custodianMode)) return
    const pending = displayedCustodians.filter((c) => !lookupCompletedFor.has(String(c.id)) && !custodianLookupOptOut.has(String(c.id)))
    if (!pending.length) return
    runCustodianLookup(pending)
  }, [useWizard, step, form.custodianMode, displayedCustodians, custodianLookupOptOut, lookupCompletedFor, runCustodianLookup])

  const handleSelectMatch = (custId, idx) => {
    const key = String(custId)
    setLookupSelection((prev) => ({ ...prev, [key]: idx }))
    const match = (lookupMatches[key]?.matches || [])[idx]
    applyMatchFields(custId, match, { overwrite: true, clearIfMissing: true })
  }

  const toggleLookupOverride = (custodian) => {
    const key = String(custodian.id)
    setUnmatchedModalOpen(false)
    setUnmatchedCount(0)
    setShowUnmatchedNotice(false)
    setCustodianLookupOptOut((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
    setLookupMatches((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
    setLookupSelection((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
    updateCustodian(custodian.id, {
      override_lookup: !custodian.override_lookup,
      override_note: !custodian.override_lookup ? `Person lookup overridden by requestor for ${custodian.name || 'custodian'}` : '',
    })
  }

  const badgesForMatch = (match) => {
    const end = match?.employee_end_date
    if (!end) return []
    const ts = Date.parse(end)
    if (Number.isNaN(ts) || ts > Date.now()) return []
    const days = (Date.now() - ts) / (1000 * 60 * 60 * 24)
    if (days < 90) return [{ label: 'S', title: 'Separated (< 3 months)', variant: 'success' }]
    if (days >= 365) return [{ label: 'S', title: 'Separated (over 1 year)', variant: 'danger' }]
    return [{ label: 'S', title: 'Separated (< 1 year)', variant: 'warn' }]
  }

  const employmentBadgesFromPayload = (cust) => {
    const end = cust?.employment_end_date
    if (!end) return []
    const ts = Date.parse(end)
    if (Number.isNaN(ts) || ts > Date.now()) return []
    const days = (Date.now() - ts) / (1000 * 60 * 60 * 24)
    if (days < 90) return [{ label: 'S', title: 'Separated (< 3 months)', variant: 'success' }]
    if (days >= 365) return [{ label: 'S', title: 'Separated (over 1 year)', variant: 'danger' }]
    return [{ label: 'S', title: 'Separated (< 1 year)', variant: 'warn' }]
  }

  const endDateStyle = (match) => {
    const end = match?.employee_end_date
    if (!end) return {}
    const ts = Date.parse(end)
    if (Number.isNaN(ts)) return {}
    if (ts > Date.now()) return {}
    const days = (Date.now() - ts) / (1000 * 60 * 60 * 24)
    if (days < 90) return { color: '#15803d', fontWeight: 600 }
    if (days >= 365) return { color: '#b91c1c', fontWeight: 600 }
    return { color: '#b45309', fontWeight: 600 }
  }

  return {
    lookupStatus,
    lookupError,
    lookupMatches,
    lookupSelection,
    lookupCompletedFor,
    unmatchedCount,
    unmatchedModalOpen,
    setUnmatchedModalOpen,
    setShowUnmatchedNotice,
    custodianLookupOptOut,
    setCustodianLookupOptOut,
    resetLookupState,
    resetLookupResults,
    selectedMatchFor,
    runCustodianLookup,
    handleSelectMatch,
    toggleLookupOverride,
    badgesForMatch,
    employmentBadgesFromPayload,
    endDateStyle,
  }
}