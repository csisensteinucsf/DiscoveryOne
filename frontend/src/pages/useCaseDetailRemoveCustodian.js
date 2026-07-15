import { useCallback, useState } from 'react'
import { saveSearches } from './caseDetailUtils.js'

const defaultRemoveCustodianModal = () => ({
  open: false,
  custodian: null,
  releaseHolds: true,
  releaseNtp: true,
  closeSearches: true,
  note: '',
  busy: false,
})

export function useCaseDetailRemoveCustodian({ apiBase, caseId, isReadOnly, setCustodians, setSearches, showToast }) {
  const [removeCustodianModal, setRemoveCustodianModal] = useState(defaultRemoveCustodianModal)

  const openRemoveCustodian = useCallback((custodian) => {
    if (isReadOnly) return
    setRemoveCustodianModal({
      open: true,
      custodian,
      releaseHolds: true,
      releaseNtp: true,
      closeSearches: true,
      note: '',
      busy: false,
    })
  }, [isReadOnly])

  const removeCustodian = useCallback(async () => {
    if (isReadOnly) return
    const target = removeCustodianModal.custodian
    if (!target) return
    setRemoveCustodianModal((modal) => ({ ...modal, busy: true }))
    let purviewError = null
    let purviewCounts = null
    try {
      if (removeCustodianModal.releaseHolds) {
        try {
          const res = await fetch(`${apiBase}/cases/${caseId}/purview_holds/release`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              custodian_ids: [target.id],
              included_sources: ['mailbox', 'site'],
            }),
          })
          const data = await res.json().catch(() => null)
          if (!res.ok) {
            const detail = data?.detail || data?.message
            throw new Error(detail || 'Unable to release Purview holds')
          }
          if (data?.status_counts) {
            purviewCounts = data.status_counts
          }
        } catch (err) {
          purviewError = err
        }
      }
      const params = new URLSearchParams()
      if (removeCustodianModal.releaseHolds) params.set('release_holds', 'true')
      if (removeCustodianModal.releaseNtp) params.set('release_ntp', 'true')
      if (removeCustodianModal.closeSearches) params.set('close_searches', 'true')
      const note = (removeCustodianModal.note || '').trim()
      if (note) params.set('approval_note', note)
      const res = await fetch(`${apiBase}/cases/${caseId}/custodians/${target.id}?${params.toString()}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Failed to remove custodian.')
      }
      setCustodians(prev => prev.filter(custodian => custodian.id !== target.id))
      setSearches(prev => {
        const next = prev.map(search => {
          const ids = (search.custodianIds ?? search.custodian_ids ?? []).map(Number).filter(id => id !== target.id)
          return { ...search, custodianIds: ids, custodian_ids: ids }
        })
        saveSearches(caseId, next)
        return next
      })
      if (purviewError) {
        const message = purviewError?.message || 'Unknown error'
        showToast(`Custodian removed; Purview hold release failed: ${message}`, { variant: 'warn', duration: 12000 })
      } else if (purviewCounts?.error) {
        showToast('Custodian removed; Purview release reported errors. Check logs for details.', { variant: 'warn', duration: 12000 })
      } else {
        showToast('Custodian removed.', { variant: 'info' })
      }
    } catch (err) {
      showToast(err?.message || 'Failed to remove custodian.', { variant: 'error' })
    } finally {
      setRemoveCustodianModal(defaultRemoveCustodianModal())
    }
  }, [apiBase, caseId, isReadOnly, removeCustodianModal, setCustodians, setSearches, showToast])

  return {
    removeCustodianModal,
    setRemoveCustodianModal,
    openRemoveCustodian,
    removeCustodian,
  }
}
