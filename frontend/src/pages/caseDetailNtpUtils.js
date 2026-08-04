import {
  NTP_NOT_REQUIRED_NON_ORG_REASON,
  NTP_VARIABLE_DEFAULTS,
  isMissingOrUnmatchedEmail,
} from './caseDetailUtils.js'
import { normalizeNtpStatus } from './custodianStatusCatalog.js'

export function normalizePersonLabel(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9@.]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function custodianMatchesClaimant(claimant, custodian) {
  const claim = normalizePersonLabel(claimant)
  if (!claim || claim === 'na' || claim === 'n/a') return false
  const email = normalizePersonLabel(custodian?.email)
  if (claim.includes('@') && email && email === claim) return true
  const name = normalizePersonLabel(custodian?.name)
  if (!name) return false
  return name === claim || (claim.length >= 4 && (name.includes(claim) || claim.includes(name)))
}

export function rememberedNtpReason(payload) {
  if (payload?.exists && typeof payload?.variables?.reason === 'string') return payload.variables.reason
  return NTP_VARIABLE_DEFAULTS.reason
}

export function isNtpBlockedCustodianRecord(custodian) {
  const status = String(custodian?.employment_status || '').trim().toLowerCase()
  const ntpStatus = normalizeNtpStatus(custodian?.ntp_status)
  return status.startsWith('separated') || ntpStatus === 'silent'
}

export function ntpAutoNaReasonForCustodian(claimant, custodian) {
  const status = String(custodian?.employment_status || '').trim().toLowerCase()
  if (status.startsWith('separated')) return 'Separated'
  if (String(custodian?.ntp_not_required_reason || '').trim() === NTP_NOT_REQUIRED_NON_ORG_REASON) return NTP_NOT_REQUIRED_NON_ORG_REASON
  if (custodianMatchesClaimant(claimant, custodian)) return 'Claimant'
  return ''
}

export function ntpNaReasonForCustodian(custodian, autoReason = '') {
  const stored = String(custodian?.ntp_not_required_reason || '').trim()
  if (stored) return stored
  if (autoReason) return autoReason
  const notes = String(custodian?.notes || '').trim()
  if (notes) {
    const match = notes.match(/(?:^|[\r\n])\s*(?:ntp\s*)?na\s*[:\-]\s*([^\r\n]+)/i)
    if (match && match[1]) return match[1].trim().slice(0, 80)
  }
  return ''
}

export function ntpStatusLabelForCustodian(custodian, autoReason = '') {
  const raw = String(custodian?.ntp_status || 'not sent').trim().toLowerCase() || 'not sent'
  if (normalizeNtpStatus(raw) !== 'silent') return raw.toUpperCase()
  const reason = ntpNaReasonForCustodian(custodian, autoReason)
  return reason ? `SILENT (${reason})` : 'SILENT'
}

export function isNtpEmailEligibleCustodian(custodian) {
  const email = String(custodian?.email || '').trim().toLowerCase()
  return email && !isMissingOrUnmatchedEmail(email) && !isNtpBlockedCustodianRecord(custodian)
}

export function buildNtpPayloadVariablesFromForm(ntpVariables) {
  const normalizeEmails = (raw) => (raw || '').split(',').map(addr => addr.trim()).filter(Boolean).join(', ')
  const sanitize = (value) => (value || '').trim()
  return {
    legal_case_name: sanitize(ntpVariables.legal_case_name),
    claimant: sanitize(ntpVariables.claimant),
    reason: sanitize(ntpVariables.reason),
    cc: normalizeEmails(ntpVariables.cc_list || ''),
    outside_counsel1: sanitize(ntpVariables.outside_counsel1),
    outside_counsel2: sanitize(ntpVariables.outside_counsel2),
    outside_counsel3: sanitize(ntpVariables.outside_counsel3),
    outside_counsel_firm: sanitize(ntpVariables.outside_counsel_firm),
  }
}

export function pickNextNtpReminder(reminders = []) {
  if (!Array.isArray(reminders) || reminders.length === 0) return null
  return reminders.reduce((best, current) => {
    if (!best) return current
    const bestTime = Date.parse(best.next_send_at || '')
    const currentTime = Date.parse(current.next_send_at || '')
    if (!Number.isFinite(bestTime)) return current
    if (!Number.isFinite(currentTime)) return best
    return currentTime < bestTime ? current : best
  }, null)
}
