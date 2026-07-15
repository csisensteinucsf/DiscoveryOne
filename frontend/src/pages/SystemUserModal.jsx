import Modal from '../components/Modal.jsx'
import { ADMIN_USERNAME, ROLE_OPTIONS } from './systemUtils.js'

export default function SystemUserModal({
  open,
  editingId,
  closeModal,
  userSaveBusy,
  saveUser,
  userModalSaveDisabled,
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
  return (
<Modal
        open={open}
        title={editingId ? 'Edit User' : 'Create User'}
        onClose={closeModal}
        footer={(
          <>
            <button className="btn" onClick={closeModal} disabled={userSaveBusy}>Cancel</button>
            <button className="btn secondary" onClick={saveUser}
              disabled={userModalSaveDisabled}>
              {userSaveBusy ? (editingId ? 'Saving...' : 'Creating...') : (editingId ? 'Save' : 'Create User')}
            </button>
          </>
        )}
      >
        <div className="form-grid">
          {editingSeedAdmin ? (
            <>
              <label>Name<input value={ADMIN_USERNAME} readOnly /></label>
              <label>Password<input type="password" value={form.password} onChange={e=>setForm({...form, password:e.target.value})} required /></label>
              <label>Confirm Password<input type="password" value={form.confirm} onChange={e=>setForm({...form, confirm:e.target.value})} required /></label>
            </>
          ) : (
            <>
              <label>First Name<input value={form.first_name} onChange={e=>setForm({...form, first_name:e.target.value})} required /></label>
              <label>Last Name<input value={form.last_name} onChange={e=>setForm({...form, last_name:e.target.value})} required /></label>
              {(!ssoEnabled || editingId || form.local_auth_only) ? (
                <>
                  <label>Password<input type="password" value={form.password} onChange={e=>setForm({...form, password:e.target.value})} /></label>
                  <label>Confirm Password<input type="password" value={form.confirm} onChange={e=>setForm({...form, confirm:e.target.value})} /></label>
                </>
              ) : (
                <div className="local-auth-toggle__help" style={{ gridColumn: '1 / -1' }}>
                  New users sign in with {ssoDisplayName}. No DiscoveryOne password is needed.
                </div>
              )}
              <label>Email<input type="email" value={form.email} onChange={e=>setForm({...form, email:e.target.value})} placeholder="user@domain" required disabled={!canManageUsers} /></label>
              {!isRequestor && (
                <>
                  <label>Role
                    <select value={form.role} onChange={e=>setForm({...form, role:e.target.value})} disabled={!canManageUsers}>
                      {ROLE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </label>
                  <label>{employeeIdLabel} (required by some ticket workflows)
                    <input
                      value={form.employee_id}
                      onChange={e=>setForm({...form, employee_id:e.target.value})}
                      placeholder={`Enter ${employeeIdLabel}`}
                    />
                  </label>
                  <label>Group / Department {form.role === 'tech' ? '(a configured ticket workflow group required)' : '(optional)'}
                    <input
                      value={form.requestor_group}
                      onChange={e=>setForm({...form, requestor_group:e.target.value})}
                      placeholder={form.role === 'tech' ? 'a configured ticket workflow group' : 'Risk, HR, etc.'}
                      disabled={!canManageUsers}
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
        </div>
      </Modal>
  )
}
