import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('Preservation Detail is selected inside the Holds workspace', () => {
  const navSource = readSource('../../src/pages/CaseDetailTabNav.jsx')
  assert.match(navSource, /setActiveTab\('holds'\)/)
  assert.doesNotMatch(navSource, /setActiveTab\('preservation'\)/)
  assert.doesNotMatch(navSource, />\s*Preservation Detail\s*</)

  const caseDetailSource = readSource('../../src/pages/CaseDetail.jsx')
  assert.match(caseDetailSource, /activeTab === 'holds'/)
  assert.match(caseDetailSource, /holdsView === 'preservation'/)
  assert.match(caseDetailSource, />Preservation Detail<\/button>/)
  assert.match(caseDetailSource, /<CaseDetailPreservationDetailTab/)

  const bootstrapSource = readSource('../../src/pages/useCaseDetailBootstrap.js')
  assert.doesNotMatch(bootstrapSource, /activeTab === 'preservation'/)
})
test('Preservation Detail includes every named Hold membership and the case-wide provider timeline', () => {
  const preservationSource = readSource('../../src/pages/CaseDetailPreservationDetailTab.jsx')
  assert.match(preservationSource, /useCaseDetailNamedHolds/)
  assert.match(preservationSource, /visibleNamedHolds\.map/)
  assert.match(preservationSource, /hold\.custodians/)
  assert.match(preservationSource, /member\.preservation_sources/)
  assert.match(preservationSource, /Provider events and preservation timeline/)
  assert.match(preservationSource, /aria-label="Select custodian preservation detail"/)
  assert.match(preservationSource, /visibleHoldCustodians\.map/)
  assert.match(preservationSource, /Export Preservation Detail/)
  assert.match(preservationSource, /buildPreservationDetailCsv/)
  assert.match(preservationSource, /detailRows: selectedHoldDetailRows/)

  const holdsSource = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')
  assert.doesNotMatch(holdsSource, /Legacy preservation timeline and provider events/)
  assert.doesNotMatch(holdsSource, /CaseDetailPreservationDetailTab/)

  assert.equal(existsSync(new URL('../../src/pages/CaseDetailHoldsTab.jsx', import.meta.url)), false)
})

test('Hold workflow summary contains only Hold-scoped NTP status', () => {
  const holdsSource = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')

  assert.match(holdsSource, /NTP: /)
  assert.doesNotMatch(holdsSource, /\['Hold', hold\.status/)
  assert.doesNotMatch(holdsSource, /\['Consent', consent\]/)
  assert.doesNotMatch(holdsSource, /HoldSearchDetails|HoldTicketDetails|Assign searches/)
})
