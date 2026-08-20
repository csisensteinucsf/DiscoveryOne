import { useCallback } from 'react'
import {
  REQUESTOR_CACHE_KEY,
  caseCache,
  isValidEmail,
  readSessionJSON,
  writeSessionJSON,
} from './caseDetailUtils.js'

export function useCaseDetailCaseActions({
  apiBase,
  caseId,
  caseData,
  setCaseData,
  setCustodians,
  showToast,
  confirmDialog,
}) {
  const updateCustodianLocal = useCallback((id, patch) => {
    setCustodians(prev => prev.map(c => c.id === id ? { ...c, ...patch } : c))
  }, [setCustodians])

  const patchCustodian = useCallback(async (custodianId, patch) => {
    const res = await fetch(`${apiBase}/cases/${caseId}/custodians/${custodianId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(patch),
    })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      throw new Error(`Save failed (${res.status}) ${t}`)
    }
    return res.json()
  }, [apiBase, caseId])

  const updateCase = useCallback(async (patch) => {
    const payload = { ...patch }
    let normalizedRequestor = null
    if (Object.prototype.hasOwnProperty.call(payload, 'requestor')) {
      const trimmed = (payload.requestor || '').trim()
      if (trimmed && !isValidEmail(trimmed)) {
        throw new Error('Requestor must be a valid email address')
      }
      normalizedRequestor = trimmed || null
      payload.requestor = normalizedRequestor
    }
    if (Object.prototype.hasOwnProperty.call(payload, 'closed')) {
      payload.closed = !!payload.closed
    }
    Object.keys(payload).forEach((key) => {
      if (payload[key] === undefined) {
        delete payload[key]
      }
    })
    if (!Object.keys(payload).length) {
      return caseData
    }
    const sendUpdate = async body => {
      const response = await fetch(`${apiBase}/cases/${caseId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      })
      const responseBody = await response.json().catch(() => null)
      return { response, responseBody }
    }

    const { response, responseBody } = await sendUpdate(payload)
    if (!response.ok) {
      const message = responseBody?.detail?.message || responseBody?.detail || responseBody?.message
      throw new Error(String(message || `HTTP ${response.status}`))
    }
    const data = responseBody
    let fresh = data
    try {
      const refreshRes = await fetch(`${apiBase}/cases/${caseId}`, { credentials: 'include' })
      if (refreshRes.ok) {
        fresh = await refreshRes.json()
      }
    } catch {
      // Keep using the update response if the follow-up read fails.
    }
    setCaseData(fresh)
    caseCache.set(caseId, fresh)
    if (normalizedRequestor) {
      const existingRaw = readSessionJSON(REQUESTOR_CACHE_KEY, []) || []
      const existing = new Set(existingRaw.filter(v => v && isValidEmail(v)))
      existing.add(normalizedRequestor)
      writeSessionJSON(REQUESTOR_CACHE_KEY, Array.from(existing).sort((a, b) => a.localeCompare(b)))
    }
    showToast('Matter updated.', { variant: 'success' })
    return fresh
  }, [apiBase, caseData, caseId, setCaseData, showToast])

  return { updateCase, updateCustodianLocal, patchCustodian }
}
