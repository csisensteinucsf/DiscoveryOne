import { Fragment, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, ChevronRight, Search, UserPlus } from 'lucide-react'
import DataTableHeader from '../components/DataTableHeader.jsx'
import D1CustodianDirectoryModal from './D1CustodianDirectoryModal.jsx'

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
          {item.is_claimant ? <Chip kind="blue-letter" title="Claimant in this matter">C</Chip> : null}
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
  const [pageSize, setPageSize] = useState(25)
  const [page, setPage] = useState(1)
  const [workflowMode, setWorkflowMode] = useState(null)
  const nav = useNavigate()

  async function load() {
    setLoading(true)
    setErr(null)
    try {
      const response = await fetch(apiBase + '/custodians', { credentials: 'include' })
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
      const globalQuery = q.trim().toLowerCase()
      const matchesGlobalQuery = !globalQuery
        || [name, email, openCases, closedCases, holds].some(value => value.includes(globalQuery))

      return (
        matchesGlobalQuery
        && name.includes(filters.name.trim().toLowerCase())
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
  }, [filters, q, rows, sort])
  useEffect(() => { setPage(1) }, [q, filters, pageSize])
  const totalPages = Math.max(1, Math.ceil(visibleRows.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const pagedRows = visibleRows.slice((safePage - 1) * pageSize, safePage * pageSize)

  const openCustodianWorkflow = () => setWorkflowMode('manual')
  return (
    <div className="wrap">
      <div className="page-header custodians-page-header" style={{ marginBottom: '1rem' }}>
        <div>
          <h2 style={{ margin: 0, color: 'var(--sidebar-fg)' }}>Custodians</h2>
          <button type="button" className="btn ghost compact custodians-back-button" onClick={() => nav(-1)}>
            <ArrowLeft size={15} aria-hidden="true" /> Back
          </button>
        </div>
        <button type="button" className="btn secondary" onClick={openCustodianWorkflow}>
          <UserPlus size={16} aria-hidden="true" /> Add Custodians
        </button>
      </div>

      {err && <div className="alert error">Error: {err}</div>}
      <div className="card">
        <div className="custodians-table-toolbar">
          <span style={{ color: 'var(--muted, #64748b)', fontSize: 13 }}>
            {visibleRows.length} of {rows.length} custodians
          </span>
          <div className="custodians-table-toolbar__controls">
            <div className="custodians-directory-search" role="search">
              <Search size={16} aria-hidden="true" />
              <input
                className="input"
                type="search"
                aria-label="Search all custodians"
                placeholder="Search custodians..."
                value={q}
                onChange={event => setQ(event.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn ghost"
              onClick={() => {
                setQ('')
                setFilters({ name: '', email: '', openCases: '', closedCases: '', holds: '' })
                setSort({ key: 'name', dir: 'asc' })
              }}
            >
              Reset
            </button>
          </div>
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
                  filterPlaceholder="Matter name contains..."
                />
                <DataTableHeader
                  label="Inactive cases"
                  sortKey="closedCases"
                  sort={sort}
                  onSort={toggleSort}
                  filterValue={filters.closedCases}
                  onFilterChange={value => setFilters(current => ({ ...current, closedCases: value }))}
                  filterPlaceholder="Matter name contains..."
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
              ) : pagedRows.length === 0 ? (
                <tr><td colSpan={5}>No custodians found.</td></tr>
              ) : pagedRows.map((custodian, index) => (
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
        <div className="custodians-pagination" aria-label="Custodian pagination">
          <label>
            Show
            <select className="input" value={pageSize} onChange={event => setPageSize(Number(event.target.value))}>
              {[25, 50, 100, 200].map(size => <option key={size} value={size}>{size}</option>)}
            </select>
            per page
          </label>
          <span>
            {visibleRows.length
              ? `${(safePage - 1) * pageSize + 1}-${Math.min(safePage * pageSize, visibleRows.length)} of ${visibleRows.length}`
              : '0 results'}
          </span>
          <button type="button" className="icon-button" aria-label="Previous page" disabled={safePage <= 1} onClick={() => setPage(current => Math.max(1, current - 1))}>
            <ChevronLeft size={17} aria-hidden="true" />
          </button>
          <span>Page {safePage} of {totalPages}</span>
          <button type="button" className="icon-button" aria-label="Next page" disabled={safePage >= totalPages} onClick={() => setPage(current => Math.min(totalPages, current + 1))}>
            <ChevronRight size={17} aria-hidden="true" />
          </button>
        </div>
      </div>
      {workflowMode && (
        <D1CustodianDirectoryModal
          apiBase={apiBase}
          initialMode={workflowMode}
          onClose={() => setWorkflowMode(null)}
          onSaved={load}
        />
      )}
    </div>
  )
}
