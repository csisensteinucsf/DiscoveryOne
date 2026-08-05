import { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { AUTH_EXPIRED_EVENT, AUTH_SYNC_CHANNEL, AUTH_SYNC_STORAGE_KEY } from './lib/apiClient.js'

const BRANDING_EVENT = 'branding:update'
const emitBrandingUpdate = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(BRANDING_EVENT))
  }
}

const AUTH_TAB_ID = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
  ? crypto.randomUUID()
  : `${Date.now()}-${Math.random()}`

function publishAuthClear(reason) {
  if (typeof window === 'undefined') return
  const payload = { type: 'clear', reason, source: AUTH_TAB_ID, at: Date.now() }
  try {
    window.localStorage.setItem(AUTH_SYNC_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // Storage can be disabled; BroadcastChannel remains the primary path.
  }
  if (typeof window.BroadcastChannel === 'function') {
    try {
      const channel = new window.BroadcastChannel(AUTH_SYNC_CHANNEL)
      channel.postMessage(payload)
      channel.close()
    } catch {
      // The current tab is still cleared even when cross-tab messaging fails.
    }
  }
}

const normalizeUser = (payload) => {
  if (!payload) return null
  const role = payload.role || (payload.is_admin ? 'sys_admin' : 'analyst')
  const theme = payload.user_theme || payload.theme || 'light'
  const case_sort_mode = payload.case_sort_mode || 'ediscovery'
  return {
    username: payload.username,
    first_name: payload.first_name || '',
    last_name: payload.last_name || '',
    is_admin: payload.is_admin,
    role,
    email: payload.email || null,
    id: payload.id,
    requestor_group: payload.requestor_group || '',
    employee_id: payload.employee_id || '',
    last_login: payload.last_login || null,
    user_theme: theme,
    theme,
    case_sort_mode,
    ui_preferences: payload.ui_preferences && typeof payload.ui_preferences === 'object' ? payload.ui_preferences : {},
    auth_provider: payload.auth_provider || 'local',
    local_password_login_allowed: payload.local_password_login_allowed !== false,
  }
}

const AuthCtx = createContext(null)

export function AuthProvider({ apiBase, children }) {
  const navigate = useNavigate()
  const [user, setUser] = useState(null)
  const userRef = useRef(null)
  const expiryHandledRef = useRef(false)
  const [loading, setLoading] = useState(true)
  const [authConfig, setAuthConfig] = useState({
    sso_enabled: false,
    sso_configured: false,
    sso_login_url: null,
    sso_logout_url: null,
    sso_display_name: 'Single sign-on',
    institution: {
      org_name: '',
      org_short_name: '',
      allowed_requestor_email_domains: [],
      employee_id_label: 'Employee ID',
      support_email: '',
    },
    local_password_admin_only: false,
  })
  const [setupStatus, setSetupStatus] = useState({
    completed: true,
    required: false,
    has_sys_admin: true,
  })

  useEffect(() => {
    userRef.current = user
  }, [user])

  const clearBrowserAuth = useCallback((reason = 'logout', { broadcast = true, redirect = true } = {}) => {
    userRef.current = null
    setUser(null)
    emitBrandingUpdate()
    if (broadcast) publishAuthClear(reason)
    if (!redirect || typeof window === 'undefined') return

    const expired = reason === 'expired'
    const target = expired ? '/login?reason=expired' : '/login'
    const currentPath = `${window.location.pathname}${window.location.search}`
    if (currentPath === target) return
    const from = window.location.pathname !== '/login'
      ? { pathname: window.location.pathname, search: window.location.search }
      : undefined
    navigate(target, { replace: true, state: from ? { from } : undefined })
  }, [navigate])

  useEffect(() => {
    const expireCurrentSession = () => {
      if (!userRef.current || expiryHandledRef.current) return
      expiryHandledRef.current = true
      void fetch(`${apiBase}/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {})
      clearBrowserAuth('expired')
    }
    const consumeSync = (payload) => {
      if (!payload || payload.type !== 'clear' || payload.source === AUTH_TAB_ID) return
      expiryHandledRef.current = payload.reason === 'expired'
      clearBrowserAuth(payload.reason === 'expired' ? 'expired' : 'logout', { broadcast: false })
    }
    const onStorage = (event) => {
      if (event.key !== AUTH_SYNC_STORAGE_KEY || !event.newValue) return
      try {
        consumeSync(JSON.parse(event.newValue))
      } catch {
        // Ignore malformed cross-tab messages.
      }
    }

    window.addEventListener(AUTH_EXPIRED_EVENT, expireCurrentSession)
    window.addEventListener('storage', onStorage)
    let channel = null
    if (typeof window.BroadcastChannel === 'function') {
      try {
        channel = new window.BroadcastChannel(AUTH_SYNC_CHANNEL)
        channel.addEventListener('message', (event) => consumeSync(event.data))
      } catch {
        channel = null
      }
    }
    return () => {
      window.removeEventListener(AUTH_EXPIRED_EVENT, expireCurrentSession)
      window.removeEventListener('storage', onStorage)
      channel?.close()
    }
  }, [apiBase, clearBrowserAuth])

  const refreshSetupStatus = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/setup/status`, { credentials: 'include' })
      if (!res.ok) throw new Error('setup_status_failed')
      const data = await res.json()
      const next = {
        completed: data?.completed !== false,
        required: !!data?.required,
        has_sys_admin: data?.has_sys_admin !== false,
        completed_at: data?.completed_at || null,
      }
      setSetupStatus(next)
      return next
    } catch {
      const fallback = { completed: true, required: false, has_sys_admin: true }
      setSetupStatus(fallback)
      return fallback
    }
  }, [apiBase])

  const refreshAuthConfig = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/auth/config`, { credentials: 'include' })
      if (!res.ok) throw new Error('auth_config_failed')
      const data = await res.json()
      setAuthConfig({
        sso_enabled: !!data?.sso_enabled,
        sso_configured: !!data?.sso_configured,
        sso_login_url: data?.sso_login_url || null,
        sso_logout_url: data?.sso_logout_url || null,
        sso_display_name: data?.sso_display_name || 'Single sign-on',
        institution: {
          org_name: data?.institution?.org_name || '',
          org_short_name: data?.institution?.org_short_name || '',
          allowed_requestor_email_domains: Array.isArray(data?.institution?.allowed_requestor_email_domains) ? data.institution.allowed_requestor_email_domains : [],
          employee_id_label: data?.institution?.employee_id_label || 'Employee ID',
          support_email: data?.institution?.support_email || '',
        },
        local_password_admin_only: !!data?.local_password_admin_only,
      })
      return data
    } catch {
      const fallback = {
        sso_enabled: false,
        sso_configured: false,
        sso_login_url: null,
        sso_logout_url: null,
        sso_display_name: 'Single sign-on',
        institution: {
          org_name: '',
          org_short_name: '',
          allowed_requestor_email_domains: [],
          employee_id_label: 'Employee ID',
          support_email: '',
        },
        local_password_admin_only: false,
      }
      setAuthConfig(fallback)
      return fallback
    }
  }, [apiBase])

  const refreshUser = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/auth/me`, { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        const normalized = normalizeUser(data)
        userRef.current = normalized
        expiryHandledRef.current = false
        setUser(normalized)
        emitBrandingUpdate()
        return data
      }
      userRef.current = null
      setUser(null)
      return null
    } catch {
      userRef.current = null
      setUser(null)
      return null
    }
  }, [apiBase])

  useEffect(() => {
    (async () => {
      try {
        await Promise.all([refreshSetupStatus(), refreshAuthConfig(), refreshUser()])
      } finally {
        setLoading(false)
      }
    })()
  }, [refreshAuthConfig, refreshSetupStatus, refreshUser])

  const login = async (username, password) => {
    const form = new URLSearchParams()
    form.set('username', username)
    form.set('password', password)
    const res = await fetch(`${apiBase}/auth/token`, {
      method: 'POST',
      body: form,
      credentials: 'include',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    })
    if (!res.ok) {
      let message = 'Invalid credentials'
      try {
        const data = await res.json()
        if (typeof data?.detail === 'string' && data.detail.trim()) message = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(message)
    }
    const data = await res.json()
    if (!data?.mfa_required) {
      const normalized = normalizeUser(data.user)
      userRef.current = normalized
      expiryHandledRef.current = false
      setUser(normalized)
      emitBrandingUpdate()
    }
    return data
  }

  const verifyMfa = async (mfaToken, code, rememberBrowser = false) => {
    const res = await fetch(`${apiBase}/auth/mfa/verify`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mfa_token: mfaToken, code, remember_browser: !!rememberBrowser }),
    })
    if (!res.ok) {
      let message = 'Invalid verification code'
      try {
        const data = await res.json()
        if (typeof data?.detail === 'string' && data.detail.trim()) message = data.detail
      } catch {
        /* ignore */
      }
      throw new Error(message)
    }
    const data = await res.json()
    const normalized = normalizeUser(data.user)
    userRef.current = normalized
    expiryHandledRef.current = false
    setUser(normalized)
    emitBrandingUpdate()
    return data
  }

  const beginSsoLogin = (nextPath = '/') => {
    const target = `${apiBase}/auth/oidc/login?next=${encodeURIComponent(nextPath || '/')}`
    window.location.assign(target)
  }

  const logout = async (nextPath = '/login') => {
    const normalizedNext = nextPath || '/login'
    if (authConfig?.sso_enabled && user?.auth_provider === 'sso') {
      clearBrowserAuth('logout', { redirect: false })
      window.location.assign(`${apiBase}/auth/oidc/logout?next=${encodeURIComponent(normalizedNext)}`)
      return { redirected: true }
    }
    try {
      await fetch(`${apiBase}/auth/logout`, { method: 'POST', credentials: 'include' })
    } catch {
      // Logout is local-first; a network failure must not strand browser state.
    } finally {
      clearBrowserAuth('logout', { redirect: false })
    }
    return { redirected: false }
  }

  return <AuthCtx.Provider value={{ user, loading, authConfig, setupStatus, setupRequired: !!setupStatus.required, login, verifyMfa, logout, refreshUser, refreshAuthConfig, refreshSetupStatus, beginSsoLogin }}>{children}</AuthCtx.Provider>
}

export function useAuth() { return useContext(AuthCtx) }
