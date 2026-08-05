import { useCallback, useMemo, useState } from 'react'
import { saveUserRequest } from '../lib/userApi.js'
import {
  ADMIN_USERNAME,
  makeEmptyForm,
} from './systemUtils.js'

const fallbackGroupLabel = (value) => {
  if (!value) return ''
  return value
    .split(' ')
    .filter(Boolean)
    .map(part => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ')
}

export function useSystemUsersWorkflow({
  apiBase,
  user,
  refreshUser,
  authConfig,
  showToast,
  canManageUsers,
  isRequestor,
  ssoEnabled,
  employeeIdLabel,
  ntpGroupOptions,
  loadNtpGroups,
  normalizeGroupValue,
  flash,
}) {
  const [users, setUsers] = useState([])
  const [editingId, setEditingId] = useState(null)
  const [editingSeedAdmin, setEditingSeedAdmin] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [approveRegTarget, setApproveRegTarget] = useState(null)
  const [approveRegRole, setApproveRegRole] = useState('')
  const [approveRegGroup, setApproveRegGroup] = useState('')
  const [approveRegNewGroup, setApproveRegNewGroup] = useState('')
  const [registrationInviteBusyId, setRegistrationInviteBusyId] = useState(null)
  const [form, setForm] = useState(makeEmptyForm)
  const [userSaveBusy, setUserSaveBusy] = useState(false)
  const [groups, setGroups] = useState([])
  const [groupModal, setGroupModal] = useState(null)
  const [groupForm, setGroupForm] = useState({ name: '', can_see_groups: [] })
  const [groupSaving, setGroupSaving] = useState(false)
  const [activeUsers, setActiveUsers] = useState({ count: 0, users: [], idle_timeout_minutes: null })
  const [activeUsersLoading, setActiveUsersLoading] = useState(false)
  const [showActiveUsersModal, setShowActiveUsersModal] = useState(false)
  const [registrationRequests, setRegistrationRequests] = useState([])
  const ssoAuthEnabled = !!authConfig?.sso_enabled

  const editingUser = useMemo(() => users.find((u) => u.id === editingId) || null, [users, editingId])

  const groupDisplayMap = useMemo(() => {
    const map = new Map()
    groups.forEach(group => {
      const raw = (group?.name || '').trim()
      const norm = normalizeGroupValue(raw)
      if (norm) map.set(norm, (group?.label || raw || fallbackGroupLabel(raw)))
    })
    users.forEach(u => {
      const raw = (u.requestor_group || '').trim()
      const norm = normalizeGroupValue(raw)
      if (norm && raw && !map.has(norm)) map.set(norm, raw)
    })
    ntpGroupOptions.forEach(value => {
      const raw = (value || '').trim()
      const norm = normalizeGroupValue(raw)
      if (norm && raw && !map.has(norm)) map.set(norm, fallbackGroupLabel(raw))
    })
    return map
  }, [groups, normalizeGroupValue, ntpGroupOptions, users])

  const formatGroupLabel = useCallback((value) => {
    const norm = normalizeGroupValue(value)
    if (!norm) return ''
    return groupDisplayMap.get(norm) || fallbackGroupLabel((value || '').trim())
  }, [groupDisplayMap, normalizeGroupValue])

  const allGroupOptions = useMemo(() => {
    const set = new Set()
    ntpGroupOptions.forEach(g => { if (g) set.add(g) })
    groups.forEach(g => {
      const name = normalizeGroupValue(g?.name || '')
      if (name) set.add(name)
    })
    users.forEach(u => {
      const g = (u.requestor_group || '').trim().toLowerCase()
      if (g) set.add(g)
    })
    return Array.from(set).sort()
  }, [groups, normalizeGroupValue, ntpGroupOptions, users])

  const analystOptions = useMemo(() => {
    return (users || [])
      .filter(u => ['analyst', 'sys_admin'].includes((u.role || (u.is_admin ? 'sys_admin' : '')) || ''))
      .map(u => ({
        value: u.id,
        label: `${(u.first_name || '').trim()} ${(u.last_name || '').trim()}`.trim() || u.username || u.email || `User ${u.id}`,
      }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [users])

  const resetForm = useCallback(() => {
    setForm(makeEmptyForm())
    setUserSaveBusy(false)
  }, [])

  const closeModal = useCallback(() => {
    setShowModal(false)
    setEditingSeedAdmin(false)
    resetForm()
  }, [resetForm])

  const loadUsers = useCallback(async () => {
    if (!canManageUsers) {
      setUsers(user ? [user] : [])
      return
    }
    try {
      const res = await fetch(`${apiBase}/users`, { credentials: 'include' })
      if (!res.ok) {
        setUsers([])
        return
      }
      const data = await res.json()
      setUsers(data || [])
    } catch {
      setUsers([])
    }
  }, [apiBase, canManageUsers, user])

  const loadActiveUsers = useCallback(async () => {
    if (!canManageUsers) {
      setActiveUsers({ count: 0, users: [], idle_timeout_minutes: null })
      return
    }
    setActiveUsersLoading(true)
    try {
      const res = await fetch(`${apiBase}/users/active`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setActiveUsers({
        count: Number(data?.count || 0),
        users: Array.isArray(data?.users) ? data.users : [],
        idle_timeout_minutes: data?.idle_timeout_minutes ?? null,
      })
    } catch {
      setActiveUsers({ count: 0, users: [], idle_timeout_minutes: null })
    } finally {
      setActiveUsersLoading(false)
    }
  }, [apiBase, canManageUsers])

  const loadGroups = useCallback(async () => {
    if (!canManageUsers) {
      setGroups([])
      return
    }
    try {
      const res = await fetch(`${apiBase}/users/groups`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      const nextGroups = Array.isArray(data)
        ? data
        : (Array.isArray(data?.groups) ? data.groups : [])
      setGroups(nextGroups)
    } catch {
      setGroups([])
    }
  }, [apiBase, canManageUsers])

  const loadRegistrationRequests = useCallback(async () => {
    if (!canManageUsers) return
    try {
      const res = await fetch(`${apiBase}/auth/register_requests`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setRegistrationRequests(Array.isArray(data) ? data : [])
    } catch {
      setRegistrationRequests([])
    }
  }, [apiBase, canManageUsers])

  const openCreate = useCallback(() => {
    if (!canManageUsers) return
    resetForm()
    setEditingId(null)
    setEditingSeedAdmin(false)
    setShowModal(true)
  }, [canManageUsers, resetForm])

  const openEdit = useCallback((u) => {
    if (!canManageUsers && user?.id !== u.id) return
    setEditingId(u.id)
    setEditingSeedAdmin((u.username || '').toLowerCase() === ADMIN_USERNAME)
    setForm({
      first_name: u.first_name || '',
      last_name: u.last_name || '',
      email: u.email || u.username || '',
      password: '',
      confirm: '',
      role: u.role || (u.is_admin ? 'sys_admin' : 'analyst'),
      requestor_group: u.requestor_group || '',
      employee_id: u.employee_id || '',
      local_auth_only: !!u.local_auth_only,
      is_active: u.is_active !== false,
    })
    setShowModal(true)
  }, [canManageUsers, user?.id])

  const saveUser = useCallback(async () => {
    if ((form.password || form.confirm) && form.password !== form.confirm) {
      flash('Passwords do not match.')
      return
    }
    if (editingId && !canManageUsers && editingId !== user?.id) {
      flash('You can only edit your own account.')
      return
    }

    let payload
    if (editingSeedAdmin) {
      if (!form.password) {
        flash('Please set a new password for the admin account.')
        return
      }
      payload = { password: form.password }
    } else {
      const first = (form.first_name || '').trim()
      const last = (form.last_name || '').trim()
      const email = (form.email || '').trim().toLowerCase()
      const editingSelfOnly = Boolean(editingId && editingId === user?.id && !canManageUsers)
      if (!first || !last || (!editingSelfOnly && !email)) {
        flash(editingSelfOnly ? 'First name and last name are required.' : 'First name, last name, and email are required.')
        return
      }
      const passwordRequiredForNewUser = !editingId && (!ssoEnabled || form.local_auth_only)
      if (passwordRequiredForNewUser && !(form.password || '').trim()) {
        flash('Password is required when creating a local credential user.')
        return
      }
      if ((form.password || '').trim() && (form.password || '').trim().length < 8) {
        flash('Password must be at least 8 characters.')
        return
      }
      const effectiveRole = isRequestor ? 'requestor' : (form.role || 'analyst')
      const techGroupRaw = (form.requestor_group || '').trim()
      if (canManageUsers && effectiveRole === 'tech') {
        if (!techGroupRaw) {
          flash('Tech accounts require a group (a configured ticket workflow group).')
          return
        }
      }
      const requiresEmployeeId = (['analyst', 'sys_admin'].includes(effectiveRole)) && email !== ADMIN_USERNAME
      if (!isRequestor) {
        if (requiresEmployeeId && !(form.employee_id || '').trim()) {
          flash(`${employeeIdLabel} is required for analysts and system admins.`)
          return
        }
      }
      payload = { first_name: first, last_name: last }
      if (editingSelfOnly) {
        if (!isRequestor) payload.employee_id = (form.employee_id || '').trim() || null
      } else {
        payload.username = email
        payload.email = email
      }
      if (canManageUsers && !isRequestor) {
        payload.role = effectiveRole
        payload.requestor_group = (form.requestor_group || '').trim() || null
        if (editingId) {
          payload.local_auth_only = !!form.local_auth_only
          payload.is_active = form.is_active !== false
        }
      } else if (!editingSelfOnly) {
        payload.role = 'requestor'
      }
      if (!isRequestor && !editingSelfOnly) payload.employee_id = (form.employee_id || '').trim() || null
      if (!editingSelfOnly) payload.is_admin = payload.role === 'sys_admin'
      if (editingId && canManageUsers && form.local_auth_only && !(form.password || '').trim() && !users.find(x => x.id === editingId)?.local_auth_only) {
        flash('Set a password when switching this account to local credentials.')
        return
      }
      if (form.password) payload.password = form.password
    }

    setUserSaveBusy(true)
    try {
      await saveUserRequest(apiBase, { editingId, payload })
      await loadUsers()
      await loadGroups()
      closeModal()
      if (editingId === user?.id) await refreshUser()
      showToast(editingId ? 'User updated.' : 'User created.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Unable to save user.', { variant: 'error' })
    } finally {
      setUserSaveBusy(false)
    }
  }, [apiBase, canManageUsers, closeModal, editingId, editingSeedAdmin, employeeIdLabel, flash, form, isRequestor, loadGroups, loadUsers, ssoEnabled, refreshUser, showToast, user?.id, users])

  const deleteUser = useCallback(async (id) => {
    if (!canManageUsers) return
    const target = users.find(u => u.id === id)
    if (!target) return
    const username = (target.username || '').trim().toLowerCase()
    if (username === ADMIN_USERNAME) {
      showToast('The built-in admin account cannot be deleted.', { variant: 'info' })
      return
    }
    const displayName = (target.first_name || target.last_name)
      ? `${target.first_name || ''} ${target.last_name || ''}`.trim()
      : (target.email || target.username || 'this user')
    if (!window.confirm(`Delete ${displayName}? This action cannot be undone.`)) return
    try {
      const res = await fetch(`${apiBase}/users/${id}`, { method: 'DELETE', credentials: 'include' })
      if (!res.ok) {
        const text = (await res.text()) || 'Unable to delete user.'
        throw new Error(text)
      }
      showToast('User deleted.', { variant: 'success' })
      await loadUsers()
      await loadGroups()
    } catch (err) {
      showToast(err?.message || 'Unable to delete user.', { variant: 'error' })
    }
  }, [apiBase, canManageUsers, loadGroups, loadUsers, showToast, users])

  const openGroup = useCallback((group) => {
    if (!group) return
    setGroupModal(group)
    setGroupForm({
      name: group.label || group.name || '',
      can_see_groups: Array.isArray(group.can_see_groups) ? [...group.can_see_groups] : [],
    })
  }, [])

  const openCreateGroup = useCallback(() => {
    if (!canManageUsers) return
    setGroupModal({ name: '', label: '', can_see_groups: [], users: [], isNew: true })
    setGroupForm({ name: '', can_see_groups: [] })
    setGroupSaving(false)
  }, [canManageUsers])

  const closeGroupModal = useCallback(() => {
    setGroupModal(null)
    setGroupForm({ name: '', can_see_groups: [] })
    setGroupSaving(false)
  }, [])

  const saveGroup = useCallback(async () => {
    if (!canManageUsers || !groupModal) return
    const nextLabel = (groupForm.name || '').trim()
    const nextName = normalizeGroupValue(nextLabel)
    if (!nextName || !nextLabel) {
      showToast('Group name is required.', { variant: 'warn' })
      return
    }
    setGroupSaving(true)
    try {
      const targets = Array.from(new Set((groupForm.can_see_groups || []).map(normalizeGroupValue).filter(Boolean)))
        .filter(g => g !== normalizeGroupValue(groupModal.name))
      const isNewGroup = !!groupModal?.isNew
      const res = await fetch(isNewGroup ? `${apiBase}/users/groups` : `${apiBase}/users/groups/${encodeURIComponent(groupModal.name)}`, {
        method: isNewGroup ? 'POST' : 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: nextLabel, can_see_groups: targets }),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || 'Unable to save group.')
      }
      const saved = await res.json().catch(() => null)
      await loadUsers()
      await loadGroups()
      await loadNtpGroups()
      setGroupModal(null)
      setGroupForm({ name: '', can_see_groups: [] })
      showToast(`Group ${saved?.label || nextLabel} ${isNewGroup ? 'created' : 'updated'}.`, { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Unable to save group.', { variant: 'error' })
    } finally {
      setGroupSaving(false)
    }
  }, [apiBase, canManageUsers, groupForm.can_see_groups, groupForm.name, groupModal, loadGroups, loadNtpGroups, loadUsers, normalizeGroupValue, showToast])

  const declineRegistration = useCallback(async (request) => {
    if (!canManageUsers) return
    const reason = window.prompt('Decline reason:', '')
    try {
      const res = await fetch(`${apiBase}/auth/register_requests/${request.id}/decline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ reason }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Request declined.', { variant: 'info' })
      loadRegistrationRequests()
    } catch (err) {
      showToast(err?.message || 'Unable to decline request.', { variant: 'error' })
    }
  }, [apiBase, canManageUsers, loadRegistrationRequests, showToast])

  const removeRegistrationRequest = useCallback(async (request) => {
    if (!canManageUsers || !request?.id) return
    const label = request?.email ? `${request.name || 'User'} (${request.email})` : (request?.name || 'this request')
    if (!window.confirm(`Remove account request for ${label}? This only deletes the stale request record.`)) return
    try {
      const res = await fetch(`${apiBase}/auth/register_requests/${request.id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Account request removed.', { variant: 'success' })
      loadRegistrationRequests()
    } catch (err) {
      showToast(err?.message || 'Unable to remove request.', { variant: 'error' })
    }
  }, [apiBase, canManageUsers, loadRegistrationRequests, showToast])

  const openApproveRegistration = useCallback((request) => {
    if (!canManageUsers) return
    const nextRole = ((request?.role || '') + '').trim().toLowerCase()
    const nextGroup = normalizeGroupValue(request?.requestor_group || '')
    setApproveRegRole(['sys_admin', 'analyst', 'requestor', 'tech'].includes(nextRole) ? nextRole : '')
    setApproveRegTarget(request)
    setApproveRegGroup(nextGroup)
    setApproveRegNewGroup('')
  }, [canManageUsers, normalizeGroupValue])

  const approveRegistration = useCallback(async () => {
    if (!canManageUsers || !approveRegTarget) return
    const role = (approveRegRole || '').trim().toLowerCase()
    if (!['sys_admin', 'analyst', 'requestor', 'tech'].includes(role)) {
      showToast('Select a user group for this account.', { variant: 'warn' })
      return
    }
    let chosen = ''
    if (role === 'tech') {
      const raw = (approveRegGroup || '').trim()
      const normalized = normalizeGroupValue(raw)
      if (!normalized) {
        showToast('Select a tech group (a configured ticket workflow group).', { variant: 'warn' })
        return
      }
      chosen = normalized
    } else if (role === 'requestor') {
      const raw = (approveRegNewGroup || approveRegGroup || '').trim()
      if (!raw) {
        showToast('Select or enter a department/group.', { variant: 'warn' })
        return
      }
      chosen = normalizeGroupValue(raw)
    }
    try {
      const res = await fetch(`${apiBase}/auth/register_requests/${approveRegTarget.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ requestor_group: chosen, role }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast((approveRegTarget?.status || '').toLowerCase() === 'approved' ? (ssoAuthEnabled ? 'Account ready email resent.' : 'Invitation resent.') : (ssoAuthEnabled ? 'Account approved and ready email sent.' : 'Invitation sent.'), { variant: 'success' })
      setApproveRegTarget(null)
      setApproveRegRole('')
      setApproveRegGroup('')
      setApproveRegNewGroup('')
      loadRegistrationRequests()
      loadUsers()
      loadGroups()
    } catch (err) {
      showToast(err?.message || 'Unable to approve request.', { variant: 'error' })
    }
  }, [apiBase, approveRegGroup, approveRegNewGroup, approveRegRole, approveRegTarget, ssoAuthEnabled, canManageUsers, loadGroups, loadRegistrationRequests, loadUsers, normalizeGroupValue, showToast])

  const resendRegistrationInvite = useCallback(async (request) => {
    if (!canManageUsers || !request) return
    const role = ((request.role || '') + '').trim().toLowerCase()
    if (!['sys_admin', 'analyst', 'requestor', 'tech'].includes(role)) {
      showToast('Role is missing for this request. Choose a role and resend.', { variant: 'warn' })
      openApproveRegistration(request)
      return
    }
    let requestorGroup = ''
    if (role === 'requestor' || role === 'tech') {
      requestorGroup = normalizeGroupValue(request.requestor_group || '')
      if (!requestorGroup) {
        showToast('Requestor/tech invites need a group. Choose one and resend.', { variant: 'warn' })
        openApproveRegistration(request)
        return
      }
    }
    setRegistrationInviteBusyId(request.id)
    try {
      const res = await fetch(`${apiBase}/auth/register_requests/${request.id}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ requestor_group: requestorGroup, role }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast(ssoAuthEnabled ? 'Account ready email resent.' : 'Invitation resent.', { variant: 'success' })
      loadRegistrationRequests()
      loadUsers()
      loadGroups()
    } catch (err) {
      showToast(err?.message || 'Unable to resend invitation.', { variant: 'error' })
    } finally {
      setRegistrationInviteBusyId(null)
    }
  }, [apiBase, ssoAuthEnabled, canManageUsers, loadGroups, loadRegistrationRequests, loadUsers, normalizeGroupValue, openApproveRegistration, showToast])

  return {
    users,
    editingId,
    editingSeedAdmin,
    showModal,
    approveRegTarget,
    approveRegRole,
    setApproveRegRole,
    approveRegGroup,
    setApproveRegGroup,
    approveRegNewGroup,
    setApproveRegNewGroup,
    setApproveRegTarget,
    registrationInviteBusyId,
    form,
    setForm,
    userSaveBusy,
    editingUser,
    groups,
    groupModal,
    groupForm,
    setGroupForm,
    groupSaving,
    activeUsers,
    activeUsersLoading,
    showActiveUsersModal,
    setShowActiveUsersModal,
    registrationRequests,
    formatGroupLabel,
    allGroupOptions,
    analystOptions,
    closeModal,
    loadUsers,
    loadActiveUsers,
    loadGroups,
    loadRegistrationRequests,
    openCreate,
    openEdit,
    saveUser,
    deleteUser,
    openGroup,
    openCreateGroup,
    closeGroupModal,
    saveGroup,
    declineRegistration,
    removeRegistrationRequest,
    openApproveRegistration,
    approveRegistration,
    resendRegistrationInvite,
  }
}