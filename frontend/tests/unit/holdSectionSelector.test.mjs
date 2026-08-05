import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('multiple Holds use one shared button selector in Holds and Preservation Detail', () => {
  const selectorSource = readSource('../../src/pages/CaseDetailHoldSelector.jsx')
  const holdsSource = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')
  const preservationSource = readSource('../../src/pages/CaseDetailPreservationDetailTab.jsx')

  assert.match(selectorSource, /if \(holdList\.length < 2\) return null/)
  assert.match(selectorSource, /aria-pressed={isSelected}/)
  assert.match(selectorSource, /onClick={\(\) => onSelect\(hold\.id\)}/)

  assert.match(holdsSource, /<CaseDetailHoldSelector/)
  assert.match(holdsSource, /visibleNamedHolds\.map/)
  assert.match(preservationSource, /<CaseDetailHoldSelector/)
  assert.match(preservationSource, /visibleNamedHolds\.map/)
})

test('Preservation Detail limits provider history to the selected Hold custodians', () => {
  const source = readSource('../../src/pages/CaseDetailPreservationDetailTab.jsx')

  assert.match(source, /selectedCustodianIds/)
  assert.match(source, /visibleHoldsDetailRows/)
  assert.match(source, /selectedCustodianIds\.has\(String\(row\?\.id\)\)/)
  assert.match(source, /visibleHoldsDetailRows\.map/)
  assert.match(source, /Provider states and event history for custodians assigned to/)
})
