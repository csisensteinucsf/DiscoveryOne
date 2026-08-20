import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

const DEFAULT_TYPES = [
  'Public Record Request',
  'General Litigation',
  'Internal Investigation',
  'Subpoena Request',
]

export default function SystemMatterTypesPanel({ apiBase = '/api', isSysAdmin, titleStyle }) {
  const [matterTypes, setMatterTypes] = useState(DEFAULT_TYPES)
  const [newType, setNewType] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')

  const load = useCallback(async () => {
    if (!isSysAdmin) return
    try {
      const response = await fetch(`${apiBase}/system/matter-types`, { credentials: 'include' })
      if (!response.ok) throw new Error(`Request failed (${response.status})`)
      const payload = await response.json()
      setMatterTypes(Array.isArray(payload?.matter_types) ? payload.matter_types : DEFAULT_TYPES)
    } catch (error) {
      setStatus(error?.message || 'Unable to load matter types.')
    }
  }, [apiBase, isSysAdmin])

  useEffect(() => { load() }, [load])

  const addType = () => {
    const value = newType.trim()
    if (!value) return
    if (value.toLowerCase() === 'other' || matterTypes.some(item => item.toLowerCase() === value.toLowerCase())) {
      setStatus('Matter types must be unique. “Other” is added automatically to Matter forms.')
      return
    }
    setMatterTypes(current => [...current, value])
    setNewType('')
    setStatus('')
  }

  const save = async () => {
    setBusy(true)
    setStatus('')
    try {
      const response = await fetch(`${apiBase}/system/matter-types`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matter_types: matterTypes }),
      })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(payload?.detail || `Request failed (${response.status})`)
      setMatterTypes(payload.matter_types)
      setStatus('Matter types saved.')
    } catch (error) {
      setStatus(error?.message || 'Unable to save matter types.')
    } finally {
      setBusy(false)
    }
  }

  if (!isSysAdmin) return null
  return (
    <section className="card system-matter-types-panel">
      <div className="system-panel-heading">
        <div>
          <h3 style={titleStyle}>Matter Types</h3>
          <p className="muted">Manage the organization-approved choices shown when a Matter is created.</p>
        </div>
        <button type="button" className="btn primary" onClick={save} disabled={busy || !matterTypes.length}>
          {busy ? 'Saving...' : 'Save Matter Types'}
        </button>
      </div>

      <div className="system-matter-type-list">
        {matterTypes.map((matterType, index) => (
          <div className="system-matter-type-row" key={`${matterType}-${index}`}>
            <input
              className="input"
              aria-label={`Matter type ${index + 1}`}
              value={matterType}
              onChange={event => setMatterTypes(current => current.map((item, itemIndex) => itemIndex === index ? event.target.value : item))}
            />
            <button type="button" className="icon-button danger" title="Remove matter type" aria-label={`Remove ${matterType}`} onClick={() => setMatterTypes(current => current.filter((_, itemIndex) => itemIndex !== index))}>
              <Trash2 size={17} aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>

      <div className="system-matter-type-add">
        <input className="input" value={newType} onChange={event => setNewType(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addType() } }} placeholder="Add a matter type" />
        <button type="button" className="btn secondary" onClick={addType}><Plus size={16} aria-hidden="true" /> Add</button>
      </div>
      {status ? <div className={status.endsWith('saved.') ? 'alert success' : 'alert'}>{status}</div> : null}
    </section>
  )
}
