import { useCallback, useState } from 'react'
import { genId, makeCustodian } from './caseRequestsUtils.js'

export function useCaseRequestCustodianUpload({
  apiBase,
  setForm,
  setHoldOpen,
  resetLookupResults,
  showToast,
  setError,
}) {
  const [custodianFileBusy, setCustodianFileBusy] = useState(false)

  const resetCustodianUpload = useCallback(() => {
    setCustodianFileBusy(false)
  }, [])

  const loadCustodiansFromUpload = useCallback(async (file) => {
    if (!file) return
    setCustodianFileBusy(true)
    setError('')
    try {
      const fd = new FormData()
      fd.append('custodian_file', file)
      const res = await fetch(`${apiBase}/case_requests/parse_custodian_file`, {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })
      const data = await res.json().catch(() => null)
      if (!res.ok) {
        const detail = data?.detail || data?.message
        throw new Error(detail || 'Unable to parse uploaded custodian file.')
      }
      const rows = Array.isArray(data?.custodians) ? data.custodians : []
      if (!rows.length) {
        throw new Error('Uploaded file did not contain any valid custodian rows.')
      }
      const roster = rows.map((row) => {
        const base = makeCustodian()
        return {
          ...base,
          id: genId(),
          name: (row?.name || '').trim(),
          email: (row?.email || '').trim(),
          notes: (row?.notes || '').trim(),
        }
      }).filter((c) => (c.name || '').trim())
      if (!roster.length) {
        throw new Error('Uploaded file did not contain any valid custodian rows.')
      }
      setForm((prev) => ({
        ...prev,
        custodianMode: 'upload',
        custodianFile: file,
        pasteText: '',
        custodians: roster,
      }))
      setHoldOpen({})
      resetLookupResults()

      showToast(`Loaded ${roster.length} custodians from file.`, { variant: 'success' })
    } catch (err) {
      console.error(err)
      setForm((prev) => ({ ...prev, custodianFile: file, custodians: [] }))
      setError(err?.message || 'Unable to load uploaded custodian file.')
    } finally {
      setCustodianFileBusy(false)
    }
  }, [apiBase, resetLookupResults, setError, setForm, setHoldOpen, showToast])

  return {
    custodianFileBusy,
    loadCustodiansFromUpload,
    resetCustodianUpload,
  }
}