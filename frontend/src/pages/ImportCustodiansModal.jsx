import { Fragment, useCallback, useMemo, useRef, useState } from 'react'
import Modal from '../components/Modal.jsx'
import FileDropZone from '../components/FileDropZone.jsx'
import HoldAssignmentPicker from './HoldAssignmentPicker.jsx'
import { Field, TextInput, Button, Badge } from './caseDetailControls.jsx'
import {
  employmentEndDateColor,
  isValidEmail,
  lookupPersonName,
  lookupPersonId,
} from './caseDetailUtils.js'
import { emptyPersonLookupFields, personLookupFieldsFromMatch } from './caseDetailPersonLookupFields.js'

export function ImportCustodiansModal({
  apiBase = '/api',
  caseId,
  holds = [],
  selectedHoldIds = [],
  onSelectedHoldIdsChange,
  onHoldCreated,
  onClose,
  onImport,
  progress,
  onSwitchToAdd,
  employeeIdLabel = 'Employee ID',
  personLookupEnabled = false,
}) {
  const [mode, setMode] = useState('paste')
  const [text, setText] = useState('')
  const [rows, setRows] = useState([])
  const [error, setError] = useState(null)
  const [firstRowHeader, setFirstRowHeader] = useState(true)
  const [lookupBusy, setLookupBusy] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const [lookupResults, setLookupResults] = useState({}) // idx -> { matches, selection, override }
  const [lookupHasRun, setLookupHasRun] = useState(false)
  const lookupRequestRef = useRef(0)
  const normalizeRows = useCallback((list) => (Array.isArray(list) ? list.filter(r => (r.name || '').trim()) : []), [])
  const nonEmptyRows = useMemo(() => (Array.isArray(rows) ? rows.filter(r => (r.name || '').trim() || (r.email || '').trim()) : []), [rows])

  const invalidateLookup = useCallback(() => {
    lookupRequestRef.current += 1
    setLookupBusy(false)
    setLookupError('')
    setLookupHasRun(false)
    setLookupResults({})
  }, [])

  const applyMatchToRow = useCallback((idx, match) => {
    if (!match && match !== null) return
    setRows((prev) => prev.map((row, i) => {
      if (i !== idx) return row
      const next = { ...row }
      const full = lookupPersonName(match)
      if (full) next.name = full
      if (match?.email) next.email = match.email
      Object.assign(next, personLookupFieldsFromMatch(match))
      return next
    }))
  }, [])

  function parseText(t){
    setError(null)
    const lines = (t || '').split(/\r?\n/).map(s => s.trim()).filter(Boolean)
    invalidateLookup()
    if (!lines.length) { setRows([]); return }
    const out = []
    const headerLike = lines[0].toLowerCase().includes('name') && lines[0].toLowerCase().includes('email')
    for (let i = 0; i < lines.length; i++) {
      if (i === 0 && headerLike) continue
      const parts = lines[i].split(/[,\t;]+/).map(s => s.trim())
      if (!parts.length) continue
      const name = parts[0] || ''
      const email = (parts[1] || '')
      if (!name && !email) continue
      out.push({ name, email })
    }
    setRows(out)
  }
  function onFile(e){
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      try { parseText(String(reader.result || '')) }
      catch { setError('Could not parse file') }
    }
    reader.readAsText(f)
  }

  const runLookup = async () => {
    const roster = normalizeRows(rows).map((r, idx) => ({
      id: String(idx),
      name: r.name || '',
      email: r.email || '',
    })).filter(r => (r.name || '').trim())
    if (!roster.length) return
    const requestId = lookupRequestRef.current + 1
    lookupRequestRef.current = requestId
    setLookupBusy(true)
    setLookupError('')
    setLookupHasRun(false)
    try {
      const res = await fetch(`${apiBase}/case_requests/custodian_lookup`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ custodians: roster }),
      })
      if (!res.ok) throw new Error(await res.text() || 'Lookup failed')
      const data = await res.json()
      if (lookupRequestRef.current !== requestId) return
      const resultsMap = {}
      for (const item of data?.results || []) {
        const idx = Number(item.id)
        if (Number.isNaN(idx)) continue
        const matches = Array.isArray(item.matches) ? item.matches.filter(Boolean) : []
        const error = (item?.error || '').trim() || null
        resultsMap[idx] = { matches, selection: matches.length === 1 ? 0 : null, override: matches.length === 0, error }
        if (matches.length === 1) {
          applyMatchToRow(idx, matches[0])
        }
      }
      setLookupResults(resultsMap)
    } catch (err) {
      if (lookupRequestRef.current !== requestId) return
      const message = (err?.message || '').trim() || 'Lookup failed'
      setLookupError(message)
      const fallback = {}
      for (const item of roster) {
        const idx = Number(item.id)
        if (Number.isNaN(idx)) continue
        fallback[idx] = { matches: [], selection: null, override: true, error: message }
      }
      setLookupResults(fallback)
    } finally {
      if (lookupRequestRef.current !== requestId) return
      setLookupBusy(false)
      setLookupHasRun(true)
    }
  }
  const validation = useMemo(() => {
    const issues = []
    const list = normalizeRows(rows)
    if (!personLookupEnabled) {
      if (!nonEmptyRows.length) {
        issues.push('Import at least one custodian with a name and email.')
      }
      nonEmptyRows.forEach((row, idx) => {
        const name = (row?.name || '').trim()
        const email = (row?.email || '').trim()
        if (!name) issues.push(`Row ${idx + 1}: name is required.`)
        if (!email) issues.push(`Row ${idx + 1}: email is required.`)
        if (email && !isValidEmail(email)) issues.push(`Row ${idx + 1}: email must be valid.`)
      })
      return { ok: issues.length === 0, issues }
    }
    for (let i = 0; i < list.length; i++) {
      const name = (list[i]?.name || '').trim()
      if (!name) continue
      const res = lookupResults[i]
      if (!res) {
        issues.push(`Row ${i + 1}: lookup not completed yet.`)
        continue
      }
      if (res.override) continue
      const matches = Array.isArray(res.matches) ? res.matches.filter(Boolean) : []
      if (matches.length === 0) {
        issues.push(`Row ${i + 1}: no person match found; enable override to import anyway.`)
        continue
      }
      if (res.selection == null) {
        issues.push(`Row ${i + 1}: select a person match or enable override.`)
      }
    }
    return { ok: issues.length === 0, issues }
  }, [nonEmptyRows, personLookupEnabled, rows, lookupResults, normalizeRows])
  const canImport = personLookupEnabled
    ? !!rows.length && lookupHasRun && !lookupBusy && !progress?.working && validation.ok
    : !!nonEmptyRows.length && !progress?.working && validation.ok
  return (
    <Modal
      open
      title="Import Custodians"
      onClose={onClose}
      width={780}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="ghost" onClick={onClose} disabled={progress?.working}>Cancel</Button>
          <Button onClick={() => onImport(rows.map((r, idx) => {
            if (!personLookupEnabled) return { ...r, person_lookup_overridden: false }
            const override = !!lookupResults[idx]?.override
            if (!override) return { ...r, person_lookup_overridden: false }
            return {
              ...r,
              person_lookup_overridden: true,
              ...emptyPersonLookupFields(),
            }
          }))} disabled={!canImport} title={!canImport ? (validation.issues[0] || (personLookupEnabled ? 'Run person lookup first' : 'Enter names and valid email addresses')) : ''}>
            {progress?.working ? 'Importing...' : `Import ${rows.length ? `(${rows.length})` : ''}`}
          </Button>
        </div>
      )}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, gap: 8 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#0f172a' }}>Import options</div>
        {onSwitchToAdd && (
          <Button variant="subtle" onClick={onSwitchToAdd} disabled={progress?.working}>Back to manual add</Button>
        )}
      </div>
      <HoldAssignmentPicker
        apiBase={apiBase}
        caseId={caseId}
        holds={holds}
        selectedHoldIds={selectedHoldIds}
        onSelectedHoldIdsChange={onSelectedHoldIdsChange}
        onHoldCreated={onHoldCreated}
        disabled={!!progress?.working}
      />
      {progress?.working && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ height: 10, background:'#eef2f7', borderRadius: 999, overflow:'hidden' }}>
            <div style={{ height:'100%', width: `${progress.total ? Math.round(progress.done*100/progress.total) : 0}%` }} />
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color:'#6b7280' }}>
            Importing {progress.done} of {progress.total}...
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
        <Button variant={mode==='paste' ? 'primary':'subtle'} onClick={() => setMode('paste')}>Paste</Button>
        <Button variant={mode==='file' ? 'primary':'subtle'} onClick={() => setMode('file')}>CSV file</Button>
      </div>
      {mode === 'paste' ? (
        <Field label="Paste rows (first two columns: name, email)">
          <label style={{ display:'inline-flex', alignItems:'center', gap:6, marginBottom:8 }}>
            <input type="checkbox" checked={firstRowHeader} onChange={e => setFirstRowHeader(e.target.checked)} />
            First row is a header
          </label>
          <textarea
            value={text}
            onChange={e => { setText(e.target.value); parseText(e.target.value) }}
            rows={8}
            style={{ width:'100%', border:'1px solid #dce0e5', borderRadius: 10, padding: 10, fontFamily:'ui-monospace, monospace' }}
            placeholder={"Example:\nJane Smith, jane@example.com\nJohn Doe, john@corp.com"}
          />
        </Field>
      ) : (
        <FileDropZone onFiles={(files) => onFile({ target: { files } })} prompt="Drag and drop a CSV file here">
          <Field label="Upload CSV">
            <label style={{ display:'inline-flex', alignItems:'center', gap:6, marginBottom:8 }}>
              <input type="checkbox" checked={firstRowHeader} onChange={e => setFirstRowHeader(e.target.checked)} />
              First row is a header
            </label>
            <input type="file" accept=".csv,text/csv" onChange={onFile} />
          </Field>
        </FileDropZone>
      )}
      {error && <div style={{ color:'#b91c1c', marginBottom: 10 }}>{error}</div>}
      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10, flexWrap:'wrap' }}>
        {personLookupEnabled ? (
          <>
            <span style={{ fontSize: 12, color: '#6b7280' }}>
              Person lookup runs only when you click Lookup Person. Full names, middle-name variants, email addresses, and {employeeIdLabel} values are all supported.
            </span>
            <Button variant="subtle" onClick={runLookup} disabled={!normalizeRows(rows).length || lookupBusy || !!progress?.working}>
              {lookupBusy ? 'Looking up...' : 'Lookup Person'}
            </Button>
            {lookupBusy ? <span style={{ fontSize: 12, color: '#6b7280' }}>Looking up...</span> : null}
            {lookupHasRun && !lookupBusy ? <span style={{ fontSize: 12, color: '#6b7280' }}>Lookup complete. Edit the list and click again to refresh.</span> : null}
            {lookupError ? <span style={{ color:'#b91c1c', fontSize:12 }}>{lookupError}</span> : null}
            {!lookupError && Object.keys(lookupResults).length > 0 ? (
              <span style={{ color:'#15803d', fontSize:12 }}>Matched {Object.keys(lookupResults).length} name(s)</span>
            ) : null}
          </>
        ) : (
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            Person lookup is not enabled. Imported rows must include both name and email.
          </span>
        )}
      </div>
      {!validation.ok && (
        <div style={{ marginBottom: 10, fontSize: 12, color: '#b91c1c' }}>
          {validation.issues[0]}
        </div>
      )}
      <div style={{ marginTop: 8 }}>
        <div style={{ fontSize: 12, color:'#6b7280', marginBottom: 6 }}>Preview</div>
        <div style={{ maxHeight: 300, overflow:'auto', border:'1px solid #e5e7eb', borderRadius: 10 }}>
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            <thead style={{ background: 'rgba(0,0,0,.04)' }}>
              <tr><th style={{ textAlign:'left', padding:8, width:'45%' }}>Name</th><th style={{ textAlign:'left', padding:8, width:'45%' }}>Email</th><th style={{ textAlign:'right', padding:8, width:'10%' }}>Actions</th></tr>
            </thead>
            <tbody>
              {rows.length ? rows.map((r,i) => {
                const lr = lookupResults[i] || {}
                const matches = Array.isArray(lr.matches) ? lr.matches : []
                const selection = lr.selection
                const override = !!lr.override
                return (
                  <Fragment key={i}>
                    <tr>
                      <td style={{ padding:8 }}>{r.name}</td>
                      <td style={{ padding:8 }}>{r.email}</td>
                      <td style={{ padding:8, textAlign:'right' }}>
                        <Button
                          variant="ghost"
                          onClick={() => {
                            setRows(prev => prev.filter((_, idx) => idx !== i))
                            invalidateLookup()
                          }}
                        >
                          Remove
                        </Button>
                      </td>
                    </tr>
                    {matches.length > 0 && (
                      <tr style={{ background:'#f8fafc' }}>
                        <td colSpan={3} style={{ padding:10 }}>
                          {lr.error ? (
                            <div style={{ fontSize: 12, color: '#b45309', marginBottom: 8 }}>
                              Lookup note: {lr.error}
                            </div>
                          ) : null}
                          <div style={{ fontSize:12, color:'#475467', marginBottom:6 }}>
                            Select the correct person for <strong>{r.name}</strong>:
                          </div>
                          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                            {matches.map((m, idx) => {
                              const selected = !override && selection === idx
                              return (
                                <label key={`match-${i}-${idx}`} style={{ display:'flex', alignItems:'flex-start', gap:8, cursor:'pointer' }}>
                                  <input
                                    type="radio"
                                    name={`lookup-${i}`}
                                    checked={selected}
                                    onChange={() => {
                                      setLookupResults(prev => ({ ...prev, [i]: { ...(prev[i] || {}), selection: idx, override: false } }))
                                      applyMatchToRow(i, m)
                                    }}
                                  />
                                  <div>
                                    <div style={{ fontWeight:600 }}>{lookupPersonName(m)}{lookupPersonId(m) ? ' (' + lookupPersonId(m) + ')' : ''}</div>
                                    <div style={{ fontSize:12, color:'#475467' }}>
                                      {m.department_name ? `Dept: ${m.department_name}` : 'Dept: -'}
                                      {m.employee_end_date ? <> | End: <span style={{ color: employmentEndDateColor({ employment_end_date: m.employee_end_date }), fontWeight: 700 }}>{m.employee_end_date}</span></> : ''}
                                      {m.email ? ` | Email: ${m.email}` : ''}
                                    </div>
                                  </div>
                                </label>
                              )
                            })}
                          </div>
                          <label style={{ display:'flex', alignItems:'center', gap:8, marginTop:10, fontSize:12, color:'#475467' }}>
                            <input
                              type="checkbox"
                              checked={override}
                              onChange={(e) => setLookupResults(prev => ({ ...prev, [i]: { ...(prev[i] || {}), override: e.target.checked, selection: e.target.checked ? null : (prev[i]?.selection ?? null) } }))}
                            />
                            Override lookup for this row (use typed values)
                          </label>
                        </td>
                      </tr>
                    )}
                    {matches.length === 0 && lookupResults[i] && (
                      <tr style={{ background:'#f8fafc' }}>
                        <td colSpan={3} style={{ padding:10 }}>
                          {lr.error ? (
                            <div style={{ fontSize: 12, color: '#b45309', marginBottom: 8 }}>
                              Lookup note: {lr.error}
                            </div>
                          ) : null}
                          <div style={{ fontSize:12, color:'#9ca3af', marginBottom:8 }}>No matches found for this lookup.</div>
                          <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:12, color:'#475467' }}>
                            <input
                              type="checkbox"
                              checked={override}
                              onChange={(e) => setLookupResults(prev => ({ ...prev, [i]: { ...(prev[i] || {}), override: e.target.checked, selection: null } }))}
                            />
                            Override lookup for this row (use typed values)
                          </label>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              }) : (
                <tr><td style={{ padding:8 }} colSpan={3}>No rows parsed yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  )
}

