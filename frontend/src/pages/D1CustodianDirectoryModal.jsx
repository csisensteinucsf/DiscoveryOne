import { useMemo, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import FileDropZone from '../components/FileDropZone.jsx'
import Modal from '../components/Modal.jsx'

const emptyRow = () => ({ name: '', email: '' })
const validEmail = value => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim())

function parseRows(text) {
  return String(text || '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => line.split(/[,\t;]+/).map(value => value.trim()))
    .filter((parts, index) => !(index === 0 && /name/i.test(parts[0] || '') && /email/i.test(parts[1] || '')))
    .map(parts => ({ name: parts[0] || '', email: parts[1] || '' }))
    .filter(row => row.name || row.email)
}

export default function D1CustodianDirectoryModal({
  apiBase = '/api',
  initialMode = 'manual',
  onClose,
  onSaved,
}) {
  const [mode, setMode] = useState(initialMode)
  const [rows, setRows] = useState([emptyRow()])
  const [pasteText, setPasteText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const activeRows = useMemo(
    () => rows.filter(row => row.name.trim() || row.email.trim()),
    [rows],
  )
  const invalid = activeRows.find(row => !row.name.trim() || !validEmail(row.email))
  const canSave = activeRows.length > 0 && !invalid && !busy

  const updateRow = (index, field, value) => {
    setRows(current => current.map((row, rowIndex) => (
      rowIndex === index ? { ...row, [field]: value } : row
    )))
  }

  const addRow = () => setRows(current => [...current, emptyRow()])
  const removeRow = index => setRows(current => (
    current.length === 1 ? [emptyRow()] : current.filter((_, rowIndex) => rowIndex !== index)
  ))

  const applyText = value => {
    setPasteText(value)
    setRows(parseRows(value))
  }

  const onFiles = files => {
    const file = files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => applyText(String(reader.result || ''))
    reader.onerror = () => setError('The file could not be read.')
    reader.readAsText(file)
  }

  const save = async () => {
    if (!canSave) {
      setError('Enter a name and valid email address for every custodian.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const response = await fetch(apiBase + '/custodians', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          custodians: activeRows.map(row => ({
            name: row.name.trim(),
            email: row.email.trim(),
          })),
        }),
      })
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail || 'Unable to save custodians.')
      }
      const result = await response.json()
      await onSaved?.(result)
      onClose()
    } catch (saveError) {
      setError(saveError?.message || 'Unable to save custodians.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title="Add D1 Custodians"
      onClose={busy ? undefined : onClose}
      width={760}
      footer={(
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn primary" onClick={save} disabled={!canSave}>
            {busy ? 'Saving...' : 'Save Custodians'}
          </button>
        </div>
      )}
    >
      <div className="custodian-entry-mode-tabs" role="tablist" aria-label="Custodian entry method">
        <button type="button" className={'btn ' + (mode === 'manual' ? 'primary' : 'secondary')} onClick={() => { setMode('manual'); setRows([emptyRow()]); setError('') }}>
          Manual Add
        </button>
        <button type="button" className={'btn ' + (mode === 'import' ? 'primary' : 'secondary')} onClick={() => { setMode('import'); setRows([]); setError('') }}>
          Import from list
        </button>
      </div>

      <p className="muted">
        Save names and email addresses to DiscoveryOne now. They can be selected when custodians are added to a case later.
      </p>

      {mode === 'manual' ? (
        <div className="d1-custodian-manual-list">
          {rows.map((row, index) => (
            <div className="d1-custodian-entry-row" key={index}>
              <label>
                Name <span className="required-marker">*</span>
                <input value={row.name} onChange={event => updateRow(index, 'name', event.target.value)} />
              </label>
              <label>
                Email <span className="required-marker">*</span>
                <input type="email" value={row.email} onChange={event => updateRow(index, 'email', event.target.value)} />
              </label>
              <div className="row d1-custodian-row-actions">
                <button type="button" className="icon-button" title="Add another custodian" aria-label="Add another custodian" onClick={addRow}>
                  <Plus size={18} aria-hidden="true" />
                </button>
                <button type="button" className="icon-button danger" title="Remove custodian" aria-label={'Remove custodian ' + (index + 1)} onClick={() => removeRow(index)}>
                  <Minus size={18} aria-hidden="true" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <>
          <label>
            Custodian list <span className="required-marker">*</span>
            <textarea
              rows={9}
              value={pasteText}
              onChange={event => applyText(event.target.value)}
              placeholder={"Jane Doe, jane.doe@example.com\nJohn Smith, john.smith@example.com"}
            />
          </label>
          <FileDropZone onFiles={onFiles} prompt="Drag and drop a CSV or text file here">
            <input type="file" accept=".csv,.txt,text/csv,text/plain" onChange={event => onFiles(event.target.files)} />
          </FileDropZone>
          <p className="muted">{activeRows.length} custodian{activeRows.length === 1 ? '' : 's'} ready to save.</p>
        </>
      )}

      {error && <div className="alert error">{error}</div>}
    </Modal>
  )
}
