import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { useToast } from '../components/ToastProvider.jsx'
import { useConfirm } from '../components/ConfirmProvider.jsx'
import LoadingOverlay from '../components/LoadingOverlay.jsx'
import CaseRequestModal from './CaseRequestModal.jsx'
import { ApproveCaseRequestModal, DeclineRequestModal, RequestDetailModal } from './CaseRequestModals.jsx'
import CaseRequestCards from './CaseRequestCards.jsx'
import CaseRequestDetailBody from './CaseRequestDetailBody.jsx'
import CaseRequestsAdminTable from './CaseRequestsAdminTable.jsx'
import {
  TYPE_LABELS,
  REQUEST_COLLAPSE_KEYS,
  loadStoredSet,
  persistStoredSet,
  hasStoredCollapseState,
} from './caseRequestsUtils.js'

export default function CaseRequests({ apiBase }) {
  const { user } = useAuth()
  const { showToast } = useToast()
  const confirmDialog = useConfirm()
  const ADMIN_USERNAME = 'admin'
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const isRequestor = role === 'requestor'
  const [requests, setRequests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalCfg, setModalCfg] = useState(null)
  const [caseLookup, setCaseLookup] = useState({})
  const location = useLocation()
  const navigate = useNavigate()
  const [declineTarget, setDeclineTarget] = useState(null)
  const [declineReason, setDeclineReason] = useState('')
  const [declineBusy, setDeclineBusy] = useState(false)
  const [analysts, setAnalysts] = useState([])
  const [approveModal, setApproveModal] = useState(null)
  const [approveAnalyst, setApproveAnalyst] = useState('')
  const [overlayMessage, setOverlayMessage] = useState('')
  const [selectedRequest, setSelectedRequest] = useState(null)
  const [showAdminFilters, setShowAdminFilters] = useState(false)
  const [adminRequestFilters, setAdminRequestFilters] = useState({ search: '', status: '', type: '', requestor: '' })
  const [expandedRequestYears, setExpandedRequestYears] = useState(() => loadStoredSet(REQUEST_COLLAPSE_KEYS.years))
  const [expandedRequestLetters, setExpandedRequestLetters] = useState(() => loadStoredSet(REQUEST_COLLAPSE_KEYS.letters))
  const [expandedRequestNames, setExpandedRequestNames] = useState(() => loadStoredSet(REQUEST_COLLAPSE_KEYS.names))
  const approveProgressRef = useRef({ timer: null, requestId: null })
  const requestGroupingInitializedRef = useRef(false)
  const requestGroupingHasStoredStateRef = useRef(hasStoredCollapseState())

  const stopApproveProgress = useCallback(() => {
    if (approveProgressRef.current.timer) {
      clearInterval(approveProgressRef.current.timer)
      approveProgressRef.current.timer = null
    }
    approveProgressRef.current.requestId = null
  }, [])

  const approvalOverlaySubtitle = useMemo(() => {
    if (!overlayMessage) return undefined
    const text = String(overlayMessage || '').toLowerCase()
    const looksLikeApprove = (
      text.includes('approv')
      || text.includes('creating case')
      || text.includes('purview')
      || text.includes('finalizing')
      || text.includes('setting up')
    )
    if (!looksLikeApprove) return undefined
    return 'This can take 5-10 minutes depending on the number of custodians and preservation requests. Please do not close the window.'
  }, [overlayMessage])

  const startApproveProgress = useCallback((requestId, initialMessage, { poll = false } = {}) => {
    stopApproveProgress()
    setOverlayMessage(initialMessage)
    if (!poll) return
    approveProgressRef.current.requestId = requestId
    const pollOnce = async () => {
      if (approveProgressRef.current.requestId !== requestId) return
      try {
        const res = await fetch(`${apiBase}/case_requests/${requestId}/progress`, { credentials: 'include' })
        if (!res.ok) return
        const data = await res.json().catch(() => null)
        if (!data || approveProgressRef.current.requestId !== requestId) return
        if (data?.message) {
          setOverlayMessage(data.message)
        }
      } catch (err) {
        console.error(err)
      }
    }
    pollOnce()
    approveProgressRef.current.timer = window.setInterval(pollOnce, 1200)
  }, [apiBase, stopApproveProgress])

  useEffect(() => () => stopApproveProgress(), [stopApproveProgress])

  const refreshStats = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/case_requests/stats`, { credentials: 'include' })
      if (!res.ok) return
      const stats = await res.json()
      window.dispatchEvent(new CustomEvent('case-requests:stats', { detail: stats }))
    } catch (err) {
      console.error(err)
    }
  }, [apiBase])

  useEffect(() => {
    if (isRequestor) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${apiBase}/users`, { credentials: 'include' })
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return
        const filtered = (Array.isArray(data) ? data : []).filter(u => {
          const r = (u.role || (u.is_admin ? 'sys_admin' : 'analyst')).toLowerCase()
          if (!(r === 'analyst' || r === 'sys_admin')) return false
          const username = String(u.username || '').trim().toLowerCase()
          return username !== ADMIN_USERNAME
        })
        setAnalysts(filtered)
      } catch (err) {
        console.error(err)
      }
    })()
    return () => { cancelled = true }
  }, [apiBase, isRequestor])

  useEffect(() => {
    if (isRequestor) return
    persistStoredSet(REQUEST_COLLAPSE_KEYS.years, expandedRequestYears)
  }, [expandedRequestYears, isRequestor])

  useEffect(() => {
    if (isRequestor) return
    persistStoredSet(REQUEST_COLLAPSE_KEYS.letters, expandedRequestLetters)
  }, [expandedRequestLetters, isRequestor])

  useEffect(() => {
    if (isRequestor) return
    persistStoredSet(REQUEST_COLLAPSE_KEYS.names, expandedRequestNames)
  }, [expandedRequestNames, isRequestor])

    const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const endpoint = isRequestor ? '/case_requests/mine' : '/case_requests'
      const perPage = 200
      let page = 1
      let total = null
      const allItems = []

      while (true) {
        const sep = endpoint.includes('?') ? '&' : '?'
        const url = `${apiBase}${endpoint}${sep}paged=1&page=${page}&per_page=${perPage}`
        const res = await fetch(url, { credentials: 'include' })
        if (!res.ok) throw new Error('Unable to load requests')
        const data = await res.json()

        if (Array.isArray(data)) {
          allItems.push(...data)
          break
        }

        const items = Array.isArray(data?.items) ? data.items : []
        allItems.push(...items)
        const nextTotal = Number(data?.total)
        if (Number.isFinite(nextTotal) && nextTotal >= 0) total = nextTotal

        if (items.length === 0) break
        if (total != null && allItems.length >= total) break
        page += 1
        if (page > 200) break
      }

      const sanitized = isRequestor ? allItems.filter((req) => !req.case_deleted) : allItems
      setRequests(sanitized)
      setSelectedRequest((current) => {
        if (!current) return current
        return sanitized.find((req) => req.id === current.id) || null
      })
      refreshStats()
    } catch (err) {
      console.error(err)
      setError(err?.message || 'Unable to load requests')
      setRequests([])
    } finally {
      setLoading(false)
    }
  }, [apiBase, isRequestor, refreshStats])

  const ensureCaseMeta = useCallback(async (id) => {
    if (!id || caseLookup[id]) return
    try {
      const res = await fetch(`${apiBase}/cases/${id}`, { credentials: 'include' })
      if (!res.ok) return
      const data = await res.json()
      setCaseLookup((prev) => ({ ...prev, [id]: data }))
    } catch (err) {
      console.error(err)
    }
  }, [apiBase, caseLookup])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const type = params.get('type')
    if (!type) return
    const normalized = type.toLowerCase()
    if (!['new_case', 'custodian', 'search'].includes(normalized)) return
    const caseId = params.get('caseId')
    if (caseId) {
      ensureCaseMeta(caseId)
    }
    setModalCfg({ mode: normalized, caseId })
  }, [location.search, ensureCaseMeta])

  const closeModal = () => {
    setModalCfg(null)
    navigate('/requests', { replace: true })
  }

  const approve = async (id) => {
    const target = requests.find(r => r.id === id)
    const isNewCase = target?.request_type === 'new_case'
    if (isNewCase) {
      setApproveAnalyst('')
      setApproveModal(target)
      return
    }
    const confirmed = await confirmDialog({
      title: 'Approve request',
      description: 'Approve this request? This action will apply immediately.',
      confirmLabel: 'Approve',
    })
    if (!confirmed) return
    try {
      startApproveProgress(id, 'Approving request...', { poll: false })
      const res = await fetch(`${apiBase}/case_requests/${id}/approve`, { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error('Approval failed')
      await load()
      showToast('Request approved.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Approval failed', { variant: 'error' })
    } finally {
      stopApproveProgress()
      setOverlayMessage('')
    }
  }

  const confirmApproveWithAnalyst = async () => {
    if (!approveModal) return
    const analystId = Number(approveAnalyst)
    if (!Number.isFinite(analystId)) {
      showToast('Select an analyst to assign.', { variant: 'warn' })
      return
    }
    try {
      startApproveProgress(approveModal.id, 'Creating case in DiscoveryOne...', { poll: true })
      const res = await fetch(`${apiBase}/case_requests/${approveModal.id}/approve`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analyst_id: analystId }),
      })
      if (!res.ok) throw new Error('Approval failed')
      setApproveModal(null)
      setApproveAnalyst('')
      await load()
      showToast('Request approved and analyst assigned.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Approval failed', { variant: 'error' })
    } finally {
      stopApproveProgress()
      setOverlayMessage('')
    }
  }

  const startDecline = (id) => {
    setDeclineTarget(id)
    setDeclineReason('')
    setDeclineBusy(false)
  }

  const closeDeclineDialog = () => {
    setDeclineTarget(null)
    setDeclineReason('')
    setDeclineBusy(false)
  }

  const submitDecline = async () => {
    if (!declineTarget) return
    if (!declineReason.trim()) {
      showToast('Decline reason is required.', { variant: 'warn' })
      return
    }
    setDeclineBusy(true)
    try {
      setOverlayMessage('Declining request\u2026')
      const res = await fetch(`${apiBase}/case_requests/${declineTarget}/decline`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: declineReason.trim() }),
      })
      if (!res.ok) throw new Error('Decline failed')
      showToast('Request declined.', { variant: 'info' })
      closeDeclineDialog()
      await load()
    } catch (err) {
      console.error(err)
      showToast(err?.message || 'Decline failed', { variant: 'error' })
      setDeclineBusy(false)
    } finally {
      setOverlayMessage('')
    }
  }

  const heading = isRequestor ? 'Case Intake & Requests' : 'Requestor Requests'
  const THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000
  const now = Date.now()
  const isRecent = (iso) => {
    if (!iso) return false
    const ts = Date.parse(iso)
    if (Number.isNaN(ts)) return false
    return now - ts <= THIRTY_DAYS_MS
  }
  const pendingRequests = useMemo(() => requests.filter((r) => r.status === 'pending'), [requests])
  const declinedRequests = useMemo(() => requests.filter((r) => r.status === 'declined' && isRecent(r.reviewed_at)), [requests])
  const approvedRequests = useMemo(() => requests.filter((r) => r.status === 'approved' && isRecent(r.reviewed_at)), [requests])

  const requestCaseName = (req) => {
    const payload = req?.payload || {}
    return req?.case_name || payload.name || (req?.case_id && caseLookup[req.case_id]?.name) || 'Pending case'
  }

  const requestorLabel = (req) => req?.requestor?.email || req?.requestor?.username || ''

  const requestYear = (req) => {
    const caseName = requestCaseName(req)
    const nameMatch = String(caseName || '').match(/\b(20\d{2}|19\d{2})\b/)
    if (nameMatch) return nameMatch[1]
    const ts = Date.parse(req?.created_at || '')
    if (!Number.isNaN(ts)) return String(new Date(ts).getFullYear())
    return 'Unknown'
  }

  const requestLetter = (req) => {
    const caseName = String(requestCaseName(req) || '').trim()
    const remainder = caseName.replace(/^\s*\d{4}[-\s]?/, '').trim() || caseName
    const ch = (remainder[0] || '#').toUpperCase()
    return ch.match(/[A-Z]/) ? ch : '#'
  }

  const adminFilteredRequests = useMemo(() => {
    if (isRequestor) return requests
    const filters = adminRequestFilters
    const search = String(filters.search || '').trim().toLowerCase()
    const status = String(filters.status || '').trim().toLowerCase()
    const type = String(filters.type || '').trim().toLowerCase()
    const requestor = String(filters.requestor || '').trim().toLowerCase()
    return (requests || []).filter((req) => {
      const payload = req?.payload || {}
      const caseName = requestCaseName(req)
      const reqRequestor = requestorLabel(req)
      const reqStatus = String(req?.status || '').toLowerCase()
      const reqType = String(req?.request_type || '').toLowerCase()
      if (status && reqStatus !== status) return false
      if (type && reqType !== type) return false
      if (requestor && !reqRequestor.toLowerCase().includes(requestor)) return false
      if (!search) return true
      const custodianText = Array.isArray(payload.custodians)
        ? payload.custodians.map(c => `${c?.name || ''} ${c?.email || ''}`).join(' ')
        : ''
      const haystack = [
        caseName,
        payload.legal_case_name,
        payload.claimant,
        reqRequestor,
        reqStatus,
        TYPE_LABELS[req?.request_type] || req?.request_type,
        custodianText,
      ].filter(Boolean).join(' ').toLowerCase()
      return haystack.includes(search)
    })
  }, [adminRequestFilters, isRequestor, requests, caseLookup])

  const adminRequestGroups = useMemo(() => {
    const yearMap = new Map()
    for (const req of adminFilteredRequests || []) {
      const year = requestYear(req)
      const letter = requestLetter(req)
      const caseName = requestCaseName(req)
      if (!yearMap.has(year)) yearMap.set(year, new Map())
      const letterMap = yearMap.get(year)
      if (!letterMap.has(letter)) letterMap.set(letter, new Map())
      const caseMap = letterMap.get(letter)
      if (!caseMap.has(caseName)) caseMap.set(caseName, [])
      caseMap.get(caseName).push(req)
    }
    return Array.from(yearMap.entries())
      .sort(([a], [b]) => {
        const na = Number(a)
        const nb = Number(b)
        if (Number.isFinite(na) && Number.isFinite(nb)) return nb - na
        return String(b).localeCompare(String(a))
      })
      .map(([year, letterMap]) => {
        const letters = Array.from(letterMap.entries())
          .sort(([a], [b]) => String(a).localeCompare(String(b)))
          .map(([letter, caseMap]) => {
            const names = Array.from(caseMap.entries())
              .sort(([a], [b]) => String(a).localeCompare(String(b)))
              .map(([name, items]) => ({
                name,
                items: [...items].sort((a, b) => (Date.parse(b.created_at || '') || 0) - (Date.parse(a.created_at || '') || 0)),
              }))
            const total = names.reduce((sum, group) => sum + group.items.length, 0)
            return { letter, names, total }
          })
        const total = letters.reduce((sum, group) => sum + group.total, 0)
        return { year, letters, total }
      })
  }, [adminFilteredRequests, caseLookup])

  useEffect(() => {
    if (isRequestor || requestGroupingInitializedRef.current || !adminRequestGroups.length) return
    if (requestGroupingHasStoredStateRef.current) {
      requestGroupingInitializedRef.current = true
      return
    }
    setExpandedRequestYears(new Set(adminRequestGroups.map(group => String(group.year))))
    setExpandedRequestLetters(new Set(adminRequestGroups.flatMap(group => group.letters.map(letterGroup => `${group.year}:${letterGroup.letter}`))))
    setExpandedRequestNames(new Set(adminRequestGroups.flatMap(group => (
      group.letters.flatMap(letterGroup => letterGroup.names.map(nameGroup => `${group.year}:${letterGroup.letter}:${nameGroup.name}`))
    ))))
    requestGroupingInitializedRef.current = true
  }, [adminRequestGroups, isRequestor])

  const resetAdminRequestFilters = () => {
    setAdminRequestFilters({ search: '', status: '', type: '', requestor: '' })
  }

  const toggleRequestYear = (year) => {
    const key = String(year)
    setExpandedRequestYears(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const requestLetterKey = (year, letter) => `${year}:${letter}`

  const toggleRequestLetter = (year, letter) => {
    const key = requestLetterKey(year, letter)
    setExpandedRequestLetters(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const requestNameKey = (year, letter, name) => `${year}:${letter}:${name}`

  const toggleRequestName = (year, letter, name) => {
    const key = requestNameKey(year, letter, name)
    setExpandedRequestNames(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className="page">
      <LoadingOverlay
        visible={!!overlayMessage}
        title={overlayMessage || 'Working\u2026'}
        subtitle={approvalOverlaySubtitle}
      />
      <div className="page-header">
        <div>
          <h1>{heading}</h1>
          <p className="muted">Track new case submissions and in-case requests.</p>
        </div>
        {isRequestor && (
          <button className="btn" onClick={() => setModalCfg({ mode: 'new_case' })}>New Case Request</button>
        )}
        {!isRequestor && (
          <button className="btn ghost" onClick={load}>Refresh</button>
        )}
      </div>
      {loading ? (
        <div>Loading</div>
      ) : error ? (
        <div className="error">{error}</div>
      ) : (
        <>
          {!isRequestor && (
            <>
              <section style={{ marginBottom: 24 }}>
                <h2>Pending Approval Requests</h2>
                <CaseRequestCards items={pendingRequests} emptyLabel="No pending requests to approve." apiBase={apiBase} caseLookup={caseLookup} isRequestor={isRequestor} onApprove={approve} onDecline={startDecline} />
              </section>
        <CaseRequestsAdminTable
          requests={requests}
          filteredRequests={adminFilteredRequests}
          groups={adminRequestGroups}
          filters={adminRequestFilters}
          showFilters={showAdminFilters}
          expandedYears={expandedRequestYears}
          expandedLetters={expandedRequestLetters}
          expandedNames={expandedRequestNames}
          onFilterChange={(patch) => setAdminRequestFilters(prev => ({ ...prev, ...patch }))}
          onToggleFilters={() => setShowAdminFilters(v => !v)}
          onResetFilters={resetAdminRequestFilters}
          onToggleYear={toggleRequestYear}
          onToggleLetter={toggleRequestLetter}
          onToggleName={toggleRequestName}
          onSelectRequest={setSelectedRequest}
        />
            </>
          )}
          {isRequestor && (
            <>
              <section style={{ marginBottom: 24 }}>
                <h2>Pending Requests</h2>
                <CaseRequestCards items={pendingRequests} emptyLabel="No pending requests." apiBase={apiBase} caseLookup={caseLookup} isRequestor={isRequestor} onApprove={approve} onDecline={startDecline} />
              </section>
              <section style={{ marginBottom: 24 }}>
                <h2>Declined Requests <span style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>(showing last 30 days)</span></h2>
                <CaseRequestCards items={declinedRequests} emptyLabel="No declined requests in the last 30 days." apiBase={apiBase} caseLookup={caseLookup} isRequestor={isRequestor} onApprove={approve} onDecline={startDecline} />
              </section>
              <section>
                <h2>Approved Requests <span style={{ fontSize: 12, color: 'var(--muted,#6b7280)' }}>(showing last 30 days)</span></h2>
                <CaseRequestCards items={approvedRequests} emptyLabel="No approved requests in the last 30 days." apiBase={apiBase} caseLookup={caseLookup} isRequestor={isRequestor} onApprove={approve} onDecline={startDecline} />
              </section>
            </>
          )}
        </>
      )}

      {modalCfg && (
        <CaseRequestModal
          key={`${modalCfg.mode}-${modalCfg.caseId || 'general'}`}
          mode={modalCfg.mode}
          apiBase={apiBase}
          caseContext={modalCfg.caseId ? { id: Number(modalCfg.caseId), name: caseLookup[modalCfg.caseId]?.name } : null}
          onClose={closeModal}
          onSuccess={() => { load(); refreshStats() }}
        />
      )}

      <RequestDetailModal
        request={!isRequestor ? selectedRequest : null}
        onClose={() => setSelectedRequest(null)}
        onDecline={(id) => {
          setSelectedRequest(null)
          startDecline(id)
        }}
        onApprove={(id) => {
          setSelectedRequest(null)
          approve(id)
        }}
        renderBody={(req) => <CaseRequestDetailBody request={req} apiBase={apiBase} caseLookup={caseLookup} />}
      />

      <DeclineRequestModal
        target={declineTarget}
        reason={declineReason}
        busy={declineBusy}
        onReasonChange={setDeclineReason}
        onClose={closeDeclineDialog}
        onSubmit={submitDecline}
      />

      <ApproveCaseRequestModal
        request={approveModal}
        analystId={approveAnalyst}
        analysts={analysts}
        onAnalystChange={setApproveAnalyst}
        onClose={() => { setApproveModal(null); setApproveAnalyst('') }}
        onConfirm={confirmApproveWithAnalyst}
      />

    </div>
  )
}
