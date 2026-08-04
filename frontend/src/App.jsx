import { Suspense, lazy, useEffect, useState } from 'react'
import { Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import { useAuth, AuthProvider } from './auth.jsx'
import { useBrandingSettings } from './lib/useBrandingSettings.js'
import BrandLogo from './components/BrandLogo.jsx'
import BrandingBoot from './components/BrandingBoot.jsx'
import HelpButton from './components/HelpButton.jsx'
import CaseRequests from './pages/CaseRequests.jsx'
import './styles/themes.css'
import { ToastProvider } from './components/ToastProvider.jsx'
import { ConfirmProvider } from './components/ConfirmProvider.jsx'
import { applyThemePreference, watchSystemTheme } from './lib/theme.js'

const Cases = lazy(() => import('./pages/Cases.jsx'))
const Dashboards = lazy(() => import('./pages/Dashboards.jsx'))
const Custodians = lazy(() => import('./pages/Custodians.jsx'))
const Reports = lazy(() => import('./pages/Reports.jsx'))
const System = lazy(() => import('./pages/System.jsx'))
const CaseDetail = lazy(() => import('./pages/CaseDetail.jsx'))
const CustodianDetail = lazy(() => import('./pages/CustodianDetail.jsx'))
const Help = lazy(() => import('./pages/Help.jsx'))
const Setup = lazy(() => import('./pages/Setup.jsx'))

const apiBase = import.meta.env.VITE_API_BASE || '/api'
const ADMIN_USERNAME = 'admin'
function Protected({ children }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <div style={{ padding: 20 }}>Loading...</div>
  if (!user) return <Navigate to="/login" state={{ from: loc }} replace />
  return children
}

function Shell() {
  const { logout, user, loading, authConfig, setupRequired } = useAuth()
  const { appName, appTagline } = useBrandingSettings(apiBase, { updateTitle: true })
  const loc = useLocation()
  const navigate = useNavigate()
  const isActive = (path) => loc.pathname === path
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const isSysAdmin = role === 'sys_admin'
  const isRequestor = role === 'requestor'
  const isTech = role === 'tech'
  const showSidebar = !loading && !!user
  const employeeIdLabel = authConfig?.institution?.employee_id_label || 'Employee ID'
  const [requestStats, setRequestStats] = useState({ pending: 0, mine_pending: 0 })
  const needsEmployeeId = Boolean(
    user &&
    ['analyst', 'sys_admin'].includes(role) &&
    (user.username || '').toLowerCase() !== ADMIN_USERNAME &&
    !(user.employee_id || '').trim()
  )
  const [registrationPending, setRegistrationPending] = useState(0)

  const doLogout = async () => {
    const result = await logout('/login')
    if (result?.redirected) return
    navigate('/login', { replace: true })
  }

  useEffect(() => {
    if (!user || isTech) return
    let cancelled = false
    const fetchStats = async () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      try {
        const res = await fetch(`${apiBase}/case_requests/stats`, { credentials: 'include' })
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) setRequestStats(data)
      } catch (err) {
        console.error(err)
      }
    }
    fetchStats()
    const timer = setInterval(fetchStats, 60000)
    const handler = (event) => {
      if (event?.detail && !cancelled) {
        setRequestStats((prev) => ({ ...prev, ...event.detail }))
      }
    }
    const onVisible = () => {
      if (typeof document === 'undefined') return
      if (document.visibilityState === 'visible') fetchStats()
    }
    window.addEventListener('case-requests:stats', handler)
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisible)
    }
    return () => {
      cancelled = true
      clearInterval(timer)
      window.removeEventListener('case-requests:stats', handler)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible)
      }
    }
  }, [user, isTech])

  useEffect(() => {
    if (!user || role !== 'sys_admin') {
      setRegistrationPending(0)
      return
    }
    let cancelled = false
    const fetchPending = async () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      try {
        const res = await fetch(`${apiBase}/auth/register_requests`, { credentials: 'include' })
        if (!res.ok) throw new Error()
        const data = await res.json()
        if (!cancelled) {
          const pending = Array.isArray(data) ? data.filter(item => item.status === 'pending').length : 0
          setRegistrationPending(pending)
        }
      } catch {
        if (!cancelled) setRegistrationPending(0)
      }
    }
    fetchPending()
    const interval = setInterval(fetchPending, 60000)
    const onVisible = () => {
      if (typeof document === 'undefined') return
      if (document.visibilityState === 'visible') fetchPending()
    }
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisible)
    }
    return () => {
      cancelled = true
      clearInterval(interval)
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible)
      }
    }
  }, [user, role])

  useEffect(() => {
    const pref = user?.user_theme || user?.theme
    const stored = (() => {
      try { return localStorage.getItem('branding:theme') || 'light' } catch { return 'light' }
    })()
    const choice = pref || stored || 'light'
    applyThemePreference(choice)
    let cleanup = null
    if (choice === 'system') {
      cleanup = watchSystemTheme(() => applyThemePreference('system'))
    }
    return () => { if (cleanup) cleanup() }
  }, [user?.user_theme, user?.theme])

  if (!loading && setupRequired && loc.pathname !== '/setup') {
    return <Navigate to="/setup" replace />
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg)' }}>
      <BrandingBoot />
      <a href="#main-content" className="sr-only skip-link">Skip to main content</a>
      {showSidebar && (
        <aside className="sidebar" style={{ width: 240, padding: '16px 0', background: 'var(--sidebar-bg)', position: 'sticky', top: 0, alignSelf: 'flex-start', height: '100vh', overflowY: 'auto' }}>
          <div className="brand" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
            <Link to="/" aria-label="Home" style={{ textDecoration: 'none', display: 'inline-block' }}>
              <BrandLogo apiBase={apiBase} height={56} />
            </Link>
            <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--sidebar-fg)', textAlign: 'center' }}>{appName}</div>
            <div className="brand-sub" style={{ color: 'var(--muted)', fontSize: 13, textAlign: 'center' }}>{appTagline}</div>
          </div>
          <nav className="nav" style={{ display: 'grid', gap: 6, paddingTop: 10 }}>
            <Link to="/cases" className={isActive('/cases') ? 'active' : ''} aria-current={isActive('/cases') ? 'page' : undefined}>Cases</Link>
            {!isTech && (
              <Link to="/dashboards" className={isActive('/dashboards') ? 'active' : ''} aria-current={isActive('/dashboards') ? 'page' : undefined}>Dashboards</Link>
            )}
            {!isTech && (
              <Link to="/reports" className={isActive('/reports') ? 'active' : ''} aria-current={isActive('/reports') ? 'page' : undefined}>Reports</Link>
            )}
            {!isTech && (
              <Link to="/requests" className={isActive('/requests') ? 'active' : ''} aria-current={isActive('/requests') ? 'page' : undefined} style={{ position: 'relative' }}>
                Requests
                {!isRequestor && requestStats.pending > 0 && (
                  <span style={{
                    position: 'absolute',
                    top: 6,
                    right: 12,
                    minWidth: 22,
                    padding: '0 6px',
                    borderRadius: 999,
                    background: 'var(--accent,#ef4444)',
                    color: '#fff',
                    fontSize: 12,
                    textAlign: 'center',
                    fontWeight: 600,
                  }}>{requestStats.pending}</span>
                )}
              </Link>
            )}
            {!isRequestor && !isTech && (
              <Link to="/custodians" className={isActive('/custodians') ? 'active' : ''} aria-current={isActive('/custodians') ? 'page' : undefined}>Custodians</Link>
            )}
            <Link to="/system" className={isActive('/system') ? 'active' : ''} aria-current={isActive('/system') ? 'page' : undefined} style={{ position: 'relative' }}>
              System
              {role === 'sys_admin' && registrationPending > 0 && (
                <span style={{
                  position: 'absolute',
                  top: 6,
                  right: 12,
                  minWidth: 22,
                  padding: '0 6px',
                  borderRadius: 999,
                  background: 'var(--accent,#0ea5e9)',
                  color: '#fff',
                  fontSize: 12,
                  textAlign: 'center',
                  fontWeight: 600,
                }}>{registrationPending}</span>
              )}
            </Link>
            <button onClick={doLogout} className="nav-logout">Logout</button>
          </nav>
        </aside>
      )}

      <main id="main-content" style={{ flex: 1 }}>
        <HelpButton />
        <div className="wrap">
          {needsEmployeeId && (
            <div className="card" style={{ marginBottom: 16, borderLeft: '4px solid #f97316' }}>
              <p style={{ margin: 0, fontWeight: 600, color: '#b45309' }}>
                Missing {employeeIdLabel}; it is needed for external ticket workflow creation. Update it in System.
              </p>
              <button className="btn secondary" type="button" onClick={() => navigate('/system')} style={{ marginTop: 8 }}>
                Go to System
              </button>
            </div>
          )}
          <Suspense fallback={<div style={{ padding: 24 }}>Loading...</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/cases" replace />} />
            <Route path="/setup" element={<Setup apiBase={apiBase} />} />
            <Route path="/login" element={<Login apiBase={apiBase} />} />
            <Route path="/register" element={<Register apiBase={apiBase} />} />
            <Route path="/cases" element={<Protected><Cases apiBase={apiBase} /></Protected>} />
            <Route path="/dashboards" element={<Protected>{isTech ? (<div className="card" style={{ marginTop: 24 }}><p style={{ margin: 0, color: 'var(--muted,#6b7280)' }}>Dashboards are not available for tech accounts.</p></div>) : (<Dashboards apiBase={apiBase} />)}</Protected>} />
            <Route path="/custodians" element={<Protected>{isTech ? (<div className="card" style={{ marginTop: 24 }}><p style={{ margin: 0, color: 'var(--muted,#6b7280)' }}>Custodian views are not available for tech accounts.</p></div>) : (<Custodians apiBase={apiBase} />)}</Protected>} />
            <Route path="/custodians/detail" element={<Protected>{isTech ? (<div className="card" style={{ marginTop: 24 }}><p style={{ margin: 0, color: 'var(--muted,#6b7280)' }}>Custodian views are not available for tech accounts.</p></div>) : (<CustodianDetail apiBase={apiBase} />)}</Protected>} />
            <Route path="/reports" element={<Protected>{isTech ? (<div className="card" style={{ marginTop: 24 }}><p style={{ margin: 0, color: 'var(--muted,#6b7280)' }}>Reports are not available for tech accounts.</p></div>) : (<Reports />)}</Protected>} />
            <Route path="/system" element={<Protected><System apiBase={apiBase} /></Protected>} />
            <Route path="/cases/:caseId" element={<Protected><CaseDetail apiBase={apiBase} /></Protected>} />
            <Route path="/logs" element={<Navigate to="/system?section=operations&view=logs" replace />} />
            <Route path="/requests" element={<Protected>{isTech ? (<div className="card" style={{ marginTop: 24 }}><p style={{ margin: 0, color: 'var(--muted,#6b7280)' }}>Requests are not available for tech accounts.</p></div>) : (<CaseRequests apiBase={apiBase} />)}</Protected>} />
            <Route path="/help" element={<Help />} />
          </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider apiBase={apiBase}>
      <ToastProvider>
        <ConfirmProvider>
          <Shell />
        </ConfirmProvider>
      </ToastProvider>
    </AuthProvider>
  )
}
