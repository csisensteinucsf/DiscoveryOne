import assert from 'node:assert/strict'
import test from 'node:test'
import { readFile } from 'node:fs/promises'

import {
  CONSENT_STATUS_OPTIONS,
  NTP_STATUS_OPTIONS,
  consentStatusBadgeVariant,
  consentStatusLabel,
  isConsentComplete,
  normalizeConsentStatus,
  normalizeNtpStatus,
  ntpStatusBadgeVariant,
  ntpStatusLabel,
} from '../../src/pages/custodianStatusCatalog.js'
import {
  buildCustodianWorkflowQuery,
  normalizeOptionalHoldIds,
} from '../../src/pages/holdAssignmentUtils.js'

test('custodian workflow permits matter-level assignment without a Hold', () => {
  assert.deepEqual(normalizeOptionalHoldIds([]), [])
  const params = buildCustodianWorkflowQuery('add', [])
  assert.equal(params.get('action'), 'custodians')
  assert.equal(params.get('mode'), 'add')
  assert.equal(params.has('hold_ids'), false)
})

test('custodian workflow preserves only explicit valid Hold selections', () => {
  assert.deepEqual(normalizeOptionalHoldIds(['4', 4, 9, 0, 'bad']), [4, 9])
  const params = buildCustodianWorkflowQuery('import', ['4', 9])
  assert.equal(params.get('mode'), 'import')
  assert.equal(params.get('hold_ids'), '4,9')
})

test('legacy NTP and consent statuses map to universal terminology', () => {
  assert.equal(normalizeNtpStatus('na'), 'silent')
  assert.equal(ntpStatusLabel('na'), 'Silent')
  assert.equal(normalizeConsentStatus('na'), 'implied')
  assert.equal(consentStatusLabel('na'), 'Implied')
  assert.equal(NTP_STATUS_OPTIONS.some(option => option.value === 'na'), false)
  assert.equal(CONSENT_STATUS_OPTIONS.some(option => option.value === 'na'), false)
})

test('AWOC satisfies consent only as a recognized completed status', () => {
  assert.equal(consentStatusLabel('awoc'), 'AWOC')
  assert.equal(isConsentComplete('awoc'), true)
  assert.equal(isConsentComplete('received'), true)
  assert.equal(isConsentComplete('implied'), true)
  assert.equal(isConsentComplete('sent'), false)
  assert.equal(CONSENT_STATUS_OPTIONS.some(option => option.value === 'awoc'), false)
})

test('custodian NTP and consent statuses use consistent badge colors', async () => {
  assert.equal(ntpStatusBadgeVariant('not sent'), 'default')
  assert.equal(ntpStatusBadgeVariant('sent'), 'warn')
  assert.equal(ntpStatusBadgeVariant('acknowledged'), 'success')
  assert.equal(ntpStatusBadgeVariant('silent'), 'info')
  assert.equal(consentStatusBadgeVariant('not sent'), 'default')
  assert.equal(consentStatusBadgeVariant('sent'), 'warn')
  assert.equal(consentStatusBadgeVariant('received'), 'success')
  assert.equal(consentStatusBadgeVariant('implied'), 'success')
  assert.equal(consentStatusBadgeVariant('awoc'), 'success')

  const caseCustodians = await readFile(new URL('../../src/pages/CaseDetailCustodiansTab.jsx', import.meta.url), 'utf8')
  assert.match(caseCustodians, /variant={ntpStatusBadgeVariant\(ntpStatus\)}[\s\S]*?variant={consentStatusBadgeVariant\(consent\)}/)
})

test('case custodian consent status is read only and omits uploaded-document wording', async () => {
  const caseCustodians = await readFile(new URL('../../src/pages/CaseDetailCustodiansTab.jsx', import.meta.url), 'utf8')
  const holds = await readFile(new URL('../../src/pages/CaseDetailNamedHoldsTab.jsx', import.meta.url), 'utf8')

  assert.match(caseCustodians, /consentStatusLabel/)
  assert.doesNotMatch(caseCustodians, /onChangeConsent\(/)
  assert.doesNotMatch(holds, /Consent/)
  assert.doesNotMatch(caseCustodians + holds, /AWOC \(document uploaded\)/)
})
test('custodians panel omits the case-wide preservation release control', async () => {
  const source = await readFile(
    new URL('../../src/pages/CaseDetailCustodiansTab.jsx', import.meta.url),
    'utf8',
  )

  assert.doesNotMatch(source, /Release All Preservation/)
  assert.doesNotMatch(source, /releaseAllHolds/)
})
