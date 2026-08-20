import { Fragment } from 'react'
import Badge from './CaseRequestBadge.jsx'
import { TYPE_LABELS, ISODate } from './caseRequestsUtils.js'

const requestLetterKey = (year, letter) => `${year}:${letter}`
const requestNameKey = (year, letter, name) => `${year}:${letter}:${name}`

export default function CaseRequestsAdminTable({
  requests,
  filteredRequests,
  groups,
  filters,
  showFilters,
  expandedYears,
  expandedLetters,
  expandedNames,
  onFilterChange,
  onToggleFilters,
  onResetFilters,
  onToggleYear,
  onToggleLetter,
  onToggleName,
  onSelectRequest,
}) {
  if (!requests.length) return <div className="empty">No requestor requests found.</div>

  const requestorLabel = (req) => req?.requestor?.email || req?.requestor?.username || ''

  return (
    <section className="card" style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0 }}>All Requestor Requests</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>
            Click a request to review the full intake details and compare what was requested against the matter.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ fontSize: 12, color: '#64748b' }}>{filteredRequests.length} shown / {requests.length} total</div>
          <button type="button" className="btn secondary" onClick={onToggleFilters}>
            {showFilters ? 'Hide Filters' : 'Show Filters'}
          </button>
          <button type="button" className="btn ghost" onClick={onResetFilters}>Reset</button>
        </div>
      </div>
      <div style={{ marginBottom: 12 }}>
        <input
          type="search"
          value={filters.search}
          onChange={(e) => onFilterChange({ search: e.target.value })}
          placeholder="Search eDiscovery name, requestor, custodian, claimant, status..."
          style={{ width: '100%', border: '1px solid var(--border,#d1d5db)', borderRadius: 10, padding: '9px 12px', fontSize: 13, background: 'var(--card,#fff)', color: 'var(--text,#0f172a)' }}
        />
      </div>
      {showFilters && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 12 }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#475569' }}>
            Status
            <select
              value={filters.status}
              onChange={(e) => onFilterChange({ status: e.target.value })}
              style={{ border: '1px solid var(--border,#d1d5db)', borderRadius: 10, padding: '8px 10px', fontSize: 13, background: 'var(--card,#fff)', color: 'var(--text,#0f172a)' }}
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="declined">Declined</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#475569' }}>
            Request Type
            <select
              value={filters.type}
              onChange={(e) => onFilterChange({ type: e.target.value })}
              style={{ border: '1px solid var(--border,#d1d5db)', borderRadius: 10, padding: '8px 10px', fontSize: 13, background: 'var(--card,#fff)', color: 'var(--text,#0f172a)' }}
            >
              <option value="">All request types</option>
              {Object.entries(TYPE_LABELS).map(([key, label]) => (
                <option key={key} value={key}>{label}</option>
              ))}
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#475569' }}>
            Requestor
            <input
              type="text"
              value={filters.requestor}
              onChange={(e) => onFilterChange({ requestor: e.target.value })}
              placeholder="Filter requestor"
              style={{ border: '1px solid var(--border,#d1d5db)', borderRadius: 10, padding: '8px 10px', fontSize: 13, background: 'var(--card,#fff)', color: 'var(--text,#0f172a)' }}
            />
          </label>
        </div>
      )}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead style={{ background: 'rgba(15,23,42,0.05)' }}>
            <tr>
              <th style={{ textAlign: 'left', padding: '10px 12px' }}>eDiscovery Name</th>
              <th style={{ textAlign: 'left', padding: '10px 12px' }}>Requestor</th>
              <th style={{ textAlign: 'left', padding: '10px 12px' }}>Date</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((yearGroup) => {
              const yearExpanded = expandedYears.has(String(yearGroup.year))
              return (
                <Fragment key={`request-year-${yearGroup.year}`}>
                  <tr style={{ borderTop: '1px solid var(--border,#e5e7eb)', background: 'rgba(15,23,42,0.02)' }}>
                    <td colSpan={3} style={{ padding: '10px 12px', fontWeight: 700 }}>
                      <button
                        type="button"
                        onClick={() => onToggleYear(yearGroup.year)}
                        aria-expanded={yearExpanded}
                        style={{ border: 0, background: 'transparent', font: 'inherit', fontWeight: 700, cursor: 'pointer', color: 'inherit', padding: 0 }}
                      >
                        <span aria-hidden="true">{yearExpanded ? 'v' : '>'}</span> {yearGroup.year}
                        <span style={{ opacity: 0.6 }}> ({yearGroup.total})</span>
                      </button>
                    </td>
                  </tr>
                  {yearExpanded && yearGroup.letters.map((letterGroup) => {
                    const letterKey = requestLetterKey(yearGroup.year, letterGroup.letter)
                    const letterExpanded = expandedLetters.has(letterKey)
                    return (
                      <Fragment key={`request-letter-${letterKey}`}>
                        <tr style={{ borderTop: '1px solid var(--border,#e5e7eb)', background: 'rgba(15,23,42,0.035)' }}>
                          <td colSpan={3} style={{ padding: '9px 12px 9px 28px', fontWeight: 700 }}>
                            <button
                              type="button"
                              onClick={() => onToggleLetter(yearGroup.year, letterGroup.letter)}
                              aria-expanded={letterExpanded}
                              style={{ border: 0, background: 'transparent', font: 'inherit', fontWeight: 700, cursor: 'pointer', color: 'inherit', padding: 0 }}
                            >
                              <span aria-hidden="true">{letterExpanded ? 'v' : '>'}</span> {letterGroup.letter}
                              <span style={{ opacity: 0.6 }}> ({letterGroup.total})</span>
                            </button>
                          </td>
                        </tr>
                        {letterExpanded && letterGroup.names.map((nameGroup) => {
                          const nameKey = requestNameKey(yearGroup.year, letterGroup.letter, nameGroup.name)
                          const nameExpanded = expandedNames.has(nameKey)
                          return (
                            <Fragment key={`request-name-${nameKey}`}>
                              <tr style={{ borderTop: '1px solid var(--border,#e5e7eb)', background: 'rgba(15,23,42,0.02)' }}>
                                <td colSpan={3} style={{ padding: '9px 12px 9px 44px', fontWeight: 700 }}>
                                  <button
                                    type="button"
                                    onClick={() => onToggleName(yearGroup.year, letterGroup.letter, nameGroup.name)}
                                    aria-expanded={nameExpanded}
                                    style={{ border: 0, background: 'transparent', font: 'inherit', fontWeight: 700, cursor: 'pointer', color: 'inherit', padding: 0 }}
                                  >
                                    <span aria-hidden="true">{nameExpanded ? 'v' : '>'}</span> {nameGroup.name}
                                    <span style={{ opacity: 0.6 }}> ({nameGroup.items.length})</span>
                                  </button>
                                </td>
                              </tr>
                              {nameExpanded && nameGroup.items.map((req) => (
                                <tr
                                  key={`admin-request-row-${req.id}`}
                                  role="button"
                                  tabIndex={0}
                                  onClick={() => onSelectRequest(req)}
                                  onKeyDown={(event) => {
                                    if (event.key === 'Enter' || event.key === ' ') {
                                      event.preventDefault()
                                      onSelectRequest(req)
                                    }
                                  }}
                                  style={{ borderTop: '1px solid var(--border,#e5e7eb)', cursor: 'pointer' }}
                                  title="View request details"
                                >
                                  <td style={{ padding: '10px 12px 10px 60px' }}>
                                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                                      <strong>{TYPE_LABELS[req.request_type] || req.request_type}</strong>
                                      <Badge status={req.status} />
                                    </div>
                                  </td>
                                  <td style={{ padding: '10px 12px' }}>{requestorLabel(req) || '-'}</td>
                                  <td style={{ padding: '10px 12px' }}>{ISODate(req.created_at) || '-'}</td>
                                </tr>
                              ))}
                            </Fragment>
                          )
                        })}
                      </Fragment>
                    )
                  })}
                </Fragment>
              )
            })}
            {!groups.length && (
              <tr>
                <td colSpan={3} style={{ padding: '14px 12px', color: '#64748b' }}>No requests match the current filters.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}