// frontend/src/components/BrandingBoot.jsx
import { useEffect } from 'react'
import { applyThemePreference } from '../lib/theme.js'

export default function BrandingBoot() {
  useEffect(() => {
    let stored = 'light'
    try {
      stored = localStorage.getItem('branding:theme') || 'light'
    } catch {
      stored = 'light'
    }
    applyThemePreference(stored)
    if (stored === 'system' && typeof window !== 'undefined') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      const handler = () => applyThemePreference('system')
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
    return undefined
  }, [])
  return null
}
