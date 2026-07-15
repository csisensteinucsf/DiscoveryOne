import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { serverLoadSearches } from './caseDetailPersistence.js'
import { saveSearches } from './caseDetailUtils.js'

const initialPurviewStatus = {
  loading: false,
  error: null,
  enabled: true,
  case_exists: false,
  hold_user_emails: [],
  hold_user_sources: [],
}

export function useCaseDetailPreservationProvider({ apiBase, caseId, caseData, custodians, setCustodians, setSearches, showToast, loading, providerName = 'Preservation provider' }) {
  const [purviewCreating, setPurviewCreating] = useState(false)
  const [showPurviewModal, setShowPurviewModal] = useState(false)
  const [purviewStatus, setPurviewStatus] = useState(initialPurviewStatus)
  const [purviewHoldBusy, setPurviewHoldBusy] = useState(false)
  const [purviewExportCheckBusy, setPurviewExportCheckBusy] = useState(false)
  const [purviewHoldResults, setPurviewHoldResults] = useState([])
  const [purviewLastHoldSources, setPurviewLastHoldSources] = useState([])
  const [purviewHoldSelection, setPurviewHoldSelection] = useState(new Set())
  const [purviewHoldOptions, setPurviewHoldOptions] = useState({ email: true, onedrive: true })
  const purviewSelectionInit = useRef(false)
  const purviewSettleTimersRef = useRef([])
  const purviewAutoRefreshScheduledRef = useRef(false)
  const purviewAutoRefreshRef = useRef({ timer: null, generation: 0, startedAt: 0, attempts: 0 })

  const custodianEmailById = useMemo(() => {
    const map = new Map()
    ;(custodians || []).forEach(c => {
      const id = Number(c?.id)
      if (Number.isFinite(id)) map.set(id, String(c?.email || '').trim().toLowerCase())
    })
    return map
  }, [custodians])

  const purviewHoldMap = useMemo(() => {
    const map = new Map()
    ;(purviewStatus.hold_user_sources || []).forEach(item => {
      const email = String(item?.email || '').trim().toLowerCase()
      if (!email) return
      map.set(email, {
        mailbox: !!item?.mailbox,
        site: !!item?.site,
      })
    })
    return map
  }, [purviewStatus.hold_user_sources])

  const purviewSelectedSources = useMemo(() => {
    const sources = []
    if (purviewHoldOptions.email) sources.push('mailbox')
    if (purviewHoldOptions.onedrive) sources.push('site')
    return sources
  }, [purviewHoldOptions])

  const refreshPurviewPendingCustodians = useCallback(async () => {
    if (!caseId) return
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/preservation_provider/status`, { credentials: 'include' })
      const data = await res.json().catch(() => null)
      if (!res.ok || !Array.isArray(data?.updated_custodians)) return
      const updateMap = new Map(data.updated_custodians.map(item => [Number(item.id), item]))
      setCustodians(prev => prev.map(c => {
        const update = updateMap.get(Number(c.id))
        return update ? { ...c, ...update } : c
      }))
    } catch {
      // ignore transient background refresh failures
    }
  }, [apiBase, caseId, setCustodians])

  const hasPurviewPendingHolds = useMemo(() => (
    (custodians || []).some(c => !!c?.holds_email_pending || !!c?.holds_onedrive_pending)
  ), [custodians])

  useEffect(() => {
    const ref = purviewAutoRefreshRef.current
    ref.generation += 1
    ref.startedAt = 0
    ref.attempts = 0
    if (ref.timer) {
      clearTimeout(ref.timer)
      ref.timer = null
    }
  }, [caseId])

  useEffect(() => {
    if (!caseId || loading) return
    const ref = purviewAutoRefreshRef.current
    const stop = () => {
      if (ref.timer) {
        clearTimeout(ref.timer)
        ref.timer = null
      }
      ref.startedAt = 0
      ref.attempts = 0
    }
    if (!hasPurviewPendingHolds) {
      stop()
      return
    }
    if (ref.timer) return
    if (!ref.startedAt) ref.startedAt = Date.now()
    const generation = ref.generation
    const maxMs = 12 * 60 * 1000
    const tick = async () => {
      if (purviewAutoRefreshRef.current.generation !== generation) return
      ref.attempts += 1
      await refreshPurviewPendingCustodians()
      if (purviewAutoRefreshRef.current.generation !== generation) return
      const elapsed = Date.now() - (ref.startedAt || Date.now())
      if (elapsed >= maxMs) {
        stop()
        return
      }
      const delayMs = ref.attempts <= 3 ? 8000 : (ref.attempts <= 8 ? 15000 : 30000)
      ref.timer = setTimeout(tick, delayMs)
    }
    ref.timer = setTimeout(tick, 8000)
    return stop
  }, [caseId, loading, hasPurviewPendingHolds, refreshPurviewPendingCustodians])

  const loadPurviewStatus = useCallback(async (options = {}) => {
    if (!caseId) return
    const background = !!options?.background
    if (!background) {
      setPurviewStatus(prev => ({ ...prev, loading: true, error: null }))
    }
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/preservation_provider/status`, { credentials: 'include' })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || 'Unable to load preservation provider status')
      }
      const holdEmails = Array.isArray(data?.hold_user_emails) ? data.hold_user_emails : []
      const holdSources = Array.isArray(data?.hold_user_sources) ? data.hold_user_sources : []
      setPurviewHoldResults(prev => {
        if (!Array.isArray(prev) || prev.length === 0) return prev
        const required = Array.isArray(purviewLastHoldSources) && purviewLastHoldSources.length
          ? purviewLastHoldSources
          : ['mailbox', 'site']
        const requiredMailbox = required.includes('mailbox')
        const requiredSite = required.includes('site')
        const map = new Map()
        holdSources.forEach(item => {
          const email = String(item?.email || '').trim().toLowerCase()
          if (!email) return
          map.set(email, { mailbox: !!item?.mailbox, site: !!item?.site })
        })
        return prev.map(row => {
          if (!row || (row.status !== 'partial_hold' && row.status !== 'pending')) return row
          const email = String(row?.email || '').trim().toLowerCase()
          if (!email) return row
          const flags = map.get(email)
          if (!flags) return row
          const okMailbox = !requiredMailbox || flags.mailbox
          const okSite = !requiredSite || flags.site
          if (!okMailbox || !okSite) return row
          const next = { ...row, status: 'on_hold' }
          delete next.message
          return next
        })
      })
      if (Array.isArray(data?.updated_custodians)) {
        const updateMap = new Map(data.updated_custodians.map(item => [Number(item.id), item]))
        setCustodians(prev => prev.map(c => {
          const update = updateMap.get(Number(c.id))
          return update ? { ...c, ...update } : c
        }))
      }
      setPurviewStatus(prev => ({
        ...(background ? prev : {}),
        ...data,
        hold_user_emails: holdEmails,
        hold_user_sources: holdSources,
        loading: false,
        error: null,
      }))
    } catch (err) {
      if (!background) {
        setPurviewStatus(prev => ({ ...prev, loading: false, error: err?.message || 'Unable to load preservation provider status' }))
      }
    }
  }, [apiBase, caseId, purviewLastHoldSources, setCustodians])

  const schedulePurviewStatusChecks = useCallback((delaysMs) => {
    try {
      ;(purviewSettleTimersRef.current || []).forEach(t => clearTimeout(t))
    } catch {}
    purviewSettleTimersRef.current = []
    ;(delaysMs || []).forEach(ms => {
      const delay = Number(ms)
      if (!Number.isFinite(delay) || delay < 0) return
      const id = setTimeout(() => {
        loadPurviewStatus({ background: true })
      }, delay)
      purviewSettleTimersRef.current.push(id)
    })
  }, [loadPurviewStatus])

  useEffect(() => {
    return () => {
      try {
        ;(purviewSettleTimersRef.current || []).forEach(t => clearTimeout(t))
      } catch {}
      purviewSettleTimersRef.current = []
    }
  }, [])

  useEffect(() => {
    if (!caseId || !purviewStatus?.enabled || !purviewStatus?.case_exists) return
    const pending = (custodians || []).some(c => !!c?.holds_email_pending || !!c?.holds_onedrive_pending)
    if (!pending) {
      purviewAutoRefreshScheduledRef.current = false
      return
    }
    if (purviewAutoRefreshScheduledRef.current) return
    purviewAutoRefreshScheduledRef.current = true
    schedulePurviewStatusChecks([10_000, 30_000, 60_000])
  }, [caseId, purviewStatus?.enabled, purviewStatus?.case_exists, custodians, schedulePurviewStatusChecks])

  async function handleCreatePurviewCase() {
    if (!caseId || purviewCreating) return
    setPurviewCreating(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/preservation_provider/case`, {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || 'Unable to create preservation provider case')
      }
      const label = data?.display_name || caseData?.name || 'case'
      if (data?.status === 'exists') {
        showToast(`${providerName} case already exists for ${label}.`, { variant: 'info' })
      } else {
        showToast(`${providerName} case created for ${label}.`, { variant: 'success' })
      }
      loadPurviewStatus()
    } catch (err) {
      console.error(err)
      showToast(err?.message || 'Unable to create preservation provider case', { variant: 'error' })
    } finally {
      setPurviewCreating(false)
    }
  }

  async function checkPurviewExports() {
    if (!caseId || purviewExportCheckBusy || purviewStatus?.enabled === false || !purviewStatus?.case_exists) return
    setPurviewExportCheckBusy(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/purview_exports/check`, {
        method: 'POST',
        credentials: 'include',
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || 'Unable to check provider exports')
      }
      const exportCount = Number(data?.exports_count ?? data?.export_count ?? 0)
      const matchedCount = Number(data?.matched_searches_count ?? data?.matched_count ?? 0)
      const unmatched = Array.isArray(data?.unmatched_exports) ? data.unmatched_exports : []
      const withoutConsent = Array.isArray(data?.matched_without_consent) ? data.matched_without_consent : []
      if (exportCount === 0) {
        showToast('No provider exports found for this case.', { variant: 'info' })
      } else {
        const pieces = [
          `Found ${exportCount} export${exportCount === 1 ? '' : 's'}`,
          `${matchedCount} matched`,
        ]
        if (withoutConsent.length) pieces.push(`${withoutConsent.length} without consent`)
        if (unmatched.length) pieces.push(`${unmatched.length} unmatched`)
        showToast(pieces.join(' | '), { variant: withoutConsent.length ? 'warn' : 'success' })
      }
      const reloaded = await serverLoadSearches(caseId)
      if (Array.isArray(reloaded)) {
        setSearches(reloaded)
        saveSearches(caseId, reloaded)
      }
      loadPurviewStatus()
    } catch (err) {
      console.error(err)
      showToast(err?.message || 'Unable to check provider exports', { variant: 'error' })
    } finally {
      setPurviewExportCheckBusy(false)
    }
  }

  async function applyPurviewHolds() {
    if (!caseId || purviewHoldBusy) return
    const ids = Array.from(purviewHoldSelection).map(Number).filter(Number.isFinite)
    if (!ids.length) {
      showToast('Select at least one custodian.', { variant: 'warn' })
      return
    }
    if (!purviewSelectedSources.length) {
      showToast('Select at least one hold type.', { variant: 'warn' })
      return
    }
    setPurviewLastHoldSources([...purviewSelectedSources])
    setPurviewHoldBusy(true)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/preservation_provider/holds`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          custodian_ids: ids,
          included_sources: purviewSelectedSources,
          verify_timeout_seconds: purviewSelectedSources.includes('site') ? 75 : 0,
        }),
      })
      const rawText = await res.text().catch(() => '')
      let data = null
      try {
        data = rawText ? JSON.parse(rawText) : null
      } catch {
        data = null
      }
      if (!res.ok) {
        const detail = (data?.detail || data?.message || rawText || '').trim()
        throw new Error(detail || 'Unable to apply provider holds')
      }
      const results = Array.isArray(data?.results) ? data.results : []
      setPurviewHoldResults(results)
      if (Array.isArray(data?.updated_custodians)) {
        const updateMap = new Map(data.updated_custodians.map(item => [Number(item.id), item]))
        setCustodians(prev => prev.map(c => {
          const update = updateMap.get(Number(c.id))
          return update ? { ...c, ...update } : c
        }))
      }
      if (Array.isArray(data?.hold_user_sources)) {
        const emails = data.hold_user_sources.map(item => String(item?.email || '').trim()).filter(Boolean)
        setPurviewStatus(prev => ({ ...prev, hold_user_sources: data.hold_user_sources, hold_user_emails: emails }))
        setPurviewHoldSelection(prev => {
          const next = new Set()
          const holdMap = new Map()
          data.hold_user_sources.forEach(item => {
            const email = String(item?.email || '').trim().toLowerCase()
            if (!email) return
            holdMap.set(email, { mailbox: !!item?.mailbox, site: !!item?.site })
          })
          prev.forEach(id => {
            const email = String(custodianEmailById.get(Number(id)) || '').trim().toLowerCase()
            if (!email) return
            const status = holdMap.get(email) || { mailbox: false, site: false }
            const needsMailbox = purviewSelectedSources.includes('mailbox') && !status.mailbox
            const needsSite = purviewSelectedSources.includes('site') && !status.site
            if (needsMailbox || needsSite) next.add(Number(id))
          })
          return next
        })
      }
      showToast('Provider holds applied.', { variant: 'success' })
      loadPurviewStatus()
      schedulePurviewStatusChecks([5_000, 15_000, 30_000, 60_000])
    } catch (err) {
      showToast(err?.message || 'Unable to apply provider holds', { variant: 'error' })
    } finally {
      setPurviewHoldBusy(false)
    }
  }

  function togglePurviewHoldSelection(id) {
    const cid = Number(id)
    if (!Number.isFinite(cid)) return
    setPurviewHoldSelection(prev => {
      const next = new Set(prev)
      if (next.has(cid)) next.delete(cid)
      else next.add(cid)
      return next
    })
  }

  function selectAllPurviewHoldTargets() {
    const next = new Set()
    ;(custodians || []).forEach(c => {
      const email = String(c?.email || '').trim().toLowerCase()
      const id = Number(c?.id)
      if (!Number.isFinite(id)) return
      if (!email || email === 'noemail' || email === 'unmatched') return
      const status = purviewHoldMap.get(email) || { mailbox: false, site: false }
      const needsMailbox = purviewSelectedSources.includes('mailbox') && !status.mailbox
      const needsSite = purviewSelectedSources.includes('site') && !status.site
      if (!needsMailbox && !needsSite) return
      next.add(id)
    })
    setPurviewHoldSelection(next)
  }

  useEffect(() => {
    if (!showPurviewModal) {
      purviewSelectionInit.current = false
      return
    }
    setPurviewHoldResults([])
    loadPurviewStatus()
  }, [showPurviewModal, loadPurviewStatus])

  useEffect(() => {
    if (!showPurviewModal || purviewSelectionInit.current || purviewStatus.loading) return
    const next = new Set()
    ;(custodians || []).forEach(c => {
      const email = String(c?.email || '').trim().toLowerCase()
      const id = Number(c?.id)
      if (!email || email === 'noemail' || email === 'unmatched') return
      if (!Number.isFinite(id)) return
      const status = purviewHoldMap.get(email) || { mailbox: false, site: false }
      const needsMailbox = purviewSelectedSources.includes('mailbox') && !status.mailbox
      const needsSite = purviewSelectedSources.includes('site') && !status.site
      if (needsMailbox || needsSite) {
        next.add(id)
      }
    })
    setPurviewHoldSelection(next)
    purviewSelectionInit.current = true
  }, [showPurviewModal, purviewStatus.loading, custodians, purviewHoldMap, purviewSelectedSources])

  return {
    showPurviewModal,
    setShowPurviewModal,
    purviewStatus,
    purviewCreating,
    purviewHoldBusy,
    purviewExportCheckBusy,
    purviewHoldResults,
    purviewHoldSelection,
    setPurviewHoldSelection,
    purviewHoldOptions,
    setPurviewHoldOptions,
    purviewHoldMap,
    purviewSelectedSources,
    handleCreatePurviewCase,
    checkPurviewExports,
    applyPurviewHolds,
    togglePurviewHoldSelection,
    selectAllPurviewHoldTargets,
  }
}