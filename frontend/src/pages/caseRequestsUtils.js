import {
  HOLD_OPTIONS,
  PRESERVATION_SOURCE_HOLD_MAP,
  holdOptionsFromPreservationSources,
  preservationSourceKey,
} from './preservationCatalog.js'

const TYPE_LABELS = {
  new_case: 'New Matter Request',
  custodian: 'Custodian Update',
  search: 'Search Request',
  close_case: 'Matter Closure Request',
}



const STATUS_COLORS = {
  pending: { bg: '#FEF3C7', fg: '#92400E' },
  approved: { bg: '#DCFCE7', fg: '#166534' },
  declined: { bg: '#FEE2E2', fg: '#991B1B' },
}
const REQUEST_COLLAPSE_KEYS = {
  years: 'caseRequests:collapse:years',
  letters: 'caseRequests:collapse:letters',
  names: 'caseRequests:collapse:names',
}
const CASE_REQUEST_MAX_MB = 5
const CASE_REQUEST_CONSENT_MAX_MB = 5
const DEFAULT_LOOKUP_INPUT_PLACEHOLDER = 'Enter full name, email address or Employee ID to begin person lookup'

const loadStoredSet = (key) => {
  if (typeof window === 'undefined') return new Set()
  try {
    const raw = window.localStorage.getItem(key)
    const parsed = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(parsed) ? parsed.map(String) : [])
  } catch {
    return new Set()
  }
}

const persistStoredSet = (key, value) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(Array.from(value || []).map(String)))
  } catch {
    // Ignore storage failures; collapse state is non-critical UI preference.
  }
}

const hasStoredCollapseState = () => {
  if (typeof window === 'undefined') return false
  return Object.values(REQUEST_COLLAPSE_KEYS).some((key) => window.localStorage.getItem(key) !== null)
}

const ISODate = (value) => {
  if (!value) return ''
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value
    return d.toLocaleString()
  } catch {
    return value
  }
}

const genId = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `tmp_${Math.random().toString(36).slice(2)}`)
const emptySearch = () => ({ keywords: '', senders: '', recipients: '', date_from: '', date_to: '', additional: '' })
const normalizeSearch = (obj = {}) => ({
  keywords: String(obj.keywords || '').trim(),
  senders: String(obj.senders || '').trim(),
  recipients: String(obj.recipients || '').trim(),
  date_from: String(obj.date_from || '').trim(),
  date_to: String(obj.date_to || '').trim(),
  additional: String(obj.additional || '').trim(),
})
const parseAdditionalRequestorEmails = (value) => (
  String(value || '')
    .split(/[\r\n,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)
)
const normalizeGroupValue = (value) => String(value || '').trim().toLowerCase()
const makeCustodian = () => ({
  id: genId(),
  name: '',
  email: '',
  notes: '',
  override_lookup: false,
  override_note: '',
  holds: HOLD_OPTIONS.reduce((acc, [field]) => ({ ...acc, [field]: false }), {}),
  ntp_sent: false,
  ntp_ack: false,
  consent_received: false,
})
const lookupPersonName = (match = {}) => {
  const safe = match || {}
  return [safe.first_name, safe.middle_name, safe.last_name].filter(Boolean).join(' ').trim()
}
const lookupPersonId = (match = {}) => {
  const safe = match || {}
  return safe.employee_id || safe.external_id || safe.person_id || ''
}
const hasSearchDetails = (obj = {}) => Object.values(obj).some((val) => {
  if (typeof val === 'string') return val.trim().length > 0
  return Boolean(val)
})

export {
  TYPE_LABELS,
  HOLD_OPTIONS,
  PRESERVATION_SOURCE_HOLD_MAP,
  preservationSourceKey,
  holdOptionsFromPreservationSources,
  STATUS_COLORS,
  REQUEST_COLLAPSE_KEYS,
  CASE_REQUEST_MAX_MB,
  CASE_REQUEST_CONSENT_MAX_MB,
  DEFAULT_LOOKUP_INPUT_PLACEHOLDER,
  loadStoredSet,
  persistStoredSet,
  hasStoredCollapseState,
  ISODate,
  genId,
  emptySearch,
  normalizeSearch,
  parseAdditionalRequestorEmails,
  normalizeGroupValue,
  makeCustodian,
  lookupPersonName,
  lookupPersonId,
  hasSearchDetails
}

