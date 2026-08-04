import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Upload, UserPlus } from 'lucide-react'
import DataTableHeader from '../components/DataTableHeader.jsx'
import Modal from '../components/Modal.jsx'
import HoldAssignmentPicker from './HoldAssignmentPicker.jsx'
import { buildCustodianWorkflowQuery } from './holdAssignmentUtils.js'

const lightBtn = { background: '#E5EEF3', color: '#00598C', border: '1px solid #C9D7E2' }

function Chip({ kind = 'default', children, title }) {
  const base = {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 999,
    fontSize: 11,
    lineHeight: '16px',
    border: '1px solid #e5e7eb',
    background: '#f8fafc',
    color: '#334155',
    whiteSpace: 'nowrap',
    marginRight: 6,
    marginBottom: 4,
  }
  const theme =
    kind === 'red'
      ? { borderColor: '#fecaca', background: '#fee2e2', color: '#991b1b' }
      : kind === 'green'
      ? { borderColor: '#bbf7d0', background: '#dcfce7', color: '#065f46' }
      : kind === 'blue'
      ? { borderColor: '#bfdbfe', background: '#dbeafe', color: '#1e3a8a' }
      : kind === 'yellow'
      ? { borderColor: '#fde68a', background: '#fef3c7', color: '#92400e' }
      : {}
  const compact =
    kind === 'blue-letter' || kind === 'yellow-letter'
      ? {
          minWidth: 18,
          height: 18,
          lineHeight: '16px',
          textAlign: 'center',
          padding: '0 5px',
          fontWeight: 700,
        }
      : {}
  const letterTheme =
    kind === 'blue-letter'
      ? { borderColor: '#bfdbfe', background: '#dbeafe', color: '#1e3a8a' }
      : kind === 'yellow-letter'
      ? { borderColor: '#fde68a', background: '#fef3c7', color: '#92400e' }
      : {}
  return <span title={title} style={{ ...base, ...theme, ...compact, ...letterTheme }}>{children}</span>
}

function CaseList({ items = [] }) {
  if (!items.length) return <span>-</span>
  return (
    <>
      {items.map((item, index) => (
        <Fragment key={item.id}>
          <Link to={'/cases/' + item.id} onClick={event => event.stopPropagation()} style={{ textDecoration: 'none', color: 'inherit' }}>
            {item.name}
          </Link>
          {item.is_claimant ? <Chip kind="blue-letter" title="Claimant in this case">C</Chip> : null}
          {index < items.length - 1 ? ', ' : ''}
        </Fragment>
      ))}
    </>
  )
}

const caseSearchText = (items = []) => items.map(item => item?.name || '').join(' ').toLowerCase()

export default function Custodians({ apiBase = '/api' }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' })
  const [filters, setFilters] = useState({
    name: '',
    email: '',
    openCases: '',
    closedCases: '',
    holds: '',
  })
  const [workflowMode, setWorkflowMode] = useState(null)
  const [caseOptions, setCaseOptions] = useState([])
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [holdOptions, setHoldOptions] = useState([])
  const [selectedHoldIds, setSelectedHoldIds] = useState([])
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [workflowError, setWorkflowError] = useState('')
  const nav = useNavigate()

  async function load() {
    setLoading(true)
    setErr(null)
    try {
      const url = q ? apiBase + '/custodians?q=' + encodeURIComponent(q) : apiBase + '/custodians'
      const response = await fetch(url, { credentials: 'include' })
      if (!response.ok) throw new Error('HTTP ' + response.status)
      const data = await response.json()
      setRows(Array.isArray(data) ? data : [])
    } catch (error) {
      setErr(String(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const toggleSort = (key) => {
    setSort(current => ({
      key,
      dir: current.key === key && current.dir === 'asc' ? 'desc' : 'asc',
    }))
  }

  const visibleRows = useMemo(() => {
    const filtered = rows.filter(custodian => {
      const name = (custodian.name || '').toLowerCase()
      const email = (custodian.email || '').toLowerCase()
      const openCases = caseSearchText(custodian.open_cases)
      const closedCases = caseSearchText(custodian.closed_cases)
      const holds = custodian.active_holds ? 'yes active hold' : 'no none'

      return (
        name.includes(filters.name.trim().toLowerCase())
        && email.includes(filters.email.trim().toLowerCase())
        && openCases.includes(filters.openCases.trim().toLowerCase())
        && closedCases.includes(filters.closedCases.trim().toLowerCase())
        && holds.includes(filters.holds.trim().toLowerCase())
      )
    })

    const valueFor = (custodian) => {
      if (sort.key === 'email') return (custodian.email || '').toLowerCase()
      if (sort.key === 'openCases') return (custodian.open_cases || []).length
      if (sort.key === 'closedCases') return (custodian.closed_cases || []).length
      if (sort.key === 'holds') return Number(custodian.active_holds || 0)
      return (custodian.name || '').toLowerCase()
    }
    const direction = sort.dir === 'desc' ? -1 : 1

    return filtered.sort((a, b) => {
      const aValue = valueFor(a)
      const bValue = valueFor(b)
      if (typeof aValue === 'number' && typeof bValue === 'number') return (aValue - bValue) * direction
      return String(aValue).localeCompare(String(bValue), undefined, { numeric: true, sensitivity: 'base' }) * direction
    })
  }, [filters, rows, sort])

  const onSearch = (event) => {
    event.preventDefault()
    load()
  }
  const loadHoldsForCase = async (caseId) => {
    setHoldOptions([])
    setSelectedHoldIds([])
    if (!caseId) return
    const response = await fetch(apiBase + '/cases/' + caseId + '/holds', { credentials: 'include' })
    if (!response.ok) throw new Error('Unable to load holds for the selected case')
    const data = await response.json()
    const nextHolds = Array.isArray(data?.holds) ? data.holds : []
    setHoldOptions(nextHolds)
    setSelectedHoldIds([])
  }

  const onWorkflowHoldCreated = (created) => {
    if (!created?.id) return
    setHoldOptions(current => current.some(hold => Number(hold.id) === Number(created.id))
      ? current
      : [...current, created])
  }

  const openCustodianWorkflow = async (mode) => {
    setWorkflowMode(mode)
    setWorkflowLoading(true)
    setWorkflowError('')
    setCaseOptions([])
    setSelectedCaseId('')
    setHoldOptions([])
    setSelectedHoldIds([])
    try {
      const response = await fetch(apiBase + '/cases?closed=false', { credentials: 'include' })
      if (!response.ok) throw new Error('Unable to load active cases')
      const data = await response.json()
      const nextCases = Array.isArray(data) ? data : []
      setCaseOptions(nextCases)
      if (nextCases.length) {
        const firstId = String(nextCases[0].id)
        setSelectedCaseId(firstId)
        await loadHoldsForCase(firstId)
      }
    } catch (error) {
      setWorkflowError(error?.message || 'Unable to prepare custodian workflow')
    } finally {
      setWorkflowLoading(false)
    }
  }

  const chooseWorkflowCase = async (caseId) => {
    setSelectedCaseId(caseId)
    setWorkflowLoading(true)
    setWorkflowError('')
    try {
      await loadHoldsForCase(caseId)
    } catch (error) {
      setWorkflowError(error?.message || 'Unable to load holds')
    } finally {
      setWorkflowLoading(false)
    }
  }


  const continueCustodianWorkflow = () => {
    if (!selectedCaseId) return
    const params = buildCustodianWorkflowQuery(workflowMode, selectedHoldIds)
    setWorkflowMode(null)
    nav('/cases/' + selectedCaseId + '?' + params.toString())
  }

  return (
    <div className="wrap">
      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, color: 'var(--sidebar-fg)' }}>Custodians</h2>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button type="button" className="btn secondary" onClick={() => openCustodianWorkflow('add')}>
            <UserPlus size={16} aria-hidden="true" /> Add Custodians
          </button>
          <button type="button" className="btn secondary" onClick={() => openCustodianWorkflow('import')}>
            <Upload size={16} aria-hidden="true" /> Import Custodians
          </button>
          <form onSubmit={onSearch} className="row" style={{ gap: 8 }}>
            <input
              type="search"
              placeholder="Search all custodians..."
              value={q}
              onChange={event => setQ(event.target.value)}
              style={{ minWidth: 260 }}
            />
            <button type="submit" className="btn" style={lightBtn}>Search</button>
          </form>
        </div>
      </div>

      {err && <div className="alert error">Error: {err}</div>}
      <div className="card">
        <div className="custodians-table-toolbar">
          <span style={{ color: 'var(--muted, #64748b)', fontSize: 13 }}>
            {visibleRows.length} of {rows.length} custodians
          </span>
          <button
            type="button"
            className="btn ghost"
            onClick={() => {
              setFilters({ name: '', email: '', openCases: '', closedCases: '', holds: '' })
              setSort({ key: 'name', dir: 'asc' })
            }}
          >
            Reset
          </button>
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <DataTableHeader
                  label="Name"
                  sortKey="name"
                  sort={sort}
                  onSort={toggleSort}
                  filterValue={filters.name}
                  onFilterChange={value => setFilters(current => ({ ...current, name: value }))}
                  style={{ width: '16%' }}
                />
                <DataTableHeader
                  label="Email"
                  sortKey="email"
                  sort={sort}
                  onSort={toggleSort}
                  filterValue={filters.email}
                  onFilterChange={value => setFilters(current => ({ ...current, email: value }))}
                  style={{ width: '18%' }}
                />
                <DataTableHeader
                  label="Active cases"
                  sortKey="openCases"
                  sort={sort}
                  onSort={toggleSort}
                  filterValue={filters.openCases}
                  onFilterChange={value => setFilters(current => ({ ...current, openCases: value }))}
                  filterPlaceholder="Case name contains..."
                />
                <DataTableHeader
                  label="Inactive cases"
                  sortKey="closedCases"
                  sort={sort}
                  onSort={toggleSort}
                  filterValue={filters.closedCases}
                  onFilterChange={value => setFilters(current => ({ ...current, closedCases: value }))}
                  filterPlaceholder="Case name contains..."
                />
                <DataTableHeader
                  label="Active preservation"
                  sortKey="holds"
                  sort={sort}
                  onSort={toggleSort}
                  filterValue={filters.holds}
                  onFilterChange={value => setFilters(current => ({ ...current, holds: value }))}
                  filterPlaceholder="Yes or no"
                  style={{ width: 130 }}
                />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={5}>Loading...</td></tr>
              ) : visibleRows.length === 0 ? (
                <tr><td colSpan={5}>No custodians found.</td></tr>
              ) : visibleRows.map((custodian, index) => (
                <tr
                  key={custodian.id || (custodian.email || custodian.name || 'custodian') + '-' + index}
                  onClick={() => {
                    const params = new URLSearchParams()
                    if (custodian.email) params.set('email', custodian.email)
                    else if (custodian.name) params.set('name', custodian.name)
                    if ([...params.keys()].length === 0) return
                    nav('/custodians/detail?' + params.toString())
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <div>{custodian.name || '-'}</div>
                    <div style={{ marginTop: 4 }}>
                      {custodian.is_separated ? <Chip kind="yellow-letter" title="Separated employee">S</Chip> : null}
                    </div>
                  </td>
                  <td>{custodian.email || '-'}</td>
                  <td><CaseList items={custodian.open_cases || []} /></td>
                  <td><CaseList items={custodian.closed_cases || []} /></td>
                  <td>{custodian.active_holds ? <Chip kind="red">Yes</Chip> : <Chip>No</Chip>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Modal
        open={!!workflowMode}
        title={workflowMode === 'import' ? 'Import Custodians' : 'Add Custodians'}
        onClose={() => setWorkflowMode(null)}
        width={560}
        footer={(
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn secondary" onClick={() => setWorkflowMode(null)}>Cancel</button>
            <button
              type="button"
              className="btn"
              onClick={continueCustodianWorkflow}
              disabled={workflowLoading || !selectedCaseId}
            >
              Continue
            </button>
          </div>
        )}
      >
        <p style={{ marginTop: 0, color: 'var(--muted,#64748b)' }}>
          Choose the active case. Hold assignment is optional; leave all Holds unselected to add custodians to the matter only, or select the named Holds they should join.
        </p>
        {workflowError && <div className="alert error">{workflowError}</div>}
        <div className="named-hold-form">
          <label>
            Active Case
            <select className="input" value={selectedCaseId} onChange={event => chooseWorkflowCase(event.target.value)} disabled={workflowLoading}>
              <option value="">Select a case</option>
              {caseOptions.map(caseRecord => (
                <option key={caseRecord.id} value={caseRecord.id}>{caseRecord.legal_case_name || caseRecord.name}</option>
              ))}
            </select>
          </label>
          <HoldAssignmentPicker
            apiBase={apiBase}
            caseId={selectedCaseId}
            holds={holdOptions}
            selectedHoldIds={selectedHoldIds}
            onSelectedHoldIdsChange={setSelectedHoldIds}
            onHoldCreated={onWorkflowHoldCreated}
            disabled={workflowLoading || !selectedCaseId}
          />
          {workflowLoading && <span className="muted">Loading...</span>}
          {!workflowLoading && caseOptions.length === 0 && !workflowError && (
            <span className="muted">Create an active case before adding custodians.</span>
          )}
        </div>
      </Modal>
    </div>
  )
}
