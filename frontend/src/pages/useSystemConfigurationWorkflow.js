import { useCallback, useMemo, useState } from 'react'
import {
  PROVIDER_DEFAULTS,
  INTEGRATION_CONFIG_DEFAULTS,
  BUILT_IN_PRESERVATION,
  CASE_NAMING_OPTIONS,
} from './systemUtils.js'
import { normalizeCaseNamingMode } from './setupCatalog.js'
import { preservationSourceKey } from './preservationCatalog.js'
import { normalizeTicketWorkflowMetadataSchema } from './ticketWorkflowCatalog.js'

const defaultIntegrationSettings = () => ({
  enabled: {},
  providers: { ...PROVIDER_DEFAULTS },
  providerOptions: {},
  configs: { ...INTEGRATION_CONFIG_DEFAULTS },
})

const normalizeIntegrationSettings = (data = {}) => {
  const providerOptions = data?.provider_options || {}
  const providers = { ...PROVIDER_DEFAULTS, ...(data?.providers || {}) }

  Object.entries(providerOptions).forEach(([key, values]) => {
    if (!Array.isArray(values) || values.length === 0) return
    if (values.includes(providers[key])) return
    const fallback = PROVIDER_DEFAULTS[key]
    providers[key] = values.includes(fallback)
      ? fallback
      : (values.includes('none') ? 'none' : values[0])
  })

  return {
    enabled: data?.enabled || {},
    providers,
    providerOptions,
    configs: { ...INTEGRATION_CONFIG_DEFAULTS, ...(data?.configs || {}) },
  }
}

const defaultPreservationSources = () => (
  BUILT_IN_PRESERVATION.map(([key, label, enabled]) => ({ key, label, enabled, built_in: true }))
)

const defaultTicketWorkflows = () => ([])

const defaultCaseClosureSettings = () => ({
  default_nag_days: 180,
  loop_seconds: 3600,
  batch_size: 25,
})

const normalizeCaseClosureSettings = (settings = {}) => ({
  default_nag_days: Number(settings.default_nag_days) || 180,
  loop_seconds: Number(settings.loop_seconds) || 3600,
  batch_size: Number(settings.batch_size) || 25,
})

const defaultCaseStatusSettings = () => ({
  ntp_ack_days: 7,
  consent_received_days: 7,
})

const normalizeCaseStatusSettings = (settings = {}) => ({
  ntp_ack_days: Number(settings.ntp_ack_days) || 7,
  consent_received_days: Number(settings.consent_received_days) || 7,
})

const defaultCaseRequestSettings = () => ({
  requestor_stats_show_global: false,
  hold_automation_allow_override: false,
  auto_rubrik_restore_for_separated_email_holds: false,
  pending_cleanup_days: 30,
  pending_cleanup_interval_hours: 12,
  hold_status_email_delay_seconds: 300,
  preservation_auto_apply_max_attempts: 3,
  preservation_auto_apply_delay_seconds: 2,
  preservation_status_max_seconds: 90,
  preservation_status_interval_seconds: 5,
})

const normalizeCaseRequestSettings = (settings = {}) => ({
  requestor_stats_show_global: !!settings.requestor_stats_show_global,
  hold_automation_allow_override: !!settings.hold_automation_allow_override,
  auto_rubrik_restore_for_separated_email_holds: !!settings.auto_rubrik_restore_for_separated_email_holds,
  pending_cleanup_days: Number(settings.pending_cleanup_days) || 30,
  pending_cleanup_interval_hours: Number(settings.pending_cleanup_interval_hours) || 12,
  hold_status_email_delay_seconds: Number(settings.hold_status_email_delay_seconds) || 300,
  preservation_auto_apply_max_attempts: Number(settings.preservation_auto_apply_max_attempts ?? settings.purview_auto_apply_max_attempts) || 3,
  preservation_auto_apply_delay_seconds: Number(settings.preservation_auto_apply_delay_seconds ?? settings.purview_auto_apply_delay_seconds) || 2,
  preservation_status_max_seconds: Number(settings.preservation_status_max_seconds ?? settings.purview_approval_status_max_seconds) || 90,
  preservation_status_interval_seconds: Number(settings.preservation_status_interval_seconds ?? settings.purview_approval_status_interval_seconds) || 5,
})

const workflowKey = preservationSourceKey

const normalizeTicketWorkflow = (workflow = {}, index = 0) => {
  const label = String(workflow.label || workflow.key || '').trim()
  const key = workflowKey(workflow.key || label || `workflow_${index + 1}`)
  const provider = String(workflow.provider || ((workflow.external_ticket_enabled ?? workflow.service_now_enabled) ? 'servicenow' : 'manual') || 'manual').trim().toLowerCase()
  return {
    key,
    label: label || key.replace(/_/g, ' '),
    enabled: workflow.enabled !== false,
    provider: provider === 'servicenow' ? 'servicenow' : 'manual',
    external_ticket_enabled: provider === 'servicenow' || !!(workflow.external_ticket_enabled ?? workflow.service_now_enabled),
    service_now_enabled: provider === 'servicenow' || !!(workflow.external_ticket_enabled ?? workflow.service_now_enabled),
    auto_create_on_approval: !!workflow.auto_create_on_approval,
    manual_status_tracking: !!workflow.manual_status_tracking,
    hold_operation: ['hold', 'release'].includes(String(workflow.hold_operation || workflow.operation || '').trim().toLowerCase())
      ? String(workflow.hold_operation || workflow.operation).trim().toLowerCase()
      : 'hold',
    completion_satisfies_source: workflowKey(workflow.completion_satisfies_source || ''),
    completion_satisfies_hold_key: String(workflow.completion_satisfies_hold_key || '').trim(),
    preservation_source: workflowKey(workflow.preservation_source || workflow.preservationSource || ''),
    hold_key: String(workflow.hold_key || workflow.holdKey || '').trim(),
    tech_group: workflowKey(workflow.tech_group || workflow.techGroup || key),
    requires_matched_email: !!workflow.requires_matched_email,
    metadata_schema: normalizeTicketWorkflowMetadataSchema(workflow.metadata_schema || workflow.metadataSchema),
    legacy_field: String(workflow.legacy_field || '').trim(),
    built_in: !!workflow.built_in,
    short_description: String(workflow.short_description || '').trim(),
    assignment_group: String(workflow.assignment_group || '').trim(),
    symptom: String(workflow.symptom || 'Inquiry').trim() || 'Inquiry',
    incident_keyword: String(workflow.incident_keyword || '').trim(),
    request_type: String(workflow.request_type || '').trim(),
    link_label: String(workflow.link_label || 'Case link').trim() || 'Case link',
  }
}

const normalizeTicketWorkflows = (workflows) => (
  Array.isArray(workflows)
    ? workflows
      .filter(item => item?.built_in || String(item?.label || item?.key || '').trim())
      .map(normalizeTicketWorkflow)
      .filter(item => item.key && item.label)
    : defaultTicketWorkflows()
)

const emptyTicketWorkflow = () => ({
  key: '',
  label: '',
  enabled: true,
  provider: 'manual',
  external_ticket_enabled: false,
  service_now_enabled: false,
  auto_create_on_approval: false,
  manual_status_tracking: false,
  hold_operation: 'hold',
  completion_satisfies_source: '',
  completion_satisfies_hold_key: '',
  preservation_source: '',
  hold_key: '',
  tech_group: '',
  requires_matched_email: false,
  metadata_schema: '',
  legacy_field: '',
  built_in: false,
  short_description: '',
  assignment_group: '',
  symptom: 'Inquiry',
  incident_keyword: '',
  request_type: '',
  link_label: 'Case link',
})

export function useSystemConfigurationWorkflow({ apiBase, isSysAdmin }) {
  const [integrationSettings, setIntegrationSettings] = useState(defaultIntegrationSettings)
  const [integrationStatus, setIntegrationStatus] = useState(null)
  const [integrationSaving, setIntegrationSaving] = useState(false)
  const [preservationSources, setPreservationSources] = useState(defaultPreservationSources)
  const [customPreservationInput, setCustomPreservationInput] = useState('')
  const [preservationStatus, setPreservationStatus] = useState(null)
  const [preservationSaving, setPreservationSaving] = useState(false)
  const [caseNamingMode, setCaseNamingMode] = useState('legal_case_name')
  const [caseNamingStatus, setCaseNamingStatus] = useState(null)
  const [caseNamingSaving, setCaseNamingSaving] = useState(false)
  const [caseClosureSettings, setCaseClosureSettings] = useState(defaultCaseClosureSettings)
  const [caseClosureStatus, setCaseClosureStatus] = useState(null)
  const [caseClosureSaving, setCaseClosureSaving] = useState(false)
  const [caseStatusSettings, setCaseStatusSettings] = useState(defaultCaseStatusSettings)
  const [caseStatusStatus, setCaseStatusStatus] = useState(null)
  const [caseStatusSaving, setCaseStatusSaving] = useState(false)
  const [caseRequestSettings, setCaseRequestSettings] = useState(defaultCaseRequestSettings)
  const [caseRequestStatus, setCaseRequestStatus] = useState(null)
  const [caseRequestSaving, setCaseRequestSaving] = useState(false)
  const [ticketWorkflows, setTicketWorkflows] = useState(defaultTicketWorkflows)
  const [ticketWorkflowStatus, setTicketWorkflowStatus] = useState(null)
  const [ticketWorkflowSaving, setTicketWorkflowSaving] = useState(false)

  const resetConfigurationSettings = useCallback(() => {
    setIntegrationSettings(defaultIntegrationSettings())
    setIntegrationStatus(null)
    setPreservationSources(defaultPreservationSources())
    setCustomPreservationInput('')
    setPreservationStatus(null)
    setCaseNamingMode('legal_case_name')
    setCaseNamingStatus(null)
    setCaseClosureSettings(defaultCaseClosureSettings())
    setCaseClosureStatus(null)
    setCaseStatusSettings(defaultCaseStatusSettings())
    setCaseStatusStatus(null)
    setCaseRequestSettings(defaultCaseRequestSettings())
    setCaseRequestStatus(null)
    setTicketWorkflows(defaultTicketWorkflows())
    setTicketWorkflowStatus(null)
  }, [])

  const applyConfigurationSettings = useCallback((data) => {
    const nextCaseNamingMode = data?.case_naming?.mode || 'legal_case_name'
    setCaseNamingMode(normalizeCaseNamingMode(nextCaseNamingMode))
    setCaseClosureSettings(normalizeCaseClosureSettings(data?.case_closure))
    setCaseStatusSettings(normalizeCaseStatusSettings(data?.case_status))
    setCaseRequestSettings(normalizeCaseRequestSettings(data?.case_requests))
    const sources = Array.isArray(data?.preservation_sources) ? data.preservation_sources : []
    if (sources.length) {
      setPreservationSources(sources)
      setCustomPreservationInput(sources.filter(item => !item?.built_in).map(item => item.label || item.key).filter(Boolean).join('\n'))
    }
    setTicketWorkflows(normalizeTicketWorkflows(data?.ticket_workflows))
  }, [])

  const loadIntegrations = useCallback(async () => {
    if (!isSysAdmin) {
      setIntegrationSettings(defaultIntegrationSettings())
      return
    }
    setIntegrationStatus(null)
    try {
      const res = await fetch(`${apiBase}/system/integrations`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setIntegrationSettings(normalizeIntegrationSettings(data))

    } catch (err) {
      console.error(err)
      setIntegrationStatus('Unable to load integration settings.')
    }
  }, [apiBase, isSysAdmin])

  const updateIntegrationEnabled = useCallback((key, value) => {
    setIntegrationSettings(prev => {
      const providers = { ...(prev.providers || {}) }
      if (key === 'person_lookup') providers.person_lookup_provider = value ? (providers.person_lookup_provider === 'none' ? 'csv' : providers.person_lookup_provider || 'csv') : 'none'
      if (key === 'servicenow') providers.ticket_provider = value ? 'servicenow' : 'none'
      if (key === 'docusign') providers.esign_provider = value ? 'docusign' : 'none'
      if (key === 'purview') providers.preservation_provider = value ? 'purview' : 'none'
      if (key === 'purview') providers.search_export_provider = value ? 'purview' : 'none'

      if (key === 'smtp') providers.mail_provider = value ? 'smtp' : 'none'
      return {
        ...prev,
        enabled: { ...(prev.enabled || {}), [key]: value },
        providers,
      }
    })
  }, [])

  const updateIntegrationProvider = useCallback((key, value) => {
    setIntegrationSettings(prev => {
      const enabled = { ...(prev.enabled || {}) }
      if (key === 'person_lookup_provider') enabled.person_lookup = value !== 'none'
      if (key === 'ticket_provider') enabled.servicenow = value === 'servicenow'
      if (key === 'mail_provider') enabled.smtp = value === 'smtp'
      if (key === 'esign_provider') enabled.docusign = value === 'docusign'
      if (key === 'preservation_provider') {
        enabled.purview = value === 'purview'

      }
      if (key === 'search_export_provider' && value === 'purview') enabled.purview = true
      return {
        ...prev,
        enabled,
        providers: { ...(prev.providers || {}), [key]: value },
      }
    })
  }, [])

  const updateIntegrationConfig = useCallback((name, key, value) => {
    setIntegrationSettings(prev => ({
      ...prev,
      configs: {
        ...(prev.configs || {}),
        [name]: {
          ...((prev.configs || {})[name] || {}),
          [key]: value,
        },
      },
    }))
  }, [])

  const customPreservationSources = useMemo(() => {
    const builtIns = new Set(BUILT_IN_PRESERVATION.map(([key]) => key))
    const seen = new Set(builtIns)
    return String(customPreservationInput || '')
      .split(/[\n,]+/)
      .map(value => value.trim())
      .filter(Boolean)
      .map(label => ({ key: preservationSourceKey(label), label }))
      .filter(item => {
        if (!item.key || seen.has(item.key)) return false
        seen.add(item.key)
        return true
      })
      .map(item => ({ ...item, enabled: true, built_in: false }))
  }, [customPreservationInput])

  const preservationSourcePayload = useMemo(() => {
    const currentByKey = new Map((preservationSources || []).map(item => [item.key, item]))
    const builtIns = BUILT_IN_PRESERVATION.map(([key, label, defaultEnabled]) => ({
      key,
      label,
      enabled: currentByKey.has(key) ? !!currentByKey.get(key)?.enabled : !!defaultEnabled,
      built_in: true,
    }))
    return [...builtIns, ...customPreservationSources]
  }, [customPreservationSources, preservationSources])

  const togglePreservationSource = useCallback((key) => {
    setPreservationSources(prev => {
      const existing = new Map((prev || []).map(item => [item.key, item]))
      const item = existing.get(key) || {
        key,
        label: BUILT_IN_PRESERVATION.find(([builtInKey]) => builtInKey === key)?.[1] || key,
        enabled: true,
        built_in: true,
      }
      existing.set(key, { ...item, enabled: !item.enabled })
      return Array.from(existing.values())
    })
  }, [])

  const savePreservationSources = useCallback(async () => {
    setPreservationSaving(true)
    setPreservationStatus(null)
    try {
      const res = await fetch(`${apiBase}/system/preservation_sources`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preservation_sources: preservationSourcePayload }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const sources = Array.isArray(data?.preservation_sources) ? data.preservation_sources : preservationSourcePayload
      setPreservationSources(sources)
      setCustomPreservationInput(sources.filter(item => !item?.built_in).map(item => item.label || item.key).filter(Boolean).join('\n'))
      setPreservationStatus('Preservation sources saved.')
    } catch (err) {
      setPreservationStatus(err?.message || 'Unable to save preservation sources.')
    } finally {
      setPreservationSaving(false)
    }
  }, [apiBase, preservationSourcePayload])

  const saveCaseNaming = useCallback(async () => {
    setCaseNamingSaving(true)
    setCaseNamingStatus(null)
    try {
      const res = await fetch(`${apiBase}/system/case_naming`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: caseNamingMode }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const nextMode = data?.case_naming?.mode || caseNamingMode
      setCaseNamingMode(normalizeCaseNamingMode(nextMode))
      setCaseNamingStatus('Case naming saved.')
    } catch (err) {
      setCaseNamingStatus(err?.message || 'Unable to save case naming.')
    } finally {
      setCaseNamingSaving(false)
    }
  }, [apiBase, caseNamingMode])

  const updateCaseClosureSetting = useCallback((key, value) => {
    setCaseClosureSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const saveCaseClosureSettings = useCallback(async () => {
    setCaseClosureSaving(true)
    setCaseClosureStatus(null)
    try {
      const payload = normalizeCaseClosureSettings(caseClosureSettings)
      const res = await fetch(`${apiBase}/system/case_closure`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setCaseClosureSettings(normalizeCaseClosureSettings(data?.case_closure))
      setCaseClosureStatus('Case closure settings saved.')
    } catch (err) {
      setCaseClosureStatus(err?.message || 'Unable to save case closure settings.')
    } finally {
      setCaseClosureSaving(false)
    }
  }, [apiBase, caseClosureSettings])

  const updateCaseStatusSetting = useCallback((key, value) => {
    setCaseStatusSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const saveCaseStatusSettings = useCallback(async () => {
    setCaseStatusSaving(true)
    setCaseStatusStatus(null)
    try {
      const payload = normalizeCaseStatusSettings(caseStatusSettings)
      const res = await fetch(`${apiBase}/system/case_status`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setCaseStatusSettings(normalizeCaseStatusSettings(data?.case_status))
      setCaseStatusStatus('Case status SLA settings saved.')
    } catch (err) {
      setCaseStatusStatus(err?.message || 'Unable to save case status SLA settings.')
    } finally {
      setCaseStatusSaving(false)
    }
  }, [apiBase, caseStatusSettings])

  const updateCaseRequestSetting = useCallback((key, value) => {
    setCaseRequestSettings(prev => ({ ...prev, [key]: value }))
  }, [])

  const saveCaseRequestSettings = useCallback(async () => {
    setCaseRequestSaving(true)
    setCaseRequestStatus(null)
    try {
      const payload = normalizeCaseRequestSettings(caseRequestSettings)
      const res = await fetch(`${apiBase}/system/case_requests`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setCaseRequestSettings(normalizeCaseRequestSettings(data?.case_requests))
      setCaseRequestStatus('Case request policy settings saved.')
    } catch (err) {
      setCaseRequestStatus(err?.message || 'Unable to save case request policy settings.')
    } finally {
      setCaseRequestSaving(false)
    }
  }, [apiBase, caseRequestSettings])

  const updateTicketWorkflow = useCallback((index, key, value) => {
    setTicketWorkflows(prev => (prev || []).map((item, itemIndex) => {
      if (itemIndex !== index) return item
      const next = { ...item, [key]: value }
      if (key === 'label' && !item.built_in && !item.key) {
        next.key = workflowKey(value)
      }
      if (key === 'key') {
        next.key = workflowKey(value)
      }
      if (key === 'provider') {
        next.provider = value === 'servicenow' ? 'servicenow' : 'manual'
        next.external_ticket_enabled = next.provider === 'servicenow'
        next.service_now_enabled = next.external_ticket_enabled
      }
      if (key === 'preservation_source' || key === 'tech_group') {
        next[key] = workflowKey(value)
      }
      return next
    }))
  }, [])

  const addTicketWorkflow = useCallback(() => {
    setTicketWorkflows(prev => [...(prev || []), emptyTicketWorkflow()])
  }, [])

  const removeTicketWorkflow = useCallback((index) => {
    setTicketWorkflows(prev => (prev || []).filter((item, itemIndex) => itemIndex !== index || item.built_in))
  }, [])

  const saveTicketWorkflows = useCallback(async () => {
    setTicketWorkflowSaving(true)
    setTicketWorkflowStatus(null)
    try {
      const payload = normalizeTicketWorkflows(ticketWorkflows)
      const res = await fetch(`${apiBase}/system/ticket_workflows`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket_workflows: payload }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setTicketWorkflows(normalizeTicketWorkflows(data?.ticket_workflows))
      setTicketWorkflowStatus('Ticket workflows saved.')
    } catch (err) {
      setTicketWorkflowStatus(err?.message || 'Unable to save ticket workflows.')
    } finally {
      setTicketWorkflowSaving(false)
    }
  }, [apiBase, ticketWorkflows])

  const saveIntegrationSettings = useCallback(async () => {
    setIntegrationSaving(true)
    setIntegrationStatus(null)
    try {
      const res = await fetch(`${apiBase}/system/integrations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          enabled_integrations: integrationSettings.enabled || {},
          providers: integrationSettings.providers || {},
          configs: integrationSettings.configs || {},
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setIntegrationSettings(normalizeIntegrationSettings(data))

      setIntegrationStatus('Integration settings saved. Restart the backend if a long-running integration had already loaded old values.')
    } catch (err) {
      console.error(err)
      setIntegrationStatus(err?.message || 'Unable to save integration settings.')
    } finally {
      setIntegrationSaving(false)
    }
  }, [apiBase, integrationSettings])

  return {
    integrationSettings,
    integrationStatus,
    integrationSaving,
    updateIntegrationEnabled,
    updateIntegrationProvider,
    updateIntegrationConfig,
    saveIntegrationSettings,
    loadIntegrations,
    preservationSourcePayload,
    customPreservationInput,
    setCustomPreservationInput,
    customPreservationSources,
    togglePreservationSource,
    savePreservationSources,
    preservationSaving,
    preservationStatus,
    caseNamingMode,
    setCaseNamingMode,
    saveCaseNaming,
    caseNamingSaving,
    caseNamingStatus,
    caseClosureSettings,
    updateCaseClosureSetting,
    saveCaseClosureSettings,
    caseClosureSaving,
    caseClosureStatus,
    caseStatusSettings,
    updateCaseStatusSetting,
    saveCaseStatusSettings,
    caseStatusSaving,
    caseStatusStatus,
    caseRequestSettings,
    updateCaseRequestSetting,
    saveCaseRequestSettings,
    caseRequestSaving,
    caseRequestStatus,
    ticketWorkflows,
    updateTicketWorkflow,
    addTicketWorkflow,
    removeTicketWorkflow,
    saveTicketWorkflows,
    ticketWorkflowSaving,
    ticketWorkflowStatus,
    applyConfigurationSettings,
    resetConfigurationSettings,
  }
}

