import { useCallback, useMemo, useState } from 'react'
import {
  consentNotRequiredAutoReason,
  lookupPersonName,
} from './caseDetailUtils.js'
import {
  editablePersonLookupFieldsFromRecord,
  personLookupFieldsFromRecord,
  personLookupExternalId,
} from './caseDetailPersonLookupFields.js'
import { normalizeConsentStatus } from './custodianStatusCatalog.js'

function normalizePersonLabel(value) {
  const text = String(value || '').trim().toLowerCase()
  if (!text) return ''
  return text
    .replace(/[^a-z0-9@]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function custodianMatchesClaimant(claimant, custodian) {
  const claim = normalizePersonLabel(claimant)
  if (!claim || claim === 'na' || claim === 'n a') return false
  const emailNorm = normalizePersonLabel(custodian?.email || '')
  if (claim.includes('@') && emailNorm && emailNorm === claim) return true
  const nameNorm = normalizePersonLabel(custodian?.name || '')
  if (!nameNorm) return false
  if (nameNorm === claim) return true
  if (claim.length >= 4 && (claim.includes(nameNorm) || nameNorm.includes(claim))) return true
  return false
}

export function useCaseDetailEditCustodian({
  apiBase,
  caseId,
  caseData,
  custodians,
  isReadOnly,
  employeeIdLabel,
  confirmDialog,
  showToast,
  updateCase,
  updateCustodianLocal,
}) {
  const [editing, setEditing] = useState(null)
  const [editSaveBusy, setEditSaveBusy] = useState(false)
  const [editLookupBusy, setEditLookupBusy] = useState(false)
  const [editLookupOptions, setEditLookupOptions] = useState(null)

  const editingConsentAutoReason = useMemo(() => {
    if (!editing) return ''
    return consentNotRequiredAutoReason(caseData?.claimant, editing, { forceClaimant: !!editing?.is_claimant })
  }, [editing, caseData?.claimant])

  const editingConsentNotRequired = useMemo(() => {
    if (!editing) return false
    if (normalizeConsentStatus(editing?.consent_status) === 'awoc') return false
    if (editingConsentAutoReason) return true
    return normalizeConsentStatus(editing?.consent_status) === 'implied'
  }, [editing, editingConsentAutoReason])

  const onEditCustodian = useCallback((custodian) => {
    if (isReadOnly) return
    setEditSaveBusy(false)
    setEditing({
      id: custodian.id,
      name: custodian.name || '',
      email: custodian.email || '',
      ...editablePersonLookupFieldsFromRecord(custodian),
      employment_status: custodian.employment_status || null,
      ntp_status: custodian.ntp_status || 'not sent',
      ntp_not_required_reason: custodian.ntp_not_required_reason || '',
      consent_status: custodian.consent_status || 'not sent',
      consent_not_required_reason: custodian.consent_not_required_reason || '',
      person_lookup_overridden: !!custodian.person_lookup_overridden,
      is_claimant: custodianMatchesClaimant(caseData?.claimant, custodian),
    })
  }, [caseData?.claimant, isReadOnly])

  const onSaveEditCustodian = useCallback(async (form) => {
    if (isReadOnly || editSaveBusy) return
    const existingClaimant = (custodians || []).find((entry) => (
      Number(entry?.id) !== Number(form?.id)
      && custodianMatchesClaimant(caseData?.claimant, entry)
    ))
    if (form?.is_claimant && existingClaimant) {
      const currentLabel = existingClaimant.name || existingClaimant.email || 'Another custodian'
      await confirmDialog({
        title: 'Claimant already assigned',
        description: `${currentLabel} is already marked as the claimant for this case. Update that claimant first before assigning another custodian.`,
        confirmLabel: 'OK',
        cancelLabel: 'Close',
      })
      return
    }
    const priorConsentStatus = normalizeConsentStatus(form?.consent_status)
    const autoConsentReason = consentNotRequiredAutoReason(caseData?.claimant, form, { forceClaimant: !!form?.is_claimant })
    const consentNotRequired = priorConsentStatus !== 'awoc' && (!!autoConsentReason || priorConsentStatus === 'implied')
    const manualConsentReason = String(form?.consent_not_required_reason || '').trim()
    const consentReason = autoConsentReason || (consentNotRequired ? manualConsentReason : '')
    if (consentNotRequired && !consentReason) {
      showToast('Enter why consent is Implied.', { variant: 'warn' })
      return
    }
    const consentStatusForSave = consentNotRequired ? 'implied' : (priorConsentStatus === 'implied' ? 'not sent' : priorConsentStatus)
    setEditSaveBusy(true)
    try {
      const payload = {
        name: form.name,
        email: form.email || null,
        ...personLookupFieldsFromRecord(form),
        notes: null,
        person_lookup_overridden: !!form.person_lookup_overridden,
      }
      if (consentStatusForSave !== 'awoc') {
        payload.consent_status = consentStatusForSave
        payload.consent_not_required_reason = consentNotRequired ? consentReason : null
      }
      const res = await fetch(`${apiBase}/cases/${caseId}/custodians/${form.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        if (res.status === 409) {
          showToast('Duplicate email for this case.', { variant: 'warn' })
        } else {
          showToast('Failed to save custodian.', { variant: 'error' })
        }
        return
      }
      const updated = await res.json()
      updateCustodianLocal(updated.id, updated)
      if (form?.is_claimant) {
        const claimantLabel = String(updated?.name || form?.name || '').trim() || String(updated?.email || form?.email || '').trim()
        if (!claimantLabel) {
          showToast('Custodian saved, but claimant was not set because this custodian has no name or email.', { variant: 'warn' })
          return
        }
        try {
          await updateCase({ claimant: claimantLabel })
        } catch (err) {
          showToast(`Custodian saved, but failed to set claimant: ${err?.message || 'unknown error'}`, { variant: 'error' })
          return
        }
      }
      setEditing(null)
    } finally {
      setEditSaveBusy(false)
    }
  }, [apiBase, caseData?.claimant, caseId, confirmDialog, custodians, editSaveBusy, isReadOnly, showToast, updateCase, updateCustodianLocal])

  const applyEditMatch = useCallback((match) => {
    if (!editing || !match) return
    const fullName = lookupPersonName(match)
    const nextEmail = String(match.email || '').trim()
    const next = {
      ...editing,
      name: fullName || editing.name,
      email: nextEmail || editing.email || '',
      ...editablePersonLookupFieldsFromRecord(match),
      person_lookup_overridden: false,
    }
    setEditing(next)
    updateCustodianLocal(editing.id, {
      name: next.name,
      email: next.email,
      ...personLookupFieldsFromRecord(next),
      person_lookup_overridden: false,
    })
  }, [editing, updateCustodianLocal])

  const runEditPersonLookup = useCallback(async () => {
    if (isReadOnly) return
    if (!editing) return
    const lookupValue = String(editing.name || editing.email || personLookupExternalId(editing) || '').trim()
    if (!lookupValue) {
      showToast(`Enter a full name, email address, or ${employeeIdLabel} before running lookup.`, { variant: 'warn' })
      return
    }
    setEditLookupBusy(true)
    setEditLookupOptions(null)
    try {
      const res = await fetch(`${apiBase}/case_requests/custodian_lookup`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custodians: [{ id: editing.id, name: lookupValue, email: editing.email }] }),
      })
      if (!res.ok) throw new Error(await res.text() || 'Lookup failed')
      const data = await res.json()
      const entry = Array.isArray(data?.results) ? data.results[0] : null
      const matches = Array.isArray(entry?.matches) ? entry.matches : []
      if (!matches.length) {
        showToast('No person match found.', { variant: 'info' })
        return
      }
      if (matches.length === 1) {
        applyEditMatch(matches[0])
        showToast('Person info updated from lookup.', { variant: 'success' })
        return
      }
      setEditLookupOptions({ matches, selection: 0 })
      applyEditMatch(matches[0])
      showToast('Multiple matches found. Select the correct person.', { variant: 'info' })
    } catch (err) {
      console.error('Custodian lookup failed', err)
      showToast('Person lookup failed.', { variant: 'error' })
    } finally {
      setEditLookupBusy(false)
    }
  }, [apiBase, applyEditMatch, editing, employeeIdLabel, isReadOnly, showToast])

  return {
    editing,
    setEditing,
    editSaveBusy,
    editLookupBusy,
    editLookupOptions,
    setEditLookupOptions,
    editingConsentAutoReason,
    editingConsentNotRequired,
    onEditCustodian,
    onSaveEditCustodian,
    applyEditMatch,
    runEditPersonLookup,
    custodianMatchesClaimant,
  }
}
