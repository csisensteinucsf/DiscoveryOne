import { useEffect, useMemo, useState } from 'react'
import { useToast } from '../components/ToastProvider.jsx'
import Modal from '../components/Modal.jsx'
import { Field, TextInput, Button, Badge } from './caseDetailControls.jsx'
import { formatNameRaw } from './caseDetailUtils.js'
import { normalizeSearchDraftFields, serverSuggestSearches } from './caseDetailPersistence.js'
export function SearchAiBuilderModal({ caseId, caseData, custodians, onClose, onUseSuggestion, onCreateSuggestions, searchQueryLabel = 'Provider query' }) {
  const { showToast } = useToast()
  const [objective, setObjective] = useState('')
  const [filter, setFilter] = useState('')
  const [selectedIds, setSelectedIds] = useState(() => (custodians || []).map(c => Number(c.id)).filter(Number.isFinite))
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)

  useEffect(() => {
    setSelectedIds((custodians || []).map(c => Number(c.id)).filter(Number.isFinite))
    setResult(null)
    setError('')
  }, [caseId])

  useEffect(() => {
    const available = new Set((custodians || []).map(c => Number(c.id)).filter(Number.isFinite))
    setSelectedIds(prev => {
      const current = Array.isArray(prev) ? prev.map(Number).filter(Number.isFinite) : []
      const next = current.filter(id => available.has(id))
      if (next.length === current.length) return prev
      return next
    })
  }, [custodians])

  const sortedCustodians = useMemo(() => {
    return [...(custodians || [])].sort((a, b) => (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' }))
  }, [custodians])

  const filteredCustodians = useMemo(() => {
    if (!filter.trim()) return sortedCustodians
    const q = filter.trim().toLowerCase()
    return sortedCustodians.filter(c =>
      (c.name || '').toLowerCase().includes(q) ||
      (c.email || '').toLowerCase().includes(q)
    )
  }, [filter, sortedCustodians])

  const custodianLabelById = useMemo(() => {
    const map = new Map()
    ;(custodians || []).forEach(c => {
      const id = Number(c?.id)
      if (!Number.isFinite(id)) return
      const label = formatNameRaw(c?.name) || String(c?.email || "").trim() || `Custodian ${id}`
      map.set(id, label)
    })
    return map
  }, [custodians])

  function suggestionCustodianNames(suggestion) {
    const ids = Array.isArray(suggestion?.custodian_ids)
      ? suggestion.custodian_ids.map(Number).filter(Number.isFinite)
      : []
    if (!ids.length) return 'None assigned'
    const labels = ids.map(id => custodianLabelById.get(id) || `Custodian ${id}`)
    return labels.join('; ')
  }
  function toggleAssignAll() {
    const allIds = sortedCustodians.map(c => Number(c.id)).filter(Number.isFinite)
    const current = new Set((selectedIds || []).map(Number))
    const isAll = allIds.length > 0 && allIds.every(id => current.has(id))
    setSelectedIds(isAll ? [] : allIds)
  }

  function toggleAssign(id) {
    const n = Number(id)
    const next = new Set((selectedIds || []).map(Number))
    if (next.has(n)) next.delete(n)
    else next.add(n)
    setSelectedIds(Array.from(next))
  }

  async function handleGenerate() {
    if (!caseId) return
    setLoading(true)
    setError('')
    try {
      const payload = {
        objective: objective.trim() || null,
        draft: {
          custodian_ids: (selectedIds || []).map(Number).filter(Number.isFinite),
        },
      }
      const data = await serverSuggestSearches(caseId, payload)
      if (data?.status !== 'ok') {
        throw new Error(data?.error || 'AI search suggestions failed')
      }
      const suggestions = Array.isArray(data?.suggestions) ? data.suggestions : []
      setResult({
        summary: data?.summary || '',
        suggestions,
      })
      if (!suggestions.length) {
        showToast('Versa returned no search suggestions.', { variant: 'warn' })
      } else {
        showToast(`Versa generated ${suggestions.length} search suggestion${suggestions.length === 1 ? '' : 's'}.`, { variant: 'success' })
      }
    } catch (err) {
      const message = err?.message || 'Unable to generate AI search suggestions.'
      setError(message)
      showToast(message, { variant: 'error' })
    } finally {
      setLoading(false)
    }
  }

  async function handleCreateAll() {
    if (!result?.suggestions?.length || creating) return
    setCreating(true)
    try {
      await Promise.resolve(onCreateSuggestions(result.suggestions))
    } finally {
      setCreating(false)
    }
  }

  async function handleCreateOne(suggestion) {
    if (!suggestion || creating) return
    setCreating(true)
    try {
      await Promise.resolve(onCreateSuggestions([suggestion]))
    } finally {
      setCreating(false)
    }
  }

  async function copyQuery(query) {
    const text = String(query || '').trim()
    if (!text) {
      showToast(`No ${searchQueryLabel.toLowerCase()} available to copy.`, { variant: 'warn' })
      return
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const el = document.createElement('textarea')
        el.value = text
        el.setAttribute('readonly', '')
        el.style.position = 'absolute'
        el.style.left = '-9999px'
        document.body.appendChild(el)
        el.select()
        document.execCommand('copy')
        document.body.removeChild(el)
      }
      showToast(`${searchQueryLabel} copied to clipboard.`, { variant: 'success' })
    } catch {
      showToast(`Unable to copy ${searchQueryLabel.toLowerCase()}.`, { variant: 'error' })
    }
  }

  const canGenerate = !loading && !creating

  return (
    <Modal
      open
      title="Versa Powered Search Builder"
      onClose={onClose}
      width={980}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ color: '#6b7280', fontSize: 12 }}>
            Case: <strong>{caseData?.name || '-'}</strong>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button variant="ghost" onClick={onClose} disabled={loading || creating}>Close</Button>
            <Button onClick={handleGenerate} disabled={!canGenerate}>{loading ? 'Generating...' : 'Generate Suggestions'}</Button>
          </div>
        </div>
      )}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 12 }}>
        <Field label="Search requirements / outcomes">
          <textarea
            rows={4}
            style={{ width: '100%', border: '1px solid #dce0e5', borderRadius: 10, padding: 10 }}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            placeholder="Enter search requirements/outcomes here. You can enter multiple requirements and the search tool will try to build suggestions."
          />
        </Field>
        <div style={{ fontSize: 12, color: '#475467' }}>
          Versa returns one search by default. It only splits into multiple suggestions when your objective contains clearly distinct requirements.
        </div>
      </div>

      <div style={{ marginTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <div className="row" style={{ gap: 8 }}>
          <Button variant="subtle" onClick={toggleAssignAll}>
            {selectedIds.length === sortedCustodians.length ? 'Unassign all custodians' : 'Assign all custodians'}
          </Button>
          <span style={{ fontSize: 12, color: '#6b7280' }}>{selectedIds.length} selected</span>
        </div>
        <div style={{ minWidth: 280 }}>
          <TextInput placeholder="Filter custodians by name or email" value={filter} onChange={e => setFilter(e.target.value)} />
        </div>
      </div>
      <div style={{ marginTop: 10, maxHeight: 220, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 10, padding: 10 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead style={{ background: 'rgba(0,0,0,.03)' }}>
            <tr>
              <th style={{ textAlign: 'left', padding: 8 }}>Assign</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Name</th>
              <th style={{ textAlign: 'left', padding: 8 }}>Email</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustodians.map(c => (
              <tr key={c.id}>
                <td style={{ padding: 8 }}><input type="checkbox" checked={selectedIds.includes(c.id)} onChange={() => toggleAssign(c.id)} /></td>
                <td style={{ padding: 8 }}>{formatNameRaw(c.name) || '-'}</td>
                <td style={{ padding: 8 }}><Badge variant="orange" compact>{c.email || '-'}</Badge></td>
              </tr>
            ))}
            {!filteredCustodians.length && (
              <tr><td style={{ padding: 8 }} colSpan={3}><em>No custodians match this filter.</em></td></tr>
            )}
          </tbody>
        </table>
      </div>

      {error ? <div style={{ marginTop: 10, color: '#b91c1c', fontSize: 13 }}>{error}</div> : null}

      {result && (
        <div style={{ marginTop: 14, borderTop: '1px solid #e5e7eb', paddingTop: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <h4 style={{ margin: 0 }}>Versa Suggestions</h4>
            {result.suggestions?.length > 1 ? (
              <Button variant="primary" onClick={handleCreateAll} disabled={creating}>{creating ? 'Creating...' : 'Create All Versa Suggestions'}</Button>
            ) : null}
          </div>
          {result.summary ? <div style={{ marginTop: 6, color: '#475467', fontSize: 13 }}>{result.summary}</div> : null}
          <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
            {(result.suggestions || []).map((s, idx) => (
              <div key={`ai-search-suggestion-${idx}`} style={{ border: '1px solid #dbe2ea', borderRadius: 10, padding: 10, background: '#f8fafc' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong>{`Suggestion ${idx + 1}`}</strong>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <Button variant="subtle" onClick={() => onUseSuggestion(s)}>Use In Search Form</Button>
                    <Button variant="subtle" onClick={() => copyQuery(s.kql)} disabled={!String(s?.kql || '').trim()}>Copy Query</Button>
                    <Button variant="primary" onClick={() => handleCreateOne(s)} disabled={creating}>{creating ? 'Creating...' : 'Create This Versa Search'}</Button>
                  </div>
                </div>
                {s.rationale ? <div style={{ marginTop: 6, fontSize: 12, color: '#475467' }}>{s.rationale}</div> : null}
                <div style={{ marginTop: 6, fontSize: 12, color: '#334155' }}><strong>Custodians:</strong> {suggestionCustodianNames(s)}</div>
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{searchQueryLabel}</div>
                  <div style={{ border: '1px solid #dbe2ea', borderRadius: 8, background: '#ffffff', padding: 8, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {String(s.kql || '').trim() || '-'}
                  </div>
                </div>
                <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div><strong>Keywords:</strong> {s.keywords || '-'}</div>
                  <div><strong>Search overview:</strong> {s.additional || '-'}</div>
                  <div><strong>Senders:</strong> {s.senders || '-'}</div>
                  <div><strong>Recipients:</strong> {s.recipients || '-'}</div>
                  <div><strong>Date From:</strong> {s.date_from || '-'}</div>
                  <div><strong>Date To:</strong> {s.date_to || '-'}</div>
                </div>
              </div>
            ))}
            {!(result.suggestions || []).length && (
              <div style={{ color: '#6b7280', fontSize: 13 }}><em>No suggestions returned. Adjust objective/details and try again.</em></div>
            )}
          </div>
        </div>
      )}
    </Modal>
  )
}
// Search Modal
export function SearchModal({ mode, draft, suggestedName, readOnly = false, custodians, onClose, onSave, searchQueryLabel = 'Provider query' }) {
  const hydrateDraft = (value) => {
    const next = { ...value, ...normalizeSearchDraftFields(value) }
    if (mode === 'create' && !(String(next.name || '').trim()) && suggestedName) next.name = suggestedName
    return next
  }
  const [d, setD] = useState(() => hydrateDraft(draft))
  const [filter, setFilter] = useState('')
  useEffect(() => setD(hydrateDraft(draft)), [draft, mode, suggestedName])
  const sortedCustodians = useMemo(() => {
    return [...(custodians || [])].sort((a, b) => {
      return (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' })
    })
  }, [custodians])
  const filteredCustodians = useMemo(() => {
    if (!filter.trim()) return sortedCustodians
    const q = filter.toLowerCase()
    return sortedCustodians.filter(c =>
      (c.name || '').toLowerCase().includes(q) ||
      (c.email || '').toLowerCase().includes(q)
    )
  }, [filter, sortedCustodians])
  const { showToast } = useToast()

  async function copyAssignedCustodians() {
    const selected = new Set((d.custodianIds || []).map(Number))
    const seen = new Set()
    const emails = []
    for (const c of (sortedCustodians || [])) {
      const id = Number(c?.id)
      if (!selected.has(id)) continue
      const email = String(c?.email || '').trim()
      if (!email) continue
      const key = email.toLowerCase()
      if (seen.has(key)) continue
      seen.add(key)
      emails.push(email)
    }
    const payload = emails.join(';')
    if (!payload) {
      showToast('No assigned custodian emails to copy.', { variant: 'warn' })
      return
    }
    try {
      await navigator.clipboard.writeText(payload)
      showToast(`Copied ${emails.length} custodian email${emails.length === 1 ? '' : 's'}.`, { variant: 'success' })
    } catch {
      const ta = document.createElement('textarea')
      ta.value = payload
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
        showToast(`Copied ${emails.length} custodian email${emails.length === 1 ? '' : 's'}.`, { variant: 'success' })
      } catch {
        showToast('Copy failed. Here is the list:\n' + payload, { variant: 'error' })
      } finally {
        document.body.removeChild(ta)
      }
    }
  }


  function toggleAssignAll() {
  const allIds = sortedCustodians.map(c => Number(c.id));
  const current = new Set((d.custodianIds || []).map(Number));
  const isAll = allIds.length > 0 && allIds.every(id => current.has(id));
  setD({ ...d, custodianIds: isAll ? [] : allIds });
}
  function toggleAssign(id) {
  const n = Number(id);
  const current = new Set((d.custodianIds || []).map(Number));
  if (current.has(n)) current.delete(n); else current.add(n);
  setD({ ...d, custodianIds: Array.from(current) });
}
  function updateSearchDraftFields(updates) {
    const next = { ...d, ...updates }
    setD({ ...next, ...normalizeSearchDraftFields(next) })
  }
  // allow zero when editing so you can unassign all custodians
  const canSave = !readOnly && (mode === 'edit' ? true : (d.custodianIds || []).length > 0)
  return (
    <Modal
      open
      title={readOnly ? 'Search Details' : ((mode === 'create' ? 'Create' : 'Edit') + ' Search')}
      onClose={onClose}
      width={900}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant='ghost' onClick={onClose}>{readOnly ? 'Close' : 'Cancel'}</Button>
          {!readOnly && <Button onClick={() => onSave(d)} disabled={!canSave}>{mode === 'create' ? 'Create' : 'Save'}</Button>}
        </div>
      )}
    >
      <fieldset disabled={readOnly} style={{ border: 0, padding: 0, margin: 0, minInlineSize: 0 }}>
      <Field label="Search Name">
        <TextInput value={d.name || ''} onChange={e => setD({ ...d, name: e.target.value })} placeholder="e.g., 2025-Yellow-Search 2" />
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
          Leave blank to auto-name. You can rename existing searches here to fix duplicates.
        </div>
      </Field>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label="Search overview">
            <textarea rows={3} style={{width:'100%',border:'1px solid #dce0e5',borderRadius:10,padding:10}} value={d.searchOverview || ''} onChange={e => updateSearchDraftFields({ searchOverview: e.target.value })} />
          </Field>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <Field label={searchQueryLabel}>
            <textarea rows={4} style={{width:'100%',border:'1px solid #dce0e5',borderRadius:10,padding:10,fontFamily:'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'}} value={d.providerQuery || ''} onChange={e => updateSearchDraftFields({ providerQuery: e.target.value })} />
          </Field>
        </div>
        <Field label="Keywords"><textarea rows={3} style={{width:'100%',border:'1px solid #dce0e5',borderRadius:10,padding:10}} value={d.keywords || ''} onChange={e => setD({...d, keywords:e.target.value})} /></Field>
        <Field label="Senders"><textarea rows={2} style={{width:'100%',border:'1px solid #dce0e5',borderRadius:10,padding:10}} value={d.senders || ''} onChange={e => setD({...d, senders:e.target.value})} /></Field>
        <Field label="Recipients"><textarea rows={2} style={{width:'100%',border:'1px solid #dce0e5',borderRadius:10,padding:10}} value={d.recipients || ''} onChange={e => setD({...d, recipients:e.target.value})} /></Field>
        <Field label="Date From"><TextInput type="date" value={d.dateFrom || ''} onChange={e => setD({...d, dateFrom:e.target.value})} /></Field>
        <Field label="Date To"><TextInput type="date" value={d.dateTo || ''} onChange={e => setD({...d, dateTo:e.target.value})} /></Field>
      </div>
      <div style={{ marginTop: 10, display:'flex', justifyContent:'space-between', alignItems:'center', gap:8, flexWrap:'wrap' }}>
        <div className="row" style={{ gap:8 }}>
          <Button variant="subtle" onClick={toggleAssignAll}>
            {d.custodianIds.length === sortedCustodians.length ? 'Unassign all' : 'Assign to all'}
          </Button>
          <Button variant="subtle" onClick={copyAssignedCustodians}>Copy custodians</Button>
        </div>
        <div style={{ minWidth: 280 }}>
          <TextInput placeholder="Search custodians by name or email" value={filter} onChange={e => setFilter(e.target.value)} />
        </div>
      </div>
      <div style={{ marginTop: 10, maxHeight: 260, overflow: 'auto', border: '1px solid #e5e7eb', borderRadius: 10, padding: 10 }}>
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead style={{ background:'rgba(0,0,0,.03)' }}>
            <tr>
              <th style={{ textAlign:'left', padding:8 }}>Assign</th>
              <th style={{ textAlign:'left', padding:8 }}>Name</th>
              <th style={{ textAlign:'left', padding:8 }}>Email</th>
            </tr>
          </thead>
          <tbody>
            {filteredCustodians.map(c => (
              <tr key={c.id}>
                <td style={{ padding:8 }}>
                  <input type="checkbox" checked={d.custodianIds.includes(c.id)} onChange={() => toggleAssign(c.id)} />
                </td>
                <td style={{ padding:8 }}>{formatNameRaw(c.name) || '-'}</td>
                <td style={{ padding:8 }}><Badge variant="orange" compact>{c.email || '-'}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </fieldset>
    </Modal>
  )
}
