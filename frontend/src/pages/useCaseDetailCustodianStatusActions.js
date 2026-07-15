import {
  CONSENT_NOT_REQUIRED_DEFAULT_REASON,
  NTP_NOT_REQUIRED_DEFAULT_REASON,
  consentNotRequiredAutoReason,
  customPreservationPatch,
  isCustomHoldKey,
} from './caseDetailUtils.js'

export function useCaseDetailCustodianStatusActions({
  caseData,
  custodians,
  setCustodians,
  bulk,
  setBulk,
  isRequestor,
  isTech,
  techHoldKeySet,
  techCustodianKeys,
  holdMetaByKey,
  holdState,
  holdPatchForState,
  normalizeEmail,
  updateCustodianLocal,
  patchCustodian,
  submitCustodianBulkUpdate,
  ntpAutoNaReason,
  showToast,
}) {
  const promptNaReason = (label, currentReason, fallbackReason) => {
    const seeded = String(currentReason || fallbackReason || '').trim()
    const answer = window.prompt(`What is the reason for the ${label} NA?`, seeded)
    if (answer === null) return null
    const trimmed = answer.trim()
    if (!trimmed) {
      showToast(`A reason is required when marking ${label} as NA.`, { variant: 'warn' })
      return ''
    }
    return trimmed
  }

  async function onToggleHold(c, fieldKey, nextState) {
    if (isRequestor) return
    if (isTech && !techHoldKeySet.has(fieldKey)) return
    const before = holdState(c, fieldKey)
    const label = holdMetaByKey.get(fieldKey)?.label || fieldKey.replace(/^custom:/, '').replace(/^holds_/, '')
    const patch = holdPatchForState(fieldKey, nextState || 'off', c, label)
    const revertPatch = holdPatchForState(
      fieldKey,
      before.pending ? 'pending' : (before.active ? 'active' : (before.failed ? 'failed' : (before.released ? 'released' : 'off'))),
      c,
      label,
    )
    if (isTech) {
      if (bulk.holds) return applyHoldToAll(fieldKey, nextState || 'off')
      updateCustodianLocal(c.id, patch)
      return
    }
    if (bulk.holds) return applyHoldToAll(fieldKey, nextState || 'off')
    updateCustodianLocal(c.id, patch)
    try {
      const saved = await patchCustodian(c.id, patch)
      updateCustodianLocal(c.id, saved)
    } catch (e) {
      updateCustodianLocal(c.id, revertPatch)
      showToast(e?.message || 'Failed to update hold.', { variant: 'error' })
    }
  }

  async function onChangeNtp(c, value) {
    if (isTech) return
    const v = value || 'not sent'
    if (!isRequestor && bulk.ntp) return applyToAll('ntp_status', v)
    const beforeStatus = c.ntp_status || 'not sent'
    const beforeReason = c.ntp_not_required_reason || null
    const patch = { ntp_status: v }
    if (String(v).trim().toLowerCase() === 'na') {
      const reason = promptNaReason('NTP', beforeReason, ntpAutoNaReason(c) || NTP_NOT_REQUIRED_DEFAULT_REASON)
      if (reason === null || !reason) return
      patch.ntp_not_required_reason = reason
    } else {
      patch.ntp_not_required_reason = null
    }
    updateCustodianLocal(c.id, patch)
    try {
      const saved = await patchCustodian(c.id, patch)
      updateCustodianLocal(c.id, saved)
    } catch (e) {
      updateCustodianLocal(c.id, { ntp_status: beforeStatus, ntp_not_required_reason: beforeReason })
      showToast(e?.message || 'Failed to update NTP status.', { variant: 'error' })
    }
  }

  async function onChangeConsent(c, value) {
    if (isTech) return
    const v = value || 'not sent'
    if (!isRequestor && bulk.consent) return applyToAll('consent_status', v)
    const beforeStatus = c.consent_status || 'not sent'
    const beforeReason = c.consent_not_required_reason || null
    const autoReason = consentNotRequiredAutoReason(caseData?.claimant, c)
    const patch = { consent_status: v }
    if (String(v).trim().toLowerCase() === 'na') {
      const reason = promptNaReason('consent', beforeReason, autoReason || CONSENT_NOT_REQUIRED_DEFAULT_REASON)
      if (reason === null || !reason) return
      patch.consent_not_required_reason = reason
    } else {
      patch.consent_not_required_reason = null
    }
    updateCustodianLocal(c.id, patch)
    try {
      const saved = await patchCustodian(c.id, patch)
      updateCustodianLocal(c.id, saved)
    } catch (e) {
      updateCustodianLocal(c.id, {
        consent_status: beforeStatus,
        consent_not_required_reason: beforeReason,
      })
      showToast(e?.message || 'Failed to update consent status.', { variant: 'error' })
    }
  }

  async function applyHoldToAll(fieldKey, checked) {
    const state = checked === true ? 'active' : (checked === false ? 'off' : checked)
    const label = holdMetaByKey.get(fieldKey)?.label || fieldKey.replace(/^custom:/, '').replace(/^holds_/, '')
    const patch = holdPatchForState(fieldKey, state || 'off', null, label)
    const targets = (isTech && techCustodianKeys)
      ? custodians.filter(c => {
        const idKey = Number.isFinite(Number(c.id)) ? `id:${Number(c.id)}` : ''
        const emailKey = c.email ? `email:${normalizeEmail(c.email)}` : ''
        return (idKey && techCustodianKeys.has(idKey)) || (emailKey && techCustodianKeys.has(emailKey))
      })
      : custodians
    const ids = targets.map(c => c.id)
    const idSet = new Set(ids)
    const snapshot = custodians.map(c => ({ ...c }))
    setCustodians(prev => prev.map(c => {
      if (!idSet.has(c.id)) return c
      if (!isCustomHoldKey(fieldKey)) return { ...c, ...patch }
      return { ...c, custom_preservation: customPreservationPatch(c, fieldKey, holdState({ ...c, ...patch }, fieldKey), label) }
    }))
    if (isTech) {
      setBulk(b => ({ ...b, holds: false }))
      return
    }
    try {
      const updated = await submitCustodianBulkUpdate({ ids, patch })
      if (updated.length) {
        const updatedMap = new Map(updated.map(item => [item.id, item]))
        setCustodians(prev => prev.map(c => {
          const next = updatedMap.get(c.id)
          return next ? { ...c, ...next } : c
        }))
      }
      const labelText = state === 'pending'
        ? 'PENDING'
        : (state === 'active' ? 'ON' : (state === 'failed' ? 'FAILED' : (state === 'released' ? 'RELEASED' : 'OFF')))
      showToast(`Applied ${labelText} for ${fieldKey.replace('holds_', '')} to ${ids.length} custodians`)
    } catch {
      setCustodians(snapshot)
      showToast('Some updates failed. Refresh to verify.', { variant: 'error' })
    } finally {
      setBulk(b => ({ ...b, holds: false }))
    }
  }

  async function applyToAll(key, value) {
    const ids = custodians.map(c => c.id)
    const snapshot = custodians.map(c => ({ ...c }))
    setCustodians(prev => prev.map(c => ({ ...c, [key]: value })))
    try {
      const updated = await submitCustodianBulkUpdate({ ids, patch: { [key]: value } })
      if (updated.length) {
        const updatedMap = new Map(updated.map(item => [item.id, item]))
        setCustodians(prev => prev.map(c => {
          const next = updatedMap.get(c.id)
          return next ? { ...c, ...next } : c
        }))
      }
      showToast(`Applied ${key.replace('_status', '')}: ${value} to ${ids.length} custodians`)
    } catch {
      setCustodians(snapshot)
      showToast('Some updates failed. Refresh to verify.', { variant: 'error' })
    } finally {
      setBulk(b => {
        const x = { ...b }
        if (key === 'ntp_status') x.ntp = false
        if (key === 'consent_status') x.consent = false
        return x
      })
    }
  }

  return { onToggleHold, onChangeNtp, onChangeConsent }
}