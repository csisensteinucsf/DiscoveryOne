import { createContext, useContext, useEffect, useState, useCallback } from 'react'

const BRANDING_EVENT = 'branding:update'
const emitBrandingUpdate = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(BRANDING_EVENT))
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
    auth_provider: payload.auth_provider || 'local',
    local_password_login_allowed: payload.local_password_login_allowed !== false,
  }
}

const AuthCtx = createContext(null)

export function AuthProvider({ apiBase, children }) {
  const [user, setUser] = useState(null)
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
        setUser(normalizeUser(data))
        emitBrandingUpdate()
        return data
      }
      setUser(null)
      return null
    } catch {
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
    setUser(normalizeUser(data.user))
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
      setUser(null)
      emitBrandingUpdate()
      window.location.assign(`${apiBase}/auth/oidc/logout?next=${encodeURIComponent(normalizedNext)}`)
      return { redirected: true }
    }
    await fetch(`${apiBase}/auth/logout`, { method: 'POST', credentials: 'include' })
    setUser(null)
    emitBrandingUpdate()
    return { redirected: false }
  }

  return <AuthCtx.Provider value={{ user, loading, authConfig, setupStatus, setupRequired: !!setupStatus.required, login, logout, refreshUser, refreshAuthConfig, refreshSetupStatus, beginSsoLogin }}>{children}</AuthCtx.Provider>
}

export function useAuth() { return useContext(AuthCtx) }
