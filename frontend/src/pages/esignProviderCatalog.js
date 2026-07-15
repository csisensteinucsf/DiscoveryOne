export const ESIGN_PROVIDER_LABELS = {
  docusign: 'DocuSign',
}

export function normalizeEsignProvider(value) {
  return String(value || 'none').trim().toLowerCase() || 'none'
}

export function esignProviderLabel(value, fallback = 'e-signature provider') {
  const provider = normalizeEsignProvider(value)
  return ESIGN_PROVIDER_LABELS[provider] || fallback
}

export function esignRequestLabel(value) {
  return 'request'
}
