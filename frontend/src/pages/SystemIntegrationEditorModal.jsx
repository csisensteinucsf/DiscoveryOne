import { LockKeyhole, X } from 'lucide-react'
import SystemEmailIntakeConfig from './SystemEmailIntakeConfig.jsx'
import SystemIntegrationConfigSections from './SystemIntegrationConfigSections.jsx'
import {
  integrationIsEnabled,
  integrationSettingsForEditor,
  setIntegrationConfig,
  setIntegrationEnabled,
  setIntegrationProvider,
} from './integrationCatalog.js'

const providerLabel = value => ({
  none: 'Manual entry',
  csv: 'CSV / static directory file',
  http: 'Identity or HR API',
}[value] || String(value || '').replaceAll('_', ' '))

const personLookupProviders = settings => {
  const options = settings?.providerOptions?.person_lookup_provider
  const values = Array.isArray(options) && options.length ? options : ['none', 'csv', 'http']
  const aliases = new Set(['api', 'idp', 'hr', 'static'])
  return [...new Set(values)].filter(value => !aliases.has(value))
}

export default function SystemIntegrationEditorModal({
  integration,
  settings,
  setSettings,
  onClose,
  onSave,
  onOpenExternal,
  saving,
  status,
}) {
  if (!integration || !settings) return null

  const enabled = integrationIsEnabled(settings, integration.key)
  const editorSettings = integrationSettingsForEditor(settings, integration.key)
  const updateConfig = (name, key, value) => setSettings(prev => setIntegrationConfig(prev, name, key, value))
  const updateProvider = (key, value) => setSettings(prev => setIntegrationProvider(prev, key, value))

  return (
    <div className="modal-backdrop integration-editor-backdrop" onMouseDown={event => event.target === event.currentTarget && onClose()}>
      <div className="modal integration-editor-modal" role="dialog" aria-modal="true" aria-labelledby="integration-editor-title">
        <div className="modal-header integration-editor__header">
          <div>
            <div className="integration-editor__eyebrow">Integration settings</div>
            <h2 id="integration-editor-title">{integration.name}</h2>
            <p>{integration.description}</p>
          </div>
          <button type="button" className="integration-icon-button" onClick={onClose} aria-label="Close integration editor" disabled={saving}>
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <div className="modal-body integration-editor__body">
          <section className="integration-editor__state-card">
            <div>
              <strong>{enabled ? 'Enabled' : 'Disabled'}</strong>
              <span>{enabled ? 'DiscoveryOne can use this integration.' : 'Settings can be saved before the integration is enabled.'}</span>
            </div>
            <label className="integration-toggle">
              <input
                type="checkbox"
                checked={enabled}
                onChange={event => setSettings(prev => setIntegrationEnabled(prev, integration.key, event.target.checked))}
              />
              <span>{enabled ? 'On' : 'Off'}</span>
            </label>
          </section>

          {integration.key === 'person_lookup' && (
            <label className="integration-editor__provider-field">
              Directory provider
              <select
                className="input"
                value={settings.providers?.person_lookup_provider || 'none'}
                onChange={event => updateProvider('person_lookup_provider', event.target.value)}
              >
                {personLookupProviders(settings).map(value => <option key={value} value={value}>{providerLabel(value)}</option>)}
              </select>
            </label>
          )}

          {integration.key === 'purview' && (
            <section className="integration-editor__roles">
              <div>
                <strong>Use Purview for</strong>
                <span>Select the workflows this connection should handle.</span>
              </div>
              <label><input type="checkbox" checked={settings.providers?.preservation_provider === 'purview'} onChange={event => updateProvider('preservation_provider', event.target.checked ? 'purview' : 'none')} />Preservation automation</label>
              <label><input type="checkbox" checked={settings.providers?.search_export_provider === 'purview'} onChange={event => updateProvider('search_export_provider', event.target.checked ? 'purview' : 'none')} />Search exports</label>
            </section>
          )}

          <div className="integration-secret-notice">
            <LockKeyhole size={20} aria-hidden="true" />
            <div>
              <strong>Saved secrets are never displayed</strong>
              <span>Secret fields remain blank when editing. Leave them blank to keep the saved value, or enter a new secret to replace it.</span>
            </div>
          </div>

          {integration.configurationOnly && (
            <div className="integration-editor__info">
              This connector currently stores configuration for future automation. DiscoveryOne does not yet execute actions through it.
            </div>
          )}

          {integration.externalEditor === 'smtp' && (
            <section className="integration-editor__state-card">
              <div>
                <strong>SMTP connection details</strong>
                <span>Host, sender, credentials, encryption, and test-email tools are managed in the dedicated SMTP settings page.</span>
              </div>
              <button type="button" className="btn secondary" onClick={onOpenExternal}>Open SMTP settings</button>
            </section>
          )}

          <section className="integration-editor__fields">
            <SystemIntegrationConfigSections
              integrationSettings={editorSettings}
              updateIntegrationConfig={updateConfig}
            />
            {integration.key === 'email_intake' && (
              <SystemEmailIntakeConfig
                integrationSettings={editorSettings}
                updateIntegrationConfig={updateConfig}
              />
            )}
          </section>

          {status && !status.startsWith('Integration settings saved.') && (
            <div className="integration-editor__status is-error">{status}</div>
          )}
        </div>

        <div className="modal-footer integration-editor__footer">
          <button type="button" className="btn secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="button" className="btn" onClick={() => onSave(settings)} disabled={saving}>
            {saving ? 'Saving' : 'Save integration'}
          </button>
        </div>
      </div>
    </div>
  )
}
