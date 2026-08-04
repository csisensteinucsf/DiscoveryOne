import { useCallback, useMemo, useRef, useState } from 'react'
import { personLookupFieldsFromRecord } from './caseDetailPersonLookupFields.js'
import { normalizeOptionalHoldIds } from './holdAssignmentUtils.js'

const normalizeEmail = (value) => (value || '').trim().toLowerCase()

export function useCaseDetailCustodianImport({ apiBase, caseId, custodians, targetHoldIds = [] }) {
  const [importWorking, setImportWorking] = useState(false)
  const [importDone, setImportDone] = useState(0)
  const [importTotal, setImportTotal] = useState(0)
  const [addCustodiansWorking, setAddCustodiansWorking] = useState(false)
  const addCustodiansWorkingRef = useRef(false)

  const existingEmails = useMemo(
    () => new Set((custodians || []).map(c => normalizeEmail(c.email)).filter(Boolean)),
    [custodians]
  )

  const submitCustodianBatch = useCallback(async (rows) => {
    const normalizedHoldIds = normalizeOptionalHoldIds(targetHoldIds)
    const seen = new Set()
    const toCreate = []
    for (const row of rows) {
      const name = row.name?.trim()
      let emailNorm = normalizeEmail(row.email)
      if (emailNorm === 'noemail' || emailNorm === 'unmatched') emailNorm = ''
      if (!name) continue
      if (emailNorm && (existingEmails.has(emailNorm) || seen.has(emailNorm))) continue
      if (emailNorm) seen.add(emailNorm)
      toCreate.push({
        name,
        email: row.email?.trim() || null,
        ...personLookupFieldsFromRecord(row),
        person_lookup_overridden: !!row.person_lookup_overridden,
      })
    }
    setImportTotal(toCreate.length)
    setImportDone(0)
    if (!toCreate.length) {
      return {
        created: [],
        createdCount: 0,
        duplicateCount: 0,
        localDuplicateCount: rows.length,
        failedCount: 0,
        errors: [],
        submittedCount: 0,
      }
    }
    const res = await fetch(`${apiBase}/cases/${caseId}/custodians/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ custodians: toCreate, hold_ids: normalizedHoldIds }),
    })
    let body = null
    try {
      body = await res.json()
    } catch {
      body = null
    }
    if (!res.ok) {
      const detail = String(body?.detail || body?.message || '').trim()
      throw new Error(detail || `HTTP ${res.status}`)
    }
    const created = Array.isArray(body?.created) ? body.created : []
    const createdCount = Number.isFinite(Number(body?.created_count)) ? Number(body.created_count) : created.length
    const duplicateCount = Number.isFinite(Number(body?.duplicate_count)) ? Number(body.duplicate_count) : 0
    const failedCount = Number.isFinite(Number(body?.failed_count)) ? Number(body.failed_count) : 0
    const errors = Array.isArray(body?.errors)
      ? body.errors.map((value) => String(value || '').trim()).filter(Boolean)
      : []
    setImportDone(toCreate.length)
    return {
      created,
      createdCount,
      duplicateCount,
      localDuplicateCount: rows.length - toCreate.length,
      failedCount,
      errors,
      submittedCount: toCreate.length,
    }
  }, [apiBase, caseId, existingEmails, targetHoldIds])

  const submitCustodianBulkUpdate = useCallback(async ({ ids = [], patch = null, updates = [] } = {}) => {
    const payload = Array.isArray(updates) && updates.length
      ? { updates }
      : { ids: Array.isArray(ids) ? ids : [], patch }
    const res = await fetch(`${apiBase}/cases/${caseId}/custodians`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
    let body = null
    try {
      body = await res.json()
    } catch {
      body = null
    }
    if (!res.ok) {
      const detail = String(body?.detail || body?.message || '').trim()
      throw new Error(detail || `HTTP ${res.status}`)
    }
    return Array.isArray(body?.updated) ? body.updated : []
  }, [apiBase, caseId])

  return {
    importWorking,
    setImportWorking,
    importDone,
    setImportDone,
    importTotal,
    setImportTotal,
    addCustodiansWorking,
    setAddCustodiansWorking,
    addCustodiansWorkingRef,
    submitCustodianBatch,
    submitCustodianBulkUpdate,
  }
}
