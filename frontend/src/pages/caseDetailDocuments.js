import { useCallback, useState } from 'react'
import { caseCache, proofCache } from './caseDetailUtils.js'

export function useCaseDetailDocuments({
  apiBase,
  caseId,
  cachedProofs,
  custodians,
  confirmDialog,
  showToast,
  reloadCustodiansRef,
  setCaseData,
}) {
  const [proofs, setProofs] = useState(() => cachedProofs || [])
  const [proofsLoaded, setProofsLoaded] = useState(() => Array.isArray(cachedProofs))
  const [docsLoading, setDocsLoading] = useState(false)
  const [docsError, setDocsError] = useState(null)
  const [showAddDocModal, setShowAddDocModal] = useState(false)
  const [docForm, setDocForm] = useState({ caseHoldId: '', custodianId: '', custodianName: '', custodianEmail: '', proofType: 'standard' })
  const [docFile, setDocFile] = useState(null)
  const [docUploading, setDocUploading] = useState(false)
  const [docUploadError, setDocUploadError] = useState(null)
  const [deletingProofId, setDeletingProofId] = useState(null)

  const setProofRows = useCallback((rows) => {
    const next = Array.isArray(rows) ? rows : []
    setProofs(next)
    setProofsLoaded(true)
    if (caseId) proofCache.set(caseId, next)
    return next
  }, [caseId])

  const loadProofs = useCallback(async () => {
    if (!caseId) return
    setDocsLoading(true)
    setDocsError(null)
    try {
      const res = await fetch(`${apiBase}/case_requests/cases/${caseId}/consent_proofs`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text() || 'Unable to load documentation')
      const data = await res.json()
      const next = setProofRows(data)
      setCaseData(prev => prev ? { ...prev, consent_proof_count: next.length } : prev)
    } catch (err) {
      setDocsError(err?.message || 'Unable to load documentation')
    } finally {
      setDocsLoading(false)
    }
  }, [apiBase, caseId, setCaseData, setProofRows])

  const resetDocForm = useCallback(() => {
    setDocForm({ caseHoldId: '', custodianId: '', custodianName: '', custodianEmail: '', proofType: 'standard' })
    setDocFile(null)
    setDocUploadError(null)
  }, [])

  const openDocModal = useCallback(() => {
    resetDocForm()
    setShowAddDocModal(true)
  }, [resetDocForm])

  const closeDocModal = useCallback(() => {
    if (docUploading) return
    setShowAddDocModal(false)
    resetDocForm()
  }, [docUploading, resetDocForm])

  const handleDocHoldSelect = useCallback((value) => {
    setDocForm(prev => ({
      ...prev,
      caseHoldId: value ? String(value) : '',
      custodianId: '',
      custodianName: '',
      custodianEmail: '',
    }))
  }, [])

  const handleDocCustodianSelect = useCallback((value) => {
    if (!value) {
      setDocForm(prev => ({ ...prev, custodianId: '' }))
      return
    }
    const numeric = Number(value)
    if (!Number.isFinite(numeric)) {
      setDocForm(prev => ({ ...prev, custodianId: value }))
      return
    }
    const match = custodians.find(c => Number(c.id) === numeric)
    setDocForm(prev => ({
      ...prev,
      custodianId: String(numeric),
      custodianName: match?.name || prev.custodianName || '',
      custodianEmail: match?.email || prev.custodianEmail || '',
    }))
  }, [custodians])

  const handleDocFieldChange = useCallback((key, value) => {
    setDocForm(prev => ({ ...prev, [key]: value }))
  }, [])

  const submitConsentDocument = useCallback(async (event) => {
    event?.preventDefault()
    if (!caseId) return
    if (!docFile) {
      setDocUploadError('Select a consent document to upload.')
      return
    }
    if (!docForm.caseHoldId) {
      setDocUploadError('Select the named hold this consent proof belongs to.')
      return
    }
    if (!docForm.custodianId) {
      setDocUploadError('Select a custodian assigned to that hold.')
      return
    }
    const name = (docForm.custodianName || '').trim()
    const email = (docForm.custodianEmail || '').trim()
    const fd = new FormData()
    fd.append('custodian_name', name)
    fd.append('custodian_email', email)
    fd.append('case_hold_id', docForm.caseHoldId)
    fd.append('custodian_id', docForm.custodianId)
    fd.append('proof_type', docForm.proofType || 'standard')
    fd.append('file', docFile)
    setDocUploading(true)
    setDocUploadError(null)
    try {
      const res = await fetch(`${apiBase}/case_requests/cases/${caseId}/consent_proofs`, {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Unable to Upload proof')
      }
      showToast(docForm.proofType === 'awoc' ? 'AWOC consent document uploaded.' : 'Consent documentation uploaded.', { variant: 'success' })
      setShowAddDocModal(false)
      resetDocForm()
      await loadProofs()
      await reloadCustodiansRef.current?.()
    } catch (err) {
      console.error(err)
      setDocUploadError(err?.message || 'Unable to Upload proof')
    } finally {
      setDocUploading(false)
    }
  }, [apiBase, caseId, docFile, docForm, loadProofs, reloadCustodiansRef, resetDocForm, showToast])

  const handleDeleteProof = useCallback(async (proof) => {
    if (!proof || !proof.id) return
    if (!confirmDialog) return
    const ok = await confirmDialog({
      title: 'Remove documentation',
      description: 'Remove this consent document? This action cannot be undone.',
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    setDeletingProofId(proof.id)
    try {
      const res = await fetch(`${apiBase}/case_requests/cases/${caseId}/consent_proofs/${proof.id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Unable to delete documentation')
      }
      showToast('Documentation removed.', { variant: 'success' })
      await loadProofs()
      await reloadCustodiansRef.current?.()
    } catch (err) {
      console.error(err)
      showToast(err?.message || 'Unable to delete documentation', { variant: 'error' })
    } finally {
      setDeletingProofId(null)
    }
  }, [apiBase, caseId, confirmDialog, loadProofs, reloadCustodiansRef, showToast])

  const updateProofCountsOnCase = useCallback((proofCount, consentCount = null) => {
    setCaseData(prev => {
      if (!prev) return prev
      const updated = {
        ...prev,
        consent_proof_count: Math.max(0, Number(proofCount) || 0),
      }
      if (consentCount !== null && consentCount !== undefined) {
        updated.consent_envelope_count = Math.max(0, Number(consentCount) || 0)
      }
      if (caseId) caseCache.set(caseId, updated)
      return updated
    })
  }, [caseId, setCaseData])

  return {
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
  }
}
