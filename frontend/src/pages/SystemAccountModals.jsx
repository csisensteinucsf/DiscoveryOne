import Modal from '../components/Modal.jsx'
import { formatDateTime } from './systemUtils.js'

export function SystemActiveUsersModal({ open, activeUsers, activeUsersLoading, onRefresh, onClose }) {
  if (!open) return null
  return (
<Modal
          open
          title="Currently Logged In Users"
          onClose={() => onClose}
          width={860}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="btn secondary" onClick={onRefresh} disabled={activeUsersLoading}>
                {activeUsersLoading ? 'Refreshing' : 'Refresh'}
              </button>
              <button type="button" className="btn" onClick={() => onClose}>Close</button>
            </div>
          )}
        >
          <p style={{ marginTop: 0, color: 'var(--muted,#6b7280)' }}>
            Showing users with an active, non-expired session
            {activeUsers.idle_timeout_minutes ? ` seen within the last ${activeUsers.idle_timeout_minutes} minutes.` : '.'}
          </p>
          {activeUsers.users.length ? (
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Sessions</th>
                    <th>Last seen</th>
                    <th>IP</th>
                  </tr>
                </thead>
                <tbody>
                  {activeUsers.users.map(row => (
                    <tr key={row.id || row.email}>
                      <td>{row.name || row.username || ''}</td>
                      <td>{row.email || ''}</td>
                      <td>{(row.role === 'sys_admin') ? 'Sys Admin' : (row.role ? row.role.charAt(0).toUpperCase() + row.role.slice(1) : '')}</td>
                      <td>{row.session_count || 1}</td>
                      <td>{formatDateTime(row.last_seen_at)}</td>
                      <td>{row.ip || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--muted,#6b7280)', marginBottom: 0 }}>
              No active logged-in users found.
            </p>
          )}
        </Modal>
  )
}

export function SystemGroupModal({ groupModal, closeGroupModal, groupSaving, saveGroup, groupForm, setGroupForm, groups, normalizeGroupValue, formatGroupLabel }) {
  if (!groupModal) return null
  return (
<Modal
          open
          title={groupModal?.isNew ? 'New Group' : `Group: ${groupModal.label || formatGroupLabel(groupModal.name)}`}
          onClose={closeGroupModal}
          width={720}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="btn secondary" onClick={closeGroupModal} disabled={groupSaving}>Cancel</button>
              <button type="button" className="btn" onClick={saveGroup} disabled={groupSaving}>
                {groupSaving ? 'Saving' : (groupModal?.isNew ? 'Create Group' : 'Save Group')}
              </button>
            </div>
          )}
        >
          <div style={{ display: 'grid', gap: 16 }}>
            <label>
              Group name
              <input
                className="input"
                value={groupForm.name}
                onChange={(e) => setGroupForm(prev => ({ ...prev, name: e.target.value }))}
              />
            </label>

            <label>
              Allow this group to see matters for these other groups
              <select
                className="input"
                multiple
                size={Math.min(8, Math.max(3, groups.length - 1))}
                value={groupForm.can_see_groups}
                onChange={(e) => {
                  const selected = Array.from(e.target.selectedOptions).map(opt => opt.value)
                  setGroupForm(prev => ({ ...prev, can_see_groups: selected }))
                }}
              >
                {groups
                  .filter(g => normalizeGroupValue(g.name) !== normalizeGroupValue(groupModal.name))
                  .map(g => (
                    <option key={g.name} value={g.name}>{g.label || formatGroupLabel(g.name)}</option>
                  ))}
              </select>
              <small style={{ color: 'var(--muted,#6b7280)' }}>
                Hold Ctrl or Cmd to select more than one group. This access does not work in reverse unless you configure it on the other group too.
              </small>
            </label>

            <div>
              <h4 style={{ margin: '0 0 8px' }}>Users in this group</h4>
              {Array.isArray(groupModal.users) && groupModal.users.length ? (
                <div className="table-responsive" style={{ maxHeight: 280, overflowY: 'auto' }}>
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {groupModal.users.map(u => (
                        <tr key={u.id || u.email}>
                          <td>{(u.first_name || u.last_name) ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : (u.username || '')}</td>
                          <td>{u.email || ''}</td>
                          <td>{(u.role === 'sys_admin' || u.is_admin) ? 'Sys Admin' : (u.role ? (u.role[0].toUpperCase()+u.role.slice(1)) : '')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p style={{ color: 'var(--muted,#6b7280)', margin: 0 }}>No users are assigned to this group.</p>
              )}
            </div>
          </div>
        </Modal>
  )
}

export function SystemRegistrationApprovalModal({
  approveRegTarget,
  authConfig,
  setApproveRegTarget,
  approveRegRole,
  setApproveRegRole,
  approveRegGroup,
  setApproveRegGroup,
  approveRegNewGroup,
  setApproveRegNewGroup,
  approveRegistration,
  allGroupOptions,
  formatGroupLabel,
}) {
  if (!approveRegTarget) return null
  const ssoEnabled = !!authConfig?.sso_enabled
  return (
<Modal
          open
          title={(approveRegTarget?.status || "").toLowerCase() === "approved" ? (ssoEnabled ? "Resend account ready email" : "Resend account invite") : "Approve account request"}
          onClose={() => { setApproveRegTarget(null); setApproveRegRole(''); setApproveRegGroup(''); setApproveRegNewGroup('') }}
          width={520}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button type="button" className="btn secondary" onClick={() => { setApproveRegTarget(null); setApproveRegRole(''); setApproveRegGroup(''); setApproveRegNewGroup('') }}>Cancel</button>
              <button type="button" className="btn" onClick={approveRegistration}>{(approveRegTarget?.status || "").toLowerCase() === "approved" ? (ssoEnabled ? "Resend Ready Email" : "Resend Invite") : (ssoEnabled ? "Approve & Notify User" : "Approve & Send Invite")}</button>
            </div>
          )}
        >
          <p style={{ marginTop: 0, color: '#475467' }}>
            Which user group does this user belong to? Choose below for <strong>{approveRegTarget.name}</strong> ({approveRegTarget.email}).
          </p>
          <div style={{ display: 'grid', gap: 12 }}>
            <label>
              User group
              <select
                className="input"
                value={approveRegRole}
                onChange={(e) => {
                  const nextRole = e.target.value
                  setApproveRegRole(nextRole)
                  setApproveRegGroup('')
                  setApproveRegNewGroup('')
                }}
              >
                <option value="">Select a user group</option>
                <option value="sys_admin">Admin</option>
                <option value="analyst">Analyst</option>
                <option value="requestor">Requestor</option>
                <option value="tech">Tech</option>
              </select>
            </label>
            {approveRegRole === 'tech' ? (
              <label>
                Tech group (a configured ticket workflow group)
                <input
                  className="input"
                  value={approveRegGroup}
                  onChange={(e) => setApproveRegGroup(e.target.value)}
                  placeholder="Enter a configured workflow group"
                />
              </label>
            ) : approveRegRole === 'requestor' ? (
              <>
                <label>
                  Existing group
                  <select
                    className="input"
                    value={approveRegGroup}
                    onChange={(e) => setApproveRegGroup(e.target.value)}
                  >
                    <option value="">Select a group</option>
                    {allGroupOptions.map(g => (
                      <option key={g} value={g}>{formatGroupLabel(g)}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Or create a new group
                  <input
                    className="input"
                    value={approveRegNewGroup}
                    onChange={(e) => setApproveRegNewGroup(e.target.value)}
                    placeholder="Enter new department/group"
                  />
                </label>
              </>
            ) : null}
          </div>
        </Modal>
  )
}
