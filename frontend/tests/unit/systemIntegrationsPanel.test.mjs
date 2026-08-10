import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { SYSTEM_INTEGRATION_FLAGS } from '../../src/pages/setupCatalog.js'
import { secretInputValue } from '../../src/pages/systemUtils.js'
import {
  INTEGRATION_CATALOG,
  integrationHasSavedDetails,
  integrationIsEnabled,
  integrationSettingsForEditor,
  setIntegrationEnabled,
} from '../../src/pages/integrationCatalog.js'

const readSource = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8')

test('integration catalog covers every configurable system integration', () => {
  const catalogKeys = new Set(INTEGRATION_CATALOG.map(item => item.key))
  for (const [key] of SYSTEM_INTEGRATION_FLAGS) assert.equal(catalogKeys.has(key), true, key)
  assert.equal(catalogKeys.has('oidc'), true)
})

test('integration editor state synchronizes provider roles without mutating source settings', () => {
  const original = { enabled: {}, providers: { ticket_provider: 'none' }, configs: {} }
  const enabled = setIntegrationEnabled(original, 'servicenow', true)

  assert.equal(integrationIsEnabled(enabled, 'servicenow'), true)
  assert.equal(enabled.providers.ticket_provider, 'servicenow')
  assert.equal(original.providers.ticket_provider, 'none')

  const editor = integrationSettingsForEditor(enabled, 'servicenow')
  assert.equal(editor.enabled.servicenow, true)
  assert.equal(editor.enabled.box, false)
  assert.equal(editor.providers.sso_provider, 'local')
})

test('saved secrets count as configured but are blank in edit inputs', () => {
  const integration = INTEGRATION_CATALOG.find(item => item.key === 'servicenow')
  const settings = {
    enabled: { servicenow: false },
    providers: { ticket_provider: 'none' },
    configs: { servicenow: { password: '__configured__' } },
  }

  assert.equal(integrationHasSavedDetails(settings, integration), true)
  assert.equal(secretInputValue(settings.configs.servicenow.password), '')
})

test('System integrations use a searchable card catalog and secret-safe edit dialog', () => {
  const panel = readSource('../../src/pages/SystemIntegrationsPanel.jsx')
  const editor = readSource('../../src/pages/SystemIntegrationEditorModal.jsx')
  const enabledSwitch = readSource('../../src/pages/IntegrationEnabledSwitch.jsx')
  const restartModal = readSource('../../src/pages/SystemBackendRestartModal.jsx')
  const styles = readSource('../../src/styles.css')
  const workflow = readSource('../../src/pages/useSystemConfigurationWorkflow.js')

  assert.match(panel, /className="integration-card-grid"/)
  assert.match(panel, /placeholder="Search integrations"/)
  assert.match(panel, /configured \? 'Edit' : 'Set up'/)
  assert.match(editor, /Saved secrets are never displayed/)
  assert.match(editor, /secret fields remain blank/i)
  assert.match(editor, /SystemIntegrationConfigSections/)
  assert.match(workflow, /settingsOverride \|\| integrationSettings/)
  assert.match(panel, /IntegrationEnabledSwitch/)
  assert.match(panel, /integration-card\$\{enabled \? ' is-enabled' : ''\}/)
  assert.match(panel, /setIntegrationEnabled\(integrationSettings, integration\.key, value\)/)
  assert.match(panel, /\/system\/restart-backend/)
  assert.match(enabledSwitch, /enabled \? 'Enabled' : 'Disabled'/)
  assert.doesNotMatch(enabledSwitch, />On<|>Off</)
  assert.match(restartModal, /Restart the backend\?/)
  assert.match(restartModal, /does not rebuild application images or deploy new code/i)
  assert.match(styles, /\.integration-card\.is-enabled/)
  assert.match(styles, /\.integration-enabled-switch__track/)
})
