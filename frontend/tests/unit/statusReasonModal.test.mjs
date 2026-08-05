import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('Silent NTP and Implied consent use the in-app reason modal', () => {
  const pageSource = readSource('../../src/pages/CaseDetail.jsx')
  const statusActionsSource = readSource('../../src/pages/useCaseDetailCustodianStatusActions.js')
  const namedHoldsSource = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')

  assert.match(pageSource, /<CaseDetailStatusReasonModal/)
  assert.match(namedHoldsSource, /<CaseDetailStatusReasonModal/)
  assert.doesNotMatch(statusActionsSource, /window\.prompt|\bprompt\(/)
  assert.doesNotMatch(namedHoldsSource, /window\.prompt|\bprompt\(/)
  assert.match(statusActionsSource, /const v = normalizeNtpStatus\(value\)/)
  assert.match(statusActionsSource, /const v = normalizeConsentStatus\(value\)/)
  assert.match(statusActionsSource, /title: 'Silent NTP reason'/)
  assert.match(statusActionsSource, /title: 'Implied consent reason'/)
})

test('status reason modal requires a nonblank reason and reports it inline', () => {
  const modalSource = readSource('../../src/pages/CaseDetailStatusReasonModal.jsx')

  assert.match(modalSource, /import Modal from '..\/components\/Modal\.jsx'/)
  assert.match(modalSource, /if \(!trimmedReason\)/)
  assert.match(modalSource, /A reason is required\./)
  assert.match(modalSource, /<textarea/)
  assert.match(modalSource, /required/)
  assert.match(modalSource, /aria-invalid=/)
})
