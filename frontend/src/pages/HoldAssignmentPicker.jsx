import { useMemo, useState } from 'react'
import { Plus } from 'lucide-react'

export default function HoldAssignmentPicker({
  apiBase = '/api',
  caseId,
  holds = [],
  selectedHoldIds = [],
  onSelectedHoldIdsChange,
  onHoldCreated,
  disabled = false,
}) {
  const [newHoldName, setNewHoldName] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const activeHolds = useMemo(
    () => (Array.isArray(holds) ? holds : []).filter(hold => hold?.status === 'active'),
    [holds]
  )
  const selected = useMemo(
    () => new Set((Array.isArray(selectedHoldIds) ? selectedHoldIds : []).map(Number)),
    [selectedHoldIds]
  )

  const toggleHold = holdId => {
    const id = Number(holdId)
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onSelectedHoldIdsChange?.([...next])
  }

  const createHold = async () => {
    if (!caseId || creating || disabled) return
    setCreating(true)
    setError('')
    try {
      const response = await fetch(apiBase + '/cases/' + caseId + '/holds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name: newHoldName.trim() || null }),
      })
      const body = await response.json().catch(() => null)
      if (!response.ok) {
        const detail = body?.detail?.message || body?.detail || 'Unable to create hold'
        throw new Error(String(detail))
      }
      setNewHoldName('')
      await onHoldCreated?.(body)
    } catch (err) {
      setError(err?.message || 'Unable to create hold')
    } finally {
      setCreating(false)
    }
  }

  return (
    <fieldset disabled={disabled || creating} style={{ border: 0, padding: 0, margin: '0 0 14px' }}>
      <legend style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>
        Assign to Holds (optional)
      </legend>
      <p style={{ fontSize: 12, color: '#64748b', margin: '0 0 8px' }}>
        Leave every Hold unselected to add these custodians to the matter only. Select a named Hold only when they should join that Hold's notices, consent, preservation, and search workflow.
      </p>
      {activeHolds.length ? (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginBottom: 10 }}>
          {activeHolds.map(hold => (
            <label key={hold.id} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
              <input
                type="checkbox"
                checked={selected.has(Number(hold.id))}
                onChange={() => toggleHold(hold.id)}
              />
              <span style={{ overflowWrap: 'anywhere' }}>{hold.name}</span>
            </label>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
          This case has no active Holds. Custodians can still be added at the matter level and assigned to a Hold later.
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          className="input"
          value={newHoldName}
          onChange={event => setNewHoldName(event.target.value)}
          placeholder={activeHolds.length ? 'Create another Hold (optional)' : 'Create a named Hold (optional)'}
          style={{ flex: '1 1 260px' }}
        />
        <button type="button" className="btn secondary" onClick={createHold} disabled={disabled || creating || !caseId}>
          <Plus size={16} aria-hidden="true" /> {creating ? 'Creating...' : 'Create Hold'}
        </button>
      </div>
      {error ? <div style={{ color: '#b91c1c', fontSize: 12, marginTop: 6 }}>{error}</div> : null}
      {!selected.size ? (
        <div style={{ color: '#64748b', fontSize: 12, marginTop: 6 }}>No Hold selected: custodians will be added to the matter only.</div>
      ) : null}
    </fieldset>
  )
}
