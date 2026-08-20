import { useMemo, useState } from 'react'
import { Minus, Plus } from 'lucide-react'
import FileDropZone from '../components/FileDropZone.jsx'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'
import CustodianEmploymentStatusSelect, { isEmploymentStatusOption, normalizeEmploymentStatus } from './CustodianEmploymentStatusSelect.jsx'

const CSV_HEADERS = ['first_name', 'last_name', 'email', 'campus', 'department', 'employee_id', 'job_title', 'employment_status']
const emptyRow = () => ({
  first_name: '', last_name: '', email: '', campus: '', department: '',
  employee_id: '', title: '', employment_status: '',
})
const validEmail = value => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim())

function parseRows(text) {
  const lines = String(text || '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
  const values = lines.map(line => line.split(/[,\t]+/).map(value => value.trim().replace(/^"|"$/g, '')))
  const hasHeader = values[0]?.some(value => CSV_HEADERS.includes(value.toLowerCase().replace(/\s+/g, '_')))
  const headers = hasHeader
    ? values.shift().map(value => value.toLowerCase().replace(/\s+/g, '_'))
    : CSV_HEADERS
  return values.map(parts => {
    const source = Object.fromEntries(headers.map((header, index) => [header, parts[index] || '']))
    return {
      ...emptyRow(),
      first_name: source.first_name || '',
      last_name: source.last_name || '',
      email: source.email || '',
      campus: source.campus || '',
      department: source.department || '',
      employee_id: source.employee_id || '',
      title: source.job_title || source.title || '',
      employment_status: normalizeEmploymentStatus(source.employment_status),
    }
  }).filter(row => Object.values(row).some(Boolean))
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
    () => rows.filter(row => Object.values(row).some(value => String(value || '').trim())),
    [rows],
  )
  const invalidRequired = activeRows.find(row => (
    !row.first_name.trim() || !row.last_name.trim() || !validEmail(row.email) || !row.campus.trim()
  ))
  const invalidEmploymentStatus = activeRows.find(row => !isEmploymentStatusOption(row.employment_status))
  const canSave = activeRows.length > 0 && !invalidRequired && !invalidEmploymentStatus && !busy

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

  const downloadCsvTemplate = () => {
    const blob = new Blob([CSV_HEADERS.join(',') + '\n'], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'discoveryone-custodian-import-template.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  const save = async () => {
    if (invalidEmploymentStatus) {
      setError('Employment Status must be Active, Inactive, or left blank for every custodian.')
      return
    }
    if (!canSave) {
      setError('Missing required fields. Enter first name, last name, a valid email, and campus for every custodian.')
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
            first_name: row.first_name.trim(),
            last_name: row.last_name.trim(),
            email: row.email.trim(),
            campus: row.campus.trim(),
            department: row.department.trim() || null,
            employee_id: row.employee_id.trim() || null,
            title: row.title.trim() || null,
            employment_status: normalizeEmploymentStatus(row.employment_status) || null,
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
      width={1040}
      footer={(
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn primary" onClick={save} disabled={!canSave}>
            {busy ? 'Saving...' : 'Save Custodians'}
          </button>
        </div>
      )}
    >
      <div className="d1-custodian-directory-content">
        <div className="custodian-entry-mode-tabs" role="tablist" aria-label="Custodian entry method">
          <button type="button" className={'btn ' + (mode === 'manual' ? 'primary' : 'secondary')} onClick={() => { setMode('manual'); setRows([emptyRow()]); setError('') }}>
            Manual Add
          </button>
          <button type="button" className={'btn ' + (mode === 'import' ? 'primary' : 'secondary')} onClick={() => { setMode('import'); setRows([]); setError('') }}>
            Import from list
          </button>
        </div>

      <p className="d1-custodian-directory-intro">
        Save reusable custodian profiles now so they can be selected when custodians are added to a matter later.
      </p>

      {mode === 'manual' ? (
        <div className="d1-custodian-manual-list">
          {rows.map((row, index) => (
            <div className="d1-custodian-profile-card" key={index}>
              <div className="d1-custodian-profile-grid">
              <label>
                <RequiredFieldLabel>First name</RequiredFieldLabel>
                <input className="input" required value={row.first_name} onChange={event => updateRow(index, 'first_name', event.target.value)} />
              </label>
              <label>
                <RequiredFieldLabel>Last name</RequiredFieldLabel>
                <input className="input" required value={row.last_name} onChange={event => updateRow(index, 'last_name', event.target.value)} />
              </label>
              <label>
                <RequiredFieldLabel>Email</RequiredFieldLabel>
                <input className="input" required type="email" value={row.email} onChange={event => updateRow(index, 'email', event.target.value)} />
              </label>
              <label>
                <RequiredFieldLabel>Campus</RequiredFieldLabel>
                <input className="input" required value={row.campus} onChange={event => updateRow(index, 'campus', event.target.value)} />
              </label>
              <label>Department<input className="input" value={row.department} onChange={event => updateRow(index, 'department', event.target.value)} /></label>
              <label>Employee ID<input className="input" value={row.employee_id} onChange={event => updateRow(index, 'employee_id', event.target.value)} /></label>
              <label>Job Title<input className="input" value={row.title} onChange={event => updateRow(index, 'title', event.target.value)} /></label>
              <label>Employment Status<CustodianEmploymentStatusSelect value={row.employment_status} onChange={value => updateRow(index, 'employment_status', value)} /></label>
              </div>
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
        <div className="d1-custodian-import-panel">
          <div className="d1-custodian-import-heading">
            <p className="d1-custodian-import-help">
              Use the downloadable header template. First name, last name, email, and campus are required. Employment Status may be Active, Inactive, or blank; remaining columns may be left blank.
            </p>
            <button type="button" className="btn secondary compact" onClick={downloadCsvTemplate}>
              Download CSV template
            </button>
          </div>
          <label className="d1-custodian-import-list">
            <RequiredFieldLabel>Custodian list</RequiredFieldLabel>
            <textarea
              rows={9}
              value={pasteText}
              className="input"
              required
              onChange={event => applyText(event.target.value)}
              placeholder={"First name, Last name, Email, Campus, Department, Employee ID, Job Title, Employment Status"}
            />
          </label>
          <FileDropZone onFiles={onFiles} prompt="Drag and drop a CSV or text file here">
            <input className="native-file-input" type="file" accept=".csv,.txt,text/csv,text/plain" onChange={event => onFiles(event.target.files)} />
          </FileDropZone>
          <p className="d1-custodian-import-count">{activeRows.length} custodian{activeRows.length === 1 ? '' : 's'} ready to save.</p>
        </div>
      )}

      {error && <div className="alert error">{error}</div>}
      </div>
    </Modal>
  )
}
