import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'
import { ADMIN_USERNAME, ROLE_OPTIONS } from './systemUtils.js'

export default function SystemUserModal({
  open,
  editingId,
  closeModal,
  userSaveBusy,
  saveUser,
  editingSeedAdmin,
  form,
  setForm,
  ssoEnabled,
  ssoDisplayName,
  canManageUsers,
  isRequestor,
  employeeIdLabel,
  user,
}) {
  const editingSelfOnly = Boolean(editingId && editingId === user?.id && !canManageUsers)
  const passwordRequired = editingSeedAdmin || (!editingId && (!ssoEnabled || form.local_auth_only))
  const employeeIdRequired = !isRequestor
    && ['analyst', 'sys_admin'].includes(form.role || 'analyst')
    && (form.email || '').trim().toLowerCase() !== ADMIN_USERNAME
  const groupRequired = !isRequestor && form.role === 'tech'
  return (
<Modal
        open={open}
        title={editingId ? 'Edit User' : 'Create User'}
        onClose={closeModal}
        footer={(
          <>
            <button type="button" className="btn" onClick={closeModal} disabled={userSaveBusy}>Cancel</button>
            <button type="submit" form="system-user-form" className="btn secondary" disabled={userSaveBusy}>
              {userSaveBusy ? (editingId ? 'Saving...' : 'Creating...') : (editingId ? 'Save' : 'Create User')}
            </button>
          </>
        )}
      >
        <form id="system-user-form" className="form-grid" onSubmit={event => { event.preventDefault(); saveUser() }}>
          {editingSeedAdmin ? (
            <>
              <label>Name<input value={ADMIN_USERNAME} readOnly /></label>
              <label><RequiredFieldLabel>Password</RequiredFieldLabel><input type="password" value={form.password} onChange={e=>setForm({...form, password:e.target.value})} required /></label>
              <label><RequiredFieldLabel>Confirm Password</RequiredFieldLabel><input type="password" value={form.confirm} onChange={e=>setForm({...form, confirm:e.target.value})} required /></label>
            </>
          ) : (
            <>
              <label><RequiredFieldLabel>First Name</RequiredFieldLabel><input value={form.first_name} onChange={e=>setForm({...form, first_name:e.target.value})} required /></label>
              <label><RequiredFieldLabel>Last Name</RequiredFieldLabel><input value={form.last_name} onChange={e=>setForm({...form, last_name:e.target.value})} required /></label>
              {(!ssoEnabled || editingId || form.local_auth_only) ? (
                <>
                  <label><RequiredFieldLabel required={passwordRequired}>Password</RequiredFieldLabel><input type="password" value={form.password} onChange={e=>setForm({...form, password:e.target.value})} required={passwordRequired} /></label>
                  <label><RequiredFieldLabel required={passwordRequired}>Confirm Password</RequiredFieldLabel><input type="password" value={form.confirm} onChange={e=>setForm({...form, confirm:e.target.value})} required={passwordRequired} /></label>
                </>
              ) : (
                <div className="local-auth-toggle__help" style={{ gridColumn: '1 / -1' }}>
                  New users sign in with {ssoDisplayName}. No DiscoveryOne password is needed.
                </div>
              )}
              <label><RequiredFieldLabel required={!editingSelfOnly}>Email</RequiredFieldLabel><input type="email" value={form.email} onChange={e=>setForm({...form, email:e.target.value})} placeholder="user@domain" required={!editingSelfOnly} disabled={!canManageUsers} /></label>
              {!isRequestor && (
                <>
                  <label>Role
                    <select value={form.role} onChange={e=>setForm({...form, role:e.target.value})} disabled={!canManageUsers}>
                      {ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </label>
                  <label><RequiredFieldLabel required={employeeIdRequired}>{employeeIdLabel}</RequiredFieldLabel>
                    <input
                      value={form.employee_id}
                      onChange={e=>setForm({...form, employee_id:e.target.value})}
                      placeholder={`Enter ${employeeIdLabel}`}
                      required={employeeIdRequired}
                    />
                    <span className="form-help">Needed for analyst and system-admin ticket workflows.</span>
                  </label>
                  <label><RequiredFieldLabel required={groupRequired}>Group / Department</RequiredFieldLabel>
                    <input
                      value={form.requestor_group}
                      onChange={e=>setForm({...form, requestor_group:e.target.value})}
                      placeholder={form.role === 'tech' ? 'a configured ticket workflow group' : 'Risk, HR, etc.'}
                      disabled={!canManageUsers}
                      required={groupRequired}
                    />
                  </label>
                  {editingId && canManageUsers && (
                    <>
                      <div className="local-auth-toggle" style={{ gridColumn: '1 / -1' }}>
                        <label className="local-auth-toggle__label">
                          <input
                            type="checkbox"
                            checked={!!form.local_auth_only}
                            onChange={e => setForm({ ...form, local_auth_only: e.target.checked })}
                          />
                          <span>Use local credentials instead of {ssoDisplayName} for this account</span>
                        </label>
                        <div className="local-auth-toggle__help">
                          When enabled, this user signs in with email and password and does not use {ssoDisplayName}. Set a new password when switching this on.
                        </div>
                      </div>
                      <div className="local-auth-toggle" style={{ gridColumn: '1 / -1' }}>
                        <label className="local-auth-toggle__label">
                          <input
                            type="checkbox"
                            checked={form.is_active !== false}
                            onChange={e => setForm({ ...form, is_active: e.target.checked })}
                            disabled={editingId === user?.id}
                          />
                          <span>Account is active</span>
                        </label>
                        <div className="local-auth-toggle__help">
                          Disable this account to block sign-in without deleting the user record.
                          {editingId === user?.id ? ' You cannot disable your own account.' : ''}
                        </div>
                      </div>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </form>
      </Modal>
  )
}
