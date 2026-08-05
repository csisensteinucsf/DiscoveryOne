import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import { useConfirm } from '../components/ConfirmProvider.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import { fetchSystemSettings } from '../lib/systemSettingsClient.js'
import { normalizeCaseNamingMode } from './setupCatalog.js'
import { esignProviderLabel, esignRequestLabel, normalizeEsignProvider } from './esignProviderCatalog.js'
import { preservationProviderLabel } from './preservationCatalog.js'
import {
  REQUEST_TICKET_CATEGORIES,
  TECH_CATEGORY_HOLD_KEYS,
  resolveTechTicketCategories,
  techCategoryHoldKeysFromCategories,
  ticketCategoriesFromWorkflows,
  ticketCategoryLookupFromCategories,
} from './ticketWorkflowCatalog.js'
import {
  apiBase,
  ADMIN_USERNAME,
  holdMetaFromPreservationSources,
  caseCache,
  proofCache,
  displayUserName,
  formatDate,
  formatDateTime,
  holdDetailStateLabel,
  holdDetailStateStyle,
  formatActionLabel,
  employmentBadges,
  formatFileSize,
  nextSearchNumber,
  uuid,
} from './caseDetailUtils.js'
import {
  normalizeSearchDraftFields,
  tryFetchJSON
} from './caseDetailPersistence.js'
import CaseDetailTabNav from './CaseDetailTabNav.jsx'
import CaseDetailHeader from './CaseDetailHeader.jsx'
import CaseDetailSlaTab from './CaseDetailSlaTab.jsx'
import CaseDetailNotesTab from './CaseDetailNotesTab.jsx'
import CaseDetailDocumentationTab from './CaseDetailDocumentationTab.jsx'
import CaseDetailSearchesTab from './CaseDetailSearchesTab.jsx'
import CaseDetailNamedHoldsTab from './CaseDetailNamedHoldsTab.jsx'
import CaseDetailPreservationDetailTab from './CaseDetailPreservationDetailTab.jsx'
import CaseDetailCustodiansTab from './CaseDetailCustodiansTab.jsx'
import CaseDetailTicketsTab from './CaseDetailTicketsTab.jsx'
import CaseDetailTicketNotesTab from './CaseDetailTicketNotesTab.jsx'
import CaseDetailCaseSummaryModal from './CaseDetailCaseSummaryModal.jsx'
import { CaseDetailAddDocModal, CaseDetailCloseCaseModal } from './CaseDetailWorkflowModals.jsx'
import CaseDetailTicketWorkflowModals from './CaseDetailTicketWorkflowModals.jsx'
import CaseDetailNtpModals from './CaseDetailNtpModals.jsx'
import CaseDetailPreservationProviderModal from './CaseDetailPreservationProviderModal.jsx'
import CaseDetailConsentModal from './CaseDetailConsentModal.jsx'
import CaseDetailEditCustodianModal from './CaseDetailEditCustodianModal.jsx'
import CaseDetailStatusReasonModal from './CaseDetailStatusReasonModal.jsx'
import CaseDetailSearchStatusModals from './CaseDetailSearchStatusModals.jsx'
import CaseDetailCustodianEntryModals from './CaseDetailCustodianEntryModals.jsx'
import CaseDetailEditCaseModal from './CaseDetailEditCaseModal.jsx'
import CaseDetailSearchModals from './CaseDetailSearchModals.jsx'
import { useCaseDetailDerivedState } from './caseDetailDerivedState.js'
import { useCaseDetailDocuments } from './caseDetailDocuments.js'
import { exportCustodiansCsv } from './caseDetailExport.js'
import { useSearchExportPush } from './useSearchExportPush.js'
import {
  normalizeSearchExportProvider,
  searchExportProviderLabel,
  searchExportQueryLabel,
} from './searchExportProviderCatalog.js'
import { useCaseDetailPreservationProvider } from './useCaseDetailPreservationProvider.js'
import { useCaseDetailSearchWorkflow } from './useCaseDetailSearchWorkflow.js'
import { useCaseDetailCaseSummary } from './useCaseDetailCaseSummary.js'
import { useCaseDetailSla } from './useCaseDetailSla.js'
import { useCaseDetailConsents } from './useCaseDetailConsents.js'
import { useCaseDetailHoldsDetail } from './useCaseDetailHoldsDetail.js'
import { useCaseDetailTicketWorkflow } from './useCaseDetailTicketWorkflow.js'
import { useCaseDetailBootstrap } from './useCaseDetailBootstrap.js'
import { useCaseDetailCustodianImport } from './useCaseDetailCustodianImport.js'
import { useCaseDetailCustodianLookups } from './useCaseDetailCustodianLookups.js'
import { useCaseDetailCustodianTable } from './useCaseDetailCustodianTable.js'
import { useCaseDetailRemoveCustodian } from './useCaseDetailRemoveCustodian.js'
import { useCaseDetailEditCustodian } from './useCaseDetailEditCustodian.js'
import { useCaseDetailNoteCounts } from './useCaseDetailNoteCounts.js'
import { useCaseDetailNtpWorkflow } from './useCaseDetailNtpWorkflow.js'
import { useCaseDetailCaseActions } from './useCaseDetailCaseActions.js'
import { useCaseDetailCustodianStatusActions } from './useCaseDetailCustodianStatusActions.js'
import { useCaseDetailTechHoldActions } from './useCaseDetailTechHoldActions.js'
import { useCaseDetailTechHoldBaseline } from './useCaseDetailTechHoldBaseline.js'
import { copyEntryCustodianEmails } from './caseDetailTicketEmails.js'
// ---------- Main Page ----------
export default function CaseDetail() {
  const { caseId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const { showToast } = useToast()
  const confirmDialog = useConfirm()
  const cachedCase = caseCache.get(caseId)
  const cachedProofs = proofCache.get(caseId)
  const reloadCustodiansRef = useRef(null)
  const [activeTab, setActiveTab] = useState('custodians')
  const [caseData, setCaseData] = useState(() => cachedCase || null)
  const [evidenceTrackingCount, setEvidenceTrackingCount] = useState(0)
  const [finalReportCount, setFinalReportCount] = useState(0)
  const [custodians, setCustodians] = useState([])
  const {
    proofs,
    proofsLoaded,
    docsLoading,
    docsError,
    showAddDocModal,
    docForm,
    docFile,
    setDocFile,
    docUploading,
    docUploadError,
    deletingProofId,
    setProofRows,
    loadProofs,
    openDocModal,
    closeDocModal,
    handleDocHoldSelect,
    handleDocCustodianSelect,
    handleDocFieldChange,
    submitConsentDocument,
    handleDeleteProof,
    updateProofCountsOnCase,
  } = useCaseDetailDocuments({
    apiBase,
    caseId,
    cachedProofs,
    custodians,
    confirmDialog,
    showToast,
    reloadCustodiansRef,
    setCaseData,
  })
  const [holdsDirty, setHoldsDirty] = useState(false)
  const [techHoldsApplying, setTechHoldsApplying] = useState(false)
  const [targetHoldIds, setTargetHoldIds] = useState([])
  const [showCustodianModal, setShowCustodianModal] = useState(false)
  const [custodianModalMode, setCustodianModalMode] = useState('add')
  const initialTabSet = useRef(false)
  const [loading, setLoading] = useState(() => !cachedCase)
  const [error, setError] = useState(null)
  const {
    importWorking,
    setImportWorking,
    importDone,
    importTotal,
    addCustodiansWorking,
    setAddCustodiansWorking,
    addCustodiansWorkingRef,
    submitCustodianBatch,
    submitCustodianBulkUpdate,
  } = useCaseDetailCustodianImport({
    apiBase,
    caseId,
    custodians,
    targetHoldIds,
  })
  const documentationBadgeCount = useMemo(() => {
    const consentCount = Number(caseData?.consent_envelope_count || 0)
    const proofCount = Number(caseData?.consent_proof_count || 0)
    const safeConsents = Number.isFinite(consentCount) ? Math.max(0, consentCount) : 0
    const safeProofs = Number.isFinite(proofCount) ? Math.max(0, proofCount) : 0
    const nonDocusignProofs = proofsLoaded
      ? (proofs || []).filter(proof => proof?.source !== 'docusign').length
      : safeProofs
    return safeConsents + Math.max(0, nonDocusignProofs)
  }, [caseData?.consent_envelope_count, caseData?.consent_proof_count, proofs, proofsLoaded])
  const [showCloseCaseModal, setShowCloseCaseModal] = useState(false)
  const [closeCaseNote, setCloseCaseNote] = useState('')
  const [closeCaseBusy, setCloseCaseBusy] = useState(false)
  const { user, authConfig } = useAuth()
  const employeeIdLabel = authConfig?.institution?.employee_id_label || 'Employee ID'
  const internalCounselLabel = authConfig?.institution?.internal_counsel_label || 'Internal Counsel'
  const lookupInputPlaceholder = `Enter full name, email address or ${employeeIdLabel} to begin person lookup`
  const [personLookupEnabled, setPersonLookupEnabled] = useState(false)
  const [preservationAutomationEnabled, setPreservationAutomationEnabled] = useState(false)
  const [preservationProvider, setPreservationProvider] = useState('none')
  const preservationProviderName = preservationProviderLabel(preservationProvider)
  const [searchExportProvider, setSearchExportProvider] = useState('none')
  const searchExportProviderName = searchExportProviderLabel(searchExportProvider)
  const searchQueryLabel = searchExportQueryLabel(searchExportProvider)
  const [configuredHoldMeta, setConfiguredHoldMeta] = useState(() => holdMetaFromPreservationSources(null))
  const [caseNamingMode, setCaseNamingMode] = useState('legal_case_name')
  const [defaultClosureNagDays, setDefaultClosureNagDays] = useState(180)
  const [esignProvider, setEsignProvider] = useState('none')
  const [ticketCategories, setTicketCategories] = useState(() => REQUEST_TICKET_CATEGORIES)
  const userRole = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const isSysAdmin = userRole === 'sys_admin'
  const isRequestor = userRole === 'requestor'
  const isTech = userRole === 'tech'
  const isReadOnly = isRequestor || isTech
  const canUseSearchAi = !isRequestor && !isTech && (userRole === 'analyst' || userRole === 'sys_admin')
  const canEditReminders = !isTech
  const techTicketCategories = useMemo(
    () => resolveTechTicketCategories(user?.requestor_group, ticketCategories),
    [user?.requestor_group, ticketCategories]
  )
  const techTicketCategorySet = useMemo(
    () => new Set(techTicketCategories),
    [techTicketCategories]
  )
  const visibleTicketCategories = useMemo(() => {
    if (!isTech) return ticketCategories
    return ticketCategories.filter(category => techTicketCategorySet.has(category.key))
  }, [isTech, techTicketCategorySet, ticketCategories])
  const requestTicketCategoryLookup = useMemo(
    () => ticketCategoryLookupFromCategories(ticketCategories),
    [ticketCategories]
  )
  const {
    noteCount,
    setNoteCount,
    requestorNoteCount,
    setRequestorNoteCount,
  } = useCaseDetailNoteCounts({
    apiBase,
    caseId,
    cachedCase,
    caseData,
    setCaseData,
    isTech,
    isRequestor,
    setProofRows,
    updateProofCountsOnCase,
  })
  useEffect(() => {
    let alive = true
    fetchSystemSettings(apiBase)
      .then(data => {
        if (!alive) return
        const enabled = !!data?.integrations?.enabled?.person_lookup
        const provider = String(data?.integrations?.providers?.person_lookup_provider || 'none').trim().toLowerCase()
        const configuredPreservationProvider = String(data?.integrations?.providers?.preservation_provider || 'none').trim().toLowerCase()
        const preservationProvider = configuredPreservationProvider !== 'none'
          ? configuredPreservationProvider
          : (data?.integrations?.enabled?.purview ? 'purview' : 'none')
        const configuredSearchExportProvider = normalizeSearchExportProvider(
          data?.integrations?.providers?.search_export_provider || preservationProvider
        )
        setPreservationProvider(preservationProvider)
        setSearchExportProvider(configuredSearchExportProvider)
        setPreservationAutomationEnabled(preservationProvider !== 'none' || !!data?.integrations?.enabled?.purview)
        setPersonLookupEnabled(enabled && provider !== 'none')
        setConfiguredHoldMeta(holdMetaFromPreservationSources(data?.preservation_sources))
        setTicketCategories(ticketCategoriesFromWorkflows(data?.ticket_workflows))
        setCaseNamingMode(normalizeCaseNamingMode(data?.case_naming?.mode))
        setDefaultClosureNagDays(Number(data?.case_closure?.default_nag_days) || 180)
        setEsignProvider(normalizeEsignProvider(data?.integrations?.providers?.esign_provider))
      })
      .catch(() => {
        if (alive) {
          setPersonLookupEnabled(false)
          setPreservationAutomationEnabled(false)
          setPreservationProvider('none')
          setSearchExportProvider('none')
          setTicketCategories(REQUEST_TICKET_CATEGORIES)
          setCaseNamingMode(normalizeCaseNamingMode(null))
          setDefaultClosureNagDays(180)
          setEsignProvider('none')
        }
      })
    return () => { alive = false }
  }, [])
  const techHoldKeySet = useMemo(() => {
    if (!isTech) return new Set()
    const keys = new Set()
    techTicketCategorySet.forEach(category => {
      const holdKey = (techCategoryHoldKeysFromCategories(ticketCategories)[category] || TECH_CATEGORY_HOLD_KEYS[category])
      if (holdKey) keys.add(holdKey)
    })
    return keys
  }, [isTech, techTicketCategorySet, ticketCategories])
  const holdMetaForView = useMemo(() => {
    if (!isTech) return configuredHoldMeta
    return configuredHoldMeta.filter(item => techHoldKeySet.has(item.key))
  }, [configuredHoldMeta, isTech, techHoldKeySet])
  const holdMetaByKey = useMemo(() => new Map(holdMetaForView.map(item => [item.key, item])), [holdMetaForView])
  const holdKeysForTech = useMemo(
    () => holdMetaForView.map(item => item.key),
    [holdMetaForView]
  )
  const esignDisplayName = useMemo(() => esignProviderLabel(esignProvider), [esignProvider])
  const esignEnvelopeName = useMemo(() => esignRequestLabel(esignProvider), [esignProvider])
  const { buildHoldState, setHoldBaseline, savedHoldMap, holdsBaselineReady } = useCaseDetailTechHoldBaseline({
    custodians,
    isTech,
    holdKeysForTech,
    setHoldsDirty,
    holdsDirty,
  })

  useEffect(() => {    if (initialTabSet.current) return
    if (isTech) {
      setActiveTab('requests')
    }
    initialTabSet.current = true
  }, [isTech])
  useEffect(() => {
    const allowedTabs = new Set(isTech
      ? ['custodians', 'holds', 'preservation', 'requests']
      : ['custodians', 'holds', 'preservation', 'searches', 'requests', 'documentation', 'sla', 'notes'])
    if (!allowedTabs.has(activeTab)) setActiveTab(isTech ? 'requests' : 'custodians')
  }, [activeTab, isTech])
  useEffect(() => {
    if (!isRequestor) return
    try {
      const params = new URLSearchParams(location.search || '')
      if ((params.get('action') || '').toLowerCase() === 'request_close') {
        setShowCloseCaseModal(true)
      }
    } catch {
      // ignore malformed query strings
    }
  }, [isRequestor, location.search])

  useEffect(() => {
    if (isReadOnly) return
    try {
      const params = new URLSearchParams(location.search || '')
      if ((params.get('action') || '').toLowerCase() !== 'custodians') return
      const mode = (params.get('mode') || 'add').toLowerCase() === 'import' ? 'import' : 'add'
      const holdIds = (params.get('hold_ids') || params.get('hold_id') || '')
        .split(',')
        .map(Number)
        .filter(value => Number.isFinite(value) && value > 0)
      setTargetHoldIds([...new Set(holdIds)])
      setCustodianModalMode(mode)
      setActiveTab('custodians')
      setShowCustodianModal(true)
      navigate(location.pathname, { replace: true })
    } catch {
      // Ignore malformed query strings.
    }
  }, [isReadOnly, location.pathname, location.search, navigate])

  useEffect(() => {
    if (!showCustodianModal) setTargetHoldIds([])
  }, [showCustodianModal])
  const canManageDocs = !isReadOnly
  const {
    showCaseSummaryModal,
    setShowCaseSummaryModal,
    caseSummary,
    caseSummaryData,
    caseSummarySections,
    caseSummaryAi,
    caseSummaryAiAttention,
    caseSummaryAiActions,
    caseSummaryAiHighlights,
    loadCaseSummary,
    openCaseSummary,
    emailCaseSummaryToSelf,
  } = useCaseDetailCaseSummary({ apiBase, caseId, showToast })
  const {
    slaStatus,
    slaLoading,
    slaError,
    loadSlaStatus,
  } = useCaseDetailSla({ apiBase, caseId })
  const {
    holdsDetail,
    holdsDetailRows,
    holdsDetailTotals,
    loadHoldsDetail,
  } = useCaseDetailHoldsDetail({ apiBase, caseId })
  const reloadCustodians = useCallback(async () => {
    if (!caseId) return
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/custodians`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text() || 'Unable to load custodians')
      const list = await res.json()
      const next = Array.isArray(list) ? list : []
      setCustodians(next)
      setHoldBaseline(next)
    } catch (err) {
      console.error('Unable to refresh custodians after consent proof change', err)
    }
  }, [apiBase, caseId, setHoldBaseline])
  reloadCustodiansRef.current = reloadCustodians
  const {
    ntpTemplates,
    ntpHolds,
    ntpHoldsLoading,
    loadNtpHolds,
    ntpHoldId,
    setNtpHoldId,
    ntpCustodians,
    ntpReminders,
    ntpRemindersLoading,
    ntpButtonDisabled,
    showSendNtpModal,
    closeSendNtp,
    previewNtpNotice,
    ntpPreview,
    setNtpPreview,
    sendingNtp,
    sendNtpNotices,
    selectedTemplateId,
    setSelectedTemplateId,
    ntpSelection,
    selectedReminderTemplateId,
    setSelectedReminderTemplateId,
    setReminderIntervalDays,
    setReminderDurationDays,
    reminderIntervalDays,
    reminderDurationDays,
    openNtpHistoryModal,
    lastNtpSend,
    copyPreviousNtpData,
    ntpVariables,
    setNtpVariables,
    ntpReasonTouchedRef,
    ntpOutsideCounselHistory,
    ntpSearch,
    setNtpSearch,
    toggleNtpSelection,
    ntpAutoNaReason,
    ntpStatusLabel,
    showNtpHistoryModal,
    setShowNtpHistoryModal,
    ntpHistory,
    ntpHistoryExporting,
    ntpHistoryEmailing,
    exportNtpHistoryCsv,
    emailNtpHistoryReport,
    loadNtpHistory,
    showReminderListModal,
    setShowReminderListModal,
    reactivateEligibleCancelledNtpReminders,
    reactivatingNtpRemindersBulk,
    reactivatingNtpReminders,
    openReminderEditor,
    reactivateCancelledNtpReminders,
    ntpBlockedModal,
    setNtpBlockedModal,
    reminderEditor,
    closeReminderEditor,
    saveReminderEditor,
    setReminderEditor,
    openReminderListModal,
    openSendNtp,
    pickNextReminder,
  } = useCaseDetailNtpWorkflow({
    apiBase,
    caseId,
    caseData,
    custodians,
    setCustodians,
    isRequestor,
    isTech,
    showToast,
  })
  const { updateCase, updateCustodianLocal, patchCustodian } = useCaseDetailCaseActions({
    apiBase,
    caseId,
    caseData,
    setCaseData,
    setCustodians,
    showToast,
    confirmDialog,
  })

  useEffect(() => {
  // requestors may view all tabs; no forced redirection
}, [isRequestor, activeTab])
  // notes badge count
  // modals
  const [showEdit, setShowEdit] = useState(false)
  const [detailsSearch, setDetailsSearch] = useState(null)
  const detailsSearchParsed = useMemo(() => normalizeSearchDraftFields(detailsSearch), [detailsSearch])
  const [blockedConsent, setBlockedConsent] = useState(null)
  // bulk apply
  const [bulk, setBulk] = useState({ holds:false, ntp:false, consent:false })
  // people
  const [users, setUsers] = useState([])
  const analystOptions = useMemo(
    () => users.filter(u => (u?.username || '').toLowerCase() !== ADMIN_USERNAME),
    [users]
  )
  const [requestorOptions, setRequestorOptions] = useState([])
  // searches
  const [searches, setSearches] = useState([])
  const {
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
  } = useCaseDetailSearchWorkflow({
    apiBase,
    caseId,
    caseData,
    custodians,
    holds: ntpHolds,
    searches,
    setSearches,
    isRequestor,
    canUseSearchAi,
    showToast,
    confirmDialog,
    setBlockedConsent,
  })
  const {
    searchExportModal,
    closeSearchExportModal,
    pushSearchToProvider,
  } = useSearchExportPush({
    caseId,
    isRequestor,
    provider: searchExportProvider,
    providerLabel: searchExportProviderName,
    setSearches,
    showToast,
  })
  const {
    showPurviewModal,
    setShowPurviewModal,
    preservationHolds,
    preservationHoldId,
    setPreservationHoldId,
    preservationCustodians,
    purviewStatus,
    purviewCreating,
    purviewHoldBusy,
    purviewExportCheckBusy,
    purviewHoldResults,
    purviewHoldSelection,
    setPurviewHoldSelection,
    purviewHoldOptions,
    setPurviewHoldOptions,
    purviewHoldMap,
    purviewSelectedSources,
    handleCreatePurviewCase,
    checkPurviewExports,
    applyPurviewHolds,
    togglePurviewHoldSelection,
    selectAllPurviewHoldTargets,
  } = useCaseDetailPreservationProvider({
    apiBase,
    caseId,
    caseData,
    custodians,
    setCustodians,
    setSearches,
    showToast,
    loading,
    providerName: preservationProviderName,
  })
  const {
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
  } = useCaseDetailCustodianLookups({
    custodians,
    searches,
    holdMetaForView,
    holdMetaByKey,
  })
  const {
    requestEntries,
    requestsDirty,
    requestsSaving,
    requestsFilledCount,
    matchedEmailWorkflowWarning,
    usedCustodianKeysByCategory,
    externalTicketBusy,
    externalTicketStatuses,
    externalTicketStatusLoading,
    externalTicketEmailBusy,
    externalTicketEmailSent,
    ticketSelfHealBusy,
    showBulkRequestModal,
    bulkCategory,
    bulkHoldId,
    setBulkHoldId,
    activeTicketHolds,
    bulkSelection,
    bulkSearch,
    setBulkSearch,
    setBulkSelection,
    accessLogInfoEntryId,
    setAccessLogInfoEntryId,
    accessLogInfoEntry,
    workflowUsesAccessLogDetails,
    addRequestEntry,
    openBulkRequestModal,
    bulkCustodianDisabledReason,
    toggleBulkCustodian,
    submitBulkRequests,
    closeBulkModal,
    updateRequestEntry,
    updateAccessLogTimeWindow,
    addAccessLogTimeWindow,
    removeAccessLogTimeWindow,
    closeAccessLogInfoModal,
    saveAccessLogInfoModal,
    removeRequestEntry,
    createExternalTicket,
    sendCustodianDetailsToAssignee,
    handleRequestEntryCustodianChange,
    commitRequestTicketSave,
    runTicketSelfHeal,
  } = useCaseDetailTicketWorkflow({
    apiBase,
    caseId,
    caseData,
    setCaseData,
    updateCase,
    isRequestor,
    isTech,
    user,
    userRole,
    employeeIdLabel,
    custodians,
    namedHolds: ntpHolds,
    custodianOptionLookup,
    techTicketCategorySet,
    ticketCategories,
    requestTicketCategoryLookup,
    entryHasUnmatchedSnowCustodian,
    confirmDialog,
    showToast,
  })
  const custodianTable = useCaseDetailCustodianTable({
    custodians,
    searches,
    requestEntries,
    isTech,
    techTicketCategorySet,
    normalizeEmail,
    hasAnyHold,
    holdMetaForView,
    holdState,
  })
  const { techCustodianKeys } = custodianTable
  const {
    showConsentModal,
    setShowConsentModal,
    consentHolds,
    consentHoldId,
    setConsentHoldId,
    consentCustodians,
    consentSelection,
    setConsentSelection,
    consentFormInline,
    setConsentFormInline,
    consentSendBusy,
    consentSearch,
    setConsentSearch,
    consentAutoSearchId,
    setConsentAutoSearchId,
    consents,
    consentsLoading,
    consentsError,
    consentActionBusy,
    consentDownloadBusyId,
    loadConsents,
    consentReceivedIds,
    consentReceivedEmails,
    consentRequestTracker,
    consentAutoSearches,
    filteredConsentCustodians,
    consentSelectedRecipients,
    addAllAvailableConsents,
    autoAddConsentFromSearch,
    sendSelectedConsents,
    resendConsent,
    downloadConsent,
    voidConsent,
  } = useCaseDetailConsents({
    apiBase,
    caseId,
    caseData,
    custodians,
    searches,
    showToast,
    confirmDialog,
    loadSlaStatus,
    setCaseData,
    esignDisplayName,
  })
  useCaseDetailBootstrap({
    apiBase,
    caseId,
    activeTab,
    isTech,
    isRequestor,
    setLoading,
    setError,
    setCaseData,
    setCustodians,
    setHoldBaseline,
    setUsers,
    setRequestorOptions,
    setSearches,
    loadHoldsDetail,
    loadProofs,
    loadConsents,
    loadSlaStatus,
  })
  const {
    removeCustodianModal,
    setRemoveCustodianModal,
    openRemoveCustodian,
    removeCustodian,
  } = useCaseDetailRemoveCustodian({
    apiBase,
    caseId,
    isReadOnly,
    setCustodians,
    setSearches,
    showToast,
  })
  function onExportCustodians() {
    exportCustodiansCsv({ caseData, custodians, searches, holdMeta: configuredHoldMeta })
  }
  async function copyEntryCustodians(entry) {
    if (isRequestor) return
    await copyEntryCustodianEmails(entry, { custodianEmailById, showToast })
  }
  const toggleClosed = useCallback(async () => {
    if (!caseData) return
    const nextClosed = !Boolean(caseData.closed)
    if (nextClosed) {
      const readinessResponse = await fetch(`${apiBase}/cases/${caseId}/closure-readiness`, { credentials: 'include' }).catch(() => null)
      if (!readinessResponse?.ok) {
        showToast('Unable to check whether this case can be closed.', { variant: 'error' })
        return
      }
      const readiness = await readinessResponse.json()
      if (!readiness.ready) {
        const activeHolds = readiness.active_holds || []
        const preservation = readiness.preservation_blockers || []
        await confirmDialog({
          title: 'Case cannot be closed',
          description: 'Close every active Hold and release every active preservation item before making this case inactive.',
          confirmLabel: 'Understood',
          hideCancel: true,
          width: 620,
          extras: (
            <div className="alert warning" style={{ marginTop: 12 }}>
              {activeHolds.length > 0 && <><strong>Active Holds</strong><ul>{activeHolds.map(hold => <li key={hold.hold_id}>{hold.hold_name} ({hold.custodian_count} custodians)</li>)}</ul></>}
              {preservation.length > 0 && <><strong>Preservation items to release</strong><ul>{preservation.map((item, index) => <li key={`${item.hold_id || 'matter'}-${item.custodian_id}-${item.source_key}-${index}`}>{item.hold_name ? `${item.hold_name}: ` : ''}{item.custodian_name} - {item.source_label} ({item.status})</li>)}</ul></>}
            </div>
          ),
        })
        return
      }
    }
    const accepted = await confirmDialog({
      title: nextClosed ? 'Close case?' : 'Reopen case?',
      description: nextClosed ? 'This will mark the case as closed.' : 'This will mark the case as open again.',
      confirmLabel: nextClosed ? 'Close case' : 'Reopen case',
      cancelLabel: 'Cancel',
    })
    if (!accepted) return
    try {
      await updateCase({ closed: nextClosed })
    } catch (err) {
      if (!err?.cancelled) showToast(err?.message || 'Unable to update case status.', { variant: 'error' })
    }
  }, [apiBase, caseData, caseId, confirmDialog, showToast, updateCase])

  const submitCloseCaseRequest = useCallback(async () => {
    if (!caseId) return
    setCloseCaseBusy(true)
    try {
      const form = new FormData()
      form.set('request_type', 'close_case')
      form.set('data', JSON.stringify({ case_id: Number(caseId), note: closeCaseNote || '' }))
      const res = await fetch(`${apiBase}/case_requests`, {
        method: 'POST',
        credentials: 'include',
        body: form,
      })
      const payload = await res.json().catch(() => null)
      if (!res.ok) throw new Error(payload?.detail || payload?.message || 'Unable to submit closure request.')
      setShowCloseCaseModal(false)
      setCloseCaseNote('')
      showToast('Case closure request submitted.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Unable to submit closure request.', { variant: 'error' })
    } finally {
      setCloseCaseBusy(false)
    }
  }, [apiBase, caseId, closeCaseNote, showToast])
  const {
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
  } = useCaseDetailEditCustodian({
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
  })
  const {
    onToggleHold,
    onChangeNtp,
    onChangeConsent,
    statusReasonRequest,
    statusReasonBusy,
    closeStatusReasonDialog,
    submitStatusReason,
  } = useCaseDetailCustodianStatusActions({
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
  })
  const { setAllTechPendingCompleted, applyTechHoldChanges } = useCaseDetailTechHoldActions({
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
  })

  // resolve analyst name
  const useLegalCaseNameAsPrimary = caseNamingMode === 'legal_case_name'

  const analystName = useMemo(() => {
    if (!caseData) return null
    const guess = displayUserName(caseData.analyst, { firstOnly: true }) || caseData.analyst_name || null
    if (guess) return guess
    if (caseData.analyst_id && users?.length) {
      const u = users.find(u => u.id === caseData.analyst_id)
      return displayUserName(u, { firstOnly: true }) || null
    }
    return null
  }, [caseData, users])
  // compute rolled-up progress across searches for a custodian
  const {
    searchCount,
    detailValueStyle,
    ntpFieldLabelStyle,
    ntpSelectStyle,
    ntpHintStyle,
    ntpHelperTextStyle,
    ntpSectionCardStyle,
    ntpModalScrollStyle,
    filteredNtpCustodians,
    reminderSummary,
    activeReminderCustodianIds,
    reminderGroups,
    ntpHistoryEvents,
    ntpHistoryCustodianRows,
    eligibleReminderReactivationCustodianIds,
    reminderTemplateNames,
    editorPrimaryReminder,
  } = useCaseDetailDerivedState({
    searches,
    custodians: ntpCustodians,
    ntpSearch,
    ntpReminders,
    ntpHistory,
    reminderEditor,
    pickNextReminder,
  })
  const reactivateEligibleCancelledNtpRemindersForActive = useCallback(
    () => reactivateEligibleCancelledNtpReminders(eligibleReminderReactivationCustodianIds),
    [reactivateEligibleCancelledNtpReminders, eligibleReminderReactivationCustodianIds]
  )
  const saveReminderEditorForActive = useCallback(
    () => saveReminderEditor(activeReminderCustodianIds),
    [saveReminderEditor, activeReminderCustodianIds]
  )
  return (
    <div className="page" style={{ padding: 16 }}>
      {loading ? (
        <div style={{ display: 'grid', gap: 12 }}>
          <div style={{ height: 18, width: 220, borderRadius: 6, background: 'linear-gradient(90deg, #e5e7eb, #f5f5f5, #e5e7eb)', backgroundSize: '200% 100%', animation: 'pulse 1.2s ease-in-out infinite' }} />
          <div style={{ height: 140, borderRadius: 10, background: 'linear-gradient(90deg, #f3f4f6, #ffffff, #f3f4f6)', backgroundSize: '200% 100%', animation: 'pulse 1.2s ease-in-out infinite' }} />
          <div style={{ height: 280, borderRadius: 10, background: 'linear-gradient(90deg, #f3f4f6, #ffffff, #f3f4f6)', backgroundSize: '200% 100%', animation: 'pulse 1.2s ease-in-out infinite' }} />
        </div>
      ) : error ? (
        <h2>Error: {String(error)}</h2>
      ) : (
        <>
          <CaseDetailHeader
            caseData={caseData}
            isReadOnly={isReadOnly}
            isTech={isTech}
            isRequestor={isRequestor}
            analystName={analystName}
            formatDate={formatDate}
            navigate={navigate}
            setShowEdit={setShowEdit}
            onExportCustodians={onExportCustodians}
            openPreservationAutomation={() => setShowPurviewModal(true)}
            preservationAutomationEnabled={preservationAutomationEnabled}
            preservationProviderName={preservationProviderName}
            openCaseSummary={openCaseSummary}
            toggleClosed={toggleClosed}
            setShowCloseCaseModal={setShowCloseCaseModal}
            useLegalCaseNameAsPrimary={useLegalCaseNameAsPrimary}
            internalCounselLabel={internalCounselLabel}
          />
          <CaseDetailTabNav
            activeTab={activeTab}
            setActiveTab={setActiveTab}
            isTech={isTech}
            isRequestor={isRequestor}
            searchCount={searchCount}
            requestsFilledCount={requestsFilledCount}
            documentationBadgeCount={documentationBadgeCount}
            noteCount={noteCount}
            requestorNoteCount={requestorNoteCount}
          />
          {activeTab === 'custodians' && (
            <CaseDetailCustodiansTab
              custodianTable={custodianTable}
              isTech={isTech}
              isReadOnly={isReadOnly}
              isRequestor={isRequestor}
              setAllTechPendingCompleted={setAllTechPendingCompleted}
              techHoldsApplying={techHoldsApplying}
              custodians={custodians}
              applyTechHoldChanges={applyTechHoldChanges}
              holdsDirty={holdsDirty}
              navigate={navigate}
              caseId={caseId}
              bulk={bulk}
              setBulk={setBulk}
              hasAnyHold={hasAnyHold}
              holdMetaForView={holdMetaForView}
              normalizeEmail={normalizeEmail}
              custodianMatchesClaimant={custodianMatchesClaimant}
              caseData={caseData}
              employmentBadges={employmentBadges}
              techHoldKeySet={techHoldKeySet}
              holdState={holdState}
              onToggleHold={onToggleHold}
              onChangeNtp={onChangeNtp}
              onChangeConsent={onChangeConsent}
              formatDateTime={formatDateTime}
              formatDate={formatDate}
              onEditCustodian={onEditCustodian}
              openRemoveCustodian={openRemoveCustodian}
              setCustodianModalMode={setCustodianModalMode}
              setShowCustodianModal={setShowCustodianModal}
              openSendNtp={openSendNtp}
              sendingNtp={sendingNtp}
              ntpButtonDisabled={ntpButtonDisabled}
            />
          )}
          {activeTab === 'holds' && (
            <CaseDetailNamedHoldsTab
              apiBase={apiBase}
              caseId={caseId}
              custodians={custodians}
              searches={searches}
              isReadOnly={isReadOnly}
              showToast={showToast}
              requestEntries={requestEntries}
            />
          )}
          {activeTab === 'preservation' && (
            <CaseDetailPreservationDetailTab
              apiBase={apiBase}
              caseId={caseId}
              showToast={showToast}
              holdsDetail={holdsDetail}
              holdsDetailTotals={holdsDetailTotals}
              holdsDetailRows={holdsDetailRows}
              formatDateTime={formatDateTime}
              loadHoldsDetail={loadHoldsDetail}
              isTech={isTech}
              techHoldKeySet={techHoldKeySet}
              holdDetailStateStyle={holdDetailStateStyle}
              holdDetailStateLabel={holdDetailStateLabel}
              formatActionLabel={formatActionLabel}
            />
          )}
          {!isTech && activeTab === 'searches' && (
            <CaseDetailSearchesTab
              isRequestor={isRequestor}
              openCreateSearch={openCreateSearch}
              canUseSearchAi={canUseSearchAi}
              openSearchAiBuilder={openSearchAiBuilder}
              navigate={navigate}
              caseId={caseId}
              searches={searches}
              custodians={custodians}
              updateSearchStatus={updateSearchStatus}
              openEditSearch={openEditSearch}
              copySearch={copySearch}
              searchExportProvider={searchExportProvider}
              searchExportProviderName={searchExportProviderName}
              pushSearchToProvider={pushSearchToProvider}
              searchExportModal={searchExportModal}
              removeSearch={removeSearch}
            />
          )}
          {activeTab === 'requests' && (
            <CaseDetailTicketsTab
              isRequestor={isRequestor}
              isTech={isTech}
              isReadOnly={isReadOnly}
              custodianOptions={custodianOptions}
              namedHolds={ntpHolds}
              visibleTicketCategories={visibleTicketCategories}
              requestEntries={requestEntries}
              openBulkRequestModal={openBulkRequestModal}
              entryHasUnmatchedSnowCustodian={entryHasUnmatchedSnowCustodian}
              matchedEmailWorkflowWarning={matchedEmailWorkflowWarning}
              handleRequestEntryCustodianChange={handleRequestEntryCustodianChange}
              updateRequestEntry={updateRequestEntry}
              formatDateTime={formatDateTime}
              externalTicketBusy={externalTicketBusy}
              externalTicketStatuses={externalTicketStatuses}
              externalTicketEmailBusy={externalTicketEmailBusy}
              externalTicketEmailSent={externalTicketEmailSent}
              sendCustodianDetailsToAssignee={sendCustodianDetailsToAssignee}
              copyEntryCustodians={copyEntryCustodians}
              setAccessLogInfoEntryId={setAccessLogInfoEntryId}
              workflowUsesAccessLogDetails={workflowUsesAccessLogDetails}
              createExternalTicket={createExternalTicket}
              removeRequestEntry={removeRequestEntry}
              requestsSaving={requestsSaving}
              requestsDirty={requestsDirty}
            />
          )}
          {activeTab === 'requests' && !isRequestor && (
            <CaseDetailTicketNotesTab
              isTech={isTech}
              runTicketSelfHeal={runTicketSelfHeal}
              ticketSelfHealBusy={ticketSelfHealBusy}
              caseId={caseId}
              showToast={showToast}
            />
          )}
          {!isTech && (activeTab === 'documentation') && (
            <CaseDetailDocumentationTab
              isRequestor={isRequestor}
              custodians={custodians}
              setShowConsentModal={setShowConsentModal}
              consentsLoading={consentsLoading}
              consentsError={consentsError}
              consents={consents}
              consentRequestTracker={consentRequestTracker}
              consentActionBusy={consentActionBusy}
              consentDownloadBusyId={consentDownloadBusyId}
              formatDateTime={formatDateTime}
              resendConsent={resendConsent}
              voidConsent={voidConsent}
              downloadConsent={downloadConsent}
              canManageDocs={canManageDocs}
              openDocModal={openDocModal}
              docsLoading={docsLoading}
              docsError={docsError}
              proofs={proofs}
              formatFileSize={formatFileSize}
              deletingProofId={deletingProofId}
              handleDeleteProof={handleDeleteProof}
              esignDisplayName={esignDisplayName}
              esignEnvelopeName={esignEnvelopeName}
            />
          )}
          {!isTech && activeTab === 'sla' && (
            <CaseDetailSlaTab
              slaLoading={slaLoading}
              slaError={slaError}
              slaStatus={slaStatus}
            />
          )}
          {!isTech && activeTab === 'notes' && (
            <CaseDetailNotesTab
              caseId={caseId}
              isRequestor={isRequestor}
              showToast={showToast}
              setNoteCount={setNoteCount}
              setRequestorNoteCount={setRequestorNoteCount}
            />
          )}
        </>
          )}
      <CaseDetailStatusReasonModal
        request={statusReasonRequest}
        onClose={closeStatusReasonDialog}
        onSubmit={submitStatusReason}
        busy={statusReasonBusy}
      />
      <CaseDetailPreservationProviderModal
        open={showPurviewModal}
        onClose={() => setShowPurviewModal(false)}
        caseData={caseData}
        purviewStatus={purviewStatus}
        purviewCreating={purviewCreating}
        handleCreatePurviewCase={handleCreatePurviewCase}
        purviewExportCheckBusy={purviewExportCheckBusy}
        checkPurviewExports={checkPurviewExports}
        purviewHoldBusy={purviewHoldBusy}
        preservationHolds={preservationHolds}
        preservationHoldId={preservationHoldId}
        setPreservationHoldId={setPreservationHoldId}
        purviewHoldOptions={purviewHoldOptions}
        setPurviewHoldOptions={setPurviewHoldOptions}
        selectAllPurviewHoldTargets={selectAllPurviewHoldTargets}
        setPurviewHoldSelection={setPurviewHoldSelection}
        custodians={preservationCustodians}
        purviewHoldMap={purviewHoldMap}
        purviewSelectedSources={purviewSelectedSources}
        purviewHoldSelection={purviewHoldSelection}
        togglePurviewHoldSelection={togglePurviewHoldSelection}
        applyPurviewHolds={applyPurviewHolds}
        purviewHoldResults={purviewHoldResults}
        custodianLabelById={custodianLabelById}
        providerName={preservationProviderName}
        exportCheckEnabled={preservationProvider === 'purview'}
      />
      <CaseDetailCaseSummaryModal
        open={showCaseSummaryModal}
        onClose={() => setShowCaseSummaryModal(false)}
        loadCaseSummary={loadCaseSummary}
        emailCaseSummaryToSelf={emailCaseSummaryToSelf}
        caseSummary={caseSummary}
        caseSummaryData={caseSummaryData}
        caseSummarySections={caseSummarySections}
        caseSummaryAi={caseSummaryAi}
        caseSummaryAiAttention={caseSummaryAiAttention}
        caseSummaryAiActions={caseSummaryAiActions}
        caseSummaryAiHighlights={caseSummaryAiHighlights}
        caseData={caseData}
        formatDateTime={formatDateTime}
        ntpSectionCardStyle={ntpSectionCardStyle}
      />
      <CaseDetailTicketWorkflowModals
        showBulkRequestModal={showBulkRequestModal}
        closeBulkModal={closeBulkModal}
        bulkCategory={bulkCategory}
        namedHolds={activeTicketHolds}
        bulkHoldId={bulkHoldId}
        setBulkHoldId={setBulkHoldId}
        bulkSearch={bulkSearch}
        setBulkSearch={setBulkSearch}
        custodians={custodians}
        bulkCustodianDisabledReason={bulkCustodianDisabledReason}
        usedCustodianKeysByCategory={usedCustodianKeysByCategory}
        setBulkSelection={setBulkSelection}
        bulkSelection={bulkSelection}
        toggleBulkCustodian={toggleBulkCustodian}
        submitBulkRequests={submitBulkRequests}
        accessLogInfoEntry={accessLogInfoEntry}
        setAccessLogInfoEntryId={setAccessLogInfoEntryId}
        requestTicketCategoryLookup={requestTicketCategoryLookup}
        workflowUsesAccessLogDetails={workflowUsesAccessLogDetails}
        employeeIdLabel={employeeIdLabel}
        isRequestor={isRequestor}
        updateRequestEntry={updateRequestEntry}
        addAccessLogTimeWindow={addAccessLogTimeWindow}
        updateAccessLogTimeWindow={updateAccessLogTimeWindow}
        removeAccessLogTimeWindow={removeAccessLogTimeWindow}
        closeAccessLogInfoModal={closeAccessLogInfoModal}
        requestsSaving={requestsSaving}
        saveAccessLogInfoModal={saveAccessLogInfoModal}
        removeCustodianModal={removeCustodianModal}
        setRemoveCustodianModal={setRemoveCustodianModal}
        removeCustodian={removeCustodian}
      />
      <CaseDetailAddDocModal
        open={showAddDocModal}
        closeDocModal={closeDocModal}
        submitConsentDocument={submitConsentDocument}
        docForm={docForm}
        namedHolds={ntpHolds}
        handleDocHoldSelect={handleDocHoldSelect}
        handleDocCustodianSelect={handleDocCustodianSelect}
        handleDocFieldChange={handleDocFieldChange}
        custodianOptions={custodianOptions}
        setDocFile={setDocFile}
        docFile={docFile}
        docUploading={docUploading}
        docUploadError={docUploadError}
      />
      <CaseDetailNtpModals
        showSendNtpModal={showSendNtpModal}
        closeSendNtp={closeSendNtp}
        previewNtpNotice={previewNtpNotice}
        ntpPreview={ntpPreview}
        setNtpPreview={setNtpPreview}
        sendingNtp={sendingNtp}
        sendNtpNotices={sendNtpNotices}
        selectedTemplateId={selectedTemplateId}
        setSelectedTemplateId={setSelectedTemplateId}
        ntpSelection={ntpSelection}
        ntpHolds={ntpHolds}
        ntpHoldsLoading={ntpHoldsLoading}
        ntpHoldId={ntpHoldId}
        setNtpHoldId={setNtpHoldId}
        ntpModalScrollStyle={ntpModalScrollStyle}
        ntpFieldLabelStyle={ntpFieldLabelStyle}
        ntpSelectStyle={ntpSelectStyle}
        ntpTemplates={ntpTemplates}
        selectedReminderTemplateId={selectedReminderTemplateId}
        setSelectedReminderTemplateId={setSelectedReminderTemplateId}
        setReminderIntervalDays={setReminderIntervalDays}
        setReminderDurationDays={setReminderDurationDays}
        reminderIntervalDays={reminderIntervalDays}
        reminderDurationDays={reminderDurationDays}
        openNtpHistoryModal={openNtpHistoryModal}
        lastNtpSend={lastNtpSend}
        copyPreviousNtpData={copyPreviousNtpData}
        ntpVariables={ntpVariables}
        setNtpVariables={setNtpVariables}
        ntpReasonTouchedRef={ntpReasonTouchedRef}
        ntpOutsideCounselHistory={ntpOutsideCounselHistory}
        reminderSummary={reminderSummary}
        ntpSectionCardStyle={ntpSectionCardStyle}
        ntpHelperTextStyle={ntpHelperTextStyle}
        openReminderListModal={openReminderListModal}
        ntpRemindersLoading={ntpRemindersLoading}
        ntpSearch={ntpSearch}
        setNtpSearch={setNtpSearch}
        filteredNtpCustodians={filteredNtpCustodians}
        toggleNtpSelection={toggleNtpSelection}
        ntpStatusLabel={ntpStatusLabel}
        showNtpHistoryModal={showNtpHistoryModal}
        setShowNtpHistoryModal={setShowNtpHistoryModal}
        ntpHistory={ntpHistory}
        ntpHistoryExporting={ntpHistoryExporting}
        ntpHistoryEmailing={ntpHistoryEmailing}
        exportNtpHistoryCsv={exportNtpHistoryCsv}
        emailNtpHistoryReport={emailNtpHistoryReport}
        loadNtpHistory={loadNtpHistory}
        ntpHistoryCustodianRows={ntpHistoryCustodianRows}
        ntpHistoryEvents={ntpHistoryEvents}
        formatDateTime={formatDateTime}
        showReminderListModal={showReminderListModal}
        setShowReminderListModal={setShowReminderListModal}
        canEditReminders={canEditReminders}
        eligibleReminderReactivationCustodianIds={eligibleReminderReactivationCustodianIds}
        reactivateEligibleCancelledNtpReminders={reactivateEligibleCancelledNtpRemindersForActive}
        reactivatingNtpRemindersBulk={reactivatingNtpRemindersBulk}
        reminderGroups={reminderGroups}
        reactivatingNtpReminders={reactivatingNtpReminders}
        openReminderEditor={openReminderEditor}
        reactivateCancelledNtpReminders={reactivateCancelledNtpReminders}
        ntpBlockedModal={ntpBlockedModal}
        setNtpBlockedModal={setNtpBlockedModal}
        reminderEditor={reminderEditor}
        closeReminderEditor={closeReminderEditor}
        saveReminderEditor={saveReminderEditorForActive}
        setReminderEditor={setReminderEditor}
        editorPrimaryReminder={editorPrimaryReminder}
      />
      <CaseDetailConsentModal
        open={showConsentModal && !isRequestor}
        onClose={() => setShowConsentModal(false)}
        consentFormInline={consentFormInline}
        setConsentFormInline={setConsentFormInline}
        consentHolds={consentHolds}
        consentHoldId={consentHoldId}
        setConsentHoldId={setConsentHoldId}
        consentAutoSearches={consentAutoSearches}
        consentAutoSearchId={consentAutoSearchId}
        setConsentAutoSearchId={setConsentAutoSearchId}
        autoAddConsentFromSearch={autoAddConsentFromSearch}
        consentSearch={consentSearch}
        setConsentSearch={setConsentSearch}
        addAllAvailableConsents={addAllAvailableConsents}
        filteredConsentCustodians={filteredConsentCustodians}
        custodians={consentCustodians}
        consentReceivedIds={consentReceivedIds}
        consentReceivedEmails={consentReceivedEmails}
        consentSelection={consentSelection}
        setConsentSelection={setConsentSelection}
        consentSelectedRecipients={consentSelectedRecipients}
        sendSelectedConsents={sendSelectedConsents}
        consentSendBusy={consentSendBusy}
        esignDisplayName={esignDisplayName}
        esignEnvelopeName={esignEnvelopeName}
      />
      <CaseDetailCloseCaseModal
        open={showCloseCaseModal}
        closeCaseBusy={closeCaseBusy}
        setShowCloseCaseModal={setShowCloseCaseModal}
        setCloseCaseNote={setCloseCaseNote}
        closeCaseNote={closeCaseNote}
        submitCloseCaseRequest={submitCloseCaseRequest}
        caseId={caseId}
      />
      <CaseDetailEditCaseModal
        open={showEdit}
        caseData={caseData}
        analystOptions={analystOptions}
        requestorOptions={requestorOptions}
        onClose={() => setShowEdit(false)}
        updateCase={updateCase}
        setCaseData={setCaseData}
        showToast={showToast}
        useLegalCaseNameAsPrimary={useLegalCaseNameAsPrimary}
        internalCounselLabel={internalCounselLabel}
        defaultClosureNagDays={defaultClosureNagDays}
      />      <CaseDetailCustodianEntryModals
        showCustodianModal={showCustodianModal}
        custodianModalMode={custodianModalMode}
        setShowCustodianModal={setShowCustodianModal}
        setCustodianModalMode={setCustodianModalMode}
        apiBase={apiBase}
        caseId={caseId}
        namedHolds={ntpHolds}
        targetHoldIds={targetHoldIds}
        setTargetHoldIds={setTargetHoldIds}
        reloadNamedHolds={loadNtpHolds}
        employeeIdLabel={employeeIdLabel}
        lookupInputPlaceholder={lookupInputPlaceholder}
        personLookupEnabled={personLookupEnabled}
        importWorking={importWorking}
        importDone={importDone}
        importTotal={importTotal}
        setImportWorking={setImportWorking}
        submitCustodianBatch={submitCustodianBatch}
        setCustodians={setCustodians}
        showToast={showToast}
        addCustodiansWorking={addCustodiansWorking}
        addCustodiansWorkingRef={addCustodiansWorkingRef}
        setAddCustodiansWorking={setAddCustodiansWorking}
      />
      <CaseDetailEditCustodianModal
        editing={editing}
        setEditing={setEditing}
        editSaveBusy={editSaveBusy}
        onSaveEditCustodian={onSaveEditCustodian}
        editLookupBusy={editLookupBusy}
        runEditPersonLookup={runEditPersonLookup}
        editLookupOptions={editLookupOptions}
        setEditLookupOptions={setEditLookupOptions}
        applyEditMatch={applyEditMatch}
        caseData={caseData}
        editingConsentNotRequired={editingConsentNotRequired}
        editingConsentAutoReason={editingConsentAutoReason}
      />
      <CaseDetailSearchModals
        showSearchAiModal={showSearchAiModal}
        canUseSearchAi={canUseSearchAi}
        caseId={caseId}
        caseData={caseData}
        custodians={custodians}
        namedHolds={ntpHolds}
        setShowSearchAiModal={setShowSearchAiModal}
        applyAiSearchSuggestion={applyAiSearchSuggestion}
        createSearchesFromAiSuggestions={createSearchesFromAiSuggestions}
        showSearchModal={showSearchModal}
        editingSearch={editingSearch}
        suggestedSearchName={suggestedSearchName}
        isRequestor={isRequestor}
        setShowSearchModal={setShowSearchModal}
        setEditingSearch={setEditingSearch}
        saveSearchDraft={saveSearchDraft}
        searchQueryLabel={searchQueryLabel}
      />
      <CaseDetailSearchStatusModals
        searchExportModal={searchExportModal}
        closeSearchExportModal={closeSearchExportModal}
        searchExportProviderName={searchExportProviderName}
        searchQueryLabel={searchQueryLabel}
        detailsSearch={detailsSearch}
        setDetailsSearch={setDetailsSearch}
        detailsSearchParsed={detailsSearchParsed}
        detailValueStyle={detailValueStyle}
        custodians={custodians}
        blockedConsent={blockedConsent}
        setBlockedConsent={setBlockedConsent}
      />
    </div>
  )
}
