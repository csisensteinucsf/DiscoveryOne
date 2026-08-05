import { useEffect, useRef } from 'react'
import {
  REQUESTOR_CACHE_KEY,
  caseCache,
  isValidEmail,
  loadSearches,
  readSessionJSON,
} from './caseDetailUtils.js'
import { mergeSearchClientState, serverLoadSearches } from './caseDetailPersistence.js'

export function useCaseDetailBootstrap({
  apiBase,
  caseId,
  activeTab,
  isTech,
  isRequestor,
  setLoading,
  setError,
  setCaseData,
  setCustodians,
  setHoldBaseline,
  setUsers,
  setRequestorOptions,
  setSearches,
  loadHoldsDetail,
  loadProofs,
  loadConsents,
  loadSlaStatus,
}) {
  const tabDataLoadedRef = useRef({ documentation: false, sla: false, preservation: false })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const casePromise = fetch(`${apiBase}/cases/${caseId}`, { credentials: 'include' })
        const custodiansPromise = fetch(`${apiBase}/cases/${caseId}/custodians`, { credentials: 'include' })
        const usersPromise = isTech
          ? Promise.resolve(null)
          : fetch(`${apiBase}/users`, { credentials: 'include' }).catch(() => null)
        const [r1, r2, ru] = await Promise.all([casePromise, custodiansPromise, usersPromise])
        if (!r1.ok) throw new Error(`Case HTTP ${r1.status}`)
        const c = await r1.json()
        if (!cancelled) {
          setCaseData(c)
          caseCache.set(caseId, c)
        }
        if (r2.ok) {
          const list = await r2.json()
          if (!cancelled) {
            const next = Array.isArray(list) ? list : []
            setCustodians(next)
            setHoldBaseline(next)
          }
        }
        if (isTech) {
          if (!cancelled) {
            setUsers([])
            setRequestorOptions([])
            setSearches([])
          }
        } else {
          if (ru && ru.ok) {
            const ul = await ru.json()
            if (!cancelled) setUsers(ul || [])
          }
          const fromCase = []
          try {
            const primary = (c?.requestor || '').trim()
            if (primary && isValidEmail(primary)) fromCase.push(primary)
            if (Array.isArray(c?.requestors)) {
              c.requestors.forEach(r => {
                const e = (r?.email || '').trim()
                if (e && isValidEmail(e)) fromCase.push(e)
              })
            }
          } catch {}
          let fromLocal = []
          try {
            fromLocal = (readSessionJSON(REQUESTOR_CACHE_KEY, []) || []).filter(v => v && isValidEmail(v))
          } catch {}
          const uniq = Array.from(new Set([...(fromCase || []), ...(fromLocal || [])]))
          if (!cancelled) setRequestorOptions(uniq)
          const cachedSearches = loadSearches(caseId)
          let loaded = await serverLoadSearches(caseId)
          if (!loaded) loaded = cachedSearches
          else loaded = mergeSearchClientState(loaded, cachedSearches)
          if (!cancelled) setSearches(loaded || [])
        }
      } catch (e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [apiBase, caseId, isTech, setCaseData, setCustodians, setError, setHoldBaseline, setLoading, setRequestorOptions, setSearches, setUsers])

  useEffect(() => {
    tabDataLoadedRef.current = { documentation: false, sla: false, preservation: false }
  }, [caseId])

  useEffect(() => {
    if (activeTab === 'preservation' && !tabDataLoadedRef.current.preservation) {
      tabDataLoadedRef.current.preservation = true
      loadHoldsDetail()
    }
    if (isTech) return
    if (activeTab === 'documentation' && !tabDataLoadedRef.current.documentation) {
      tabDataLoadedRef.current.documentation = true
      loadProofs()
      loadConsents()
    }
    if (activeTab === 'sla' && !tabDataLoadedRef.current.sla) {
      tabDataLoadedRef.current.sla = true
      loadSlaStatus()
    }
  }, [activeTab, caseId, isTech, loadProofs, loadConsents, loadSlaStatus, loadHoldsDetail])
}