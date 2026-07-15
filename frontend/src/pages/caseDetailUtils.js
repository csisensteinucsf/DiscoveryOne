import {
  HOLD_FAILED_FIELDS,
  HOLD_FIELDS,
  HOLD_META,
  HOLD_PENDING_FIELDS,
  HOLD_RELEASED_FIELDS,
  customHoldSourceKey,
  customPreservationEntry,
  customPreservationPatch,
  holdMetaFromPreservationSources,
  isCustomHoldKey,
  preservationSourceKey,
} from './preservationCatalog.js'
import {
  REQUEST_TICKET_CATEGORIES,
  REQUEST_TICKET_CATEGORY_LOOKUP,
  TECH_CATEGORY_HOLD_KEYS,
  matchedEmailCategorySetFromCategories,
  requiresMatchedEmailForTicketWorkflow,
  resolveTechTicketCategories,
  techCategoryHoldKeysFromCategories,
  ticketCategoriesFromWorkflows,
  ticketCategoryLookupFromCategories,
  ticketWorkflowUsesAccessLogDetails,
} from './ticketWorkflowCatalog.js'

// Display helper: Title/Sentence case for names (handles spaces & hyphens)
function formatNameRaw(s) {
  if (!s) return s
  const parts = String(s).trim().split(/\s+/).map(word => {
    return word
      .split('-')
      .map(seg => (seg ? seg[0].toUpperCase() + seg.slice(1).toLowerCase() : seg))
      .join('-')
  })
  return parts.join(' ')
}
const apiBase = import.meta.env?.VITE_API_BASE || '/api'
const ADMIN_USERNAME = 'admin'
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/i
const isValidEmail = (value) => EMAIL_REGEX.test((value || '').trim())
const DEFAULT_LOOKUP_INPUT_PLACEHOLDER = 'Enter full name, email address or Employee ID to begin person lookup'
const lookupPersonName = (match = {}) => {
  const safe = match || {}
  return [safe.first_name, safe.middle_name, safe.last_name].filter(Boolean).join(' ').trim()
}
const lookupPersonId = (match = {}) => {
  const safe = match || {}
  return safe.employee_id || safe.external_id || safe.person_id || ''
}

const NTP_VARIABLE_DEFAULTS = {
  legal_case_name: '',
  claimant: '',
  reason: 'retaliation',
  cc_list: '',
  outside_counsel1: '',
  outside_counsel2: '',
  outside_counsel3: '',
  outside_counsel_firm: '',
}
const NTP_OUTSIDE_COUNSEL_HISTORY_KEY = 'd1_ntp_outside_counsel_history_v1'
const NTP_OUTSIDE_COUNSEL_HISTORY_LIMIT = 12
function readNtpOutsideCounselHistory() {
  if (typeof window === 'undefined') return { counsel: [], firms: [] }
  try {
    const raw = window.localStorage.getItem(NTP_OUTSIDE_COUNSEL_HISTORY_KEY)
    if (!raw) return { counsel: [], firms: [] }
    const parsed = JSON.parse(raw)
    const counsel = Array.isArray(parsed?.counsel) ? parsed.counsel.map(v => String(v || '').trim()).filter(Boolean) : []
    const firms = Array.isArray(parsed?.firms) ? parsed.firms.map(v => String(v || '').trim()).filter(Boolean) : []
    return { counsel, firms }
  } catch {
    return { counsel: [], firms: [] }
  }
}
function mergeNtpOutsideCounselHistory(current, variables) {
  const next = {
    counsel: Array.isArray(current?.counsel) ? [...current.counsel] : [],
    firms: Array.isArray(current?.firms) ? [...current.firms] : [],
  }
  const seenCounsel = new Set(next.counsel.map(v => v.toLowerCase()))
  const seenFirms = new Set(next.firms.map(v => v.toLowerCase()))
  for (const key of ['outside_counsel1', 'outside_counsel2', 'outside_counsel3']) {
    const value = String(variables?.[key] || '').trim()
    if (!value) continue
    const normalized = value.toLowerCase()
    if (seenCounsel.has(normalized)) continue
    seenCounsel.add(normalized)
    next.counsel.unshift(value)
  }
  const firm = String(variables?.outside_counsel_firm || '').trim()
  if (firm) {
    const normalizedFirm = firm.toLowerCase()
    if (!seenFirms.has(normalizedFirm)) {
      seenFirms.add(normalizedFirm)
      next.firms.unshift(firm)
    }
  }
  return {
    counsel: next.counsel.slice(0, NTP_OUTSIDE_COUNSEL_HISTORY_LIMIT),
    firms: next.firms.slice(0, NTP_OUTSIDE_COUNSEL_HISTORY_LIMIT),
  }
}
function writeNtpOutsideCounselHistory(history) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(NTP_OUTSIDE_COUNSEL_HISTORY_KEY, JSON.stringify(history || { counsel: [], firms: [] }))
  } catch {
    // ignore storage errors
  }
}
const NTP_NOT_REQUIRED_DEFAULT_REASON = 'ntp not required'
const NTP_NOT_REQUIRED_NON_ORG_REASON = 'non-organization email'
const CONSENT_NOT_REQUIRED_DEFAULT_REASON = 'consent not required'
const CONSENT_NOT_REQUIRED_SEPARATED_REASON = 'separated, consent not required'
const CONSENT_NOT_REQUIRED_CLAIMANT_REASON = 'claimant, consent inherently provided'
const blankAccessLogTimeWindow = () => ({ id: uuid(), date: '', start_time: '', end_time: '' })
const isMissingOrUnmatchedEmail = (email) => {
  const normalized = String(email || '').trim().toLowerCase()
  return !normalized || normalized === 'noemail' || normalized === 'unmatched'
}
const isSnowUnmatchedCustodian = (custodian) => {
  if (!custodian) return true
  return !!custodian.person_lookup_overridden || isMissingOrUnmatchedEmail(custodian.email)
}
const normalizeGroupValue = (value) => (value || '').trim().toLowerCase()
const REMINDER_INTERVAL_DEFAULT = 14 // days
const REMINDER_DURATION_DEFAULT = 90 // days
const caseCache = new Map()
const proofCache = new Map()
const consentCache = new Map()
const slaCache = new Map()
const displayUserName = (person, { firstOnly = false } = {}) => {
  if (!person) return ''
  const first = (person.first_name || '').trim()
  const last = (person.last_name || '').trim()
  if (firstOnly) return first || person.username || person.email || ''
  const combined = [first, last].filter(Boolean).join(' ')
  return combined || person.email || person.username || ''
}
const formatDate = (value) => {
  if (!value) return ""
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return value
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(d)
  } catch {
    return value
  }
}
const formatDateTime = (value) => {
  if (!value) return ''
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return ''
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(d)
  } catch {
    return ''
  }
}
const holdDetailStateLabel = (state) => {
  const value = String(state || '').trim().toLowerCase()
  if (value === 'active') return 'Active'
  if (value === 'pending') return 'Pending'
  if (value === 'failed') return 'Failed'
  if (value === 'released') return 'Released'
  if (value === 'off') return 'Off'
  if (value === 'info') return 'Info'
  return value || 'Unknown'
}

const holdDetailStateStyle = (state) => {
  const value = String(state || '').trim().toLowerCase()
  if (value === 'active') return { background: '#dcfce7', color: '#166534', border: '1px solid #86efac' }
  if (value === 'pending') return { background: '#fef9c3', color: '#92400e', border: '1px solid #facc15' }
  if (value === 'failed') return { background: '#fee2e2', color: '#b91c1c', border: '1px solid #fca5a5' }
  if (value === 'released') return { background: '#ede9fe', color: '#6d28d9', border: '1px solid #c4b5fd' }
  if (value === 'off') return { background: '#f1f5f9', color: '#334155', border: '1px solid #cbd5e1' }
  return { background: '#e2e8f0', color: '#334155', border: '1px solid #cbd5e1' }
}

const formatActionLabel = (value) => String(value || '').replace(/_/g, ' ').trim() || '-'

const daysFromNow = (value) => {
  if (!value) return null
  try {
    const end = new Date(value)
    if (Number.isNaN(end.getTime())) return null
    const diff = Math.ceil((end.getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    return Number.isFinite(diff) ? diff : null
  } catch {
    return null
  }
}
const employmentBadges = (custodian) => {
  const end = custodian?.employment_end_date
  if (!end) return []
  const ts = Date.parse(end)
  if (Number.isNaN(ts)) return []
  const now = Date.now()
  if (ts > now) return [] // current
  const days = (now - ts) / (1000 * 60 * 60 * 24)
  if (days < 90) return [{ variant: 'success', label: 'S', title: 'Separated (< 3 months)' }]
  if (days >= 365) return [{ variant: 'danger', label: 'S', title: 'Separated (over 1 year)' }]
  return [{ variant: 'warn', label: 'S', title: 'Separated (< 1 year)' }]
}
const employmentEndDateColor = (custodian) => {
  const badges = employmentBadges(custodian)
  const variant = badges[0]?.variant || ''
  if (variant === 'success') return '#166534'
  if (variant === 'danger') return '#991b1b'
  if (variant === 'warn') return '#92400e'
  return '#475467'
}
const isSeparatedCustodian = (custodian) => {
  const status = String(custodian?.employment_status || '').trim().toLowerCase()
  if (status.startsWith('separated')) return true
  const end = String(custodian?.employment_end_date || '').trim()
  if (!end) return false
  const ts = Date.parse(end)
  return Number.isFinite(ts) && ts <= Date.now()
}
const separatedStatusLabel = (custodian) => {
  if (!isSeparatedCustodian(custodian)) return 'NO'
  const end = String(custodian?.employment_end_date || '').trim()
  if (!end) return 'YES'
  const ts = Date.parse(end)
  if (!Number.isFinite(ts) || ts > Date.now()) return 'NO'
  const days = (Date.now() - ts) / (1000 * 60 * 60 * 24)
  if (days < 90) return 'less than 3 months'
  if (days >= 365) return 'more than 1 year'
  return 'less than 1 year'
}
const normalizeClaimantLabel = (value) => {
  const text = String(value || '').trim().toLowerCase()
  if (!text) return ''
  return text
    .replace(/[^a-z0-9@]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
const claimantMatchesCustodian = (claimant, custodian) => {
  const claim = normalizeClaimantLabel(claimant)
  if (!claim || claim === 'na' || claim === 'n a') return false
  const emailNorm = normalizeClaimantLabel(custodian?.email || '')
  if (claim.includes('@') && emailNorm && emailNorm === claim) return true
  const nameNorm = normalizeClaimantLabel(custodian?.name || '')
  if (!nameNorm) return false
  if (nameNorm === claim) return true
  if (claim.length >= 4 && (claim.includes(nameNorm) || nameNorm.includes(claim))) return true
  return false
}
const consentNotRequiredAutoReason = (claimant, custodian, { forceClaimant = false } = {}) => {
  if (isSeparatedCustodian(custodian)) return CONSENT_NOT_REQUIRED_SEPARATED_REASON
  if (forceClaimant || claimantMatchesCustodian(claimant, custodian)) return CONSENT_NOT_REQUIRED_CLAIMANT_REASON
  return ''
}
const formatFileSize = (bytes) => {
  const size = Number(bytes)
  if (!Number.isFinite(size) || size < 0) return ''
  if (size < 1024) return `${size} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let idx = 0
  let value = size / 1024
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value.toFixed(value >= 10 ? 0 : 1)} ${units[idx]}`
}

const sessionStore = (() => {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage
  } catch {
    return null
  }
})()
const REQUESTOR_CACHE_KEY = 'requestors'
function readSessionJSON(key, fallback){
  if (!sessionStore) return fallback
  try {
    const raw = sessionStore.getItem(key)
    if (raw === null || raw === undefined || raw === '') return fallback
    return JSON.parse(raw)
  } catch {
    return fallback
  }
}
function writeSessionJSON(key, value){
  if (!sessionStore) return
  try {
    sessionStore.setItem(key, JSON.stringify(value))
  } catch {
    /* ignore storage failures */
  }
}
// ---------- Searches local storage ----------
function lsKeyForSearches(caseId){ return `ediscovery:case:${caseId}:searches` }
function loadSearches(caseId){
  const parsed = readSessionJSON(lsKeyForSearches(caseId), [])
  return Array.isArray(parsed) ? parsed : []
}
function saveSearches(caseId,arr){ writeSessionJSON(lsKeyForSearches(caseId), arr || []) }
function nextSearchNumber(caseName, searches){
  const rawCase = (caseName || '').trim()
  if (!rawCase) return 1
  const escaped = rawCase.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')
  const patterns = [
    new RegExp(`^${escaped}-Search\\s+(\\d+)$`, 'i'),
    new RegExp(`^${escaped}\\s+Search\\s+(\\d+)$`, 'i'),
    new RegExp(`^${escaped}-Search\\s*(\\d+)$`, 'i'),
  ]
  const nums = (searches||[]).map(s => {
    const name = String(s?.name || '').trim()
    for (const re of patterns) {
      const m = name.match(re)
      if (m) {
        const n = parseInt(m[1], 10)
        return Number.isFinite(n) ? n : 0
      }
    }
    return 0
  })
  return (nums.length ? Math.max(...nums) : 0) + 1
}
function uuid(){ return (crypto?.randomUUID && crypto.randomUUID()) || ('id_' + Math.random().toString(36).slice(2)) }
function normalizeTicketEntriesForState(entries){
  if (!Array.isArray(entries)) return []
  return entries.map((entry, index) => {
    const safe = (entry && typeof entry === 'object') ? { ...entry } : {}
    const category = REQUEST_TICKET_CATEGORY_LOOKUP[safe.category] ? safe.category : REQUEST_TICKET_CATEGORIES[0].key
    let custodianId = safe.custodian_id
    if (custodianId !== null && custodianId !== undefined) {
      const parsed = Number(custodianId)
      custodianId = Number.isFinite(parsed) ? parsed : null
    } else {
      custodianId = null
    }
    const extras = {}
    for (const key of [
      'created_at',
      'ticket_status',
      'status',
      'assigned_to_display',
      'assigned_to_sys_id',
      'assigned_to',
      'assigned_to_email',
      'sys_id',
      'last_status',
      'last_checked_at',
      'bulk_custodians',
      'assignment_email_sent',
    ]) {
      const value = safe[key]
      if (value === undefined || value === null) continue
      extras[key] = typeof value === 'string' ? value.trim() : value
    }
    return {
      ...safe,
      ...extras,
      id: safe.id || `req-${category}-${index}-${uuid()}`,
      category,
      ticket: (safe.ticket || '').trim(),
      custodian_id: custodianId,
      custodian_name: (safe.custodian_name || '').trim(),
      custodian_email: (safe.custodian_email || '').trim(),
      access_log_time_windows: normalizeAccessLogTimeWindows(safe.access_log_time_windows),
      access_log_employee_id: (safe.access_log_employee_id || '').trim(),
      access_log_request_notes: (safe.access_log_request_notes || '').trim(),
      sys_id: (safe.sys_id || '').trim(),
      status: (safe.status || '').trim(),
    }
  })
}
function deriveRequestEntriesFromCase(caseData){
  if (!caseData) return []
  if (Array.isArray(caseData.request_ticket_entries) && caseData.request_ticket_entries.length) {
    return normalizeTicketEntriesForState(caseData.request_ticket_entries)
  }
  const legacy = []
  for (const meta of REQUEST_TICKET_CATEGORIES) {
    const value = (caseData?.[meta.legacyKey] || '').trim()
    if (value) {
      legacy.push({
        id: `legacy-${meta.key}-${uuid()}`,
        category: meta.key,
        ticket: value,
        custodian_id: null,
        custodian_name: '',
        custodian_email: '',
      })
    }
  }
  return normalizeTicketEntriesForState(legacy)
}
function prepareEntriesForSave(entries){
  const normalized = normalizeTicketEntriesForState(Array.isArray(entries) ? entries : [])
  return normalized.map(entry => {
    const base = {
      id: entry.id || uuid(),
      category: REQUEST_TICKET_CATEGORY_LOOKUP[entry.category] ? entry.category : REQUEST_TICKET_CATEGORIES[0].key,
      ticket: (entry.ticket || '').trim(),
      custodian_id: entry.custodian_id ?? null,
      custodian_name: (entry.custodian_name || '').trim() || null,
      custodian_email: (entry.custodian_email || '').trim() || null,
      assignment_email_sent: !!entry.assignment_email_sent,
    }
    const extras = {}
    for (const [key, value] of Object.entries(entry || {})) {
      if (['id', 'category', 'ticket', 'custodian_id', 'custodian_name', 'custodian_email'].includes(key)) {
        continue
      }
      if (value === undefined) continue
      extras[key] = typeof value === 'string' ? value.trim() : value
    }
    return { ...base, ...extras }
  })
}
function primaryCustodian(entry) {
  if (!entry) return { name: '', email: '' }
  const bulk = Array.isArray(entry.bulk_custodians) ? entry.bulk_custodians : []
  const firstBulk = bulk.find(c => (c?.email || c?.name))
  if (firstBulk) {
    return { name: (firstBulk.name || '').trim(), email: (firstBulk.email || '').trim() }
  }
  return {
    name: (entry.custodian_name || '').trim(),
    email: (entry.custodian_email || '').trim(),
  }
}
function workflowUsesAccessLogDetailsStatic(entryOrCategory) {
  if (typeof entryOrCategory === 'string') {
    return ticketWorkflowUsesAccessLogDetails(REQUEST_TICKET_CATEGORY_LOOKUP[entryOrCategory])
  }
  return ticketWorkflowUsesAccessLogDetails(entryOrCategory)
}
function normalizeAccessLogTimeWindows(windows) {
  if (!Array.isArray(windows)) return []
  return windows.map((window, index) => ({
    id: window?.id || `access-log-window-${index}-${uuid()}`,
    date: String(window?.date || '').trim(),
    start_time: String(window?.start_time || '').trim(),
    end_time: String(window?.end_time || '').trim(),
  }))
}
function entryAccessLogTimeWindows(entry) {
  const normalized = normalizeAccessLogTimeWindows(entry?.access_log_time_windows)
  return normalized.length ? normalized : [blankAccessLogTimeWindow()]
}

export {
  formatNameRaw,
  apiBase,
  ADMIN_USERNAME,
  isValidEmail,
  DEFAULT_LOOKUP_INPUT_PLACEHOLDER,
  lookupPersonName,
  lookupPersonId,
  HOLD_FIELDS,
  HOLD_PENDING_FIELDS,
  HOLD_FAILED_FIELDS,
  HOLD_RELEASED_FIELDS,
  HOLD_META,
  holdMetaFromPreservationSources,
  preservationSourceKey,
  isCustomHoldKey,
  customHoldSourceKey,
  customPreservationEntry,
  customPreservationPatch,
  NTP_VARIABLE_DEFAULTS,
  readNtpOutsideCounselHistory,
  mergeNtpOutsideCounselHistory,
  writeNtpOutsideCounselHistory,
  NTP_NOT_REQUIRED_DEFAULT_REASON,
  NTP_NOT_REQUIRED_NON_ORG_REASON,
  CONSENT_NOT_REQUIRED_DEFAULT_REASON,
  CONSENT_NOT_REQUIRED_SEPARATED_REASON,
  CONSENT_NOT_REQUIRED_CLAIMANT_REASON,
  REQUEST_TICKET_CATEGORIES,
  ticketCategoriesFromWorkflows,
  ticketCategoryLookupFromCategories,
  techCategoryHoldKeysFromCategories,
  matchedEmailCategorySetFromCategories,
  blankAccessLogTimeWindow,
  TECH_CATEGORY_HOLD_KEYS,
  isMissingOrUnmatchedEmail,
  requiresMatchedEmailForTicketWorkflow,
  isSnowUnmatchedCustodian,
  normalizeGroupValue,
  resolveTechTicketCategories,
  REMINDER_INTERVAL_DEFAULT,
  REMINDER_DURATION_DEFAULT,
  REQUEST_TICKET_CATEGORY_LOOKUP,
  caseCache,
  proofCache,
  consentCache,
  slaCache,
  displayUserName,
  formatDate,
  formatDateTime,
  holdDetailStateLabel,
  holdDetailStateStyle,
  formatActionLabel,
  daysFromNow,
  employmentBadges,
  employmentEndDateColor,
  isSeparatedCustodian,
  separatedStatusLabel,
  claimantMatchesCustodian,
  consentNotRequiredAutoReason,
  formatFileSize,
  REQUESTOR_CACHE_KEY,
  readSessionJSON,
  writeSessionJSON,
  loadSearches,
  saveSearches,
  nextSearchNumber,
  uuid,
  normalizeTicketEntriesForState,
  deriveRequestEntriesFromCase,
  prepareEntriesForSave,
  primaryCustodian,
  workflowUsesAccessLogDetailsStatic,
  normalizeAccessLogTimeWindows,
  entryAccessLogTimeWindows
}

