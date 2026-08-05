import {
  customPreservationPatch,
  isCustomHoldKey,
} from './caseDetailUtils.js'

export function useCaseDetailTechHoldActions({
  apiBase,
  caseId,
  custodians,
  setCustodians,
  isTech,
  techHoldsApplying,
  setTechHoldsApplying,
  holdsDirty,
  holdKeysForTech,
  holdState,
  holdPatchForState,
  holdMetaByKey,
  techHoldKeySet,
  savedHoldMap,
  holdsBaselineReady,
  setHoldBaseline,
  buildHoldState,
  submitCustodianBulkUpdate,
  confirmDialog,
  showToast,
}) {
  const setAllTechPendingCompleted = () => {
    if (!isTech || !holdKeysForTech.length) return
    setCustodians(prev => prev.map(c => {
      let patch = null
      holdKeysForTech.forEach((key) => {
        if (c?.[`${key}_pending`]) {
          patch = { ...(patch || {}), ...holdPatchForState(key, 'active') }
        }
      })
      return patch ? { ...c, ...patch } : c
    }))
  }

  const applyTechHoldChanges = async () => {
    if (!isTech || techHoldsApplying) return
    if (!holdKeysForTech.length) {
      showToast('No preservation sources are available to update.', { variant: 'info' })
      return
    }
    if (!holdsDirty) {
      showToast('No preservation changes to apply.', { variant: 'info' })
      return
    }
    const ok = await confirmDialog({
      title: 'Apply preservation changes',
      description: 'Apply these preservation updates so everyone can see them?',
      confirmLabel: 'Apply',
    })
    if (!ok) return
    setTechHoldsApplying(true)
    try {
      const baseline = savedHoldMap.current || new Map()
      const updates = []
      for (const custodian of (custodians || [])) {
        const base = baseline.get(custodian.id) || {}
        const patch = {}
        let changed = false
        for (const key of holdKeysForTech) {
          const state = holdState(custodian, key)
          const active = !!state.active
          const pending = !!state.pending
          const failed = !!state.failed
          const released = !!state.released
          if (
            active !== !!base[key]
            || pending !== !!base[`${key}_pending`]
            || failed !== !!base[`${key}_failed`]
            || released !== !!base[`${key}_released`]
          ) {
            if (isCustomHoldKey(key)) {
              patch.custom_preservation = customPreservationPatch(
                { ...custodian, custom_preservation: patch.custom_preservation || custodian.custom_preservation },
                key,
                { active, pending, failed, released },
                holdMetaByKey.get(key)?.label,
              )
            } else {
              patch[key] = active
              patch[`${key}_pending`] = pending
              patch[`${key}_failed`] = failed
              patch[`${key}_released`] = released
            }
            changed = true
          }
        }
        if (changed) updates.push({ id: custodian.id, patch })
      }
      if (!updates.length) {
        setHoldBaseline(custodians)
        showToast('No preservation changes to apply.', { variant: 'info' })
        return
      }
      const succeeded = await submitCustodianBulkUpdate({ updates })
      if (succeeded.length) {
        const updatedMap = new Map(succeeded.map(item => [item.id, item]))
        const baseMap = new Map(savedHoldMap.current || [])
        succeeded.forEach(item => {
          baseMap.set(item.id, buildHoldState(item))
        })
        savedHoldMap.current = baseMap
        holdsBaselineReady.current = true
        setCustodians(prev => prev.map(c => {
          const updated = updatedMap.get(c.id)
          return updated ? { ...c, ...updated } : c
        }))
      }
      showToast('Preservation changes applied.', { variant: 'success' })
      const containsReleaseUpdate = updates.some(({ patch }) => Object.entries(patch || {}).some(([k, v]) => k.endsWith('_released') && v === true))
      if (techHoldKeySet.has('holds_box') && !containsReleaseUpdate) {
        try {
          const res = await fetch(`${apiBase}/cases/${caseId}/requestor_hold_status_email`, {
            method: 'POST',
            credentials: 'include',
          })
          const data = await res.json().catch(() => null)
          if (!res.ok) {
            const detail = data?.detail || data?.message
            throw new Error(detail || 'Unable to send requestor preservation status email')
          }
        } catch (err) {
          showToast(err?.message || 'Failed to send requestor preservation status email.', { variant: 'error' })
        }
      }
    } catch (err) {
      showToast(err?.message || 'Failed to apply preservation updates.', { variant: 'error' })
    } finally {
      setTechHoldsApplying(false)
    }
  }

  return { setAllTechPendingCompleted, applyTechHoldChanges }
}
