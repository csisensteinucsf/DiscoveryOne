const prefersDark = () => {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

export const THEME_OPTIONS = ['light', 'dark', 'system']

export function resolveTheme(pref) {
  const choice = (pref || '').toLowerCase()
  if (choice === 'system') return prefersDark() ? 'dark' : 'light'
  if (choice === 'dark') return 'dark'
  return 'light'
}

export function applyThemePreference(pref) {
  const finalTheme = resolveTheme(pref)
  if (typeof document !== 'undefined') {
    document.body.classList.toggle('theme-dark', finalTheme === 'dark')
    document.documentElement.style.colorScheme = finalTheme === 'dark' ? 'dark' : 'light'
  }
  try {
    localStorage.setItem('branding:theme', pref || 'light')
  } catch {
    /* ignore */
  }
  return finalTheme
}

export function watchSystemTheme(onChange) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {}
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  const handler = () => onChange(resolveTheme('system'))
  mq.addEventListener('change', handler)
  return () => mq.removeEventListener('change', handler)
}
