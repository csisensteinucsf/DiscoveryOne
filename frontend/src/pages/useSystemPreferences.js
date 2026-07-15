import { useEffect, useState } from 'react'

function storedTheme() {
  try { return localStorage.getItem('branding:theme') || 'light' } catch { return 'light' }
}

export function useSystemPreferences({ apiBase, user, refreshUser, showToast }) {
  const [userTheme, setUserTheme] = useState(user?.theme || user?.user_theme || storedTheme())
  const [themeSaving, setThemeSaving] = useState(false)
  const [caseSortMode, setCaseSortMode] = useState(user?.case_sort_mode || 'ediscovery')
  const [caseSortSaving, setCaseSortSaving] = useState(false)

  useEffect(() => {
    setUserTheme(user?.theme || user?.user_theme || storedTheme())
    setCaseSortMode(user?.case_sort_mode || 'ediscovery')
  }, [user])

  const updateThemePreference = async (next) => {
    const previous = userTheme
    setUserTheme(next)
    setThemeSaving(true)
    try {
      const res = await fetch(`${apiBase}/auth/preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ theme: next }),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Unable to update theme.')
      }
      await refreshUser()
      showToast('Theme preference saved.', { variant: 'success' })
    } catch (err) {
      console.error(err)
      setUserTheme(previous)
      showToast(err?.message || 'Unable to update theme.', { variant: 'error' })
    } finally {
      setThemeSaving(false)
    }
  }

  const updateCaseSortPreference = async (next) => {
    const previous = caseSortMode
    setCaseSortMode(next)
    setCaseSortSaving(true)
    try {
      const res = await fetch(`${apiBase}/auth/preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ case_sort_mode: next }),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Unable to update case sort preference.')
      }
      await refreshUser()
      showToast('Case sort preference saved.', { variant: 'success' })
    } catch (err) {
      console.error(err)
      setCaseSortMode(previous)
      showToast(err?.message || 'Unable to update case sort preference.', { variant: 'error' })
    } finally {
      setCaseSortSaving(false)
    }
  }

  return {
    userTheme,
    themeSaving,
    updateThemePreference,
    caseSortMode,
    caseSortSaving,
    updateCaseSortPreference,
  }
}