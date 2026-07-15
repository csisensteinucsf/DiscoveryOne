export const HOLD_OPTIONS = [
  ['email', 'Email'],
  ['onedrive', 'OneDrive'],
  ['gdrive', 'Google Drive'],
  ['box', 'Box'],
  ['slack', 'Slack'],
  ['rubrik_restore', 'Rubrik Restore'],
]

export const HOLD_META = [
  { key: 'holds_email', label: 'Email' },
  { key: 'holds_onedrive', label: 'OneDrive' },
  { key: 'holds_gdrive', label: 'Google Drive' },
  { key: 'holds_box', label: 'Box' },
  { key: 'holds_slack', label: 'Slack' },
  { key: 'holds_rubrik_restore', label: 'Rubrik Restore' },
]

export const HOLD_FIELDS = HOLD_META.map(item => item.key)
export const HOLD_PENDING_FIELDS = HOLD_FIELDS.map(key => `${key}_pending`)
export const HOLD_FAILED_FIELDS = HOLD_FIELDS.map(key => `${key}_failed`)
export const HOLD_RELEASED_FIELDS = HOLD_FIELDS.map(key => `${key}_released`)

export const PRESERVATION_SOURCE_HOLD_MAP = {
  email: { requestKey: 'email', holdKey: 'holds_email', label: 'Email' },
  mail: { requestKey: 'email', holdKey: 'holds_email', label: 'Email' },
  o365: { requestKey: 'email', holdKey: 'holds_email', label: 'Email' },
  google_mail: { requestKey: 'email', holdKey: 'holds_email', label: 'Email' },
  gmail: { requestKey: 'email', holdKey: 'holds_email', label: 'Email' },
  onedrive: { requestKey: 'onedrive', holdKey: 'holds_onedrive', label: 'OneDrive' },
  one_drive: { requestKey: 'onedrive', holdKey: 'holds_onedrive', label: 'OneDrive' },
  gdrive: { requestKey: 'gdrive', holdKey: 'holds_gdrive', label: 'Google Drive' },
  google_drive: { requestKey: 'gdrive', holdKey: 'holds_gdrive', label: 'Google Drive' },
  drive: { requestKey: 'gdrive', holdKey: 'holds_gdrive', label: 'Google Drive' },
  box: { requestKey: 'box', holdKey: 'holds_box', label: 'Box' },
  slack: { requestKey: 'slack', holdKey: 'holds_slack', label: 'Slack' },
  rubrik: { requestKey: 'rubrik_restore', holdKey: 'holds_rubrik_restore', label: 'Rubrik Restore' },
  rubrik_restore: { requestKey: 'rubrik_restore', holdKey: 'holds_rubrik_restore', label: 'Rubrik Restore' },
  rubrik_restores: { requestKey: 'rubrik_restore', holdKey: 'holds_rubrik_restore', label: 'Rubrik Restore' },
}

export const preservationSourceKey = (value) => String(value || '')
  .trim()
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, '_')
  .replace(/^_+|_+$/g, '')

const defaultRequestHoldOptions = () => HOLD_OPTIONS.filter(([field]) => field !== 'rubrik_restore')
const defaultHoldMeta = () => HOLD_META.filter(item => item.key !== 'holds_rubrik_restore')

export function holdOptionsFromPreservationSources(sources) {
  if (!Array.isArray(sources) || !sources.length) return defaultRequestHoldOptions()
  const seen = new Set()
  const out = []
  sources.forEach(source => {
    if (!source || source.enabled === false) return
    const sourceKey = preservationSourceKey(source.key || source.label)
    const mapped = PRESERVATION_SOURCE_HOLD_MAP[sourceKey] || PRESERVATION_SOURCE_HOLD_MAP[preservationSourceKey(source.label)]
    const field = mapped ? mapped.requestKey : `custom:${sourceKey}`
    const label = source.label || (mapped ? mapped.label : sourceKey.replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase()))
    if (!field || seen.has(field)) return
    seen.add(field)
    out.push([field, label])
  })
  return out.length ? out : defaultRequestHoldOptions()
}

export function holdMetaFromPreservationSources(sources) {
  if (!Array.isArray(sources) || !sources.length) return defaultHoldMeta()
  const seen = new Set()
  const out = []
  sources.forEach(source => {
    if (!source || source.enabled === false) return
    const sourceKey = preservationSourceKey(source.key || source.label)
    const mapped = PRESERVATION_SOURCE_HOLD_MAP[sourceKey] || PRESERVATION_SOURCE_HOLD_MAP[preservationSourceKey(source.label)]
    const item = mapped
      ? { key: mapped.holdKey, label: source.label || mapped.label, custom: false }
      : { key: `custom:${sourceKey}`, source_key: sourceKey, label: source.label || sourceKey.replace(/_/g, ' ').replace(/\b\w/g, ch => ch.toUpperCase()), custom: true }
    if (!item.source_key) item.source_key = sourceKey
    if (!item.key || seen.has(item.key)) return
    seen.add(item.key)
    out.push(item)
  })
  return out.length ? out : defaultHoldMeta()
}

export const isCustomHoldKey = (key) => String(key || '').startsWith('custom:')
export const customHoldSourceKey = (key) => String(key || '').replace(/^custom:/, '')

export function customPreservationEntry(custodian, fieldKey) {
  const sourceKey = customHoldSourceKey(fieldKey)
  return (Array.isArray(custodian?.custom_preservation) ? custodian.custom_preservation : [])
    .find(item => preservationSourceKey(item?.source_key || item?.key || item?.source_label) === sourceKey) || null
}

export function customPreservationPatch(custodian, fieldKey, statePatch, label) {
  const sourceKey = customHoldSourceKey(fieldKey)
  const existing = Array.isArray(custodian?.custom_preservation) ? custodian.custom_preservation : []
  const byKey = new Map(existing.map(item => [preservationSourceKey(item?.source_key || item?.key || item?.source_label), item]))
  const current = byKey.get(sourceKey) || { source_key: sourceKey, source_label: label || sourceKey }
  byKey.set(sourceKey, {
    source_key: sourceKey,
    source_label: current.source_label || label || sourceKey,
    active: !!statePatch.active,
    pending: !!statePatch.pending,
    failed: !!statePatch.failed,
    released: !!statePatch.released,
  })
  return Array.from(byKey.values())
}
const PRESERVATION_PROVIDER_LABELS = Object.freeze({
  none: 'Manual tracking',
  purview: 'Microsoft Purview',
  google_workspace: 'Google Workspace',
})

export function preservationProviderLabel(value) {
  const provider = String(value || 'none').trim().toLowerCase() || 'none'
  return PRESERVATION_PROVIDER_LABELS[provider]
    || provider.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
}
