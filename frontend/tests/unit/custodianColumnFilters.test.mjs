import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('case detail custodians use per-column filters without a filter panel toggle', () => {
  const tabSource = readSource('../../src/pages/CaseDetailCustodiansTab.jsx')
  const tableHookSource = readSource('../../src/pages/useCaseDetailCustodianTable.js')

  assert.match(tabSource, /import DataTableHeader from '..\/components\/DataTableHeader\.jsx'/)
  assert.equal((tabSource.match(/<DataTableHeader/g) || []).length, 5)
  assert.match(tabSource, /filterOptions={PRESERVATION_FILTER_OPTIONS}/)
  assert.match(tabSource, /filterOptions={NTP_FILTER_OPTIONS}/)
  assert.doesNotMatch(tabSource, /Sort & Filter custodians/)
  assert.match(tabSource, /filterOptions={CONSENT_FILTER_OPTIONS}/)
  assert.match(tabSource, /filterClearValue="all"/)
  assert.doesNotMatch(tabSource, /Show Filters|Hide Filters|showCustFilters|setShowCustFilters/)
  assert.doesNotMatch(tabSource, /resetFilters|>\s*Reset\s*</)
  assert.doesNotMatch(tableHookSource, /showCustFilters|setShowCustFilters/)
  assert.doesNotMatch(tableHookSource, /resetFilters/)
})

test('shared column filters support text and select popovers with clear values', () => {
  const headerSource = readSource('../../src/components/DataTableHeader.jsx')

  assert.match(headerSource, /Array\.isArray\(filterOptions\)/)
  assert.match(headerSource, /<select/)
  assert.match(headerSource, /onFilterChange\(filterClearValue\)/)
})
