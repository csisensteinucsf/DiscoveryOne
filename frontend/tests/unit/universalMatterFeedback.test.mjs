import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('custodian directory exposes profile fields, CSV template, pagination, and back navigation', () => {
  const modal = source('../../src/pages/D1CustodianDirectoryModal.jsx')
  const page = source('../../src/pages/Custodians.jsx')
  const detail = source('../../src/pages/CustodianDetail.jsx')

  for (const label of ['First name', 'Last name', 'Email', 'Campus']) {
    assert.match(modal, new RegExp('<RequiredFieldLabel>' + label + '<\\/RequiredFieldLabel>'))
  }
  for (const field of ['department', 'employee_id', 'title', 'employment_status']) {
    assert.match(modal, new RegExp(field))
  }
  assert.match(modal, /CSV_HEADERS\.join\(','\)/)
  assert.match(modal, /Download CSV template/)
  assert.match(page, /\[25, 50, 100, 200\]/)
  assert.match(page, /useState\(25\)/)
  assert.match(page, /custodians-back-button/)
  assert.match(detail, /First Name/)
  assert.match(detail, /Employment Status/)
  assert.doesNotMatch(detail, />Department ID</)
  assert.doesNotMatch(detail, />Employment End</)
  assert.doesNotMatch(detail, />Current Employee</)
  assert.doesNotMatch(detail, />Last Lookup</)
})

test('matter types configure create templates and support Other values', () => {
  const panel = source('../../src/pages/SystemMatterTypesPanel.jsx')
  const system = source('../../src/pages/System.jsx')
  const createModal = source('../../src/pages/CaseModals.jsx')
  const templates = source('../../src/pages/SystemCaseTemplatesPanel.jsx')

  assert.match(system, /id: 'matter_types'/)
  assert.match(panel, /Public Record Request/)
  assert.match(panel, /General Litigation/)
  assert.match(panel, /Internal Investigation/)
  assert.match(panel, /Subpoena Request/)
  assert.match(panel, /\/system\/matter-types/)
  assert.match(createModal, /Matter Type/)
  assert.match(createModal, /value="Other"/)
  assert.match(createModal, /Other Matter Type/)
  assert.match(createModal, /fieldRequired\('campus'\)/)
  assert.match(templates, /\['campus', 'Campus', 'text'\]/)
  assert.match(templates, /\['matter_type', 'Matter type', 'matter_type'\]/)
})

test('matter detail exposes a custodian profile dialog and matter-scoped logs', () => {
  const detail = source('../../src/pages/CaseDetail.jsx')
  const custodians = source('../../src/pages/CaseDetailCustodiansTab.jsx')
  const profile = source('../../src/pages/CustodianProfileModal.jsx')
  const tabs = source('../../src/pages/CaseDetailTabNav.jsx')
  const logs = source('../../src/pages/Logs.jsx')

  assert.match(custodians, /onViewCustodian\(c\)/)
  assert.match(custodians, /table-link-button/)
  assert.match(detail, /CustodianProfileModal/)
  assert.match(profile, /\/custodians\/detail\?/)
  assert.match(profile, /Matters/)
  assert.match(tabs, /Matter Logs/)
  assert.match(detail, /<Logs apiBase={apiBase} caseId={caseId} embedded/)
  assert.match(logs, /case_query/)
  assert.match(logs, />Matter</)
})

test('requester new request chooser supports new and existing matters', () => {
  const requests = source('../../src/pages/CaseRequests.jsx')
  const chooser = source('../../src/pages/NewRequestChooserModal.jsx')

  assert.match(requests, />New Request</)
  assert.match(requests, /NewRequestChooserModal/)
  assert.match(chooser, /New matter/)
  assert.match(chooser, /Existing matter/)
  assert.match(chooser, /type="search"/)
  assert.match(chooser, /Add custodians/)
  assert.match(chooser, /Search request/)
  assert.match(chooser, /mode: 'new_case'/)
  assert.match(chooser, /mode: requestType/)
})
test('matter logs explain hold changes in plain language with a compact IP-only network column', () => {
  const logs = source('../../src/pages/Logs.jsx')
  const styles = source('../../src/styles.css')

  assert.match(logs, /Preservation changed/)
  assert.match(logs, /Hold workflow changed/)
  assert.match(logs, /Changed \$\{source\} preservation/)
  assert.match(logs, /details\.changes\?\.status/)
  assert.match(logs, /Technical action:/)
  assert.match(logs, /DETAIL_FIELD_LABELS/)
  assert.match(logs, />IP address</)
  assert.doesNotMatch(logs, /r\\.user_agent/)
  assert.doesNotMatch(logs, /function truncate/)
  assert.match(styles, /\.logs-table \.log-ip-column/)
  assert.match(styles, /\.logs-table \.log-details-column/)
})
test('custodian directory names highlight and details expose profile editing', () => {
  const page = source('../../src/pages/Custodians.jsx')
  const detail = source('../../src/pages/CustodianDetail.jsx')
  const editor = source('../../src/pages/EditCustodianProfileModal.jsx')
  const styles = source('../../src/styles.css')

  assert.match(page, /table-link-button custodian-name-link/)
  assert.match(page, /custodian-directory-row/)
  assert.match(styles, /\.custodian-name-link/)
  assert.match(styles, /\.custodian-directory-row:hover td/)
  assert.match(detail, /Custodian Detail[\s\S]*custodians-back-button/)
  assert.match(detail, /aria-label="Edit custodian"/)
  assert.match(detail, /EditCustodianProfileModal/)
  assert.match(editor, /method: 'PUT'/)
  assert.match(editor, /\/custodians\/profile\?/)
  for (const label of ['First name', 'Last name', 'Email', 'Campus']) {
    assert.match(editor, new RegExp('<RequiredFieldLabel>' + label + '<\\/RequiredFieldLabel>'))
  }
})