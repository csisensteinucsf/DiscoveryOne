const SEARCH_EXPORT_PROVIDER_LABELS = Object.freeze({
  none: 'Manual tracking',
  purview: 'Microsoft Purview',
  google_workspace: 'Google Workspace',
})

function normalizeSearchExportProvider(value) {
  const provider = String(value || 'none').trim().toLowerCase()
  return provider || 'none'
}

function searchExportProviderLabel(value) {
  const provider = normalizeSearchExportProvider(value)
  return SEARCH_EXPORT_PROVIDER_LABELS[provider]
    || provider.replace(/_/g, ' ').replace(/\b\w/g, character => character.toUpperCase())
}

function searchExportQueryLabel(value) {
  const provider = normalizeSearchExportProvider(value)
  if (provider === 'purview') return 'KQL query'
  return 'Provider query'
}

function searchExportIsAutomated(value) {
  return normalizeSearchExportProvider(value) !== 'none'
}

export {
  normalizeSearchExportProvider,
  searchExportProviderLabel,
  searchExportQueryLabel,
  searchExportIsAutomated,
}
