import { useEffect, useMemo, useState } from 'react'
import Modal from '../components/Modal.jsx'
import { Button } from './caseDetailControls.jsx'

const rowKey = row => String(row.directory_id || row.email || row.name || '')

export default function SelectD1CustodiansModal({
  apiBase = '/api',
  existingCustodians = [],
  onClose,
  onSave,
  onSwitchToAdd,
  onSwitchToImport,
  saving = false,
}) {
  const [rows, setRows] = useState([])
  const [selected, setSelected] = useState([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    setLoading(true)
    fetch(apiBase + '/custodians', { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Unable to load D1 custodians.')
        return response.json()
      })
      .then(data => {
        if (active) setRows(Array.isArray(data) ? data : [])
      })
      .catch(loadError => {
        if (active) setError(loadError?.message || 'Unable to load D1 custodians.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [apiBase])

  const existingEmails = useMemo(
    () => new Set(existingCustodians.map(item => String(item.email || '').trim().toLowerCase()).filter(Boolean)),
    [existingCustodians],
  )
  const available = useMemo(() => rows.filter(row => {
    const email = String(row.email || '').trim().toLowerCase()
    if (!email || existingEmails.has(email)) return false
    const search = query.trim().toLowerCase()
    return !search || String(row.name || '').toLowerCase().includes(search) || email.includes(search)
  }), [existingEmails, query, rows])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const chosenRows = useMemo(
    () => rows.filter(row => selectedSet.has(rowKey(row))),
    [rows, selectedSet],
  )

  const toggle = row => {
    const key = rowKey(row)
    setSelected(current => current.includes(key)
      ? current.filter(value => value !== key)
      : [...current, key])
  }

  const allVisibleSelected = available.length > 0 && available.every(row => selectedSet.has(rowKey(row)))
  const toggleVisible = () => {
    const visibleKeys = available.map(rowKey)
    setSelected(current => {
      const currentSet = new Set(current)
      if (visibleKeys.every(key => currentSet.has(key))) {
        return current.filter(key => !visibleKeys.includes(key))
      }
      visibleKeys.forEach(key => currentSet.add(key))
      return [...currentSet]
    })
  }

  return (
    <Modal
      open
      title="Add Custodians"
      onClose={saving ? undefined : onClose}
      width={820}
      footer={(
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button
            onClick={() => onSave(chosenRows)}
            disabled={!chosenRows.length || saving}
          >
            {saving ? 'Adding...' : `Add selected (${chosenRows.length})`}
          </Button>
        </div>
      )}
    >
      <div className="custodian-entry-mode-tabs" role="tablist" aria-label="Custodian entry method">
        <Button variant="subtle" onClick={onSwitchToAdd} disabled={saving}>Manual Add</Button>
        <Button variant="subtle" onClick={onSwitchToImport} disabled={saving}>Import from list</Button>
        <Button variant="primary" disabled>Select from D1 Custodians</Button>
      </div>

      <div className="d1-custodian-picker-toolbar">
        <input
          type="search"
          value={query}
          onChange={event => setQuery(event.target.value)}
          placeholder="Search by name or email..."
          aria-label="Search D1 custodians"
        />
        <label>
          <input type="checkbox" checked={allVisibleSelected} onChange={toggleVisible} disabled={!available.length} />
          Select all shown
        </label>
      </div>

      {error && <div className="alert error">{error}</div>}
      <div className="d1-custodian-picker-list" role="listbox" aria-label="D1 custodians" aria-multiselectable="true">
        {loading ? <p className="muted">Loading custodians...</p> : null}
        {!loading && !available.length ? (
          <p className="muted">No available custodians match this search.</p>
        ) : null}
        {available.map(row => {
          const key = rowKey(row)
          const checked = selectedSet.has(key)
          return (
            <label className={'d1-custodian-picker-option ' + (checked ? 'is-selected' : '')} key={key}>
              <input type="checkbox" checked={checked} onChange={() => toggle(row)} />
              <span>
                <strong>{row.name || row.email}</strong>
                <small>{row.email}</small>
                {row.campus || row.department ? (
                  <small>{[row.campus, row.department].filter(Boolean).join(' • ')}</small>
                ) : null}
              </span>
            </label>
          )
        })}
      </div>
      <p className="muted">
        Custodians already on this matter are hidden. Select one or more people, then add them to the matter.
      </p>
    </Modal>
  )
}
