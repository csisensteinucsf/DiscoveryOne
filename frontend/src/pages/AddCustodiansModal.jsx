import { Fragment, useCallback, useMemo, useRef, useState } from 'react'
import { useToast } from '../components/ToastProvider.jsx'
import Modal from '../components/Modal.jsx'
import HoldAssignmentPicker from './HoldAssignmentPicker.jsx'
import { Field, TextInput, Button, Badge } from './caseDetailControls.jsx'
import {
  DEFAULT_LOOKUP_INPUT_PLACEHOLDER,
  employmentBadges,
  employmentEndDateColor,
  isValidEmail,
  lookupPersonName,
  lookupPersonId,
} from './caseDetailUtils.js'
import { emptyPersonLookupFields, personLookupFieldsFromMatch } from './caseDetailPersonLookupFields.js'
export function AddCustodiansModal({
  apiBase = '/api',
  caseId,
  holds = [],
  selectedHoldIds = [],
  onSelectedHoldIdsChange,
  onHoldCreated,
  onClose,
  onSave,
  onSwitchToImport,
  onSwitchToDirectory,
  saving = false,
  employeeIdLabel = 'Employee ID',
  lookupInputPlaceholder = DEFAULT_LOOKUP_INPUT_PLACEHOLDER,
  personLookupEnabled = false,
}) {
  const { showToast } = useToast()
  const [rows, setRows] = useState([{ name: '', email: '' }])
  const [lookupBusy, setLookupBusy] = useState(false)
  const [lookupHasRun, setLookupHasRun] = useState(false)
  const [lookupResults, setLookupResults] = useState({})
  const lookupRequestRef = useRef(0)

  const invalidateLookup = useCallback(() => {
    lookupRequestRef.current += 1
    setLookupBusy(false)
    setLookupHasRun(false)
    setLookupResults({})
  }, [])

  function update(i, key, val, options = {}) {
    const shouldInvalidate = options.invalidate !== false
    setRows(prev => prev.map((r, idx) => idx === i ? { ...r, [key]: val } : r))
    if (shouldInvalidate) invalidateLookup()
  }
  function updateLookupName(i, val) {
    setRows(prev => prev.map((r, idx) => idx === i ? { ...r, name: val, email: '' } : r))
    invalidateLookup()
  }
  function addRow() {
    setRows(prev => [...prev, { name: '', email: '' }])
    invalidateLookup()
  }
  function removeRow(i) {
    setRows(prev => prev.filter((_, idx) => idx !== i))
    invalidateLookup()
  }
  const applyMatchToRow = useCallback((idx, match) => {
    setRows(prev => prev.map((row, i) => {
      if (i !== idx) return row
      const next = { ...row }
      const full = lookupPersonName(match)
      if (full) next.name = full
      if (match?.email) next.email = match.email
      return next
    }))
  }, [])
  const hasAtLeastOneName = rows.some(r => r.name.trim().length > 0)
  const manualRows = useMemo(() => rows
    .map(r => ({ name: (r.name || '').trim(), email: (r.email || '').trim() }))
    .filter(r => r.name || r.email), [rows])
  const onKeyDown = (i) => (e) => { if (e.key === 'Enter'){ e.preventDefault(); if (i === rows.length - 1 && rows[i].name.trim()) addRow() } }
  const runLookup = async () => {
    const roster = rows.map((r, idx) => ({
      id: idx,
      name: (r.name || '').trim(),
      email: (r.email || '').trim(),
    })).filter(r => r.name)
    if (!roster.length) return
    const requestId = lookupRequestRef.current + 1
    lookupRequestRef.current = requestId
    setLookupBusy(true)
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
      const next = {}
      const autoEmails = []
      for (const entry of data?.results || []) {
        const matches = Array.isArray(entry.matches) ? entry.matches : []
        const error = (entry?.error || '').trim() || null
        next[entry.id] = {
          matches,
          selection: matches.length === 1 ? 0 : null,
          override: matches.length === 0,
          error,
        }
        if (matches.length === 1) {
          autoEmails.push({ idx: entry.id, match: matches[0] })
        }
      }
      setLookupResults(next)
      if (autoEmails.length) {
        setRows(prev => prev.map((row, idx) => {
          const found = autoEmails.find(x => x.idx === idx)
          if (!found) return row
          const nextRow = { ...row }
          const full = lookupPersonName(found.match)
          if (full) nextRow.name = full
          if (!(row.email || '').trim() && found.match?.email) nextRow.email = found.match.email
          return nextRow
        }))
      }
      if (!Object.keys(next).length) showToast('No matches found.', { variant: 'info' })
    } catch (err) {
      if (lookupRequestRef.current !== requestId) return
      console.error('Lookup failed', err)
      const message = (err?.message || '').trim() || 'Lookup failed'
      showToast('Person lookup failed.', { variant: 'error' })
      const fallback = {}
      for (const item of roster) {
        fallback[item.id] = { matches: [], selection: null, override: true, error: message }
      }
      setLookupResults(fallback)
    } finally {
      if (lookupRequestRef.current !== requestId) return
      setLookupBusy(false)
      setLookupHasRun(true)
    }
  }
  const mergedRows = useMemo(() => {
    if (!personLookupEnabled) {
      return manualRows.map(r => ({
        ...r,
        person_lookup_overridden: false,
        ...emptyPersonLookupFields(),
      }))
    }
    return rows.map((r, idx) => {
      const res = lookupResults[idx]
      const match = res && !res.override && Array.isArray(res.matches) && res.selection != null ? res.matches[res.selection] : null
      const matchedName = lookupPersonName(match)
      return {
        ...r,
        name: (res?.override ? r.name : (matchedName || r.name)).trim(),
        ...personLookupFieldsFromMatch(match),
        email: ((r.email || match?.email || '').trim()) || (res?.override ? 'UNMATCHED' : ''),
        person_lookup_overridden: !!res?.override,
      }
    })
  }, [manualRows, personLookupEnabled, rows, lookupResults])
  const validation = useMemo(() => {
    const issues = []
    if (!personLookupEnabled) {
      if (!manualRows.length) {
        issues.push('Enter at least one custodian name and email.')
      }
      manualRows.forEach((row, idx) => {
        if (!row.name) issues.push(`Row ${idx + 1}: name is required.`)
        if (!row.email) issues.push(`Row ${idx + 1}: email is required.`)
        if (row.email && !isValidEmail(row.email)) issues.push(`Row ${idx + 1}: email must be valid.`)
      })
      return { ok: issues.length === 0, issues }
    }
    for (let i = 0; i < rows.length; i++) {
      const name = (rows[i]?.name || '').trim()
      if (!name) continue
      const res = lookupResults[i]
      if (!res) {
        issues.push(`Row ${i + 1}: lookup not completed yet.`)
        continue
      }
      if (res.override) continue
      const matches = Array.isArray(res.matches) ? res.matches.filter(Boolean) : []
      if (matches.length === 0) {
        issues.push(`Row ${i + 1}: no person match found; enable override to add anyway.`)
        continue
      }
      if (res.selection == null) {
        issues.push(`Row ${i + 1}: select a person match or enable override.`)
      }
    }
    return { ok: issues.length === 0, issues }
  }, [manualRows, personLookupEnabled, rows, lookupResults])
  const canSubmit = personLookupEnabled
    ? hasAtLeastOneName && lookupHasRun && !lookupBusy && !saving && validation.ok
    : manualRows.length > 0 && !saving && validation.ok
  return (
    <Modal
      open
      title="Add Custodians"
      onClose={saving ? () => {} : onClose}
      width={700}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={() => onSave(mergedRows)} disabled={!canSubmit} title={!canSubmit ? (validation.issues[0] || "Run person lookup first") : "Add"}>{saving ? "Adding..." : "Add"}</Button>
        </div>
      )}
    >
      <div className="custodian-entry-mode-tabs" role="tablist" aria-label="Custodian entry method">
        <Button variant="primary" disabled>Manual Add</Button>
        <Button variant="subtle" onClick={onSwitchToImport} disabled={saving}>Import from list</Button>
        <Button variant="subtle" onClick={onSwitchToDirectory} disabled={saving}>Select from D1 Custodians</Button>
      </div>
      <HoldAssignmentPicker
        apiBase={apiBase}
        caseId={caseId}
        holds={holds}
        selectedHoldIds={selectedHoldIds}
        onSelectedHoldIdsChange={onSelectedHoldIdsChange}
        onHoldCreated={onHoldCreated}
        disabled={saving}
      />
      <div style={{ display: 'flex', gap: 10, marginBottom: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {personLookupEnabled ? (
          <>
            <span style={{ fontSize: 12, color: '#6b7280' }}>
              Person lookup runs only when you click Lookup Person. Enter a full name, email address, or {employeeIdLabel}, then select the correct match or override it before adding.
            </span>
            <Button variant="subtle" onClick={runLookup} disabled={!hasAtLeastOneName || lookupBusy || saving}>
              {lookupBusy ? 'Looking up...' : 'Lookup Person'}
            </Button>
            {lookupHasRun && !lookupBusy ? <span style={{ fontSize: 12, color: '#6b7280' }}>Lookup complete. Edit a row and click again to refresh.</span> : null}
          </>
        ) : (
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            Person lookup is not enabled. Enter each custodian's name and email address.
          </span>
        )}
        {saving ? <span style={{ fontSize: 12, color: '#6b7280' }}>Adding...</span> : null}
      </div>
      {!validation.ok && (
        <div style={{ marginBottom: 10, fontSize: 12, color: '#b91c1c' }}>
          {validation.issues[0]}
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: personLookupEnabled ? '1fr auto' : 'minmax(0, 1fr) minmax(0, 1fr) auto', gap: 10, alignItems: 'center' }}>
        {rows.map((r, i) => (
          <Fragment key={i}>
            <TextInput placeholder={personLookupEnabled ? (lookupInputPlaceholder || DEFAULT_LOOKUP_INPUT_PLACEHOLDER) : 'Name'} value={r.name} onChange={e => personLookupEnabled ? updateLookupName(i, e.target.value) : update(i, 'name', e.target.value, { invalidate: false })} onKeyDown={onKeyDown(i)} autoFocus={i === 0} disabled={saving} />
            {!personLookupEnabled && (
              <TextInput placeholder="Email" value={r.email} onChange={e => update(i, 'email', e.target.value, { invalidate: false })} onKeyDown={onKeyDown(i)} disabled={saving} />
            )}
            <div style={{ display: 'flex', gap: 8 }}>
              {i === rows.length - 1 && (<Button variant="subtle" onClick={addRow} title="Add another row" disabled={saving}>+</Button>)}
              {rows.length > 1 && (<Button variant="ghost" onClick={() => removeRow(i)} title="Remove this row" disabled={saving}>Remove</Button>)}
            </div>
            {personLookupEnabled && lookupResults[i] && (
              <div style={{ gridColumn: '1 / span 2', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 10 }}>
                {lookupResults[i].error ? (
                  <div style={{ fontSize: 12, color: '#b45309', marginBottom: 8 }}>
                    Lookup note: {lookupResults[i].error}
                  </div>
                ) : null}
                {Array.isArray(lookupResults[i].matches) && lookupResults[i].matches.length > 0 ? (
                  <>
                    <div style={{ fontSize: 12, color: '#475467', marginBottom: 6 }}>Select the correct person:</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      {lookupResults[i].matches.map((m, idx) => {
                        const selected = !lookupResults[i].override && lookupResults[i].selection === idx
                        const end = m.employee_end_date
                        const badge = employmentBadges({ employment_end_date: end })
                        return (
                          <label key={`match-${i}-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                            <input type="radio" name={`match-${i}`} checked={selected} disabled={saving} onChange={() => { setLookupResults(prev => ({ ...prev, [i]: { ...(prev[i] || {}), selection: idx, override: false } })); applyMatchToRow(i, m) }} />
                            <div>
                              <div style={{ fontWeight: 600 }}>{lookupPersonName(m)}{lookupPersonId(m) ? ' (' + lookupPersonId(m) + ')' : ''}</div>
                              <div style={{ fontSize: 12, color: '#475467' }}>
                                {m.department_name ? `Dept: ${m.department_name}` : 'Dept: -'}
                                {end ? <> | End: <span style={{ color: employmentEndDateColor({ employment_end_date: end }), fontWeight: 700 }}>{end}</span></> : ''}
                                {m.email ? ` | Email: ${m.email}` : ''}
                              </div>
                            </div>
                            <div style={{ display: 'flex', gap: 4 }}>
                              {badge.map((b, bi) => (
                                <Badge key={`badge-${i}-${idx}-${bi}`} variant={b.variant} compact title={b.title}>{b.label}</Badge>
                              ))}
                            </div>
                          </label>
                        )
                      })}
                    </div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 12, color: '#475467' }}>
                      <input
                        type="checkbox"
                        checked={!!lookupResults[i].override}
                        disabled={saving}
                        onChange={(e) => setLookupResults(prev => ({ ...prev, [i]: { ...(prev[i] || {}), override: e.target.checked, selection: e.target.checked ? null : (prev[i]?.selection ?? null) } }))}
                      />
                      Override lookup for this row (use typed values)
                    </label>
                    {lookupResults[i].override && (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 10 }}>
                        <TextInput placeholder="Final name" value={r.name} onChange={e => update(i, 'name', e.target.value, { invalidate: false })} disabled={saving} />
                        <TextInput placeholder="Final email" value={r.email} onChange={e => update(i, 'email', e.target.value, { invalidate: false })} disabled={saving} />
                      </div>
                    )}
                  </>
                ) : (
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ fontSize: 12, color: '#9ca3af' }}>No matches found for this lookup.</div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#475467' }}>
                      <input
                        type="checkbox"
                        checked={!!lookupResults[i].override}
                        disabled={saving}
                        onChange={(e) => setLookupResults(prev => ({ ...prev, [i]: { ...(prev[i] || {}), override: e.target.checked, selection: null } }))}
                      />
                      Override lookup for this row (use typed values)
                    </label>
                    {lookupResults[i].override && (
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                        <TextInput placeholder="Final name" value={r.name} onChange={e => update(i, 'name', e.target.value, { invalidate: false })} disabled={saving} />
                        <TextInput placeholder="Final email" value={r.email} onChange={e => update(i, 'email', e.target.value, { invalidate: false })} disabled={saving} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </Fragment>
        ))}
      </div>
      <div style={{ marginTop: 10, fontSize: 12, color: '#6b7280' }}>
        Tip: Press <kbd>Enter</kbd> to add a new row from the last {personLookupEnabled ? 'lookup' : 'name'} field.
      </div>
    </Modal>
  )
}

