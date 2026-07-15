import { useCallback, useMemo } from 'react'
import {
  customPreservationEntry,
  customPreservationPatch,
  isCustomHoldKey,
  isMissingOrUnmatchedEmail,
  isSnowUnmatchedCustodian,
} from './caseDetailUtils.js'
import { requiresMatchedEmailForTicketWorkflow } from './ticketWorkflowCatalog.js'
import { personLookupExternalId } from './caseDetailPersonLookupFields.js'

const normalizeEmail = (value) => (value || '').trim().toLowerCase()

export function useCaseDetailCustodianLookups({ custodians, searches, holdMetaForView, holdMetaByKey }) {
  const custodianSearchAgg = useMemo(() => {
    const map = new Map()
    for (const search of (searches || [])) {
      const custodianIds = (search.custodian_ids ?? search.custodianIds ?? []).map(Number)
      const status = {
        search: search.status_search ?? search.status?.search ?? 'not performed',
        export: search.status_export ?? search.status?.export ?? 'not performed',
        delivery: search.status_delivery ?? search.status?.delivery ?? 'not performed',
      }
      for (const custodianId of custodianIds) {
        const previous = map.get(custodianId) || { search: 'not performed', export: 'not performed', delivery: 'not performed' }
        map.set(custodianId, {
          search: (previous.search === 'performed' || status.search === 'performed') ? 'performed' : 'not performed',
          export: (previous.export === 'performed' || status.export === 'performed') ? 'performed' : 'not performed',
          delivery: (
            previous.delivery === 'performed' ||
            previous.delivery === 'not required' ||
            status.delivery === 'performed' ||
            status.delivery === 'not required'
          ) ? 'performed' : 'not performed',
        })
      }
    }
    return map
  }, [searches])

  const holdState = useCallback((custodian, key) => {
    if (isCustomHoldKey(key)) {
      const entry = customPreservationEntry(custodian, key)
      return {
        active: !!entry?.active,
        pending: !!entry?.pending,
        failed: !!entry?.failed,
        released: !!entry?.released,
      }
    }
    return {
      active: !!(custodian?.[key]),
      pending: !!(custodian?.[`${key}_pending`]),
      failed: !!(custodian?.[`${key}_failed`]),
      released: !!(custodian?.[`${key}_released`]),
    }
  }, [])

  const hasAnyHold = useCallback((custodian) => holdMetaForView.some(({ key }) => {
    const state = holdState(custodian, key)
    return !!(state.active || state.pending || state.failed)
  }), [holdMetaForView, holdState])

  const holdPatchForState = useCallback((key, state, custodian = null, label = '') => {
    const statePatch = state === 'active'
      ? { active: true, pending: false, failed: false, released: false }
      : state === 'pending'
        ? { active: true, pending: true, failed: false, released: false }
        : state === 'failed'
          ? { active: false, pending: false, failed: true, released: false }
          : state === 'released'
            ? { active: false, pending: false, failed: false, released: true }
            : { active: false, pending: false, failed: false, released: false }
    if (isCustomHoldKey(key)) {
      return { custom_preservation: customPreservationPatch(custodian || {}, key, statePatch, label || holdMetaByKey.get(key)?.label) }
    }
    const pendingKey = `${key}_pending`
    const failedKey = `${key}_failed`
    const releasedKey = `${key}_released`
    return { [key]: statePatch.active, [pendingKey]: statePatch.pending, [failedKey]: statePatch.failed, [releasedKey]: statePatch.released }
  }, [holdMetaByKey])

  const custodianOptions = useMemo(() => {
    return (custodians || []).map(custodian => {
      const rawName = (custodian.name || '').trim()
      const rawEmail = (custodian.email || '').trim()
      const fallback = rawName || rawEmail || `Custodian ${custodian.id}`
      const emailPart = rawEmail && rawEmail.toLowerCase() !== fallback.toLowerCase() ? ` (${rawEmail})` : ''
      const label = `${fallback}${emailPart} [ID:${custodian.id}]`
      return {
        id: Number(custodian.id),
        name: rawName,
        email: rawEmail,
        external_id: personLookupExternalId(custodian) || '',
        person_lookup_overridden: !!custodian.person_lookup_overridden,
        snow_unmatched: isSnowUnmatchedCustodian(custodian),
        label,
      }
    })
  }, [custodians])

  const custodianLabelById = useMemo(() => {
    const map = new Map()
    custodianOptions.forEach(option => {
      if (Number.isFinite(option.id)) {
        map.set(option.id, option.label)
      }
    })
    return map
  }, [custodianOptions])

  const custodianOptionLookup = useMemo(() => {
    const map = new Map()
    custodianOptions.forEach(option => {
      map.set(option.label, option)
      if (option.email) map.set(option.email.toLowerCase(), option)
      if (option.name) map.set(option.name.toLowerCase(), option)
    })
    return map
  }, [custodianOptions])

  const custodianEmailById = useMemo(() => {
    const map = new Map()
    ;(custodians || []).forEach(custodian => {
      const email = (custodian.email || '').trim()
      if (email) {
        map.set(Number(custodian.id), email)
      }
    })
    return map
  }, [custodians])

  const custodianByIdForTickets = useMemo(() => {
    const map = new Map()
    ;(custodians || []).forEach(custodian => {
      const id = Number(custodian?.id)
      if (Number.isFinite(id)) map.set(id, custodian)
    })
    return map
  }, [custodians])

  const entryHasUnmatchedSnowCustodian = useCallback((entry) => {
    if (!entry || !requiresMatchedEmailForTicketWorkflow(entry.category)) return false
    const bulk = Array.isArray(entry.bulk_custodians) ? entry.bulk_custodians : []
    const hasSelectedCustodian = bulk.length > 0 || entry.custodian_id || entry.custodian_name || entry.custodian_email
    if (!hasSelectedCustodian) return false
    const invalidBulk = bulk.some(custodian => {
      const id = Number(custodian?.id)
      const source = Number.isFinite(id) ? custodianByIdForTickets.get(id) : null
      return source ? isSnowUnmatchedCustodian(source) : isMissingOrUnmatchedEmail(custodian?.email)
    })
    if (invalidBulk) return true
    const custodianId = Number(entry.custodian_id)
    const source = Number.isFinite(custodianId) ? custodianByIdForTickets.get(custodianId) : null
    if (source) return isSnowUnmatchedCustodian(source)
    return isMissingOrUnmatchedEmail(entry.custodian_email)
  }, [custodianByIdForTickets])

  return {
    normalizeEmail,
    custodianSearchAgg,
    holdState,
    hasAnyHold,
    holdPatchForState,
    custodianOptions,
    custodianLabelById,
    custodianOptionLookup,
    custodianEmailById,
    custodianByIdForTickets,
    entryHasUnmatchedSnowCustodian,
  }
}
