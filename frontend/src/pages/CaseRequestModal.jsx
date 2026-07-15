import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import { useConfirm } from '../components/ConfirmProvider.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import { fetchSystemSettings } from '../lib/systemSettingsClient.js'
import { normalizeCaseNamingMode } from './setupCatalog.js'
import { CaseRequestModalShell, CaseRequestUnmatchedModal } from './CaseRequestModalShell.jsx'
import CaseRequestSearchSection from './CaseRequestSearchSection.jsx'
import CaseRequestIntakeStep from './CaseRequestIntakeStep.jsx'
import CaseRequestPreservationStep from './CaseRequestPreservationStep.jsx'
import { useCaseRequestCustodianLookup } from './useCaseRequestCustodianLookup.js'
import { useCaseRequestCustodianUpload } from './useCaseRequestCustodianUpload.js'
import {
  emptySearch,
  genId,
  hasSearchDetails,
  holdOptionsFromPreservationSources,
  makeCustodian,
  normalizeGroupValue,
  normalizeSearch,
  parseAdditionalRequestorEmails
} from './caseRequestsUtils.js'
import { personLookupFieldsFromMatch } from './caseDetailPersonLookupFields.js'

export default function CaseRequestModal({
  mode,
  apiBase,
  onClose,
  caseContext,
  onSuccess,
}) {
  const isNewCase = mode === 'new_case'
  const isCustodian = mode === 'custodian'
  const isSearch = mode === 'search'
  const { user, authConfig } = useAuth()
  const { showToast } = useToast()
  const confirmDialog = useConfirm()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const requestorGroup = normalizeGroupValue(user?.requestor_group || '')
  const employeeIdLabel = authConfig?.institution?.employee_id_label || 'Employee ID'
  const lookupInputPlaceholder = `Enter full name, email address or ${employeeIdLabel} to begin person lookup`
  const prefersLegalCaseLabel = requestorGroup === 'risk' || requestorGroup === 'legal'
  const secondaryCaseNameLabel = prefersLegalCaseLabel ? 'Legal Case Name' : 'Case Name'
  const isRequestor = role === 'requestor'
  const useWizard = !isSearch
  const autofillNonce = useMemo(() => Math.random().toString(36).slice(2), [])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [suggesting, setSuggesting] = useState(false)
  const [caseNamingMode, setCaseNamingMode] = useState('legal_case_name')
  const [configuredHoldOptions, setConfiguredHoldOptions] = useState(() => holdOptionsFromPreservationSources(null))
  const [step, setStep] = useState(1)
  const [holdOpen, setHoldOpen] = useState({})
  const normalizeHolds = useCallback((holds = {}) => (
    configuredHoldOptions.reduce((acc, [field]) => ({ ...acc, [field]: !!holds[field] }), {})
  ), [configuredHoldOptions])
  const buildInitialForm = useCallback(() => ({
    name: '',
    legal_case_name: '',
    claimant: '',
    description: '',
    is_private: false,
    additional_requestors: '',
    custodianMode: isSearch ? 'none' : 'manual',
    custodians: [makeCustodian()],
    custodianFile: null,
    ntpAllSent: false,
    includeSearch: isSearch,
    versa_search_requirements: '',
    search: emptySearch(),
    searches: [],
    pasteText: '',
  }), [isSearch])
  const [form, setForm] = useState(buildInitialForm)
  const [additionalVersaSearches, setAdditionalVersaSearches] = useState([])
  const [searchRequestsFinalized, setSearchRequestsFinalized] = useState(false)
  const [custodianProofFiles, setCustodianProofFiles] = useState({})

  useEffect(() => {
    let alive = true
    fetchSystemSettings(apiBase)
      .then(data => {
        if (!alive) return
        setCaseNamingMode(normalizeCaseNamingMode(data?.case_naming?.mode))
        setConfiguredHoldOptions(holdOptionsFromPreservationSources(data?.preservation_sources))
      })
      .catch(() => {
        if (alive) setCaseNamingMode(normalizeCaseNamingMode(null))
      })
    return () => { alive = false }
  }, [apiBase])
  const configuredRequestHoldOptions = useMemo(() => configuredHoldOptions, [configuredHoldOptions])

  useEffect(() => {
    if (!isNewCase) return
    if (caseNamingMode === 'legal_case_name') return
    let cancelled = false
    const fetchName = async () => {
      try {
        setSuggesting(true)
        const r = await fetch(`${apiBase}/cases/suggest_name`, { credentials: 'include' })
        if (!r.ok) throw new Error('Unable to suggest name')
        const data = await r.json()
        const suggestedName = typeof data?.name === 'string'
          ? data.name
          : (typeof data?.suggested_name === 'string' ? data.suggested_name : '')
        if (!cancelled && suggestedName) {
          setForm((prev) => (prev.name?.trim() ? prev : { ...prev, name: suggestedName }))
        }
      } catch (err) {
        console.error(err)
      } finally {
        if (!cancelled) setSuggesting(false)
      }
    }
    fetchName()
    return () => { cancelled = true }
  }, [apiBase, isNewCase, caseNamingMode])

  const updateLegalCaseName = (value) => {
    setForm((prev) => ({
      ...prev,
      legal_case_name: value,
      name: isNewCase && caseNamingMode === 'legal_case_name' ? value : prev.name,
    }))
  }

  const updateCustodian = (id, patch) => {
    setForm((prev) => ({
      ...prev,
      custodians: prev.custodians.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    }))
  }

  const addCustodianRow = () => {
    setForm((prev) => ({ ...prev, custodians: [...prev.custodians, makeCustodian()] }))
  }

  const removeCustodianRow = (id) => {
    setForm((prev) => ({ ...prev, custodians: prev.custodians.filter((c) => c.id !== id) }))
  }

  const handleProofFile = (custId, file) => {
    setCustodianProofFiles((prev) => {
      const next = { ...prev }
      if (file) {
        next[custId] = file
      } else {
        delete next[custId]
      }
      return next
    })
  }

  const parsePastedCustodians = (text) => {
    if (!text) return []
    const rows = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
    const emailRegex = /([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/i
    const parsed = []
    for (const row of rows) {
      const match = row.match(emailRegex)
      const email = match ? match[1].trim() : ''
      let nameSource = row
      if (email) {
        nameSource = row.replace(email, '')
      }
      let name = nameSource
        .replace(/[-,;|:/]/g, ' ')
        .replace(/[()<>\[\]'`"]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
      if (!name && email) {
        name = email.split('@')[0]
      }
      if (!name && !email) continue
      parsed.push({ name, email })
    }
    return parsed
  }

  const pasteResults = useMemo(() => parsePastedCustodians(form.pasteText), [form.pasteText])

  const displayedCustodians = useMemo(() => {
    if (!['manual', 'paste', 'upload'].includes(form.custodianMode)) return []
    return (form.custodians || [])
      .map((c) => ({
        ...c,
        name: (c.name || '').trim(),
        email: (c.email || '').trim(),
      }))
      .filter((c) => (c.name || '').trim() || c.override_lookup)
  }, [form.custodianMode, form.custodians])

  const {
    lookupStatus,
    lookupError,
    lookupMatches,
    lookupSelection,
    unmatchedCount,
    unmatchedModalOpen,
    setUnmatchedModalOpen,
    setShowUnmatchedNotice,
    setCustodianLookupOptOut,
    resetLookupState,
    resetLookupResults,
    selectedMatchFor,
    runCustodianLookup,
    handleSelectMatch,
    toggleLookupOverride,
    badgesForMatch,
    employmentBadgesFromPayload,
    endDateStyle,
  } = useCaseRequestCustodianLookup({
    apiBase,
    useWizard,
    step,
    form,
    setForm,
    displayedCustodians,
    updateCustodian,
  })
  const {
    custodianFileBusy,
    loadCustodiansFromUpload,
    resetCustodianUpload,
  } = useCaseRequestCustodianUpload({
    apiBase,
    setForm,
    setHoldOpen,
    resetLookupResults,
    showToast,
    setError,
  })
  useEffect(() => {
    setForm(buildInitialForm())
    setAdditionalVersaSearches([])
    setSearchRequestsFinalized(false)
    setCustodianProofFiles({})
    setStep(1)
    setHoldOpen({})
    resetLookupState()

    resetCustodianUpload()
  }, [buildInitialForm, mode, caseContext?.id, resetCustodianUpload, resetLookupState])

  useEffect(() => {
    const allowed = new Set((form.custodians || []).map((c) => String(c.id)))
    setCustodianProofFiles((prev) => {
      const next = {}
      let changed = false
      Object.entries(prev || {}).forEach(([id, file]) => {
        if (allowed.has(id)) {
          next[id] = file
        } else {
          changed = true
        }
      })
      return changed ? next : prev
    })
  }, [form.custodians])

  const lockCustodiansForWizard = useCallback(() => {
    let result = []
    setForm((prev) => {
      if (!['manual', 'paste', 'upload'].includes(prev.custodianMode)) {
        result = []
        return { ...prev, custodians: [] }
      }
      if (prev.custodianMode === 'manual' || prev.custodianMode === 'upload') {
        result = (prev.custodians || [])
          .map((c) => ({
            ...c,
            name: (c.name || '').trim(),
            email: (c.email || '').trim(),
          }))
          .filter((c) => c.name)
        return { ...prev, custodians: result }
      }
      const lookup = new Map()
      for (const cust of prev.custodians || []) {
        const key = ((cust.email || cust.name || '').trim().toLowerCase()) || cust.id
        if (key) lookup.set(key, cust)
      }
      const roster = pasteResults.map((entry) => {
        const key = (entry.email || entry.name || '').trim().toLowerCase()
        const prior = lookup.get(key)
        const base = prior || makeCustodian()
        return {
          ...base,
          id: prior?.id || base.id || genId(),
          name: entry.name || '',
          email: entry.email || '',
        }
      })
      result = roster
      return { ...prev, custodians: roster }
    })
    setHoldOpen({})
    return result
  }, [pasteResults])

  const handleHoldChange = (custId, field, value) => {
    const cust = displayedCustodians.find((c) => c.id === custId)
    const currentHolds = normalizeHolds(cust?.holds)
    const newHolds = normalizeHolds({ ...currentHolds, [field]: value })
    updateCustodian(custId, { holds: newHolds })
  }

  const applyHoldsToAll = (holdsPattern) => {
    const normalized = normalizeHolds(holdsPattern)
    setForm((prev) => ({
      ...prev,
      custodians: prev.custodians.map((c) => ({ ...c, holds: normalized })),
    }))
    setHoldOpen((prev) => {
      const next = { ...prev }
      displayedCustodians.forEach((c) => { next[c.id] = true })
      return next
    })
  }

  const handleNtpUpdate = (custId, sent, ack) => {
    const nextState = { ntp_sent: !!sent, ntp_ack: !!ack && !!sent }
    updateCustodian(custId, nextState)
  }

  const applyNtpToAll = (sent, ack) => {
    const nextState = { ntp_sent: !!sent, ntp_ack: !!ack && !!sent }
    setForm((prev) => ({
      ...prev,
      custodians: prev.custodians.map((c) => ({ ...c, ...nextState })),
    }))
  }

  const custodianPayload = useMemo(() => {
    if (!['manual', 'paste', 'upload'].includes(form.custodianMode)) return []
    return displayedCustodians.map((c) => {
      const selectedMatch = selectedMatchFor(c.id)
      return {
        id: c.id,
        name: c.name,
        email: (c.email || '').trim() || 'UNMATCHED',
        notes: (c.notes || '').trim(),
        holds: normalizeHolds(c.holds),
        ntp_status: c.ntp_ack ? 'acknowledged' : (c.ntp_sent ? 'sent' : 'not sent'),
        consent_received: !!c.consent_received,
        ...personLookupFieldsFromMatch(selectedMatch),
        lookup_override: !!c.override_lookup,
        lookup_override_note: (c.override_note || '').trim() || undefined,
      }
    })
  }, [displayedCustodians, form.custodianMode, normalizeHolds, selectedMatchFor])
  const consentCustodians = useMemo(() => custodianPayload.filter((c) => c.consent_received), [custodianPayload])
  const missingProofs = useMemo(() => consentCustodians.some((c) => !custodianProofFiles[c.id]), [consentCustodians, custodianProofFiles])

  const custodianInputSatisfied = useMemo(() => {
    if (!(isNewCase || isCustodian)) return true
    if (form.custodianMode === 'manual') return displayedCustodians.length > 0
    if (form.custodianMode === 'paste') return pasteResults.length > 0
    if (form.custodianMode === 'upload') return displayedCustodians.length > 0
    if (form.custodianMode === 'none') return true
    return false
  }, [displayedCustodians.length, form.custodianMode, isCustodian, isNewCase, pasteResults])

  const canAdvanceFromStep1 = useMemo(() => {
    if (!useWizard) return false
    if (isNewCase && !(form.name || '').trim()) return false
    return custodianInputSatisfied
  }, [custodianInputSatisfied, form.name, isNewCase, useWizard])

  const canAdvanceFromStep2 = useMemo(() => {
    if (!useWizard) return false
    if (missingProofs) return false
    return true
  }, [missingProofs, useWizard])

  const searchIncluded = isSearch || form.includeSearch
  const searchRequestFlowActive = (isNewCase && form.includeSearch) || isSearch
  const normalizedAdditionalVersaSearches = useMemo(
    () => additionalVersaSearches.map((entry) => String(entry || '').trim()).filter(Boolean),
    [additionalVersaSearches]
  )
  const versaRequirements = String(form.versa_search_requirements || '').trim()
  const totalSearchCount = useMemo(() => {
    if (!searchIncluded) return 0
    if (isNewCase || isSearch) return (versaRequirements ? 1 : 0) + normalizedAdditionalVersaSearches.length
    const saved = (Array.isArray(form.searches) ? form.searches : []).filter(hasSearchDetails).length
    const draft = hasSearchDetails(form.search) ? 1 : 0
    return saved + draft
  }, [form.search, form.searches, normalizedAdditionalVersaSearches.length, searchIncluded, isNewCase, isSearch, versaRequirements])
  const wideModal = isSearch || (useWizard && step === 3 && !!form.includeSearch)
  const effectiveRequestCaseName = isNewCase && caseNamingMode === 'legal_case_name'
    ? form.legal_case_name
    : form.name
  const canSubmit = useMemo(() => {
    if (loading) return false
    if (useWizard && step !== 3) return false
    if (isNewCase && !(effectiveRequestCaseName || '').trim()) return false
    if (!custodianInputSatisfied) return false
    if (searchIncluded && totalSearchCount === 0) return false
    if (missingProofs) return false
    return true
  }, [custodianInputSatisfied, effectiveRequestCaseName, isNewCase, loading, missingProofs, searchIncluded, step, totalSearchCount, useWizard])

  const submit = async ({ searchesOverride } = {}) => {
    setError('')
    setLoading(true)
    try {
      const additionalRequestorEmails = (isNewCase && isRequestor && form.is_private)
        ? parseAdditionalRequestorEmails(form.additional_requestors)
        : []
      const searchesProvided = Array.isArray(searchesOverride) ? searchesOverride : null
      const computedSearches = (
        (!isNewCase && !isSearch && form.includeSearch)
          ? [
            ...(Array.isArray(form.searches) ? form.searches : []).filter(hasSearchDetails).map(normalizeSearch),
            ...(hasSearchDetails(form.search) ? [normalizeSearch(form.search)] : []),
          ]
          : []
      )
      const searchesToSubmit = (searchesProvided || computedSearches).filter(hasSearchDetails)
      const versaRequirementsToSubmit = [versaRequirements, ...normalizedAdditionalVersaSearches].filter(Boolean).join('\n\n--- Search Request ---\n\n')
      const payload = {
        name: effectiveRequestCaseName?.trim() || undefined,
        legal_case_name: form.legal_case_name?.trim() || undefined,
        claimant: form.claimant?.trim() || undefined,
        description: form.description?.trim() || undefined,
        is_private: isNewCase ? !!form.is_private : undefined,
        custodian_entry_mode: form.custodianMode === 'upload' ? 'manual' : form.custodianMode,
        custodians: custodianPayload,
        ntp_all_sent: !!form.ntpAllSent,
        case_id: caseContext?.id || undefined,
        search: (!isNewCase && !isSearch && form.includeSearch) ? (searchesToSubmit[0] || undefined) : undefined,
        searches: (!isNewCase && !isSearch && form.includeSearch) ? (searchesToSubmit.length ? searchesToSubmit : undefined) : undefined,
        versa_search_requirements: ((isNewCase && form.includeSearch) || isSearch) ? (versaRequirementsToSubmit || undefined) : undefined,
      }
      if (isNewCase && isRequestor && form.is_private) {
        payload.requestors = [
          {
            email: user?.email || '',
            user_id: user?.id || undefined,
            requestor_group: user?.requestor_group || undefined,
            is_primary: true,
          },
          ...additionalRequestorEmails.map((email) => ({
            email,
            is_primary: false,
          })),
        ].filter((entry) => (entry.email || '').trim())
      }
      payload.consents = consentCustodians.map((c) => ({
        custodian_id: c.id,
        name: c.name,
        email: c.email,
        notes: c.notes,
      }))
      if (isSearch) {
        payload.custodian_entry_mode = 'none'
      }
      const fd = new FormData()
      fd.append('request_type', mode)
      fd.append('data', JSON.stringify(payload))
      if ((isNewCase || isCustodian) && form.custodianMode === 'upload' && form.custodianFile) {
        fd.append('custodian_file', form.custodianFile)
      }
      Object.entries(custodianProofFiles).forEach(([custId, file]) => {
        if (!file) return
        const safeName = file.name || 'consent'
        fd.append(`consent_proof_${custId}`, file, `consent_${custId}_${safeName}`)
      })
      const res = await fetch(`${apiBase}/case_requests`, {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })
      if (!res.ok) {
        let msg = 'Unable to submit request'
        try {
          const data = await res.json()
          if (data?.detail) msg = data.detail
          else {
            const text = await res.text().catch(() => '')
            msg = text || msg
          }
        } catch {
          const text = await res.text().catch(() => '')
          msg = text || msg
        }
        throw new Error(msg)
      }
      let created = null
      try { created = await res.json() } catch { created = null }
      if (isRequestor && isCustodian && caseContext?.id && (created?.status || '').toLowerCase() === 'approved') {
        showToast(
          'New custodian request is auto approved. Please allow 5-10 minutes for the system to place requested preservation holds. Case/custodian/hold status may change once complete.',
          { variant: 'info', duration: 12000 }
        )
      }
      onSuccess?.()
      onClose?.()
    } catch (err) {
      console.error(err)
      setError(err?.message || 'Submission failed')
    } finally {
      setLoading(false)
    }
  }
  const handleSearchRequestSubmit = async () => {
    if (!searchRequestFlowActive) {
      await submit()
      return
    }
    if (totalSearchCount === 0) return
    const addAnother = await confirmDialog({
      title: 'Add another search request?',
      description: 'Would you like to add another search request?',
      confirmLabel: 'Yes',
      cancelLabel: 'No',
    })
    if (addAnother) {
      setAdditionalVersaSearches((prev) => [...prev, ''])
      setSearchRequestsFinalized(false)
      return
    }
    setSearchRequestsFinalized(true)
    await submit()
  }

  const handleNext = () => {
    if (!useWizard) {
      submit()
      return
    }
    if (step === 1) {
      if (!canAdvanceFromStep1) return
      const locked = lockCustodiansForWizard()
      setStep(2)
      runCustodianLookup(locked)
      return
    }
    if (step === 2) {
      if (!canAdvanceFromStep2) return
      setStep(3)
      return
    }
    submit()
  }
  const handleBack = () => {
    if (!useWizard) return
    setStep((prev) => Math.max(1, prev - 1))
  }
  const handleFormSubmit = async (e) => {
    e.preventDefault()
    if (useWizard && step < 3) {
      handleNext()
      return
    }
    if (!canSubmit) return
    if (searchRequestFlowActive && !searchRequestsFinalized) {
      await handleSearchRequestSubmit()
      return
    }
    await submit()
  }

  const primaryActionLabel = useWizard
    ? (step === 3
      ? (loading
        ? 'Submitting'
        : (searchRequestFlowActive && !searchRequestsFinalized ? 'Submit Search Request' : 'Submit Request'))
      : 'Next')
    : (loading ? 'Submitting' : (searchRequestFlowActive && !searchRequestsFinalized ? 'Submit Search Request' : 'Submit Request'))
  const sectionTitle = isNewCase ? 'Submit New Case Intake' : isCustodian ? 'Request Custodian Changes' : 'Request New Search'
  return (
    <>
      <CaseRequestModalShell
        sectionTitle={sectionTitle}
        onClose={onClose}
        wideModal={wideModal}
        useWizard={useWizard}
        step={step}
        handleBack={handleBack}
        canAdvanceFromStep1={canAdvanceFromStep1}
        canAdvanceFromStep2={canAdvanceFromStep2}
        canSubmit={canSubmit}
        primaryActionLabel={primaryActionLabel}
        handleFormSubmit={handleFormSubmit}
        autofillNonce={autofillNonce}
        error={error}
      >        <CaseRequestIntakeStep
          useWizard={useWizard}
          step={step}
          caseContext={caseContext}
          isNewCase={isNewCase}
          isSearch={isSearch}
          isRequestor={isRequestor}
          caseNamingMode={caseNamingMode}
          form={form}
          suggesting={suggesting}
          secondaryCaseNameLabel={secondaryCaseNameLabel}
          updateLegalCaseName={updateLegalCaseName}
          setForm={setForm}
          lookupInputPlaceholder={lookupInputPlaceholder}
          autofillNonce={autofillNonce}
          updateCustodian={updateCustodian}
          removeCustodianRow={removeCustodianRow}
          addCustodianRow={addCustodianRow}
          custodianFileBusy={custodianFileBusy}
          loadCustodiansFromUpload={loadCustodiansFromUpload}
        />
        <CaseRequestPreservationStep
          useWizard={useWizard}
          isSearch={isSearch}
          step={step}
          lookupStatus={lookupStatus}
          lookupError={lookupError}
          form={form}
          displayedCustodians={displayedCustodians}
          configuredRequestHoldOptions={configuredRequestHoldOptions}
          normalizeHolds={normalizeHolds}
          holdOpen={holdOpen}
          setHoldOpen={setHoldOpen}
          lookupMatches={lookupMatches}
          selectedMatchFor={selectedMatchFor}
          badgesForMatch={badgesForMatch}
          lookupSelection={lookupSelection}
          handleSelectMatch={handleSelectMatch}
          endDateStyle={endDateStyle}
          updateCustodian={updateCustodian}
          removeCustodianRow={removeCustodianRow}
          toggleLookupOverride={toggleLookupOverride}
          handleNtpUpdate={handleNtpUpdate}
          handleProofFile={handleProofFile}
          handleHoldChange={handleHoldChange}
          applyHoldsToAll={applyHoldsToAll}
          applyNtpToAll={applyNtpToAll}
          custodianProofFiles={custodianProofFiles}
          missingProofs={missingProofs}
        />
        {!isSearch && ((useWizard && step === 3) || !useWizard) && (
          <label className="field inline">
            <input
              type="checkbox"
              checked={form.includeSearch}
              onChange={(e) => {
                const checked = e.target.checked
                setForm((prev) => ({ ...prev, includeSearch: checked }))
                if (isNewCase) setSearchRequestsFinalized(false)
              }}
            />
            <span>{isNewCase ? 'Include Search Requirements' : 'Include search request details'}</span>
          </label>
        )}

        <LoadingOverlay
          visible={loading || lookupStatus === 'loading'}
          title={loading ? 'Submitting' : 'Running person lookup'}
          subtitle="This can take a few seconds. Please do not close the window."
        />

        <CaseRequestSearchSection
          visible={useWizard ? step === 3 : true}
          searchIncluded={searchIncluded}
          isNewCase={isNewCase}
          isSearch={isSearch}
          form={form}
          setForm={setForm}
          autofillNonce={autofillNonce}
          caseContext={caseContext}
          additionalVersaSearches={additionalVersaSearches}
          setAdditionalVersaSearches={setAdditionalVersaSearches}
          setSearchRequestsFinalized={setSearchRequestsFinalized}
          searchRequestsFinalized={searchRequestsFinalized}
          totalSearchCount={totalSearchCount}
        />
      </CaseRequestModalShell>

      <CaseRequestUnmatchedModal
        open={unmatchedModalOpen}
        count={unmatchedCount}
        onClose={() => setUnmatchedModalOpen(false)}
      />
    </>
  )
}

