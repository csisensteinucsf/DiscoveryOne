import { useState } from 'react'
import Modal from './Modal.jsx'
import { useToast } from './ToastProvider.jsx'
import RequiredFieldLabel from './RequiredFieldLabel.jsx'

const ADMIN_USERNAME = 'admin'

export default function EditUserModal({ apiBase, user, onClose, onSaved }) {
  const isSeedAdmin = (user.username || '').toLowerCase() === ADMIN_USERNAME
  const initialRole = user.role || (user.is_admin ? 'sys_admin' : 'analyst')
  const { showToast } = useToast()

  const [form, setForm] = useState({
    first_name: user.first_name || '',
    last_name: user.last_name || '',
    email: user.email || user.username || '',
    role: initialRole,
    password: '',
    confirmPassword: '',
  })

  const [submitting, setSubmitting] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (form.password && form.password !== form.confirmPassword) {
      showToast('Passwords do not match.', { variant: 'warn' })
      return
    }

    let payload = {}
    if (isSeedAdmin) {
      if (!form.password) {
        showToast('Please provide a new password for the admin account.', { variant: 'warn' })
        return
      }
      payload = { password: form.password }
    } else {
      const first = form.first_name.trim()
      const last = form.last_name.trim()
      const email = form.email.trim().toLowerCase()
      if (!first || !last || !email) {
        showToast('First name, last name, and email are required.', { variant: 'warn' })
        return
      }
      payload = {
        username: email,
        email,
        first_name: first,
        last_name: last,
        role: form.role || 'analyst',
        is_admin: (form.role || 'analyst') === 'sys_admin',
      }
      if (form.password) {
        payload.password = form.password
      }
    }
    setSubmitting(true)
    try {
      const res = await fetch(`${apiBase}/users/${user.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })

      if (res.ok) {
        onSaved?.()
        showToast('User updated.', { variant: 'success' })
        onClose()
      } else {
        let msg = ''
        try { msg = await res.text() } catch (_) {}
        showToast(msg || 'Failed to update user', { variant: 'error' })
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open
      title="Edit User"
      onClose={() => !submitting && onClose()}
      width={520}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={submitting}>Cancel</button>
          <button type="submit" form="edit-user-form" className="btn" disabled={submitting}>
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
    >
      <form id="edit-user-form" onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {isSeedAdmin ? (
            <>
              <label>Display Name</label>
              <input className="input" value={form.first_name || ADMIN_USERNAME} readOnly />
            </>
          ) : (
            <>
              <label><RequiredFieldLabel>First Name</RequiredFieldLabel></label>
              <input
                className="input"
                value={form.first_name}
                onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))}
                required
              />

              <label><RequiredFieldLabel>Last Name</RequiredFieldLabel></label>
              <input
                className="input"
                value={form.last_name}
                onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))}
                required
              />
            </>
          )}

          <label><RequiredFieldLabel required={isSeedAdmin}>New Password</RequiredFieldLabel></label>
          <input
            type="password"
            className="input"
            value={form.password}
            onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            required={isSeedAdmin}
          />

          <label><RequiredFieldLabel required={isSeedAdmin}>Confirm New Password</RequiredFieldLabel></label>
          <input
            type="password"
            className="input"
            value={form.confirmPassword}
            onChange={e => setForm(f => ({ ...f, confirmPassword: e.target.value }))}
            required={isSeedAdmin}
          />
          {!isSeedAdmin && (
            <>
              <label><RequiredFieldLabel>Email</RequiredFieldLabel></label>
              <input
                type="email"
                className="input"
                value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                required
              />

              <label>Role</label>
              <select
                className="input"
                value={form.role}
                onChange={e => setForm(f => ({ ...f, role: e.target.value }))}
              >
                <option value="sys_admin">Sys Admin</option>
                <option value="analyst">Analyst</option>
                <option value="tech">Tech</option>
                <option value="requestor">Requestor</option>
                <option value="tester">Tester</option>
              </select>
            </>
          )}

      </form>
    </Modal>
  )
}
