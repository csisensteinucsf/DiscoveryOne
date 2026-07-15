import { useState } from 'react'
import {
  normalizeSearchDraftFields,
  serverPushSearchToProvider,
} from './caseDetailPersistence.js'
import { saveSearches } from './caseDetailUtils.js'
import {
  normalizeSearchExportProvider,
  searchExportIsAutomated,
  searchExportProviderLabel,
  searchExportQueryLabel,
} from './searchExportProviderCatalog.js'

const initialSearchExportModal = {
  open: false,
  busy: false,
  searchName: '',
  message: '',
  error: null,
  result: null,
}

export function useSearchExportPush({
  caseId,
  isRequestor,
  provider,
  providerLabel,
  setSearches,
  showToast,
}) {
  const normalizedProvider = normalizeSearchExportProvider(provider)
  const displayName = providerLabel || searchExportProviderLabel(normalizedProvider)
  const queryLabel = searchExportQueryLabel(normalizedProvider)
  const [searchExportModal, setSearchExportModal] = useState(initialSearchExportModal)

  function closeSearchExportModal() {
    if (searchExportModal.busy) return
    setSearchExportModal(initialSearchExportModal)
  }

  async function pushSearchToProvider(search) {
    if (isRequestor || !caseId || !search) return
    if (!searchExportIsAutomated(normalizedProvider)) {
      showToast('Configure a search export provider in System > Integrations before using automated export.', { variant: 'warn' })
      return
    }
    const searchId = Number(search?.id)
    if (!Number.isFinite(searchId)) {
      showToast(`Save this search before pushing it to ${displayName}.`, { variant: 'warn' })
      return
    }
    const parsed = normalizeSearchDraftFields(search)
    const providerQuery = String(parsed?.providerQuery || '').trim()
    if (!providerQuery) {
      showToast(`${queryLabel} is required before pushing this search.`, { variant: 'warn' })
      return
    }
    const initialName = String(search?.name || `Search ${searchId}`).trim() || `Search ${searchId}`
    setSearchExportModal({
      open: true,
      busy: true,
      searchName: initialName,
      message: `Pushing search to ${displayName}...`,
      error: null,
      result: null,
    })
    try {
      const data = await serverPushSearchToProvider(caseId, searchId, {
        query: providerQuery,
        display_name: initialName,
        description: String(parsed?.searchOverview || '').trim(),
      })
      const caseWasCreated = String(data?.provider_case_status || data?.purview_case_status || '').toLowerCase() === 'created'
      const providerSearchId = data?.provider_search_id || data?.purview_search_id || null
      const providerSearchName = data?.provider_search_name || data?.purview_search_name || initialName
      const providerCaseId = data?.provider_case_id || data?.purview_case_id || null
      setSearchExportModal({
        open: true,
        busy: false,
        searchName: String(data?.search_name || initialName),
        message: caseWasCreated
          ? `${displayName} case was created and the search was submitted.`
          : `Search submitted to ${displayName}.`,
        error: null,
        result: data || null,
      })
      setSearches(previous => {
        const next = previous.map(item => Number(item?.id) === searchId ? {
          ...item,
          pushed_to_provider: true,
          provider: data?.provider || normalizedProvider,
          provider_search_id: providerSearchId || item?.provider_search_id || null,
          provider_search_name: providerSearchName || item?.provider_search_name || initialName,
          provider_case_id: providerCaseId || item?.provider_case_id || null,
          ...(normalizedProvider === 'purview' ? {
            pushed_to_purview: true,
            purview_search_id: providerSearchId || item?.purview_search_id || null,
            purview_search_name: providerSearchName || item?.purview_search_name || initialName,
            purview_case_id: providerCaseId || item?.purview_case_id || null,
          } : {}),
        } : item)
        saveSearches(caseId, next)
        return next
      })
      showToast(
        caseWasCreated
          ? `${displayName} case created and search pushed.`
          : `Search pushed to ${displayName}.`,
        { variant: 'success' },
      )
    } catch (error) {
      const message = error?.message || `Unable to push search to ${displayName}.`
      setSearchExportModal({
        open: true,
        busy: false,
        searchName: initialName,
        message: `Push to ${displayName} failed.`,
        error: message,
        result: null,
      })
      showToast(message, { variant: 'error' })
    }
  }

  return {
    searchExportModal,
    closeSearchExportModal,
    pushSearchToProvider,
  }
}
