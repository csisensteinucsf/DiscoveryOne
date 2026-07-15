import { useRef, useState } from 'react'

function buildCaseDetailEntries(cases = []) {
  return (cases || [])
    .filter(c => c?.id && c?.name)
    .map(c => ({
      id: c.id,
      name: c.name,
      legal_case_name: c.legal_case_name || '',
      requestor_email: c.requestor_email || c.requestor || '',
      claimant: c.claimant || '',
      analyst_id: null,
      saving: false,
      status: null,
    }))
}

export function useSystemImportsWorkflow({ apiBase, isSysAdmin, showToast }) {
  const [importFiles, setImportFiles] = useState([])
  const [importing, setImporting] = useState(false)
  const [importStatus, setImportStatus] = useState(null)
  const [importResult, setImportResult] = useState(null)
  const [importLog, setImportLog] = useState('')
  const [importCaseDetails, setImportCaseDetails] = useState([])
  const [importFinalizeIdx, setImportFinalizeIdx] = useState(null)
  const importInputRef = useRef(null)
  const importFolderInputRef = useRef(null)

  const addImports = (picked) => {
    setImportFiles((prev) => {
      const next = [...prev]
      const seen = new Set(next.map((f) => f.webkitRelativePath || f.name))
      picked.forEach((file) => {
        const key = file.webkitRelativePath || file.name
        if (!seen.has(key)) {
          next.push(file)
          seen.add(key)
        }
      })
      return next
    })
  }

  const onSelectImportFiles = (e) => {
    const picked = Array.from(e.target.files || [])
    addImports(picked)
    setImportStatus(null)
  }

  const onSelectImportFolder = (e) => {
    const picked = Array.from(e.target.files || [])
    addImports(picked)
    setImportStatus(null)
  }

  const clearImportSelection = () => {
    setImportFiles([])
    setImportStatus(null)
    setImportLog('')
    setImportFinalizeIdx(null)
    if (importInputRef.current) importInputRef.current.value = ''
    if (importFolderInputRef.current) importFolderInputRef.current.value = ''
  }

  const updateImportCaseField = (id, field, value) => {
    setImportCaseDetails(prev => prev.map(item => item.id === id ? { ...item, [field]: value } : item))
  }

  const saveImportedCase = async (id) => {
    const entry = importCaseDetails.find(c => c.id === id)
    if (!entry) return false
    const payload = {}
    if (entry.legal_case_name && entry.legal_case_name.trim()) payload.legal_case_name = entry.legal_case_name.trim()
    if (entry.requestor_email && entry.requestor_email.trim()) payload.requestor = entry.requestor_email.trim()
    if (entry.claimant && entry.claimant.trim()) payload.claimant = entry.claimant.trim()
    if (entry.analyst_id) payload.analyst_id = entry.analyst_id
    if (!Object.keys(payload).length) {
      updateImportCaseField(id, 'status', 'Add at least one detail to save.')
      return false
    }
    setImportCaseDetails(prev => prev.map(item => item.id === id ? { ...item, saving: true, status: null } : item))
    try {
      const res = await fetch(`${apiBase}/cases/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => 'Unable to save case details')
        throw new Error(text || 'Unable to save case details')
      }
      setImportCaseDetails(prev => prev.map(item => item.id === id ? { ...item, saving: false, status: 'Saved' } : item))
      showToast(`Updated case details for ${entry.name}`, { variant: 'success' })
      return true
    } catch (err) {
      console.error(err)
      setImportCaseDetails(prev => prev.map(item => item.id === id ? { ...item, saving: false, status: err?.message || 'Save failed' } : item))
      return false
    }
  }

  const runImport = async () => {
    setImportStatus('Import running...')
    if (!isSysAdmin) {
      setImportStatus('Only system administrators can run imports.')
      return
    }
    if (!importFiles.length) {
      setImportStatus('Please select one or more files first.')
      return
    }
    setImportCaseDetails([])
    setImportResult(null)
    setImportLog('')
    setImporting(true)
    try {
      const fd = new FormData()
      importFiles.forEach((file, idx) => {
        const name = file.webkitRelativePath || file.name || `case-${idx + 1}.xlsx`
        fd.append('files', file, name)
      })
      const res = await fetch(`${apiBase}/system/import`, {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'import_failed')
      }
      const data = await res.json().catch(() => null)
      if (!data) throw new Error('invalid_response')
      setImportResult(data)
      setImportStatus('Import completed.')
      setImportLog(data.log_text || '')
      setImportCaseDetails(buildCaseDetailEntries(data.created_cases))
      setImportFinalizeIdx(data.created_cases?.length ? 0 : null)
      setImportFiles([])
      if (importInputRef.current) importInputRef.current.value = ''
      if (importFolderInputRef.current) importFolderInputRef.current.value = ''
      if (data?.log_path) {
        showToast(`Import report saved in ${data.log_path}`, { variant: 'info' })
      }
    } catch (err) {
      console.error(err)
      setImportResult(null)
      const msg = err?.message || 'Import failed. Check the import report for details.'
      setImportStatus(msg)
      setImportLog(msg)
    } finally {
      setImporting(false)
    }
  }

  const currentFinalizeCase = (importFinalizeIdx !== null && importFinalizeIdx < importCaseDetails.length)
    ? importCaseDetails[importFinalizeIdx]
    : null

  const handleFinalizeAdvance = async () => {
    const current = currentFinalizeCase
    if (!current) {
      setImportFinalizeIdx(null)
      return
    }
    const ok = await saveImportedCase(current.id)
    if (!ok) return
    if (importFinalizeIdx >= importCaseDetails.length - 1) {
      setImportFinalizeIdx(null)
      showToast('All imported cases finalized.', { variant: 'success' })
    } else {
      setImportFinalizeIdx((prev) => (prev === null ? 0 : prev + 1))
    }
  }

  return {
    importInputRef,
    importFolderInputRef,
    importFiles,
    importing,
    importStatus,
    importResult,
    importLog,
    importCaseDetails,
    importFinalizeIdx,
    currentFinalizeCase,
    onSelectImportFiles,
    onSelectImportFolder,
    clearImportSelection,
    runImport,
    setImportFinalizeIdx,
    updateImportCaseField,
    handleFinalizeAdvance,
  }
}