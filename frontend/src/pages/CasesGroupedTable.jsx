import { Fragment } from 'react'

export default function CasesGroupedTable({
  title,
  groups,
  emptyLabel,
  which,
  showFilters,
  setShowFilters,
  resetCaseFilters,
  caseFilters,
  setCaseFilters,
  showSecondaryCaseNameColumn,
  primaryCaseNameLabel = 'Case Name',
  secondaryCaseNameLabel,
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
  const renderFiltersRow = () => (
    <tr style={{ background: '#f3f4f6' }}>
      <th style={{ padding: 6 }}>
        <input
          className="input"
          placeholder="Filter name"
          style={{ width: '100%' }}
          value={caseFilters.name}
          onChange={e => setCaseFilters(f => ({ ...f, name: e.target.value }))}
          onMouseDown={(e)=>e.stopPropagation()}
          onKeyDown={(e)=>e.stopPropagation()}
          autoComplete="off"
        />
      </th>
      {showSecondaryCaseNameColumn && (
        <th style={{ padding: 6 }}>
          <input
            className="input"
            placeholder={`Filter ${secondaryCaseNameLabel.toLowerCase()}`}
            style={{ width: '100%' }}
            value={caseFilters.legal}
            onChange={e => setCaseFilters(f => ({ ...f, legal: e.target.value }))}
            onMouseDown={(e)=>e.stopPropagation()}
            onKeyDown={(e)=>e.stopPropagation()}
            autoComplete="off"
          />
        </th>
      )}
      <th style={{ padding: 6 }}>
        <input
          className="input"
          placeholder="Filter analyst"
          style={{ width: '100%' }}
          value={caseFilters.analyst}
          onChange={e => setCaseFilters(f => ({ ...f, analyst: e.target.value }))}
          onMouseDown={(e)=>e.stopPropagation()}
          onKeyDown={(e)=>e.stopPropagation()}
          autoComplete="off"
        />
      </th>
      <th style={{ padding: 6 }}>
        <input
          className="input"
          placeholder="Filter requestor"
          style={{ width: '100%' }}
          value={caseFilters.requestor}
          onChange={e => setCaseFilters(f => ({ ...f, requestor: e.target.value }))}
          onMouseDown={(e)=>e.stopPropagation()}
          onKeyDown={(e)=>e.stopPropagation()}
          autoComplete="off"
        />
      </th>
      <th />
      <th style={{ ...tableStyles.headerCell, ...tableStyles.actionsCell }} />
    </tr>
  )

  const TableColumns = () => (
    <colgroup>
      <col style={tableStyles.caseNameCell} />
      {showSecondaryCaseNameColumn && <col style={tableStyles.legalCaseCell} />}
      <col style={tableStyles.analystCell} />
      <col style={tableStyles.requestorCell} />
      <col style={tableStyles.statusCell} />
      <col style={tableStyles.actionsCell} />
    </colgroup>
  )

  return (
    <div className="card" style={style}>
      <h3 style={{ marginTop: 0 }}>{title}</h3>

      <div className="row" style={{ gap: 8, justifyContent: 'flex-end', marginBottom: 8, flexWrap: 'wrap' }}>
        <button className="btn secondary" onClick={() => setShowFilters(s => !s)}>
          {showFilters ? 'Hide Filters' : 'Show Filters'}
        </button>
        <button className="btn ghost" onClick={resetCaseFilters}>Reset</button>
      </div>

      <table style={tableStyles.table}>
        <TableColumns />
        <thead>
          <tr>
            <th style={{ ...tableStyles.headerCell, ...tableStyles.caseNameCell }}>{primaryCaseNameLabel}</th>
            {showSecondaryCaseNameColumn && <th style={{ ...tableStyles.headerCell, ...tableStyles.legalCaseCell }}>{secondaryCaseNameLabel}</th>}
            <th style={{ ...tableStyles.headerCell, ...tableStyles.analystCell }}>Analyst</th>
            <th style={{ ...tableStyles.headerCell, ...tableStyles.requestorCell }}>Requestor</th>
            <th style={{ ...tableStyles.headerCell, ...tableStyles.statusCell }}>Status</th>
            <th style={{ ...tableStyles.headerCell, ...tableStyles.actionsCell }}></th>
          </tr>
          {showFilters && renderFiltersRow()}
        </thead>
        <tbody>
          {(groups || []).map(g => {
            const yearKey = String(g.year)
            const yearExpanded = expandedYears.has(yearKey)
            return (
              <Fragment key={g.year}>
                <tr>
                  <td colSpan={caseTableColumnCount}>
                    <button
                      type="button"
                      className="collapse-trigger"
                      aria-expanded={yearExpanded}
                      onClick={() => toggleYear(which, g.year)}
                    >
                      <span>
                        <span aria-hidden="true">{yearExpanded ? 'v' : '>'}</span> {g.year}
                        <span style={{ opacity:.6 }}> ({g.total})</span>
                      </span>
                    </button>
                  </td>
                </tr>
                {yearExpanded && g.letters.map(letterGroup => {
                  const lKey = letterKey(g.year, letterGroup.letter)
                  const letterExpanded = expandedLetters.has(lKey)
                  return (
                    <Fragment key={lKey}>
                      <tr>
                        <td colSpan={caseTableColumnCount}>
                          <button
                            type="button"
                            className="collapse-trigger"
                            style={{ paddingLeft:'1.5rem' }}
                            aria-expanded={letterExpanded}
                            onClick={() => toggleLetter(which, g.year, letterGroup.letter)}
                          >
                            <span>
                              <span aria-hidden="true">{letterExpanded ? 'v' : '>'}</span> {letterGroup.letter}
                              <span style={{ opacity:.6 }}> ({letterGroup.items.length})</span>
                            </span>
                          </button>
                        </td>
                      </tr>
                      {letterExpanded && letterGroup.items.map(c => (
                        <RowComponent key={c.id} c={c} />
                      ))}
                    </Fragment>
                  )
                })}
              </Fragment>
            )
          })}
          {(groups || []).length === 0 && <tr><td colSpan={caseTableColumnCount}>{emptyLabel}</td></tr>}
        </tbody>
      </table>
    </div>
  )
}