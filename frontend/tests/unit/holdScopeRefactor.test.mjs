import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('Holds contain preservation and NTP only', () => {
  const holds = source('../../src/pages/CaseDetailNamedHoldsTab.jsx')

  assert.match(holds, /Preservation/)
  assert.match(holds, /NTP/)
  assert.doesNotMatch(holds, /<th>Consent<\/th>|<h5>Searches<\/h5>|<h5>Tickets<\/h5>/)
  assert.doesNotMatch(holds, /Assign searches|setNamedHoldSearches|consent_status/)
})

test('searches, tickets, and consent are created at the case level', () => {
  const searchModal = source('../../src/pages/CaseDetailSearchEditorModals.jsx')
  const searchWorkflow = source('../../src/pages/useCaseDetailSearchWorkflow.js')
  const ticketModal = source('../../src/pages/CaseDetailTicketWorkflowModals.jsx')
  const ticketWorkflow = source('../../src/pages/useCaseDetailTicketWorkflow.js')
  const consentModal = source('../../src/pages/CaseDetailConsentModal.jsx')
  const consentWorkflow = source('../../src/pages/useCaseDetailConsents.js')
  const consentProofModal = source('../../src/pages/CaseDetailWorkflowModals.jsx')
  const consentProofWorkflow = source('../../src/pages/caseDetailDocuments.js')

  assert.doesNotMatch(searchModal, /<Field label="Holds"/)
  assert.doesNotMatch(searchWorkflow, /Select at least one Hold/)
  assert.doesNotMatch(ticketModal, /Named Hold|Select an active Hold/)
  assert.match(ticketWorkflow, /case_hold_id: null/)
  assert.doesNotMatch(consentModal, /<Field label="Hold"/)
  assert.doesNotMatch(consentWorkflow, /case_hold_id: Number\(consentHoldId\)/)
  assert.doesNotMatch(consentProofModal, /Named hold|selected hold/)
  assert.doesNotMatch(consentProofWorkflow, /case_hold_id|caseHoldId/)
})

test('D1 custodian directory supports standalone entry and case multi-select', () => {
  const globalPage = source('../../src/pages/Custodians.jsx')
  const directoryModal = source('../../src/pages/D1CustodianDirectoryModal.jsx')
  const caseWrapper = source('../../src/pages/CaseDetailCustodianEntryModals.jsx')
  const picker = source('../../src/pages/SelectD1CustodiansModal.jsx')

  assert.match(globalPage, /D1CustodianDirectoryModal/)
  assert.doesNotMatch(globalPage, /\/cases\?closed=false|Active Case/)
  assert.match(directoryModal, /Manual Add/)
  assert.match(directoryModal, /Import from list/)
  assert.match(caseWrapper, /custodianModalMode === 'directory'/)
  assert.match(picker, /Select from D1 Custodians/)
  assert.match(picker, /aria-multiselectable="true"/)
})

test('D1 custodian entry uses polished required labels and file controls', () => {
  const globalPage = source('../../src/pages/Custodians.jsx')
  const directoryModal = source('../../src/pages/D1CustodianDirectoryModal.jsx')
  const styles = source('../../src/styles.css')

  assert.doesNotMatch(globalPage, />\s*Import Custodians\s*</)
  assert.match(directoryModal, /<RequiredFieldLabel>First name<\/RequiredFieldLabel>/)
  assert.match(directoryModal, /<RequiredFieldLabel>Last name<\/RequiredFieldLabel>/)
  assert.match(directoryModal, /<RequiredFieldLabel>Email<\/RequiredFieldLabel>/)
  assert.match(directoryModal, /<RequiredFieldLabel>Campus<\/RequiredFieldLabel>/)
  assert.match(directoryModal, /Download CSV template/)
  assert.doesNotMatch(directoryModal, /required-marker/)
  assert.match(styles, /input\[type="file"\]::file-selector-button/)
})

test('NTP access and Hold preservation changes stay synchronized across Case Detail', () => {
  const detail = source('../../src/pages/CaseDetail.jsx')
  const custodianTab = source('../../src/pages/CaseDetailCustodiansTab.jsx')
  const namedHoldsTab = source('../../src/pages/CaseDetailNamedHoldsTab.jsx')
  const namedHoldsWorkflow = source('../../src/pages/useCaseDetailNamedHolds.js')
  const ntpWorkflow = source('../../src/pages/useCaseDetailNtpWorkflow.js')
  const ntpModals = source('../../src/pages/CaseDetailNtpModals.jsx')
  const openStart = ntpWorkflow.indexOf('const openSendNtp')
  const openEnd = ntpWorkflow.indexOf('const closeSendNtp')
  const openNtpSource = ntpWorkflow.slice(openStart, openEnd)

  assert.notEqual(openStart, -1)
  assert.notEqual(openEnd, -1)
  assert.equal(custodianTab.includes('onClick={openSendNtp} disabled={sendingNtp}'), true)
  assert.equal(custodianTab.includes('ntpButtonDisabled'), false)
  assert.equal(openNtpSource.includes('setShowSendNtpModal(true)'), true)
  assert.equal(openNtpSource.includes('if (!ntpTemplates.length)'), false)
  assert.equal(openNtpSource.includes('if (!ntpHolds.length)'), false)
  assert.match(ntpModals, /No active Holds are available/)
  assert.match(ntpModals, /No NTP templates are available/)
  assert.match(detail, /onHoldDataChanged={refreshHoldDerivedViews}/)
  assert.match(detail, /Promise\.all\(\[reloadCustodians\(\), loadHoldsDetail\(\)\]\)/)
  assert.match(namedHoldsTab, /onMutationComplete: onHoldDataChanged/)
  assert.match(namedHoldsWorkflow, /typeof onMutationComplete === 'function' \? onMutationComplete\(\)/)
})

test('Custodian directory search filters live beside Reset', () => {
  const page = source('../../src/pages/Custodians.jsx')
  const styles = source('../../src/styles.css')
  const toolbarStart = page.indexOf('className="custodians-table-toolbar"')
  const searchStart = page.indexOf('className="custodians-directory-search"')
  const resetStart = page.indexOf('Reset', searchStart)

  assert.notEqual(toolbarStart, -1)
  assert.notEqual(searchStart, -1)
  assert.notEqual(resetStart, -1)
  assert.equal(toolbarStart < searchStart && searchStart < resetStart, true)
  assert.match(page, /<Search size=\{16\} aria-hidden="true" \/>/)
  assert.match(page, /onChange={event => setQ\(event\.target\.value\)}/)
  assert.match(page, /const globalQuery = q\.trim\(\)\.toLowerCase\(\)/)
  assert.match(page, /setQ\(''\)/)
  assert.doesNotMatch(page, /onSubmit={onSearch}|>Search<\/button>/)
  assert.match(styles, /\.custodians-directory-search \{/)
  assert.match(styles, /\.custodians-table-toolbar__controls \{/)
})
