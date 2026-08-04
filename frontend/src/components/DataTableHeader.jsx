import { useEffect, useId, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, Filter, X } from 'lucide-react'

export default function DataTableHeader({
  label,
  sortKey,
  sort,
  onSort,
  filterValue,
  onFilterChange,
  filterPlaceholder,
  style,
  className = '',
}) {
  const [filterOpen, setFilterOpen] = useState(false)
  const rootRef = useRef(null)
  const filterId = useId()
  const sortable = Boolean(sortKey && onSort)
  const filterable = typeof onFilterChange === 'function'
  const isSorted = sortable && sort?.key === sortKey
  const hasFilter = filterable && String(filterValue || '').trim().length > 0

  useEffect(() => {
    if (!filterOpen) return undefined

    const closeOnOutsidePointer = (event) => {
      if (!rootRef.current?.contains(event.target)) setFilterOpen(false)
    }
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setFilterOpen(false)
    }

    document.addEventListener('pointerdown', closeOnOutsidePointer)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [filterOpen])

  const SortIcon = !isSorted ? ArrowUpDown : sort.dir === 'desc' ? ArrowDown : ArrowUp
  const sortTitle = !isSorted
    ? `Sort by ${label}`
    : `${label} sorted ${sort.dir === 'desc' ? 'descending' : 'ascending'}; reverse order`

  return (
    <th style={style} className={className}>
      <div className="data-table-header" ref={rootRef}>
        {sortable ? (
          <button
            type="button"
            className={`data-table-header__sort${isSorted ? ' is-active' : ''}`}
            onClick={() => onSort(sortKey)}
            title={sortTitle}
            aria-label={sortTitle}
          >
            <span>{label}</span>
            <SortIcon size={14} strokeWidth={2} aria-hidden="true" />
          </button>
        ) : (
          <span className="data-table-header__label">{label}</span>
        )}

        {filterable && (
          <button
            type="button"
            className={`data-table-header__filter${hasFilter ? ' is-active' : ''}`}
            onClick={() => setFilterOpen(open => !open)}
            title={hasFilter ? `Filter ${label} (active)` : `Filter ${label}`}
            aria-label={hasFilter ? `Filter ${label} (active)` : `Filter ${label}`}
            aria-expanded={filterOpen}
            aria-controls={filterOpen ? filterId : undefined}
          >
            <Filter size={14} fill={hasFilter ? 'currentColor' : 'none'} aria-hidden="true" />
          </button>
        )}

        {filterOpen && (
          <div
            id={filterId}
            className="data-table-filter-popover"
            role="dialog"
            aria-label={`Filter ${label}`}
            onClick={event => event.stopPropagation()}
          >
            <label htmlFor={`${filterId}-input`}>Filter {label}</label>
            <div className="data-table-filter-popover__control">
              <input
                id={`${filterId}-input`}
                className="input"
                value={filterValue || ''}
                placeholder={filterPlaceholder || `Contains...`}
                onChange={event => onFilterChange(event.target.value)}
                autoFocus
                autoComplete="off"
              />
              {hasFilter && (
                <button
                  type="button"
                  className="icon-button"
                  title={`Clear ${label} filter`}
                  aria-label={`Clear ${label} filter`}
                  onClick={() => onFilterChange('')}
                >
                  <X size={16} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </th>
  )
}