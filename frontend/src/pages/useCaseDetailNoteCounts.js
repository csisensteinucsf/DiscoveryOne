import { useEffect, useState } from 'react'
import { tryFetchJSON } from './caseDetailPersistence.js'
import { caseCache } from './caseDetailUtils.js'

export function useCaseDetailNoteCounts({
  apiBase,
  caseId,
  cachedCase,
  caseData,
  setCaseData,
  isTech,
  isRequestor,
  isSysAdmin,
  setProofRows,
  updateProofCountsOnCase,
}) {
  const [noteCount, setNoteCount] = useState(() => Number(cachedCase?.notes_internal_count || 0))
  const [requestorNoteCount, setRequestorNoteCount] = useState(() => Number(cachedCase?.notes_requestor_count || 0))
  const [activeNoteCount, setActiveNoteCount] = useState(0)

  useEffect(() => {
    if (!caseId) return undefined
    if (isTech) {
      setNoteCount(0)
      setRequestorNoteCount(0)
      setActiveNoteCount(0)
      return undefined
    }
    let cancelled = false
    ;(async () => {
      try {
        const [internalRows, requestorRows, activeRows] = await Promise.all([
          isRequestor ? Promise.resolve([]) : tryFetchJSON(`${apiBase}/cases/${caseId}/notes`),
          tryFetchJSON(`${apiBase}/cases/${caseId}/requestor_notes`),
          (!isRequestor && isSysAdmin) ? tryFetchJSON(`${apiBase}/cases/${caseId}/active_notes`) : Promise.resolve([]),
        ])
        if (cancelled) return
        const nextInternal = Array.isArray(internalRows) ? internalRows.length : 0
        const nextRequestor = Array.isArray(requestorRows) ? requestorRows.length : 0
        const nextActive = Array.isArray(activeRows) ? activeRows.length : 0
        setNoteCount(Math.max(0, nextInternal))
        setRequestorNoteCount(Math.max(0, nextRequestor))
        setActiveNoteCount(Math.max(0, nextActive))
        setCaseData(prev => {
          if (!prev) return prev
          const updated = {
            ...prev,
            notes_internal_count: Math.max(0, nextInternal),
            notes_requestor_count: Math.max(0, nextRequestor),
          }
          if (
            Number(prev.notes_internal_count || 0) === updated.notes_internal_count
            && Number(prev.notes_requestor_count || 0) === updated.notes_requestor_count
          ) return prev
          caseCache.set(caseId, updated)
          return updated
        })
      } catch {
        // Counts are opportunistic badges; leave existing values on refresh failure.
      }
    })()
    return () => { cancelled = true }
  }, [apiBase, caseId, isTech, isRequestor, isSysAdmin, setCaseData])

  useEffect(() => {
    if (isTech || !caseId) return undefined
    const consentCount = Number(caseData?.consent_envelope_count || 0)
    const proofCount = Number(caseData?.consent_proof_count || 0)
    if (consentCount > 0 || proofCount > 0) return undefined
    let cancelled = false
    ;(async () => {
      try {
        const [consentsRows, proofRows] = await Promise.all([
          tryFetchJSON(`${apiBase}/cases/${caseId}/consents`),
          tryFetchJSON(`${apiBase}/case_requests/cases/${caseId}/consent_proofs`),
        ])
        if (cancelled) return
        const nextConsentCount = Array.isArray(consentsRows) ? consentsRows.length : consentCount
        const nextProofCount = Array.isArray(proofRows) ? proofRows.length : proofCount
        if (Array.isArray(proofRows)) setProofRows(proofRows)
        if (nextConsentCount === consentCount && nextProofCount === proofCount) return
        updateProofCountsOnCase(nextProofCount, nextConsentCount)
      } catch {
        // Proof counts are backfilled opportunistically; keep the current counters.
      }
    })()
    return () => { cancelled = true }
  }, [apiBase, caseId, isTech, caseData?.consent_envelope_count, caseData?.consent_proof_count, setProofRows, updateProofCountsOnCase])

  return {
    noteCount,
    setNoteCount,
    requestorNoteCount,
    setRequestorNoteCount,
    activeNoteCount,
    setActiveNoteCount,
  }
}