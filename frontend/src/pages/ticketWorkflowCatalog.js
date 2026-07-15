import { preservationSourceKey } from './preservationCatalog.js'

export const TICKET_PROVIDER_LABELS = {
  none: 'No external ticket provider',
  manual: 'Manual tracking',
  servicenow: 'ServiceNow',
}

export const normalizeTicketProvider = (provider) => {
  const value = String(provider || 'manual').trim().toLowerCase()
  if (value === 'servicenow') return 'servicenow'
  if (value === 'none') return 'none'
  return 'manual'
}

export const ticketProviderLabel = (provider, { action = false } = {}) => {
  const normalized = normalizeTicketProvider(provider)
  if (action && normalized === 'servicenow') return 'ServiceNow ticket'
  return TICKET_PROVIDER_LABELS[normalized] || TICKET_PROVIDER_LABELS.manual
}

export const externalTicketProviderLabel = (provider) => {
  const normalized = normalizeTicketProvider(provider)
  if (normalized === 'manual' || normalized === 'none') return 'external ticket provider'
  return ticketProviderLabel(normalized)
}

export const ticketProviderUsesExternalTicket = (provider) => normalizeTicketProvider(provider) === 'servicenow'

export const TICKET_WORKFLOW_METADATA_SCHEMAS = {
  none: '',
  accessLogRequest: 'access_log_request',
}

export const normalizeTicketWorkflowMetadataSchema = (schema) => {
  const value = String(schema || '').trim().toLowerCase()
  if (value === TICKET_WORKFLOW_METADATA_SCHEMAS.accessLogRequest) return value
  return TICKET_WORKFLOW_METADATA_SCHEMAS.none
}

export const ticketWorkflowUsesAccessLogDetails = (workflow) => (
  normalizeTicketWorkflowMetadataSchema(workflow?.metadata_schema || workflow?.metadataSchema) === TICKET_WORKFLOW_METADATA_SCHEMAS.accessLogRequest
)

export const REQUEST_TICKET_CATEGORIES = [
  { key: 'box_hold', legacyKey: 'box_hold_ticket', label: 'Box Hold', provider: 'servicenow', externalTicketEnabled: true, serviceNowEnabled: true, techGroup: 'box', holdKey: 'holds_box', requiresMatchedEmail: true, metadataSchema: '' },
  { key: 'box_hold_release', legacyKey: null, label: 'Box Hold Release', provider: 'servicenow', externalTicketEnabled: true, serviceNowEnabled: true, techGroup: 'box', holdKey: 'holds_box', requiresMatchedEmail: true, metadataSchema: '' },
]

const ticketGroupKey = (value) => preservationSourceKey(value)

export const TECH_TICKET_GROUPS = REQUEST_TICKET_CATEGORIES.reduce((acc, item) => {
  const group = ticketGroupKey(item.techGroup)
  if (!group) return acc
  if (!acc[group]) acc[group] = []
  acc[group].push(item.key)
  return acc
}, {})

export const TECH_CATEGORY_HOLD_KEYS = REQUEST_TICKET_CATEGORIES.reduce((acc, item) => {
  if (item.holdKey) acc[item.key] = item.holdKey
  return acc
}, {})

export const REQUEST_TICKET_CATEGORY_LOOKUP = REQUEST_TICKET_CATEGORIES.reduce((acc, item) => {
  acc[item.key] = item
  return acc
}, {})

export const ticketCategoriesFromWorkflows = (workflows) => {
  if (!Array.isArray(workflows) || !workflows.length) return REQUEST_TICKET_CATEGORIES
  const categories = workflows
    .filter(item => item && item.enabled !== false)
    .map(item => {
      const provider = normalizeTicketProvider(item.provider || ((item.external_ticket_enabled ?? item.service_now_enabled) === false ? 'manual' : 'servicenow'))
      return {
        key: preservationSourceKey(item.key || item.label),
        legacyKey: item.legacy_field || item.legacyKey || null,
        label: item.label || item.key || 'Ticket Workflow',
        provider,
        externalTicketEnabled: (item.external_ticket_enabled ?? item.service_now_enabled) !== false && ticketProviderUsesExternalTicket(provider),
        serviceNowEnabled: (item.external_ticket_enabled ?? item.service_now_enabled) !== false && ticketProviderUsesExternalTicket(provider),
        techGroup: ticketGroupKey(item.tech_group || item.techGroup || item.key),
        holdKey: item.hold_key || item.holdKey || '',
        requiresMatchedEmail: !!item.requires_matched_email,
        metadataSchema: normalizeTicketWorkflowMetadataSchema(item.metadata_schema || item.metadataSchema),
        metadata_schema: normalizeTicketWorkflowMetadataSchema(item.metadata_schema || item.metadataSchema),
      }
    })
    .filter(item => item.key)
  return categories.length ? categories : REQUEST_TICKET_CATEGORIES
}

export const ticketCategoryLookupFromCategories = (categories) => (categories || REQUEST_TICKET_CATEGORIES).reduce((acc, item) => {
  if (item?.key) acc[item.key] = item
  return acc
}, {})

export const techTicketGroupsFromCategories = (categories) => (categories || REQUEST_TICKET_CATEGORIES).reduce((acc, item) => {
  const group = ticketGroupKey(item.techGroup)
  if (!group) return acc
  if (!acc[group]) acc[group] = []
  acc[group].push(item.key)
  return acc
}, {})

export const techCategoryHoldKeysFromCategories = (categories) => (categories || REQUEST_TICKET_CATEGORIES).reduce((acc, item) => {
  if (item?.holdKey) acc[item.key] = item.holdKey
  return acc
}, {})

export const matchedEmailCategorySetFromCategories = (categories) => new Set(
  (categories || REQUEST_TICKET_CATEGORIES).filter(item => item.requiresMatchedEmail).map(item => item.key)
)

export const requiresMatchedEmailForTicketWorkflow = (category, categories = null) => (
  matchedEmailCategorySetFromCategories(categories).has(String(category || ''))
)

export const requiresMatchedEmailForSnow = requiresMatchedEmailForTicketWorkflow

const normalizeGroupValue = (value) => (value || '').trim().toLowerCase()

export const resolveTechTicketCategories = (groupValue, ticketCategories = null) => {
  const normalized = normalizeGroupValue(groupValue)
  if (!normalized) return []
  const parts = normalized.split(/[;,]/).map(part => part.trim()).filter(Boolean)
  const resolvedCategories = new Set()
  parts.forEach(part => {
    const mapped = (ticketCategories ? techTicketGroupsFromCategories(ticketCategories) : TECH_TICKET_GROUPS)[part] || []
    mapped.forEach(entry => resolvedCategories.add(entry))
  })
  return Array.from(resolvedCategories)
}
