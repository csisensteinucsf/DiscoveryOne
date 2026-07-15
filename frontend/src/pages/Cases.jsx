import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import { useConfirm } from '../components/ConfirmProvider.jsx'
import { fetchSystemSettings } from '../lib/systemSettingsClient.js'
import { normalizeCaseNamingMode } from './setupCatalog.js'
import { useBrandingSettings } from '../lib/useBrandingSettings.js'
import { CaseEditorModal, RequestorGroupInviteModal } from './CaseModals.jsx'
import CasesGroupedTable from './CasesGroupedTable.jsx'
import { CasesTableRow, tableStyles } from './CasesTableRow.jsx'
import { useCasesGrouping } from './useCasesGrouping.js'
import {
  defaultCaseForm,
  displayNameFromEmail,
  firstToken,
  formatGroupLabel,
  formatUserName,
  isValidEmail,
  nameFromEmail,
  normalizeGroupValue,
  toSentenceCase,
} from './casesUtils.js'


export default function Cases({ apiBase }) {
  const { user } = useAuth()
  const { appName } = useBrandingSettings(apiBase, { updateTitle: true, titleSuffix: 'Cases' })
  const casesPageTitle = `${appName} Cases`
  const { showToast } = useToast()
  const confirmDialog = useConfirm()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const caseSortMode = (user?.case_sort_mode || 'ediscovery').toLowerCase()
  const requestorGroup = normalizeGroupValue(user?.requestor_group || '')
  const isRequestor = role === 'requestor'
  const isTech = role === 'tech'
  const isReadOnly = isRequestor || isTech
  const [caseNamingMode, setCaseNamingMode] = useState('legal_case_name')
  const [defaultClosureNagDays, setDefaultClosureNagDays] = useState(180)
  const useLegalCaseNameAsPrimary = caseNamingMode === 'legal_case_name'
  const showSecondaryCaseNameColumn = !isTech && !useLegalCaseNameAsPrimary
  const primaryCaseNameLabel = useLegalCaseNameAsPrimary ? 'Case Name' : 'eDiscovery Name'
  const prefersLegalCaseLabel = requestorGroup === 'risk' || requestorGroup === 'legal'
  const secondaryCaseNameLabel = prefersLegalCaseLabel ? 'Legal Case Name' : 'Case Name'
  const caseTableColumnCount = 5 + (showSecondaryCaseNameColumn ? 1 : 0)
  const [cases, setCases] = useState([])
  const [analysts, setAnalysts] = useState([])
  const [users, setUsers] = useState([])
  const [ntpGroupOptions, setNtpGroupOptions] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(defaultCaseForm)
  const [inviteGroupModal, setInviteGroupModal] = useState(null)
  const [inviteGroup, setInviteGroup] = useState('')
  const [inviteNewGroup, setInviteNewGroup] = useState('')
  const [stats, setStats] = useState({})
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
    let alive = true
    fetchSystemSettings(apiBase)
      .then(data => {
        if (!alive) return
        setCaseNamingMode(normalizeCaseNamingMode(data?.case_naming?.mode))
        setDefaultClosureNagDays(Number(data?.case_closure?.default_nag_days) || 180)
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
    setForm({ ...defaultCaseForm(defaultClosureNagDays), name: suggestion })
    setShowModal(true)
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
      claimant: c.claimant || '',
      requestor: c.requestor || '',
      analyst_id: c.analyst_id ? String(c.analyst_id) : '',
      additional_requestors: extras,
      closure_nag_days: c.closure_nag_days ?? defaultClosureNagDays,
      closed: !!c.closed,
      is_private: !!c.is_private,
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
      requestor: trimmedRequestor || null,
      requestors: requestorsPayload.length ? requestorsPayload : undefined,
      analyst_id: form.analyst_id ? Number(form.analyst_id) : null,
      closed: editingId ? !!form.closed : false,
      is_private: !!form.is_private,
      color: form.color,
      description: form.description,
      start_date: form.start_date,
      closure_nag_days: Number.isFinite(closureDays) ? closureDays : undefined,
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

  const remove = async (id) => {
    if (isReadOnly) return
    const accepted = await confirmDialog({
      title: 'Delete case',
      description: 'Are you sure you want to delete this case? This action cannot be undone.',
      confirmLabel: 'Delete case',
      destructive: true,
    })
    if (!accepted) return
    const res = await fetch(`${apiBase}/cases/${id}`, { method: 'DELETE', credentials: 'include' })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      showToast(`Delete failed: ${t || 'Unknown error'}`, { variant: 'error' })
      return
    }
    showToast('Case deleted.', { variant: 'success' })
    load()
  }

  const {
    showFilters,
    setShowFilters,
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
      useLegalCaseNameAsPrimary={useLegalCaseNameAsPrimary}
      analystFirstName={analystFirstName}
      requestorDisplayName={(email) => displayNameFromEmail(email, usersByEmail)}
      isReadOnly={isReadOnly}
      onEdit={openEdit}
      onDelete={remove}
    />
  )
  return (
    <div>
      <div className="page-header">
        <h2>{casesPageTitle}</h2>
        {!isReadOnly && <button className="btn" onClick={openNewCase}>New Case</button>}
      </div>

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
        title="Open Cases"
        groups={openGroups}
        emptyLabel="No open cases"
        which="open"
        showFilters={showFilters}
        setShowFilters={setShowFilters}
        resetCaseFilters={resetCaseFilters}
        caseFilters={caseFilters}
        setCaseFilters={setCaseFilters}
        showSecondaryCaseNameColumn={showSecondaryCaseNameColumn}
        primaryCaseNameLabel={primaryCaseNameLabel}
        secondaryCaseNameLabel={secondaryCaseNameLabel}
        tableStyles={tableStyles}
        caseTableColumnCount={caseTableColumnCount}
        expandedYears={expandedYearsOpen}
        expandedLetters={expandedLettersOpen}
        toggleYear={toggleYear}
        toggleLetter={toggleLetter}
        letterKey={letterKey}
        RowComponent={Row}
        style={{ marginBottom: '1rem' }}
      />
      <CasesGroupedTable
        title="Closed Cases"
        groups={closedGroups}
        emptyLabel="No closed cases"
        which="closed"
        showFilters={showFilters}
        setShowFilters={setShowFilters}
        resetCaseFilters={resetCaseFilters}
        caseFilters={caseFilters}
        setCaseFilters={setCaseFilters}
        showSecondaryCaseNameColumn={showSecondaryCaseNameColumn}
        primaryCaseNameLabel={primaryCaseNameLabel}
        secondaryCaseNameLabel={secondaryCaseNameLabel}
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
        onClose={closeModal}
        onSubmit={submit}
        onLegalCaseNameChange={updateLegalCaseName}
        formatAnalystName={formatUserName}
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
