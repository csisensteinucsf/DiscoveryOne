import { useEffect, useState } from 'react'
import { fetchSystemSettings, invalidateSystemSettingsCache } from '../lib/systemSettingsClient'

const STORAGE_KEY = 'branding:theme'
const THEMES = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'Match device' },
]

export default function ThemeToggle({ apiBase = '/api' }) {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light'
    return window.localStorage?.getItem(STORAGE_KEY) || 'light'
  })
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let abort = false
    const fetchPref = async () => {
      try {
        const data = await fetchSystemSettings(apiBase)
        if (abort) return
        const next = data?.user_theme || data?.active_theme || 'light'
        setTheme(next)
      } catch {
        // ignore
      }
    }
    fetchPref()
    return () => { abort = true }
  }, [apiBase])

  const applyTheme = async (next) => {
    if (busy || theme === next) return
    const prev = theme
    setTheme(next)
    setBusy(true)
    try {
      const res = await fetch(`${apiBase}/system/theme`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ theme: next }),
      })
      if (!res.ok) throw new Error('Theme update failed')
      if (typeof window !== 'undefined') {
        invalidateSystemSettingsCache(apiBase)
        window.localStorage?.setItem(STORAGE_KEY, next)
        window.dispatchEvent(new Event('branding:update'))
      }
    } catch (err) {
      console.error(err)
      setTheme(prev)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ padding: '0 16px', marginTop: 12 }}>
      <div style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--muted)' }}>Display</div>
      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
        {THEMES.map((opt) => (
          <button
            key={opt.id}
            className="btn secondary"
            type="button"
            onClick={() => applyTheme(opt.id)}
            disabled={busy}
            style={{
              flex: 1,
              borderRadius: 999,
              background: theme === opt.id ? 'var(--brand)' : 'transparent',
              color: theme === opt.id ? 'var(--brand-contrast)' : 'var(--link)',
              border: theme === opt.id ? '1px solid var(--brand)' : '1px solid var(--border)',
              fontWeight: theme === opt.id ? 600 : 500,
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}
