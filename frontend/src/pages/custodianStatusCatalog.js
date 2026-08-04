export const NTP_STATUS_OPTIONS = [
  { value: 'silent', label: 'Silent' },
  { value: 'not sent', label: 'Not sent' },
  { value: 'sent', label: 'Sent' },
  { value: 'acknowledged', label: 'ACK' },
]

export const CONSENT_STATUS_OPTIONS = [
  { value: 'implied', label: 'Implied' },
  { value: 'not sent', label: 'Not sent' },
  { value: 'sent', label: 'Sent' },
  { value: 'received', label: 'Received' },
]

export function normalizeNtpStatus(value) {
  const status = String(value || 'not sent').trim().toLowerCase()
  return status === 'na' ? 'silent' : status
}

export function normalizeConsentStatus(value) {
  const status = String(value || 'not sent').trim().toLowerCase()
  return status === 'na' ? 'implied' : status
}

export function ntpStatusLabel(value) {
  const status = normalizeNtpStatus(value)
  return NTP_STATUS_OPTIONS.find(option => option.value === status)?.label || status
}

export function consentStatusLabel(value) {
  const status = normalizeConsentStatus(value)
  if (status === 'awoc') return 'AWOC'
  return CONSENT_STATUS_OPTIONS.find(option => option.value === status)?.label || status
}

export function isConsentComplete(value) {
  return ['received', 'implied', 'awoc'].includes(normalizeConsentStatus(value))
}

export function isConsentUnavailableForRequest(value) {
  return isConsentComplete(value)
}
