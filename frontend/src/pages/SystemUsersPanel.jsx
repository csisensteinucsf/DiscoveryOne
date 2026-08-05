import { ADMIN_USERNAME, formatDateTime } from './systemUtils.js'
import { DeleteIconButton, EditIconButton } from '../components/RowActionIconButton.jsx'

export default function SystemUsersPanel({
  active,
  titleStyle,
  canManageUsers,
  activeUsers,
  activeUsersLoading,
  setShowActiveUsersModal,
  loadActiveUsers,
  openCreate,
  users,
  authConfig,
  ssoDisplayName,
  formatGroupLabel,
  user,
  openEdit,
  deleteUser,
  openCreateGroup,
  accountReviewSettings,
  updateAccountReviewSetting,
  saveAccountReviewSettings,
  accountReviewSaving,
  accountReviewStatus,
  groups,
  openGroup,
  registrationRequests,
  openApproveRegistration,
  declineRegistration,
  registrationInviteBusyId,
  resendRegistrationInvite,
  removeRegistrationRequest,
}) {
  if (!active) return null
  const ssoEnabled = !!authConfig?.sso_enabled

  return (
    <>
      <div className="card">
        <div style={{ ...titleStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span>Users</span>
          {canManageUsers && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <button
                className="btn secondary"
                type="button"
                onClick={() => {
                  setShowActiveUsersModal(true)
                  loadActiveUsers()
                }}
                disabled={activeUsersLoading}
                title="View current active DiscoveryOne sessions"
              >
                {activeUsersLoading ? 'Checking sessions' : `${activeUsers.count || 0} logged in`}
              </button>
              <button className="btn secondary" onClick={openCreate}>Create User</button>
            </div>
          )}
        </div>
        <div className="table-responsive">
          <table className="table users-table users-table--accounts">
            <thead>
              <tr>
                <th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Auth</th><th>Group</th><th>Last logged in</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td>{(u.first_name || u.last_name) ? `${u.first_name || ''} ${u.last_name || ''}`.trim() : u.username}</td>
                  <td>{u.email || ''}</td>
                  <td>{(u.role === 'sys_admin' || u.is_admin) ? 'Sys Admin' : (u.role ? (u.role[0].toUpperCase()+u.role.slice(1)) : 'Analyst')}</td>
                  <td>{u.is_active === false ? 'Disabled' : 'Active'}</td>
                  <td className="users-table__auth">{u.local_auth_only || (u.username || '').toLowerCase() === ADMIN_USERNAME ? 'Local' : (ssoEnabled ? ssoDisplayName : 'Local')}</td>
                  <td>{formatGroupLabel(u.requestor_group || '')}</td>
                  <td>{formatDateTime(u.last_login)}</td>
                  <td className="users-table__actions">
                    <EditIconButton
                      label={'Edit ' + (u.email || u.username || 'user')}
                      onClick={() => openEdit(u)}
                      disabled={!(canManageUsers || user?.id === u.id)}
                    />
                    {canManageUsers && user?.id !== u.id && (
                      <DeleteIconButton
                        label={'Delete ' + (u.email || u.username || 'user')}
                        onClick={() => deleteUser(u.id)}
                        disabled={(u.username || '').toLowerCase() === ADMIN_USERNAME}
                        title={(u.username || '').toLowerCase() === ADMIN_USERNAME ? 'Built-in admin cannot be deleted.' : undefined}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {canManageUsers && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ ...titleStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginBottom: 8 }}>
            <span>Groups</span>
            <button className="btn secondary" type="button" onClick={openCreateGroup}>Add Group</button>
          </div>
          <p style={{ marginTop: 0, color: 'var(--muted,#6b7280)', fontSize: 13 }}>
            Group visibility is one-way. If Legal is allowed to see Risk cases, Risk does not automatically see Legal cases.
          </p>
          {groups.length ? (
            <div className="table-responsive">
              <table className="table">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Users</th>
                    <th>Can see cases for</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map(group => (
                    <tr key={group.name}>
                      <td>{group.label || formatGroupLabel(group.name)}</td>
                      <td>{group.user_count || 0}</td>
                      <td>
                        {Array.isArray(group.can_see_groups) && group.can_see_groups.length
                          ? group.can_see_groups.map(formatGroupLabel).join(', ')
                          : '-'}
                      </td>
                      <td>
                        <button className="btn secondary compact" type="button" onClick={() => openGroup(group)}>
                          View / Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--muted,#6b7280)', margin: 0 }}>No groups found.</p>
          )}
        </div>
      )}

      {canManageUsers && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ ...titleStyle, marginBottom: 8 }}>Account Requests</div>
          {registrationRequests.length ? (
            <table className="table account-requests-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Requested</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {registrationRequests.map(req => (
                  <tr key={req.id}>
                    <td>{req.name}</td>
                    <td>{req.email}</td>
                    <td style={{ textTransform: 'capitalize' }}>{req.status}</td>
                    <td>{formatDateTime(req.created_at)}</td>
                    <td className="account-requests-table__actions">
                      {req.status === 'pending' ? (
                        <>
                          <button className="btn secondary compact" onClick={() => openApproveRegistration(req)}>Approve</button>
                          <button className="btn danger compact" onClick={() => declineRegistration(req)}>Decline</button>
                        </>
                      ) : req.status === 'approved' ? (
                        <>
                          <span>{ssoEnabled ? 'Account ready email sent' : 'Invite sent'}</span>
                          <button
                            className="btn secondary compact"
                            onClick={() => resendRegistrationInvite(req)}
                            disabled={registrationInviteBusyId === req.id}
                          >
                            {registrationInviteBusyId === req.id ? 'Resending' : (ssoEnabled ? 'Resend email' : 'Resend invite')}
                          </button>
                          <button
                            className="btn danger compact"
                            onClick={() => removeRegistrationRequest(req)}
                          >
                            Remove
                          </button>
                        </>
                      ) : req.status === 'completed' ? (
                        <span>Completed</span>
                      ) : (
                        <span>Declined</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: 'var(--muted,#6b7280)', margin: 0 }}>No account requests.</p>
          )}
        </div>
      )}

      {canManageUsers && (
        <div className="card" style={{ marginTop: 16 }}>
          <div style={{ ...titleStyle, marginBottom: 8 }}>Account Review</div>
          <p style={{ marginTop: 0, color: 'var(--muted,#6b7280)', fontSize: 13 }}>
            DiscoveryOne can periodically email system administrators an account inventory so access, roles, and local-only accounts can be reviewed. These values are stored in application settings and do not require environment-file changes.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 700 }}>
              <input
                type="checkbox"
                checked={accountReviewSettings?.enabled !== false}
                onChange={e => updateAccountReviewSetting('enabled', e.target.checked)}
                style={{ marginTop: 3 }}
              />
              <span>
                Send account review emails
                <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                  When enabled, DiscoveryOne sends the account review inventory to current system administrators.
                </span>
              </span>
            </label>
            <label style={{ display: 'block', fontWeight: 700 }}>
              Review interval days
              <input
                className="input"
                type="number"
                min="1"
                max="3650"
                step="1"
                value={accountReviewSettings?.interval_days ?? 120}
                onChange={e => updateAccountReviewSetting('interval_days', e.target.value)}
                style={{ marginTop: 6 }}
              />
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                Number of days between account review emails after the last successful send.
              </span>
            </label>
            <label style={{ display: 'block', fontWeight: 700 }}>
              Scheduler check interval hours
              <input
                className="input"
                type="number"
                min="1"
                max="168"
                step="1"
                value={accountReviewSettings?.check_interval_hours ?? 12}
                onChange={e => updateAccountReviewSetting('check_interval_hours', e.target.value)}
                style={{ marginTop: 6 }}
              />
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                How often the backend checks whether an account review email is due.
              </span>
            </label>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 14, flexWrap: 'wrap' }}>
            <button className="btn secondary" type="button" onClick={saveAccountReviewSettings} disabled={accountReviewSaving}>
              {accountReviewSaving ? 'Saving' : 'Save Account Review'}
            </button>
            <span style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>
              Last sent: {formatDateTime(accountReviewSettings?.last_sent_at)}
            </span>
            {accountReviewStatus && (
              <span style={{ color: accountReviewStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
                {accountReviewStatus}
              </span>
            )}
          </div>
        </div>
      )}
    </>
  )
}
