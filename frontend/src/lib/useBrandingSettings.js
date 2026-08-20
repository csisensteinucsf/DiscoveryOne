import { useCallback, useEffect, useState } from 'react'
import { fetchSystemSettings } from './systemSettingsClient.js'

const DEFAULT_BRANDING = {
  appName: 'DiscoveryOne',
  appTagline: 'eDiscovery Matter Manager',
}

function normalizeBranding(data) {
  const branding = data?.branding || {}
  return {
    appName: String(branding.app_name || data?.app_name || DEFAULT_BRANDING.appName).trim() || DEFAULT_BRANDING.appName,
    appTagline: String(branding.app_tagline || data?.app_tagline || DEFAULT_BRANDING.appTagline).trim(),
  }
}

export function useBrandingSettings(apiBase = '/api', { updateTitle = false, titleSuffix = '' } = {}) {
  const [branding, setBranding] = useState(DEFAULT_BRANDING)

  const refresh = useCallback(async ({ force = false } = {}) => {
    try {
      const data = await fetchSystemSettings(apiBase, { force })
      setBranding(normalizeBranding(data))
    } catch {
      setBranding(DEFAULT_BRANDING)
    }
  }, [apiBase])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handler = () => refresh({ force: true })
    window.addEventListener('branding:update', handler)
    return () => window.removeEventListener('branding:update', handler)
  }, [refresh])

  useEffect(() => {
    if (!updateTitle || typeof document === 'undefined') return
    document.title = titleSuffix ? `${branding.appName} ${titleSuffix}` : branding.appName
  }, [branding.appName, titleSuffix, updateTitle])

  return branding
}
