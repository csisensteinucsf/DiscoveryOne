import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('Preservation Detail is a dedicated case tab between Holds and Searches', () => {
  const navSource = readSource('../../src/pages/CaseDetailTabNav.jsx')
  const holdsIndex = navSource.indexOf("setActiveTab('holds')")
  const preservationIndex = navSource.indexOf("setActiveTab('preservation')")
  const searchesIndex = navSource.indexOf("setActiveTab('searches')")

  assert.ok(holdsIndex >= 0)
  assert.ok(preservationIndex > holdsIndex)
  assert.ok(searchesIndex > preservationIndex)
  assert.match(navSource, />\s*Preservation Detail\s*</)

  const caseDetailSource = readSource('../../src/pages/CaseDetail.jsx')
  assert.match(caseDetailSource, /activeTab === 'preservation'/)
  assert.match(caseDetailSource, /<CaseDetailPreservationDetailTab/)

  const bootstrapSource = readSource('../../src/pages/useCaseDetailBootstrap.js')
  assert.match(bootstrapSource, /activeTab === 'preservation'.*loadHoldsDetail\(\)/s)
  assert.doesNotMatch(bootstrapSource, /activeTab === 'holds'.*loadHoldsDetail\(\)/s)
})

test('Preservation Detail includes every named Hold membership and the case-wide provider timeline', () => {
  const preservationSource = readSource('../../src/pages/CaseDetailPreservationDetailTab.jsx')
  assert.match(preservationSource, /useCaseDetailNamedHolds/)
  assert.match(preservationSource, /visibleNamedHolds\.map/)
  assert.match(preservationSource, /hold\.custodians/)
  assert.match(preservationSource, /member\.preservation_sources/)
  assert.match(preservationSource, /Provider events and preservation timeline/)

  const holdsSource = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')
  assert.doesNotMatch(holdsSource, /Legacy preservation timeline and provider events/)
  assert.doesNotMatch(holdsSource, /CaseDetailPreservationDetailTab/)

  assert.equal(existsSync(new URL('../../src/pages/CaseDetailHoldsTab.jsx', import.meta.url)), false)
})

test('Hold workflow summary omits the redundant Hold completion badge', () => {
  const holdsSource = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')

  assert.doesNotMatch(holdsSource, /\['Hold', hold\.status/)
  assert.match(holdsSource, /\['NTP', ntp\]/)
  assert.match(holdsSource, /\['Consent', consent\]/)
})
