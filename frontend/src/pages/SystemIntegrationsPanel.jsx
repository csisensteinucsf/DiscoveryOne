import { Cloud, Mail, Pencil, Plus, RotateCw, Search, Settings, Shield, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import IntegrationEnabledSwitch from './IntegrationEnabledSwitch.jsx'
import SystemBackendRestartModal from './SystemBackendRestartModal.jsx'
import SystemEmailIntakeWorkspace from './SystemEmailIntakeWorkspace.jsx'
import SystemIntegrationEditorModal from './SystemIntegrationEditorModal.jsx'
import {
  cloneIntegrationSettings,
  INTEGRATION_CATALOG,
  INTEGRATION_CATEGORIES,
  integrationHasSavedDetails,
  integrationIsEnabled,
  setIntegrationEnabled,
} from './integrationCatalog.js'

const CATEGORY_ICONS = {
  Identity: Users,
  Communication: Mail,
  'Legal workflows': Settings,
  Preservation: Cloud,
  'Security and devices': Shield,
  Operations: Settings,
}

export default function SystemIntegrationsPanel({
  isSysAdmin,
  adminOnlyCard,
  integrationSettings,
  saveIntegrationSettings,
  integrationSaving,
  integrationStatus,
  apiBase,
  showToast,
  onOpenSmtp,
}) {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('All')
  const [editingKey, setEditingKey] = useState(null)
  const [draftSettings, setDraftSettings] = useState(null)
  const [restartOpen, setRestartOpen] = useState(false)
  const [restartBusy, setRestartBusy] = useState(false)
  const [restartRequested, setRestartRequested] = useState(false)
  const [restartStatus, setRestartStatus] = useState('')

  const enabledCount = INTEGRATION_CATALOG.filter(item => integrationIsEnabled(integrationSettings, item.key)).length
  const configuredCount = INTEGRATION_CATALOG.filter(item => integrationHasSavedDetails(integrationSettings, item)).length
  const visibleIntegrations = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return INTEGRATION_CATALOG.filter(item => {
      if (category !== 'All' && item.category !== category) return false
      if (!normalizedQuery) return true
      return `${item.name} ${item.description} ${item.category}`.toLowerCase().includes(normalizedQuery)
    })
  }, [category, query])

  if (!isSysAdmin) return adminOnlyCard('Only system administrators can configure integrations.')

  const editingIntegration = INTEGRATION_CATALOG.find(item => item.key === editingKey)
  const openEditor = integration => {
    setDraftSettings(cloneIntegrationSettings(integrationSettings))
    setEditingKey(integration.key)
  }
  const closeEditor = () => {
    if (integrationSaving) return
    setEditingKey(null)
    setDraftSettings(null)
  }
  const promptForRestart = () => {
    setRestartStatus('')
    setRestartRequested(false)
    setRestartOpen(true)
  }
  const saveEditor = async settings => {
    const saved = await saveIntegrationSettings(settings)
    if (saved) {
      setEditingKey(null)
      setDraftSettings(null)
      promptForRestart()
    }
  }
  const toggleIntegration = async (integration, value) => {
    const next = setIntegrationEnabled(integrationSettings, integration.key, value)
    const saved = await saveIntegrationSettings(next)
    if (saved) promptForRestart()
  }
  const closeRestartPrompt = () => {
    if (restartBusy || restartRequested) return
    setRestartOpen(false)
    setRestartStatus('')
  }
  const restartBackend = async () => {
    setRestartBusy(true)
    setRestartStatus('')
    try {
      const response = await fetch(`${apiBase}/system/restart-backend`, {
        method: 'POST',
        credentials: 'include',
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data?.detail || 'Unable to restart the backend.')
      setRestartRequested(true)
      setRestartStatus(data?.message || 'Backend restart requested.')
      window.setTimeout(() => window.location.reload(), 8000)
    } catch (error) {
      setRestartStatus(error?.message || 'Unable to restart the backend.')
    } finally {
      setRestartBusy(false)
    }
  }

  return (
    <>
      <div className="card integrations-hub">
        <header className="integrations-hub__header">
          <div>
            <span className="integrations-hub__eyebrow">Connected systems</span>
            <h2>Integrations</h2>
            <p>Connect the services DiscoveryOne uses for identity, communication, preservation, legal workflows, and operations.</p>
          </div>
          <div className="integrations-hub__header-actions">
            <div className="integrations-hub__summary" aria-label="Integration summary">
              <div><strong>{enabledCount}</strong><span>Enabled</span></div>
              <div><strong>{configuredCount}</strong><span>Set up</span></div>
              <div><strong>{INTEGRATION_CATALOG.length}</strong><span>Available</span></div>
            </div>
            <button type="button" className="btn secondary integrations-restart-button" onClick={promptForRestart}>
              <RotateCw size={16} aria-hidden="true" />Restart backend
            </button>
          </div>
        </header>

        <div className="integrations-toolbar">
          <label className="integrations-search">
            <Search size={18} aria-hidden="true" />
            <span className="sr-only">Search integrations</span>
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search integrations" />
          </label>
          <label className="integrations-category-filter">
            <span>Category</span>
            <select value={category} onChange={event => setCategory(event.target.value)}>
              {INTEGRATION_CATEGORIES.map(value => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>

        {integrationStatus && !editingIntegration && (
          <div className={`integrations-hub__status${integrationStatus.toLowerCase().includes('unable') ? ' is-error' : ''}`}>
            {integrationStatus}
          </div>
        )}

        <div className="integration-card-grid">
          {visibleIntegrations.map(integration => {
            const enabled = integrationIsEnabled(integrationSettings, integration.key)
            const configured = integrationHasSavedDetails(integrationSettings, integration)
            const Icon = CATEGORY_ICONS[integration.category] || Settings
            return (
              <article className={`integration-card${enabled ? ' is-enabled' : ''}`} key={integration.key}>
                <div className="integration-card__topline">
                  <span className="integration-card__icon"><Icon size={22} aria-hidden="true" /></span>
                  <IntegrationEnabledSwitch
                    compact
                    enabled={enabled}
                    disabled={integrationSaving}
                    onChange={value => toggleIntegration(integration, value)}
                  />
                </div>
                <div className="integration-card__content">
                  <h3>{integration.name}</h3>
                  <p>{integration.description}</p>
                </div>
                <div className="integration-card__meta">
                  <span>{integration.category}</span>
                  {configured && <span>Setup saved</span>}
                  {integration.configurationOnly && <span>Configuration only</span>}
                </div>
                <button type="button" className="btn secondary integration-card__action" onClick={() => openEditor(integration)}>
                  {configured ? <Pencil size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
                  {configured ? 'Edit' : 'Set up'}
                </button>
              </article>
            )
          })}
        </div>

        {visibleIntegrations.length === 0 && (
          <div className="integrations-empty">No integrations match your search.</div>
        )}
      </div>

      {integrationSettings.enabled?.email_intake && (
        <div className="integrations-operations">
          <SystemEmailIntakeWorkspace
            apiBase={apiBase}
            enabled={!!integrationSettings.enabled?.email_intake}
            showToast={showToast}
            mode="operations"
          />
        </div>
      )}

      <SystemIntegrationEditorModal
        integration={editingIntegration}
        settings={draftSettings}
        setSettings={setDraftSettings}
        onClose={closeEditor}
        onSave={saveEditor}
        saving={integrationSaving}
        status={integrationStatus}
        onOpenExternal={() => {
          closeEditor()
          onOpenSmtp?.()
        }}
      />

      <SystemBackendRestartModal
        open={restartOpen}
        busy={restartBusy}
        requested={restartRequested}
        status={restartStatus}
        onClose={closeRestartPrompt}
        onRestart={restartBackend}
      />
    </>
  )
}
