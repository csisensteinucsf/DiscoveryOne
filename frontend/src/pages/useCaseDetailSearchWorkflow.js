import { useState } from 'react'
import {
  aiSuggestionToDraft,
  fromApiSearch,
  normalizeSearchDraftFields,
  serverCreateSearch,
  serverDeleteSearch,
  serverUpdateSearch,
} from './caseDetailPersistence.js'
import { nextSearchNumber, saveSearches, uuid } from './caseDetailUtils.js'
import { isConsentComplete } from './custodianStatusCatalog.js'

export function useCaseDetailSearchWorkflow({
  apiBase,
  caseId,
  caseData,
  custodians,
  holds,
  searches,
  setSearches,
  isRequestor,
  canUseSearchAi,
  showToast,
  confirmDialog,
  setBlockedConsent,
}) {
  const [showSearchModal, setShowSearchModal] = useState(false)
  const [showSearchAiModal, setShowSearchAiModal] = useState(false)
  const [editingSearch, setEditingSearch] = useState(null)

  async function updateSearchStatus(s, field, value) {
    if (isRequestor) return
    const fieldName = `status_${field}`
    const requiresConsent = (field === 'export' || field === 'delivery') && value === 'performed'
    if (requiresConsent) {
      const assignedIds = (s.custodianIds ?? s.custodian_ids ?? []).map(Number)
      if (assignedIds.length) {
        const pendingConsent = custodians.filter(c => {
          if (!assignedIds.includes(Number(c.id))) return false
          const consent = String(c.consent_status || '').toLowerCase()
          return !isConsentComplete(consent)
        })
        if (pendingConsent.length) {
          setBlockedConsent({
            searchName: s.name,
            field,
            custodians: pendingConsent.map(c => ({
              id: c.id,
              name: c.name,
              email: c.email,
              consent: c.consent_status || 'not sent',
            })),
          })
          return
        }
      }
    }
    setSearches(prev => {
      const next = prev.map(x =>
        x.id === s.id
          ? {
              ...x,
              [fieldName]: value,
              status: { ...(x.status || {}), [field]: value },
              export_without_consent: field === 'export' && value !== 'performed' ? false : !!x.export_without_consent,
            }
          : x
      )
      saveSearches(caseId, next)
      return next
    })
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/searches/${s.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ [fieldName]: value }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const norm = fromApiSearch(data)
      setSearches(prev => {
        const next = prev.map(x => (x.id === s.id ? norm : x))
        saveSearches(caseId, next)
        return next
      })
    } catch (err) {
      console.error('status update failed', err)
    }
  }

  function openSearchAiBuilder() {
    if (!canUseSearchAi) return
    setShowSearchAiModal(true)
  }

  function suggestedSearchName(existing = searches) {
    const n = nextSearchNumber(caseData?.name, existing)
    return caseData?.name ? `${caseData.name}-Search ${n}` : `Search ${n}`
  }

  function applyAiSearchSuggestion(suggestion) {
    if (!suggestion) return
    const draft = aiSuggestionToDraft(suggestion)
    setShowSearchAiModal(false)
    setEditingSearch({ ...draft, name: (draft.name || '').trim() || suggestedSearchName() })
    setShowSearchModal(true)
  }

  async function createSearchesFromAiSuggestions(suggestions) {
    if (isRequestor || !caseId) return
    const rows = Array.isArray(suggestions) ? suggestions.filter(Boolean) : []
    if (!rows.length) {
      showToast('No AI suggestions to create.', { variant: 'info' })
      return
    }
    let next = [...searches]
    let createdCount = 0
    let failedCount = 0
    let skippedNoCustodianCount = 0
    for (const row of rows) {
      const draft = aiSuggestionToDraft(row)
      const assignedIds = (draft.custodianIds || []).map(Number).filter(Number.isFinite)
      if (!assignedIds.length) {
        skippedNoCustodianCount += 1
        continue
      }
      try {
        const created = await serverCreateSearch(caseId, draft)
        if (created && created.id) {
          next.push(created)
        } else {
          next.push({ ...draft, id: uuid() })
        }
        createdCount += 1
      } catch {
        failedCount += 1
      }
    }
    if (createdCount > 0) {
      setSearches(next)
      saveSearches(caseId, next)
      setShowSearchAiModal(false)
    }
    if (createdCount > 0) {
      showToast(`Created ${createdCount} AI search suggestion${createdCount === 1 ? '' : 's'}.`, { variant: 'success' })
    }
    if (skippedNoCustodianCount > 0) {
      showToast(`${skippedNoCustodianCount} AI suggestion${skippedNoCustodianCount === 1 ? '' : 's'} had no custodian assignment and was skipped. Review before creating.`, { variant: 'warn' })
    }
    if (failedCount > 0) {
      showToast(`${failedCount} AI suggestion${failedCount === 1 ? '' : 's'} could not be created.`, { variant: 'warn' })
    }
  }

  function openCreateSearch() {
    if (isRequestor) return
    setEditingSearch({
      id: null,
      name: suggestedSearchName(),
      keywords: '',
      senders: '',
      recipients: '',
      dateFrom: '',
      dateTo: '',
      additional: '',
      searchOverview: '',
      purviewKql: '',
      custodianIds: [],
      holdIds: [],
      status: { search: 'not performed', export: 'not performed', delivery: 'not performed' },
    })
    setShowSearchModal(true)
  }

  function openEditSearch(s) {
    const cloned = JSON.parse(JSON.stringify(s))
    setEditingSearch({ ...cloned, ...normalizeSearchDraftFields(cloned) })
    setShowSearchModal(true)
  }

  async function saveSearchDraft(draft) {
    let next = [...searches]
    draft = { ...draft, ...normalizeSearchDraftFields(draft) }
    if (!draft.id) {
      const n = nextSearchNumber(caseData?.name, next)
      draft.id = uuid()
      if (!(draft.name || '').trim()) {
        draft.name = `${caseData?.name}-Search ${n}`
      }
      const created = await serverCreateSearch(caseId, draft)
      if (created && created.id) draft = created
      next.push(draft)
    } else {
      const updated = await serverUpdateSearch(caseId, draft.id, draft)
      if (updated && updated.id) draft = updated
      next = next.map(x => x.id === draft.id ? draft : x)
    }
    setSearches(next)
    saveSearches(caseId, next)
    setShowSearchModal(false)
    setEditingSearch(null)
  }

  async function removeSearch(id) {
    if (isRequestor) return
    const ok = await confirmDialog({
      title: 'Remove search',
      description: 'Remove this search request?',
      confirmLabel: 'Remove search',
      destructive: true,
    })
    if (!ok) return
    try {
      await serverDeleteSearch(caseId, id)
      const next = searches.filter(s => s.id !== id)
      setSearches(next)
      saveSearches(caseId, next)
      showToast('Search removed.', { variant: 'info' })
    } catch (err) {
      showToast(err?.message || 'Failed to remove search.', { variant: 'error' })
    }
  }

  async function copySearch(search) {
    if (isRequestor) return
    try {
      const caseName = caseData?.name || 'Case'
      const number = nextSearchNumber(caseName, searches)
      const assignedIds = (search.custodianIds ?? search.custodian_ids ?? []).map(Number)
      const normalized = normalizeSearchDraftFields(search)
      const draft = {
        id: null,
        name: `${caseName}-Search ${number}`,
        keywords: search.keywords || '',
        additional: normalized.additional,
        searchOverview: normalized.searchOverview,
        purviewKql: normalized.purviewKql,
        senders: search.senders || '',
        recipients: search.recipients || '',
        dateFrom: search.dateFrom || search.date_from || '',
        dateTo: search.dateTo || search.date_to || '',
        custodianIds: assignedIds,
        status_search: 'not performed',
        status_export: 'not performed',
        status_delivery: 'not performed',
        status: { search: 'not performed', export: 'not performed', delivery: 'not performed' },
      }
      let entry = draft
      const created = await serverCreateSearch(caseId, draft)
      if (created && created.id) {
        entry = created
      } else {
        entry = { ...draft, id: uuid() }
      }
      const next = [...searches, entry]
      setSearches(next)
      saveSearches(caseId, next)
      showToast('Search copied.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Failed to copy search.', { variant: 'error' })
    }
  }

  return {
    showSearchModal,
    setShowSearchModal,
    showSearchAiModal,
    setShowSearchAiModal,
    editingSearch,
    setEditingSearch,
    updateSearchStatus,
    openSearchAiBuilder,
    suggestedSearchName,
    applyAiSearchSuggestion,
    createSearchesFromAiSuggestions,
    openCreateSearch,
    openEditSearch,
    saveSearchDraft,
    removeSearch,
    copySearch,
  }
}
