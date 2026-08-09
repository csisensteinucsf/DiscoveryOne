import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Columns3 } from 'lucide-react'
import { useAuth } from '../auth.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import { useConfirm } from '../components/ConfirmProvider.jsx'
import { fetchSystemSettings } from '../lib/systemSettingsClient.js'
import { normalizeCaseNamingMode } from './setupCatalog.js'
import { useBrandingSettings } from '../lib/useBrandingSettings.js'
import { CaseClosureModal, CaseDeleteModal, CaseEditorModal, RequestorGroupInviteModal } from './CaseModals.jsx'
import CasesGroupedTable from './CasesGroupedTable.jsx'
import { CasesTableRow, tableStyles } from './CasesTableRow.jsx'
import { useCasesGrouping } from './useCasesGrouping.js'
import {
  customFieldsFromDefinitions,
  customFieldValues,
  normalizeStoredCustomFields,
} from './caseCustomFields.js'
import {
  defaultCaseForm,
  displayNameFromEmail,
  firstToken,
  formatGroupLabel,
  formatUserName,
  isValidEmail,
  nameFromEmail,
  normalizeGroupValue,
  optionalDateValue,
  toSentenceCase,
} from './casesUtils.js'

const DEFAULT_CASE_COLUMNS = [
  'secondary_case_name',
  'matter_number',
  'internal_counsel',
  'analyst',
  'requestor',
  'state',
  'holds',
  'notes',
]

function formFromCaseTemplate(template, closureNagDays, current = {}) {
  const next = defaultCaseForm(closureNagDays)
  if (!template) {
    return {
      ...next,
      name: current.name || '',
      legal_case_name: current.legal_case_name || '',
    }
  }
  const defaults = template.defaults || {}
  for (const key of Object.keys(next)) {
    if (Object.prototype.hasOwnProperty.call(defaults, key)) next[key] = defaults[key] ?? ''
  }
  if (defaults.start_date_mode === 'today' && !defaults.start_date) {
    next.start_date = new Date().toISOString().slice(0, 10)
  }
  if (Array.isArray(defaults.requestors)) {
    const primary = defaults.requestors.find(item => item?.is_primary)
    const primaryEmail = primary?.email || defaults.requestor || defaults.requestors[0]?.email || ''
    next.requestor = primaryEmail
    next.additional_requestors = defaults.requestors
      .filter(item => item?.email && item !== primary && item.email.toLowerCase() !== primaryEmail.toLowerCase())
      .map(item => item.email)
      .join(', ')
  }
  next.custom_fields = customFieldsFromDefinitions(template.custom_fields)
  next.case_template_id = String(template.id)
  next.name = current.name || next.name || ''
  next.legal_case_name = current.legal_case_name || next.legal_case_name || ''
  return next
}


export default function Cases({ apiBase }) {
  const { user, refreshUser } = useAuth()
  const { appName } = useBrandingSettings(apiBase, { updateTitle: true, titleSuffix: 'Cases' })
  const casesPageTitle = `${appName} Cases`
  const { showToast } = useToast()
  const confirmDialog = useConfirm()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const caseSortMode = (user?.case_sort_mode || 'ediscovery').toLowerCase()
  const requestorGroup = normalizeGroupValue(user?.requestor_group || '')
  const isSysAdmin = role === 'sys_admin'
  const isRequestor = role === 'requestor'
  const isTech = role === 'tech'
  const isReadOnly = isRequestor || isTech
  const [caseNamingMode, setCaseNamingMode] = useState('legal_case_name')
  const [defaultClosureNagDays, setDefaultClosureNagDays] = useState(180)
  const [internalCounselLabel, setInternalCounselLabel] = useState('Internal Counsel')
  const useLegalCaseNameAsPrimary = caseNamingMode === 'legal_case_name'
  const showSecondaryCaseNameColumn = !isTech && !useLegalCaseNameAsPrimary
  const primaryCaseNameLabel = useLegalCaseNameAsPrimary ? 'Case Name' : 'eDiscovery Name'
  const prefersLegalCaseLabel = requestorGroup === 'risk' || requestorGroup === 'legal'
  const secondaryCaseNameLabel = prefersLegalCaseLabel ? 'Legal Case Name' : 'Case Name'
  const savedColumns = user?.ui_preferences?.cases?.visible_columns
  const [visibleColumns, setVisibleColumns] = useState(
    Array.isArray(savedColumns) ? savedColumns : DEFAULT_CASE_COLUMNS
  )
  const isColumnVisible = (key) => visibleColumns.includes(key)
  const showSecondaryColumn = showSecondaryCaseNameColumn && isColumnVisible('secondary_case_name')
  const caseTableColumnCount = 2 + DEFAULT_CASE_COLUMNS.reduce(
    (count, key) => count + ((key === 'secondary_case_name' ? showSecondaryColumn : isColumnVisible(key)) ? 1 : 0),
    0,
  )
  const [cases, setCases] = useState([])
  const [analysts, setAnalysts] = useState([])
  const [users, setUsers] = useState([])
  const [ntpGroupOptions, setNtpGroupOptions] = useState([])
  const [caseTemplates, setCaseTemplates] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(defaultCaseForm)
  const [inviteGroupModal, setInviteGroupModal] = useState(null)
  const [inviteGroup, setInviteGroup] = useState('')
  const [inviteNewGroup, setInviteNewGroup] = useState('')
  const [stats, setStats] = useState({})
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteWarning, setDeleteWarning] = useState(null)
  const [deleteOverrideReason, setDeleteOverrideReason] = useState('')
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [closureTarget, setClosureTarget] = useState(null)
  const [closureReadiness, setClosureReadiness] = useState(null)
  const [closureBusy, setClosureBusy] = useState(false)
  const navigate = useNavigate()
  const closeModal = () => {
    setShowModal(false)
    setEditingId(null)
  }

  const load = async () => {
    const cRes = await fetch(`${apiBase}/cases`, { credentials: 'include' })
    let casesData = []
    if (cRes.ok) casesData = await cRes.json()
    setCases(casesData)

    if (!isTech) {
      const [aRes, uRes, gRes] = await Promise.all([
        fetch(`${apiBase}/users/analysts`, { credentials: 'include' }),
        fetch(`${apiBase}/users`, { credentials: 'include' }).catch(() => null),
        fetch(`${apiBase}/ntp/groups`, { credentials: 'include' }).catch(() => null),
      ])
      if (aRes.ok) setAnalysts(await aRes.json())
      if (uRes && uRes.ok) setUsers(await uRes.json())
      if (gRes && gRes.ok) {
        const data = await gRes.json().catch(() => ({}))
        const groups = Array.isArray(data?.groups) ? data.groups.map(normalizeGroupValue).filter(Boolean) : []
        setNtpGroupOptions([...new Set(groups)].sort())
      } else {
        setNtpGroupOptions([])
      }
    } else {
      setAnalysts([])
      setUsers([])
      setNtpGroupOptions([])
    }

    if (isTech) {
      setStats({})
      return
    }

    const caseIds = (casesData || []).map(c => Number(c?.id)).filter(Number.isFinite)
    if (!caseIds.length) {
      setStats({})
      return
    }
    try {
      const statsRes = await fetch(`${apiBase}/cases/stats`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ case_ids: caseIds }),
      })
      if (statsRes.ok) {
        const payload = await statsRes.json().catch(() => ({}))
        if (payload && typeof payload === 'object') {
          setStats(payload)
          return
        }
      }
    } catch {
      setStats({})
      return
    }

    setStats({})
  }

  useEffect(() => { load() }, [isTech])

  useEffect(() => {
    const next = user?.ui_preferences?.cases?.visible_columns
    if (Array.isArray(next)) setVisibleColumns(next)
  }, [user?.ui_preferences])

  useEffect(() => {
    if (isTech) {
      setCaseTemplates([])
      return
    }
    let alive = true
    fetch(apiBase + '/case-templates', { credentials: 'include' })
      .then(response => response.ok ? response.json() : [])
      .then(rows => {
        if (alive) setCaseTemplates(Array.isArray(rows) ? rows : [])
      })
      .catch(() => {
        if (alive) setCaseTemplates([])
      })
    return () => { alive = false }
  }, [apiBase, isTech])

  useEffect(() => {
    let alive = true
    fetchSystemSettings(apiBase)
      .then(data => {
        if (!alive) return
        setCaseNamingMode(normalizeCaseNamingMode(data?.case_naming?.mode))
        setDefaultClosureNagDays(Number(data?.case_closure?.default_nag_days) || 180)
        setInternalCounselLabel(data?.institution?.internal_counsel_label || 'Internal Counsel')
      })
      .catch(() => {
        if (alive) {
          setCaseNamingMode(normalizeCaseNamingMode(null))
          setDefaultClosureNagDays(180)
        }
      })
    return () => { alive = false }
  }, [apiBase])

  const getSuggestedName = async () => {
    try {
      const r = await fetch(`${apiBase}/cases/suggest_name`, { credentials: 'include' })
      if (!r.ok) return ''
      const j = await r.json()
      return typeof j?.name === 'string' ? j.name : ''
    } catch {
      return ''
    }
  }

  const openNewCase = async () => {
    if (isReadOnly) return
    setEditingId(null)
    const suggestion = caseNamingMode === 'legal_case_name' ? '' : await getSuggestedName()
    const defaultTemplate = caseTemplates.find(template => template.is_default) || null
    setForm(formFromCaseTemplate(defaultTemplate, defaultClosureNagDays, { name: suggestion }))
    setShowModal(true)
  }

  const selectCaseTemplate = (templateId) => {
    const template = caseTemplates.find(item => String(item.id) === String(templateId)) || null
    setForm(current => formFromCaseTemplate(template, defaultClosureNagDays, current))
  }

  const toggleCaseColumn = async (key) => {
    const previous = visibleColumns
    const next = previous.includes(key)
      ? previous.filter(item => item !== key)
      : DEFAULT_CASE_COLUMNS.filter(item => item === key || previous.includes(item))
    setVisibleColumns(next)
    try {
      const response = await fetch(apiBase + '/auth/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ cases_visible_columns: next }),
      })
      if (!response.ok) throw new Error('Unable to save column preferences')
      await refreshUser()
    } catch {
      setVisibleColumns(previous)
      showToast('Unable to save Cases column preferences.', { variant: 'error' })
    }
  }

  const updateLegalCaseName = (value) => {
    setForm(f => ({
      ...f,
      legal_case_name: value,
      name: caseNamingMode === 'legal_case_name' ? value : f.name,
    }))
  }

  const openEdit = (c) => {
    if (isReadOnly) return
    const primary = (c.requestor || '').trim().toLowerCase()
    const extras = Array.isArray(c.requestors)
      ? c.requestors
        .filter(r => !r?.is_primary && (r.email || '').trim().toLowerCase() !== primary)
        .map(r => r.email)
        .filter(Boolean)
        .join(', ')
      : ''
    setEditingId(c.id)
    setForm({
      ...defaultCaseForm(defaultClosureNagDays),
      name: c.name || '',
      legal_case_name: c.legal_case_name || '',
      servicenow_inc_number: c.servicenow_inc_number || '',
      matter_number: c.matter_number || '',
      internal_counsel: c.internal_counsel || '',
      outside_counsel: c.outside_counsel || '',
      description: c.description || '',
      start_date: c.start_date || '',
      claimant: c.claimant || '',
      requestor: c.requestor || '',
      analyst_id: c.analyst_id ? String(c.analyst_id) : '',
      additional_requestors: extras,
      closure_nag_days: c.closure_nag_days ?? defaultClosureNagDays,
      case_template_id: c.case_template_id ? String(c.case_template_id) : '',
      custom_fields: normalizeStoredCustomFields(c.custom_fields),
      closed: !!c.closed,
      is_private: !!c.is_private,
      is_test_case: !!c.is_test_case,
    })
    setShowModal(true)
  }

  const analystsById = useMemo(() => {
    const m = new Map()
    for (const a of analysts) m.set(a.id, formatUserName(a))
    return m
  }, [analysts])
  const usersByEmail = useMemo(() => {
    const m = new Map()
    for (const u of users || []) {
      const email = (u.email || '').trim().toLowerCase()
      if (email) m.set(email, u)
    }
    return m
  }, [users])
  const requestorGroupOptions = useMemo(() => {
    const groups = new Set()
    for (const group of ntpGroupOptions || []) {
      const normalized = normalizeGroupValue(group)
      if (normalized) groups.add(normalized)
    }
    for (const u of users || []) {
      const group = normalizeGroupValue(u?.requestor_group || '')
      if (group) groups.add(group)
    }
    for (const c of cases || []) {
      if (!Array.isArray(c?.requestors)) continue
      c.requestors.forEach(r => {
        const group = normalizeGroupValue(r?.requestor_group || '')
        if (group) groups.add(group)
      })
    }
    return Array.from(groups).sort()
  }, [cases, ntpGroupOptions, users])

  const openCases = cases.filter(c => !c.closed)
  const closedCases = cases.filter(c => c.closed)

  const requestorOptions = useMemo(() => {
    const s = new Set()
    for (const c of cases) {
      const v = (c.requestor || '').trim()
      if (v && isValidEmail(v)) s.add(v)
      if (Array.isArray(c.requestors)) {
        c.requestors.forEach(r => {
          const e = (r?.email || '').trim()
          if (e && isValidEmail(e)) s.add(e)
        })
      }
    }
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [cases])

  const hasUserForEmail = (email) => {
    const key = (email || '').trim().toLowerCase()
    if (!key) return false
    return usersByEmail.has(key)
  }

  const askInviteGroup = (email) => {
    setInviteGroup('')
    setInviteNewGroup('')
    return new Promise(resolve => {
      setInviteGroupModal({ email, resolve })
    })
  }

  const closeInviteGroupModal = () => {
    inviteGroupModal?.resolve(null)
    setInviteGroupModal(null)
    setInviteGroup('')
    setInviteNewGroup('')
  }

  const confirmInviteGroup = () => {
    const chosen = normalizeGroupValue(inviteNewGroup || inviteGroup)
    if (!chosen) {
      showToast('Select or enter a group before sending the invite.', { variant: 'warn' })
      return
    }
    inviteGroupModal?.resolve(chosen)
    setInviteGroupModal(null)
    setInviteGroup('')
    setInviteNewGroup('')
  }

  const maybeInviteRequestorAccount = async (caseId, requestorEmail) => {
    const email = (requestorEmail || '').trim()
    if (!caseId || !email) return
    if (hasUserForEmail(email)) return
    const accepted = await confirmDialog({
      title: 'Invite requestor?',
      description: 'Would you like to create a DiscoveryOne account for this requestor?',
      confirmLabel: 'Send invite',
      cancelLabel: 'Not now',
    })
    if (!accepted) return
    const requestorGroup = await askInviteGroup(email)
    if (!requestorGroup) return
    const friendlyName = nameFromEmail(email)
    const res = await fetch(`${apiBase}/cases/${caseId}/invite_requestor`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ email, name: friendlyName, requestor_group: requestorGroup }),
    })
    if (res.ok) {
      const data = await res.json().catch(() => null)
      if (data?.reason === 'user_exists') {
        showToast('Requestor already has an account.', { variant: 'info' })
      } else {
        showToast('Requestor invite email sent.', { variant: 'success' })
      }
      return
    }
    const t = await res.text().catch(() => '')
    showToast(`Unable to send invite: ${t || 'Unknown error'}`, { variant: 'error' })
  }

  const submit = async (e) => {
    e.preventDefault()
    if (isReadOnly) return
    const trimmedRequestor = (form.requestor || '').trim()
    const primaryEmail = trimmedRequestor || ''
    const trimmedClaimant = (form.claimant || '').trim()
    if (trimmedRequestor && !isValidEmail(trimmedRequestor)) {
      showToast('Requestor must be a valid email address', { variant: 'warn' })
      return
    }
    const extraRequestors = (form.additional_requestors || '')
      .split(',')
      .map(v => v.trim())
      .filter(v => v)
    for (const addr of extraRequestors) {
      if (!isValidEmail(addr)) {
        showToast(`Invalid additional requestor email: ${addr}`, { variant: 'warn' })
        return
      }
    }
    const requestorsPayload = []
    if (primaryEmail) {
      requestorsPayload.push({ email: primaryEmail, is_primary: true })
    }
    extraRequestors.forEach(email => {
      if (email && !requestorsPayload.find(r => (r.email || '').toLowerCase() === email.toLowerCase())) {
        requestorsPayload.push({ email, is_primary: false })
      }
    })
    if (!requestorsPayload.length && trimmedRequestor) {
      requestorsPayload.push({ email: trimmedRequestor, is_primary: true })
    }

    const closureDaysRaw = form.closure_nag_days
    const closureDays = (closureDaysRaw === '' || closureDaysRaw === null || closureDaysRaw === undefined)
      ? undefined
      : Number(closureDaysRaw)

    if (!editingId && caseNamingMode === 'legal_case_name' && !form.legal_case_name.trim()) {
      showToast('Legal case name is required for the selected eDiscovery naming mode.', { variant: 'warn' })
      return
    }

    const payload = {
      name: caseNamingMode === 'legal_case_name' ? form.legal_case_name : form.name,
      legal_case_name: form.legal_case_name,
      servicenow_inc_number: null,
      claimant: trimmedClaimant || null,
      ler_representative: null,
      internal_counsel: (form.internal_counsel || '').trim() || null,
      outside_counsel: (form.outside_counsel || '').trim() || null,
      matter_number: (form.matter_number || '').trim() || null,
      requestor: trimmedRequestor || null,
      requestors: requestorsPayload.length ? requestorsPayload : undefined,
      analyst_id: form.analyst_id ? Number(form.analyst_id) : null,
      closed: editingId ? !!form.closed : false,
      is_private: !!form.is_private,
      is_test_case: !!form.is_test_case,
      color: form.color,
      description: form.description,
      start_date: optionalDateValue(form.start_date),
      closure_nag_days: Number.isFinite(closureDays) ? closureDays : undefined,
      case_template_id: !editingId && form.case_template_id ? Number(form.case_template_id) : undefined,
      custom_fields: customFieldValues(form.custom_fields),
    }
    const url = editingId ? `${apiBase}/cases/${editingId}` : `${apiBase}/cases`
    const method = editingId ? 'PUT' : 'POST'
    const res = await fetch(url, {
      method, headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify(payload)
    })
    if (res.ok) {
      const saved = await res.json().catch(() => null)
      closeModal()
      setForm(defaultCaseForm(defaultClosureNagDays))
      const caseId = (saved && saved.id) || editingId
      if (caseId && primaryEmail) {
        await maybeInviteRequestorAccount(caseId, primaryEmail)
      }
      try {
        await load()
      } catch {
        navigate(0)
      }
      showToast(editingId ? 'Case updated.' : 'Case created.', { variant: 'success' })
      return
    }
    const t = await res.text().catch(() => '')
    showToast(`${editingId ? 'Update' : 'Create'} failed: ${t || 'Unknown error'}`, { variant: 'error' })
  }

  const toggleClosed = async (caseRecord) => {
    if (isReadOnly) return
    const closing = !caseRecord.closed
    if (closing) {
      const response = await fetch(`${apiBase}/cases/${caseRecord.id}/closure-readiness`, { credentials: 'include' })
      if (!response.ok) {
        showToast('Unable to check whether this case can be closed.', { variant: 'error' })
        return
      }
      setClosureReadiness(await response.json())
      setClosureTarget(caseRecord)
      return
    }
    const accepted = await confirmDialog({
      title: 'Reopen case',
      description: 'Reopen this case and move it to Active Cases?',
      confirmLabel: 'Reopen case',
    })
    if (!accepted) return
    await updateClosedState(caseRecord, false)
  }

  const updateClosedState = async (caseRecord, closed) => {
    const response = await fetch(apiBase + '/cases/' + caseRecord.id, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ closed }),
    })
    if (!response.ok) {
      const detail = await response.json().catch(() => null)
      const message = detail?.detail?.message || detail?.detail || 'Unknown error'
      throw new Error(typeof message === 'string' ? message : 'Unable to update case status')
    }
    showToast(closed ? 'Case closed.' : 'Case reopened.', { variant: 'success' })
    await load()
  }

  const confirmCloseCase = async () => {
    if (!closureTarget || closureReadiness?.ready === false) return
    setClosureBusy(true)
    try {
      await updateClosedState(closureTarget, true)
      setClosureTarget(null)
      setClosureReadiness(null)
    } catch (error) {
      showToast(`Close failed: ${error?.message || 'Unknown error'}`, { variant: 'error' })
      const response = await fetch(`${apiBase}/cases/${closureTarget.id}/closure-readiness`, { credentials: 'include' }).catch(() => null)
      if (response?.ok) setClosureReadiness(await response.json())
    } finally {
      setClosureBusy(false)
    }
  }

  const remove = (caseRecord) => {
    if (!isSysAdmin) return
    setDeleteTarget(caseRecord)
    setDeleteWarning(null)
    setDeleteOverrideReason('')
  }

  const closeDeleteModal = () => {
    if (deleteBusy) return
    setDeleteTarget(null)
    setDeleteWarning(null)
    setDeleteOverrideReason('')
  }

  const confirmDelete = async () => {
    if (!deleteTarget || !isSysAdmin || deleteBusy) return
    const requiresOverride = deleteWarning?.code === 'case_has_history'
    const reason = deleteOverrideReason.trim()
    if (requiresOverride && reason.length < 10) {
      showToast('Enter an override reason of at least 10 characters.', { variant: 'warn' })
      return
    }

    setDeleteBusy(true)
    try {
      const params = new URLSearchParams()
      if (requiresOverride) {
        params.set('override', 'true')
        params.set('override_reason', reason)
      }
      const suffix = params.toString() ? '?' + params.toString() : ''
      const response = await fetch(apiBase + '/cases/' + deleteTarget.id + suffix, {
        method: 'DELETE',
        credentials: 'include',
      })
      const body = await response.json().catch(() => null)
      if (response.status === 409 && body?.detail?.code === 'case_has_history') {
        setDeleteWarning(body.detail)
        return
      }
      if (!response.ok) {
        const message = body?.detail?.message || body?.detail || 'Unknown error'
        showToast('Delete failed: ' + message, { variant: 'error' })
        return
      }

      showToast('Case permanently deleted.', { variant: 'success' })
      setDeleteTarget(null)
      setDeleteWarning(null)
      setDeleteOverrideReason('')
      await load()
    } finally {
      setDeleteBusy(false)
    }
  }
  const {
    groupCases,
    setGroupCases,
    caseSort,
    setCaseSort,
    toggleSort,
    caseFilters,
    setCaseFilters,
    resetCaseFilters,
    analystFirstName,
    expandedYearsOpen,
    expandedYearsClosed,
    expandedLettersOpen,
    expandedLettersClosed,
    toggleYear,
    toggleLetter,
    letterKey,
    openFiltered,
    closedFiltered,
    openGroups,
    closedGroups,
  } = useCasesGrouping({
    openCases,
    closedCases,
    stats,
    analysts,
    analystsById,
    caseSortMode,
  })
  const Row = ({ c }) => (
    <CasesTableRow
      c={c}
      stats={stats}
      showSecondaryCaseNameColumn={showSecondaryCaseNameColumn}
      visibleColumns={visibleColumns}
      useLegalCaseNameAsPrimary={useLegalCaseNameAsPrimary}
      analystFirstName={analystFirstName}
      requestorDisplayName={(email) => displayNameFromEmail(email, usersByEmail)}
      isReadOnly={isReadOnly}
      canDelete={isSysAdmin}
      onEdit={openEdit}
      onToggleClosed={toggleClosed}
      onDelete={remove}
    />
  )
  const columnPicker = (
    <details className="column-picker column-picker--compact">
      <summary className="btn ghost compact">
        <Columns3 size={14} aria-hidden="true" />
        Columns
      </summary>
      <div className="column-picker__menu">
        <div className="column-picker__locked">Case Name and Actions are always shown.</div>
        {DEFAULT_CASE_COLUMNS
          .filter(key => key !== 'secondary_case_name' || showSecondaryCaseNameColumn)
          .map(key => (
            <label key={key}>
              <input
                type="checkbox"
                checked={isColumnVisible(key)}
                onChange={() => toggleCaseColumn(key)}
              />
              <span>{({
                secondary_case_name: secondaryCaseNameLabel,
                matter_number: 'Matter Number',
                internal_counsel: internalCounselLabel,
                analyst: 'Analyst',
                requestor: 'Requestor',
                state: 'State',
                holds: 'Holds',
                notes: 'Additional Notes / Comments',
              })[key]}</span>
            </label>
          ))}
      </div>
    </details>
  )
  return (
    <div className="cases-page">
      <div className="page-header">
        <h2>{casesPageTitle}</h2>
      </div>
      {!isReadOnly && <div className="cases-primary-actions"><button className="btn" onClick={openNewCase}>New Case</button></div>}

      {isRequestor && (
        <div className="card" style={{ marginBottom: '1rem', background: '#fefce8', border: '1px solid #fde68a' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: '0 0 4px 0' }}>Need to start a new case?</h3>
              <p style={{ margin: 0, color: '#92400e' }}>Use the case intake form to submit requests or add custodians/searches.</p>
            </div>
            <button className="btn" onClick={() => navigate('/requests')}>Open Case Intake</button>
          </div>
        </div>
      )}
      {isTech && (
        <div className="card" style={{ marginBottom: '1rem', background: '#eff6ff', border: '1px solid #bfdbfe' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h3 style={{ margin: '0 0 4px 0' }}>Ticket-only access</h3>
              <p style={{ margin: 0, color: '#1d4ed8' }}>Tech accounts can view cases that match their ticket group and manage tickets only.</p>
            </div>
          </div>
        </div>
      )}

      <CasesGroupedTable
        title="Active Cases"
        items={openFiltered}
        groups={openGroups}
        emptyLabel="No active cases"
        which="open"
        caseSort={caseSort}
        setCaseSort={setCaseSort}
        toggleSort={toggleSort}
        groupCases={groupCases}
        setGroupCases={setGroupCases}
        resetCaseFilters={resetCaseFilters}
        caseFilters={caseFilters}
        setCaseFilters={setCaseFilters}
        showSecondaryCaseNameColumn={showSecondaryColumn}
        visibleColumns={visibleColumns}
        primaryCaseNameLabel={primaryCaseNameLabel}
        secondaryCaseNameLabel={secondaryCaseNameLabel}
        internalCounselLabel={internalCounselLabel}
        tableStyles={tableStyles}
        caseTableColumnCount={caseTableColumnCount}
        expandedYears={expandedYearsOpen}
        expandedLetters={expandedLettersOpen}
        toggleYear={toggleYear}
        toggleLetter={toggleLetter}
        letterKey={letterKey}
        RowComponent={Row}
        toolbarExtra={columnPicker}
        style={{ marginBottom: '1rem' }}
      />
      <CasesGroupedTable
        title="Inactive Cases"
        items={closedFiltered}
        groups={closedGroups}
        emptyLabel="No inactive cases"
        which="closed"
        caseSort={caseSort}
        setCaseSort={setCaseSort}
        toggleSort={toggleSort}
        groupCases={groupCases}
        setGroupCases={setGroupCases}
        resetCaseFilters={resetCaseFilters}
        caseFilters={caseFilters}
        setCaseFilters={setCaseFilters}
        showSecondaryCaseNameColumn={showSecondaryColumn}
        visibleColumns={visibleColumns}
        primaryCaseNameLabel={primaryCaseNameLabel}
        secondaryCaseNameLabel={secondaryCaseNameLabel}
        internalCounselLabel={internalCounselLabel}
        tableStyles={tableStyles}
        caseTableColumnCount={caseTableColumnCount}
        expandedYears={expandedYearsClosed}
        expandedLetters={expandedLettersClosed}
        toggleYear={toggleYear}
        toggleLetter={toggleLetter}
        letterKey={letterKey}
        RowComponent={Row}
      />
      <CaseEditorModal
        open={showModal}
        editingId={editingId}
        form={form}
        setForm={setForm}
        analysts={analysts}
        requestorOptions={requestorOptions}
        caseNamingMode={caseNamingMode}
        secondaryCaseNameLabel={secondaryCaseNameLabel}
        useLegalCaseNameAsPrimary={useLegalCaseNameAsPrimary}
        internalCounselLabel={internalCounselLabel}
        onClose={closeModal}
        onSubmit={submit}
        onLegalCaseNameChange={updateLegalCaseName}
        formatAnalystName={formatUserName}
        caseTemplates={caseTemplates}
        selectedTemplate={caseTemplates.find(item => String(item.id) === String(form.case_template_id)) || null}
        onTemplateChange={selectCaseTemplate}
      />

      <CaseDeleteModal
        target={deleteTarget}
        warning={deleteWarning}
        overrideReason={deleteOverrideReason}
        setOverrideReason={setDeleteOverrideReason}
        busy={deleteBusy}
        onClose={closeDeleteModal}
        onConfirm={confirmDelete}
      />
      <CaseClosureModal
        target={closureTarget}
        readiness={closureReadiness}
        busy={closureBusy}
        onClose={() => {
          setClosureTarget(null)
          setClosureReadiness(null)
        }}
        onConfirm={confirmCloseCase}
        onOpenHold={(hold) => {
          if (!closureTarget?.id || !hold?.hold_id) return
          const targetCaseId = closureTarget.id
          setClosureTarget(null)
          setClosureReadiness(null)
          navigate(`/cases/${targetCaseId}?tab=holds&hold_id=${hold.hold_id}`)
        }}
      />
      <RequestorGroupInviteModal
        inviteGroupModal={inviteGroupModal}
        inviteGroup={inviteGroup}
        inviteNewGroup={inviteNewGroup}
        requestorGroupOptions={requestorGroupOptions}
        onClose={closeInviteGroupModal}
        onConfirm={confirmInviteGroup}
        onInviteGroupChange={(value) => {
          setInviteGroup(value)
          setInviteNewGroup('')
        }}
        onInviteNewGroupChange={(value) => {
          setInviteNewGroup(value)
          setInviteGroup('')
        }}
        formatGroupLabel={formatGroupLabel}
      />
    </div>
  )
}
