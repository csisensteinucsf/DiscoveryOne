// frontend/src/components/BrandLogo.jsx
import { useCallback, useEffect, useState } from 'react'
import { fetchSystemSettings } from '../lib/systemSettingsClient'

const DEFAULT_LOGO = '/img/D1_Logo.png'

export default function BrandLogo({ apiBase = '/api', height = 50 }) {
  const fallback = DEFAULT_LOGO
  const [url, setUrl] = useState(fallback)
  const [errored, setErrored] = useState(false)

  const refresh = useCallback(async ({ force = false } = {}) => {
    try {
      const data = await fetchSystemSettings(apiBase, { force })
      const activeId = data?.active_logo ?? data?.active_logo_id ?? null
      const logos = Array.isArray(data?.logos) ? data.logos : []
      const entry = logos.find((l) => l.id === activeId)
      const explicit = data?.active_logo_url
      setUrl(explicit || (entry ? entry.url : fallback))
      setErrored(false)
    } catch {
      setUrl(fallback)
    }
  }, [apiBase])

  useEffect(() => { refresh() }, [refresh])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const handler = () => { refresh({ force: true }) }
    window.addEventListener('branding:update', handler)
    return () => window.removeEventListener('branding:update', handler)
  }, [refresh])

  return (
    <img
      src={url}
      alt="Logo"
      style={{ height, objectFit: 'contain', display: 'block' }}
      onError={() => {
        if (!errored) {
          setErrored(true)
          setUrl(fallback)
        }
      }}
    />
  )
}
