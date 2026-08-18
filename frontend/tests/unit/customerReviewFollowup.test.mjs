import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('Cases places its primary and column controls in the requested toolbars', () => {
  const cases = readSource('../../src/pages/Cases.jsx')
  const grouped = readSource('../../src/pages/CasesGroupedTable.jsx')

  assert.match(cases, /cases-primary-actions[\s\S]*?>New Case</)
  assert.match(cases, /column-picker--compact/)
  assert.match(cases, /toolbarExtra={columnPicker}/)
  assert.match(grouped, /cases-group-toggle[\s\S]*?\{toolbarExtra\}[\s\S]*?>Reset</)
})

test('blocked case closure links directly to the active Hold and hides confirmation', () => {
  const modals = readSource('../../src/pages/CaseModals.jsx')
  const cases = readSource('../../src/pages/Cases.jsx')
  const holds = readSource('../../src/pages/CaseDetailNamedHoldsTab.jsx')

  assert.match(modals, /\{!blocked && \(/)
  assert.match(modals, /case-closure-hold-link/)
  assert.match(modals, /onOpenHold\?\.\(hold\)/)
  assert.match(cases, /\?tab=holds&hold_id=\$\{hold\.hold_id\}/)
  assert.match(holds, /initialHoldId/)
})

test('case editors and requestor intake expose the designated test-case flag', () => {
  const caseModals = readSource('../../src/pages/CaseModals.jsx')
  const detailModals = readSource('../../src/pages/CaseDetailModals.jsx')
  const intake = readSource('../../src/pages/CaseRequestIntakeStep.jsx')
  const requestModal = readSource('../../src/pages/CaseRequestModal.jsx')

  for (const source of [caseModals, detailModals, intake]) {
    assert.match(source, /Test case/)
    assert.match(source, /is_test_case/)
  }
  assert.match(requestModal, /is_test_case: isNewCase \? !!form\.is_test_case/)
})

test('requestor custodian entry has concise controls, examples, and required feedback', () => {
  const intake = readSource('../../src/pages/CaseRequestIntakeStep.jsx')
  const requestModal = readSource('../../src/pages/CaseRequestModal.jsx')
  const shell = readSource('../../src/pages/CaseRequestModalShell.jsx')

  assert.match(intake, /Enter a full name, email address, or employee ID\./)
  assert.match(intake, /Jane Doe, jane@example\.com\\nJohn Smith, john@company\.com/)
  assert.match(intake, /<Plus size=/)
  assert.match(intake, /<Minus size=/)
  assert.match(intake, /caseNamingMode === 'legal_case_name'/)
  assert.match(requestModal, /setShowMissingRequired\(true\)/)
  assert.match(shell, /Missing required fields/)
  assert.match(shell, /data-show-missing-required=/)
  assert.match(shell, /disabled={loading}/)
})

test('file upload surfaces use the shared drag-and-drop target', () => {
  const uploadModules = [
    '../../src/components/NotesPanel.jsx',
    '../../src/pages/CaseDetailWorkflowModals.jsx',
    '../../src/pages/CaseRequestIntakeStep.jsx',
    '../../src/pages/CaseRequestPreservationStep.jsx',
    '../../src/pages/ImportCustodiansModal.jsx',
    '../../src/pages/SetupCoreSteps.jsx',
    '../../src/pages/SystemBackupBrandingPanels.jsx',
    '../../src/pages/SystemImportsPanel.jsx',
  ]

  for (const path of uploadModules) {
    const source = readSource(path)
    assert.match(source, /FileDropZone/, path)
  }
})

test('template editor scrolls within the viewport and case tabs expose active state', () => {
  const templates = readSource('../../src/pages/SystemCaseTemplatesPanel.jsx')
  const tabs = readSource('../../src/pages/CaseDetailTabNav.jsx')

  assert.match(templates, /maxHeight: 'calc\(100vh - 170px\)'/)
  assert.match(templates, /overscrollBehavior: 'contain'/)
  assert.match(tabs, /case-detail-tab-nav/)
  assert.match(tabs, /aria-pressed={activeTab === 'custodians'}/)
  assert.match(tabs, /aria-pressed={activeTab === 'notes'}/)
})
test('Case Detail places Tickets before Edit Case and removes it from the tab row', () => {
  const header = readSource('../../src/pages/CaseDetailHeader.jsx')
  const tabs = readSource('../../src/pages/CaseDetailTabNav.jsx')
  const detail = readSource('../../src/pages/CaseDetail.jsx')
  const ticketsAction = header.indexOf('onClick={onOpenTickets}')
  const editAction = header.indexOf('>Edit Case</button>')

  assert.notEqual(ticketsAction, -1)
  assert.notEqual(editAction, -1)
  assert.equal(ticketsAction < editAction, true)
  assert.equal(tabs.includes('Tickets'), false)
  assert.equal(detail.includes("onOpenTickets={() => setActiveTab('requests')}"), true)
  assert.equal(detail.includes('requestsFilledCount={requestsFilledCount}'), true)
})

test('Login keeps native required validation without displaying required asterisks', () => {
  const login = readSource('../../src/pages/Login.jsx')
  const identifierControl = login.slice(login.indexOf('id="login-identifier"'), login.indexOf('id="login-identifier"') + 250)
  const passwordControl = login.slice(login.indexOf('id="login-password"'), login.indexOf('id="login-password"') + 250)

  assert.equal(login.includes('RequiredFieldLabel'), false)
  assert.equal(login.includes('<label htmlFor="login-identifier">Email or Username</label>'), true)
  assert.equal(login.includes('<label htmlFor="login-password">Password</label>'), true)
  assert.equal(identifierControl.includes('required'), true)
  assert.equal(passwordControl.includes('required'), true)
})
