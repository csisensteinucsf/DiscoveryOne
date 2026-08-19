import { useCallback, useEffect, useState } from 'react'

async function responseError(response, fallback) {
  const body = await response.json().catch(() => null)
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback + ' (HTTP ' + response.status + ')'
}

export function useCaseDetailNamedHolds({ apiBase, caseId, showToast, onMutationComplete }) {
  const [namedHolds, setNamedHolds] = useState([])
  const [namedHoldTotals, setNamedHoldTotals] = useState({})
  const [namedHoldsLoading, setNamedHoldsLoading] = useState(false)
  const [namedHoldsError, setNamedHoldsError] = useState('')
  const [namedHoldBusy, setNamedHoldBusy] = useState(false)

  const loadNamedHolds = useCallback(async () => {
    if (!caseId) return
    setNamedHoldsLoading(true)
    setNamedHoldsError('')
    try {
      const response = await fetch(apiBase + '/cases/' + caseId + '/holds', { credentials: 'include' })
      if (!response.ok) throw new Error(await responseError(response, 'Unable to load holds'))
      const data = await response.json()
      setNamedHolds(Array.isArray(data?.holds) ? data.holds : [])
      setNamedHoldTotals(data?.totals || {})
    } catch (error) {
      setNamedHoldsError(error?.message || 'Unable to load holds')
    } finally {
      setNamedHoldsLoading(false)
    }
  }, [apiBase, caseId])

  useEffect(() => {
    loadNamedHolds()
  }, [loadNamedHolds])

  const mutate = useCallback(async (path, options, successMessage) => {
    setNamedHoldBusy(true)
    try {
      const response = await fetch(apiBase + '/cases/' + caseId + '/holds' + path, {
        credentials: 'include',
        headers: options?.body ? { 'Content-Type': 'application/json' } : undefined,
        ...options,
      })
      if (!response.ok) throw new Error(await responseError(response, 'Hold update failed'))
      await Promise.all([
        loadNamedHolds(),
        typeof onMutationComplete === 'function' ? onMutationComplete() : Promise.resolve(),
      ])
      if (successMessage) showToast(successMessage, { variant: 'success' })
      return true
    } catch (error) {
      showToast(error?.message || 'Hold update failed', { variant: 'error' })
      return false
    } finally {
      setNamedHoldBusy(false)
    }
  }, [apiBase, caseId, loadNamedHolds, onMutationComplete, showToast])

  const createNamedHold = useCallback(payload => mutate('', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, 'Hold created.'), [mutate])

  const updateNamedHold = useCallback((holdId, payload) => mutate('/' + holdId, {
    method: 'PUT',
    body: JSON.stringify(payload),
  }, 'Hold updated.'), [mutate])

  const addNamedHoldCustodians = useCallback((holdId, custodianIds) => mutate('/' + holdId + '/custodians', {
    method: 'POST',
    body: JSON.stringify({ custodian_ids: custodianIds }),
  }, 'Custodians assigned to hold.'), [mutate])

  const removeNamedHoldCustodian = useCallback((holdId, custodianId) => mutate(
    '/' + holdId + '/custodians/' + custodianId,
    { method: 'DELETE' },
    'Custodian removed from hold.',
  ), [mutate])

  const updateNamedHoldPreservation = useCallback((holdId, custodianId, sourceKey, status) => {
    const basePath = '/' + holdId + '/custodians/' + custodianId + '/preservation/' + encodeURIComponent(sourceKey)
    const useAutomation = status === 'pending' || status === 'released'
    return mutate(
      basePath + (useAutomation ? '/automation' : ''),
      {
        method: useAutomation ? 'POST' : 'PUT',
        body: JSON.stringify(useAutomation ? { enabled: status === 'pending' } : { status }),
      },
      useAutomation
        ? (status === 'pending' ? 'Preservation hold started.' : 'Preservation hold released.')
        : 'Preservation status updated.',
    )
  }, [mutate])

  const updateNamedHoldWorkflow = useCallback((holdId, custodianId, payload) => mutate(
    '/' + holdId + '/custodians/' + custodianId + '/workflow',
    { method: 'PUT', body: JSON.stringify(payload) },
    'Hold workflow status updated.',
  ), [mutate])

  const setNamedHoldSearches = useCallback((holdId, searchIds) => mutate(
    '/' + holdId + '/searches',
    { method: 'PUT', body: JSON.stringify({ search_ids: searchIds }) },
    'Hold searches updated.',
  ), [mutate])

  return {
    namedHolds,
    namedHoldTotals,
    namedHoldsLoading,
    namedHoldsError,
    namedHoldBusy,
    loadNamedHolds,
    createNamedHold,
    updateNamedHold,
    addNamedHoldCustodians,
    removeNamedHoldCustodian,
    updateNamedHoldPreservation,
    updateNamedHoldWorkflow,
    setNamedHoldSearches,
  }
}