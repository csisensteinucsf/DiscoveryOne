import { useMemo, useState } from 'react'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'

const validEmail = value => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || '').trim())

const initialForm = custodian => ({
  first_name: custodian?.first_name || '',
  last_name: custodian?.last_name || '',
  email: custodian?.email || '',
  campus: custodian?.campus || '',
  department: custodian?.department || '',
  employee_id: custodian?.employee_id || custodian?.external_id || '',
  title: custodian?.title || '',
  employment_status: custodian?.employment_status || '',
})

export default function EditCustodianProfileModal({ apiBase = '/api', custodian, onClose, onSaved }) {
  const [form, setForm] = useState(() => initialForm(custodian))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const invalid = useMemo(() => (
    !form.first_name.trim()
    || !form.last_name.trim()
    || !validEmail(form.email)
    || !form.campus.trim()
  ), [form])

  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))

  const save = async () => {
    if (invalid || busy) {
      setError('Missing required fields. Enter first name, last name, a valid email, and campus.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (custodian?.email) params.set('email', custodian.email)
      else if (custodian?.name) params.set('name', custodian.name)
      const response = await fetch(`${apiBase}/custodians/profile?${params.toString()}`, {
        method: 'PUT',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: form.first_name.trim(),
          last_name: form.last_name.trim(),
          email: form.email.trim(),
          campus: form.campus.trim(),
          department: form.department.trim() || null,
          employee_id: form.employee_id.trim() || null,
          title: form.title.trim() || null,
          employment_status: form.employment_status.trim() || null,
        }),
      })
      const result = await response.json().catch(() => null)
      if (!response.ok) throw new Error(result?.detail || 'Unable to update the custodian.')
      onSaved?.(result)
    } catch (saveError) {
      setError(saveError?.message || 'Unable to update the custodian.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      title="Edit Custodian"
      onClose={busy ? undefined : onClose}
      width={760}
      footer={(
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn primary" onClick={save} disabled={busy}>
            {busy ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      )}
    >
      <div className="edit-custodian-profile-grid">
        <label>
          <RequiredFieldLabel>First name</RequiredFieldLabel>
          <input className="input" required value={form.first_name} onChange={event => update('first_name', event.target.value)} />
        </label>
        <label>
          <RequiredFieldLabel>Last name</RequiredFieldLabel>
          <input className="input" required value={form.last_name} onChange={event => update('last_name', event.target.value)} />
        </label>
        <label>
          <RequiredFieldLabel>Email</RequiredFieldLabel>
          <input className="input" required type="email" value={form.email} onChange={event => update('email', event.target.value)} />
        </label>
        <label>
          <RequiredFieldLabel>Campus</RequiredFieldLabel>
          <input className="input" required value={form.campus} onChange={event => update('campus', event.target.value)} />
        </label>
        <label>Department<input className="input" value={form.department} onChange={event => update('department', event.target.value)} /></label>
        <label>Employee ID<input className="input" value={form.employee_id} onChange={event => update('employee_id', event.target.value)} /></label>
        <label>Job Title<input className="input" value={form.title} onChange={event => update('title', event.target.value)} /></label>
        <label>Employment Status<input className="input" value={form.employment_status} onChange={event => update('employment_status', event.target.value)} /></label>
      </div>
      {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}
    </Modal>
  )
}