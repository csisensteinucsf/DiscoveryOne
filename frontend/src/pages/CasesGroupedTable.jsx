import { Fragment } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import DataTableHeader from '../components/DataTableHeader.jsx'

const SORT_OPTIONS = [
  { key: 'created', label: 'Created date' },
  { key: 'start', label: 'Start date' },
  { key: 'updated', label: 'Updated date' },
  { key: 'name', label: 'Case name' },
  { key: 'legal', label: 'Legal case name' },
  { key: 'matter', label: 'Matter number' },
  { key: 'attorney', label: 'Internal counsel' },
  { key: 'analyst', label: 'Analyst' },
  { key: 'requestor', label: 'Requestor' },
  { key: 'hold', label: 'Hold count' },
  { key: 'notes', label: 'Notes' },
]

export default function CasesGroupedTable({
  title,
  items,
  groups,
  emptyLabel,
  which,
  caseSort,
  setCaseSort,
  toggleSort,
  groupCases,
  setGroupCases,
  resetCaseFilters,
  caseFilters,
  setCaseFilters,
  showSecondaryCaseNameColumn,
  primaryCaseNameLabel = 'Case Name',
  secondaryCaseNameLabel,
  internalCounselLabel = 'Internal Counsel',
  tableStyles,
  caseTableColumnCount,
  expandedYears,
  expandedLetters,
  toggleYear,
  toggleLetter,
  letterKey,
  RowComponent,
  style,
}) {
  const TableColumns = () => (
    <colgroup>
      <col style={tableStyles.caseNameCell} />
      {showSecondaryCaseNameColumn && <col style={tableStyles.legalCaseCell} />}
      <col style={tableStyles.matterCell} />
      <col style={tableStyles.counselCell} />
      <col style={tableStyles.analystCell} />
      <col style={tableStyles.requestorCell} />
      <col style={tableStyles.stateCell} />
      <col style={tableStyles.statusCell} />
      <col style={tableStyles.notesCell} />
      <col style={tableStyles.actionsCell} />
    </colgroup>
  )

  const renderGroupedRows = () => (
    (groups || []).map(group => {
      const yearKey = String(group.year)
      const yearExpanded = expandedYears.has(yearKey)
      return (
        <Fragment key={group.year}>
          <tr>
            <td colSpan={caseTableColumnCount}>
              <button
                type="button"
                className="collapse-trigger"
                aria-expanded={yearExpanded}
                onClick={() => toggleYear(which, group.year)}
              >
                <span>
                  <span aria-hidden="true">{yearExpanded ? 'v' : '>'}</span> {group.year}
                  <span style={{ opacity: 0.6 }}> ({group.total})</span>
                </span>
              </button>
            </td>
          </tr>
          {yearExpanded && group.letters.map(letterGroup => {
            const key = letterKey(group.year, letterGroup.letter)
            const letterExpanded = expandedLetters.has(key)
            return (
              <Fragment key={key}>
                <tr>
                  <td colSpan={caseTableColumnCount}>
                    <button
                      type="button"
                      className="collapse-trigger"
                      style={{ paddingLeft: '1.5rem' }}
                      aria-expanded={letterExpanded}
                      onClick={() => toggleLetter(which, group.year, letterGroup.letter)}
                    >
                      <span>
                        <span aria-hidden="true">{letterExpanded ? 'v' : '>'}</span> {letterGroup.letter}
                        <span style={{ opacity: 0.6 }}> ({letterGroup.items.length})</span>
                      </span>
                    </button>
                  </td>
                </tr>
                {letterExpanded && letterGroup.items.map(c => <RowComponent key={c.id} c={c} />)}
              </Fragment>
            )
          })}
        </Fragment>
      )
    })
  )

  const DirectionIcon = caseSort.dir === 'desc' ? ArrowDown : ArrowUp
  const visibleCount = groupCases ? (groups || []).length : (items || []).length

  return (
    <div className="card cases-table-card" style={style}>
      <div className="cases-table-toolbar">
        <h3>{title}</h3>
        <div className="cases-table-toolbar__controls">
          <label className="cases-sort-select">
            <span>Sort by</span>
            <select
              value={caseSort.key}
              onChange={event => setCaseSort(current => ({ ...current, key: event.target.value }))}
            >
              {SORT_OPTIONS.map(option => (
                <option key={option.key} value={option.key}>{option.label}</option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="icon-button"
            title={caseSort.dir === 'desc' ? 'Descending; switch to ascending' : 'Ascending; switch to descending'}
            aria-label={caseSort.dir === 'desc' ? 'Descending; switch to ascending' : 'Ascending; switch to descending'}
            onClick={() => setCaseSort(current => ({ ...current, dir: current.dir === 'desc' ? 'asc' : 'desc' }))}
          >
            <DirectionIcon size={18} aria-hidden="true" />
          </button>
          <label className="cases-group-toggle">
            <input
              type="checkbox"
              checked={groupCases}
              onChange={event => setGroupCases(event.target.checked)}
            />
            <span>Group by year</span>
          </label>
          <button className="btn ghost" type="button" onClick={resetCaseFilters}>Reset</button>
        </div>
      </div>

      <div className="table-scroll">
        <table style={tableStyles.table}>
          <TableColumns />
          <thead>
            <tr>
              <DataTableHeader
                label={primaryCaseNameLabel}
                sortKey="name"
                sort={caseSort}
                onSort={toggleSort}
                filterValue={caseFilters.name}
                onFilterChange={value => setCaseFilters(filters => ({ ...filters, name: value }))}
                filterPlaceholder="Name contains..."
                style={{ ...tableStyles.headerCell, ...tableStyles.caseNameCell }}
              />
              {showSecondaryCaseNameColumn && (
                <DataTableHeader
                  label={secondaryCaseNameLabel}
                  sortKey="legal"
                  sort={caseSort}
                  onSort={toggleSort}
                  filterValue={caseFilters.legal}
                  onFilterChange={value => setCaseFilters(filters => ({ ...filters, legal: value }))}
                  filterPlaceholder="Name contains..."
                  style={{ ...tableStyles.headerCell, ...tableStyles.legalCaseCell }}
                />
              )}
              <DataTableHeader
                label="Matter Number"
                sortKey="matter"
                sort={caseSort}
                onSort={toggleSort}
                filterValue={caseFilters.matter}
                onFilterChange={value => setCaseFilters(filters => ({ ...filters, matter: value }))}
                style={{ ...tableStyles.headerCell, ...tableStyles.matterCell }}
              />
              <DataTableHeader
                label={internalCounselLabel}
                sortKey="attorney"
                sort={caseSort}
                onSort={toggleSort}
                filterValue={caseFilters.counsel}
                onFilterChange={value => setCaseFilters(filters => ({ ...filters, counsel: value }))}
                style={{ ...tableStyles.headerCell, ...tableStyles.counselCell }}
              />
              <DataTableHeader
                label="Analyst"
                sortKey="analyst"
                sort={caseSort}
                onSort={toggleSort}
                filterValue={caseFilters.analyst}
                onFilterChange={value => setCaseFilters(filters => ({ ...filters, analyst: value }))}
                style={{ ...tableStyles.headerCell, ...tableStyles.analystCell }}
              />
              <DataTableHeader
                label="Requestor"
                sortKey="requestor"
                sort={caseSort}
                onSort={toggleSort}
                filterValue={caseFilters.requestor}
                onFilterChange={value => setCaseFilters(filters => ({ ...filters, requestor: value }))}
                style={{ ...tableStyles.headerCell, ...tableStyles.requestorCell }}
              />
              <DataTableHeader
                label="State"
                style={{ ...tableStyles.headerCell, ...tableStyles.stateCell }}
              />
              <DataTableHeader
                label="Holds"
                sortKey="hold"
                sort={caseSort}
                onSort={toggleSort}
                style={{ ...tableStyles.headerCell, ...tableStyles.statusCell }}
              />
              <DataTableHeader
                label="Additional Notes / Comments"
                sortKey="notes"
                sort={caseSort}
                onSort={toggleSort}
                filterValue={caseFilters.notes}
                onFilterChange={value => setCaseFilters(filters => ({ ...filters, notes: value }))}
                style={{ ...tableStyles.headerCell, ...tableStyles.notesCell }}
              />
              <th style={{ ...tableStyles.headerCell, ...tableStyles.actionsCell }} aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {groupCases ? renderGroupedRows() : (items || []).map(c => <RowComponent key={c.id} c={c} />)}
            {visibleCount === 0 && <tr><td colSpan={caseTableColumnCount}>{emptyLabel}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}