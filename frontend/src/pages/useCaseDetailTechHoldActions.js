import {
  HOLD_FAILED_FIELDS,
  HOLD_FIELDS,
  HOLD_PENDING_FIELDS,
  HOLD_RELEASED_FIELDS,
  customPreservationEntry,
  customPreservationPatch,
  isCustomHoldKey,
} from './caseDetailUtils.js'

export function useCaseDetailTechHoldActions({
  apiBase,
  caseId,
  custodians,
  setCustodians,
  isTech,
  isReadOnly,
  techHoldsApplying,
  setTechHoldsApplying,
  holdsDirty,
  holdKeysForTech,
  holdState,
  holdPatchForState,
  holdMetaByKey,
  holdMetaForView,
  techHoldKeySet,
  savedHoldMap,
  holdsBaselineReady,
  setHoldBaseline,
  buildHoldState,
  submitCustodianBulkUpdate,
  setReleasingHolds,
  confirmDialog,
  showToast,
  preservationAutomationEnabled,
  preservationProvider,
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
      showToast('No hold categories available to update.', { variant: 'info' })
      return
    }
    if (!holdsDirty) {
      showToast('No hold changes to apply.', { variant: 'info' })
      return
    }
    const ok = await confirmDialog({
      title: 'Apply hold changes',
      description: 'Apply these hold updates so everyone can see them?',
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
        showToast('No hold changes to apply.', { variant: 'info' })
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
      showToast('Hold changes applied.', { variant: 'success' })
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
            throw new Error(detail || 'Unable to send requestor hold status email')
          }
        } catch (err) {
          showToast(err?.message || 'Failed to send requestor hold status email.', { variant: 'error' })
        }
      }
    } catch (err) {
      showToast(err?.message || 'Failed to apply hold updates.', { variant: 'error' })
    } finally {
      setTechHoldsApplying(false)
    }
  }

  const releaseAllHolds = async ({ skipConfirm = false } = {}) => {
    if (isReadOnly || !custodians.length) return false
    if (!skipConfirm) {
      const ok = await confirmDialog({
        title: 'Release all holds',
        description: preservationProvider === 'purview'
          ? 'Release all holds for every custodian in this case? This will also delete the Purview hold policy.' 
          : preservationAutomationEnabled
            ? 'Release all holds through the configured preservation provider?'
            : 'Release all manually tracked holds for every custodian in this case?',
        confirmLabel: 'Release holds',
        destructive: true,
      })
      if (!ok) return false
    }
    const resetPatch = [...HOLD_FIELDS, ...HOLD_PENDING_FIELDS, ...HOLD_FAILED_FIELDS].reduce((acc, key) => ({ ...acc, [key]: false }), {})
    const releasePatchFor = (custodian) => {
      const patch = { ...resetPatch }
      HOLD_FIELDS.forEach((key, idx) => {
        const pendingKey = `${key}_pending`
        const failedKey = `${key}_failed`
        const releasedKey = HOLD_RELEASED_FIELDS[idx]
        if (custodian?.[failedKey]) {
          patch[key] = !!custodian?.[key]
          patch[pendingKey] = !!custodian?.[pendingKey]
          patch[failedKey] = !!custodian?.[failedKey]
          patch[releasedKey] = !!custodian?.[releasedKey]
          return
        }
        const wasHeld = !!(
          custodian?.[releasedKey]
          || custodian?.[key]
          || custodian?.[pendingKey]
          || custodian?.[failedKey]
        )
        patch[releasedKey] = wasHeld
      })
      const customEntries = (holdMetaForView || [])
        .filter(item => isCustomHoldKey(item.key))
        .reduce((entries, item) => {
          const current = customPreservationEntry({ ...custodian, custom_preservation: entries }, item.key)
            || customPreservationEntry(custodian, item.key)
          const failed = !!current?.failed
          const statePatch = failed
            ? {
                active: !!current?.active,
                pending: !!current?.pending,
                failed: true,
                released: !!current?.released,
              }
            : {
                active: false,
                pending: false,
                failed: false,
                released: !!(current?.released || current?.active || current?.pending || current?.failed),
              }
          return customPreservationPatch(
            { ...custodian, custom_preservation: entries },
            item.key,
            statePatch,
            item.label,
          )
        }, Array.isArray(custodian?.custom_preservation) ? custodian.custom_preservation : [])
      if (customEntries.length) patch.custom_preservation = customEntries
      return patch
    }
    const snapshot = custodians.map(c => ({ ...c }))
    setReleasingHolds(true)
    try {
      let providerUpdatedCustodians = []
      const mailboxReleaseIds = snapshot.filter(c => !c?.holds_email_failed).map(c => c.id)
      const siteReleaseIds = snapshot.filter(c => !c?.holds_onedrive_failed).map(c => c.id)
      const skippedPurviewFailed = snapshot.filter(c => c?.holds_email_failed || c?.holds_onedrive_failed)
      const skippedFailedAny = snapshot.filter(c => HOLD_FIELDS.some(key => !!c?.[`${key}_failed`]))
      const automationBatches = []
      if (preservationAutomationEnabled && mailboxReleaseIds.length) automationBatches.push({ ids: mailboxReleaseIds, sources: ['mailbox'] })
      if (preservationAutomationEnabled && siteReleaseIds.length) automationBatches.push({ ids: siteReleaseIds, sources: ['site'] })
      if (automationBatches.length) {
        const shouldDeleteHoldPolicy = skippedPurviewFailed.length === 0
        for (let i = 0; i < automationBatches.length; i += 1) {
          const batch = automationBatches[i]
          const res = await fetch(`${apiBase}/cases/${caseId}/purview_holds/release`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              custodian_ids: batch.ids,
              included_sources: batch.sources,
              delete_hold_policy: shouldDeleteHoldPolicy && i === automationBatches.length - 1,
            }),
          })
          const data = await res.json().catch(() => null)
          if (!res.ok) {
            const detail = data?.detail || data?.message
            throw new Error(detail || 'Unable to release holds through the configured provider')
          }
          if (data?.status_counts?.error) {
            throw new Error('Preservation provider release reported errors')
          }
          if (Array.isArray(data?.updated_custodians)) {
            providerUpdatedCustodians = providerUpdatedCustodians.concat(data.updated_custodians)
          }
        }
      }
      setCustodians(prev => prev.map(c => ({ ...c, ...releasePatchFor(c) })))
      const releasedCustodians = await submitCustodianBulkUpdate({
        updates: snapshot.map(c => ({ id: c.id, patch: releasePatchFor(c) })),
      })
      if (Array.isArray(releasedCustodians) && releasedCustodians.length) {
        const updatedMap = new Map(releasedCustodians.map(item => [Number(item.id), item]))
        setCustodians(prev => prev.map(c => {
          const update = updatedMap.get(Number(c.id))
          return update ? { ...c, ...update } : c
        }))
      }
      if (Array.isArray(providerUpdatedCustodians) && providerUpdatedCustodians.length) {
        const updateMap = new Map(providerUpdatedCustodians.map(item => [Number(item.id), item]))
        setCustodians(prev => prev.map(c => {
          const update = updateMap.get(Number(c.id))
          return update ? { ...c, ...update } : c
        }))
      }
      if (skippedFailedAny.length) {
        showToast('Released all eligible holds. Failed (red X) holds were left unchanged.', { variant: 'info' })
      } else {
        showToast('All holds released', { variant: 'info' })
      }
      return true
    } catch (err) {
      showToast(`Failed to release holds: ${err.message}`, { variant: 'error', duration: 12000 })
      setCustodians(snapshot)
      return false
    } finally {
      setReleasingHolds(false)
    }
  }

  return { setAllTechPendingCompleted, applyTechHoldChanges, releaseAllHolds }
}