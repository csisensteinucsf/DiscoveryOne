import { useMemo, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth.jsx'
import { useBrandingSettings } from '../lib/useBrandingSettings.js'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'

export default function Login({ apiBase }) {
  const { login, verifyMfa, authConfig, beginSsoLogin } = useAuth()
  const { appName } = useBrandingSettings(apiBase, { updateTitle: true })
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [showLocalAdmin, setShowLocalAdmin] = useState(false)
  const [mfaToken, setMfaToken] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const [rememberBrowser, setRememberBrowser] = useState(false)
  const nav = useNavigate()
  const loc = useLocation()
  const searchParams = useMemo(() => new URLSearchParams(loc.search), [loc.search])
  const expiredSession = searchParams.get('reason') === 'expired'
  const ssoRegistrationPrompt = searchParams.get('sso_unregistered') === '1'
  const ssoRegistrationToken = searchParams.get('sso_registration_token') || ''
  const [showRegister, setShowRegister] = useState(searchParams.get('register') === '1')
  const [registerName, setRegisterName] = useState(searchParams.get('name') || '')
  const [registerEmail, setRegisterEmail] = useState(searchParams.get('email') || '')
  const [registerStatus, setRegisterStatus] = useState('')
  const [registerError, setRegisterError] = useState('')
  const [registerBusy, setRegisterBusy] = useState(false)
  const ssoEnabled = !!authConfig?.sso_enabled
  const ssoDisplayName = authConfig?.sso_display_name || 'Single sign-on'
  const ssoConfigured = !ssoEnabled || !!authConfig?.sso_configured
  const showPasswordForm = !ssoEnabled || showLocalAdmin
  const allowRegistration = ssoRegistrationPrompt || showRegister
  const nextPath = `${loc.state?.from?.pathname || '/'}${loc.state?.from?.search || ''}`
  const externalError = searchParams.get('error') || ''
  const displayError = err || externalError

  const resetState = () => {
    setErr('')
    setPassword('')
  }

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setErr('')
    try {
      setBusy(true)
      const result = await login(email.trim().toLowerCase(), password)
      if (result?.mfa_required) {
        setMfaToken(result.mfa_token || '')
        setMfaCode('')
        setPassword('')
        return
      }
      const to = loc.state?.from?.pathname || '/'
      nav(to, { replace: true })
    } catch (e) {
      if (e?.message) {
        setErr(e.message)
      } else {
        setErr('Invalid email or password')
      }
    } finally {
      setBusy(false)
    }
  }

  const submitMfa = async (e) => {
    e.preventDefault()
    if (busy || !mfaToken) return
    setErr('')
    try {
      setBusy(true)
      await verifyMfa(mfaToken, mfaCode, rememberBrowser)
      const to = loc.state?.from?.pathname || '/'
      nav(to, { replace: true })
    } catch (e) {
      setErr(e?.message || 'Invalid verification code')
    } finally {
      setBusy(false)
    }
  }

  const cancelMfa = () => {
    setMfaToken('')
    setMfaCode('')
    setRememberBrowser(false)
    setErr('')
  }

  const startSso = () => {
    if (busy || !ssoConfigured) return
    beginSsoLogin(nextPath)
  }

  const toggleRegister = () => {
    setShowRegister(v => !v)
    if (!showRegister) {
      setRegisterError('')
      setRegisterStatus('')
    }
  }

  const toggleLocalAdmin = () => {
    setShowLocalAdmin(v => !v)
    resetState()
  }

  const submitRegistration = async (e) => {
    e.preventDefault()
    if (registerBusy) return
    const name = registerName.trim()
    const emailVal = registerEmail.trim().toLowerCase()
    if (!name || !emailVal) {
      setRegisterError('Name and email are required.')
      return
    }
    setRegisterBusy(true)
    setRegisterError('')
    setRegisterStatus('')
    try {
      const res = await fetch(`${apiBase}/auth/register_request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email: emailVal, source: ssoRegistrationPrompt ? 'sso' : 'self_service', sso_registration_token: ssoRegistrationPrompt ? ssoRegistrationToken : undefined }),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'Unable to submit request')
      }
      setRegisterStatus('Request submitted. A system administrator will contact you once it is reviewed.')
      setRegisterName('')
      setRegisterEmail('')
    } catch (err) {
      setRegisterError(err?.message || 'Unable to submit request.')
    } finally {
      setRegisterBusy(false)
    }
  }

  return (
    <div className="wrap" style={{maxWidth:420}}>
      <div className="card">
        <h3>{ssoEnabled && !showPasswordForm ? `Sign in with ${ssoDisplayName}` : 'Sign in'}</h3>
        {expiredSession && (
          <p role="status" aria-live="polite" className="auth-session-message">
            Your session expired. Sign in again to continue.
          </p>
        )}
        {ssoEnabled && !showPasswordForm && (
          <>
            <p style={{ color: 'var(--muted,#6b7280)' }}>
              Sign in through {ssoDisplayName} for your normal {appName} access. Local username and password login remains available for local-only {appName} accounts and the break-glass admin account.
            </p>
            <div style={{ display: 'grid', gap: 12 }}>
              <div style={{ textAlign: 'center', fontSize: 22, fontWeight: 700, letterSpacing: '0.02em' }}>
                {appName}
              </div>
              <button className="btn" type="button" onClick={startSso} disabled={!ssoConfigured || busy}>
                {busy ? 'Redirecting...' : `Sign in with ${ssoDisplayName}`}
              </button>
              {!ssoConfigured && (
                <p style={{ color: '#b91c1c', margin: 0 }}>
                  {ssoDisplayName} is enabled but not fully configured on the server.
                </p>
              )}
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0, textAlign: 'left' }}
                onClick={toggleLocalAdmin}
              >
                Use local account sign-in
              </button>
            </div>
          </>
        )}
        {showPasswordForm && !mfaToken && (
          <form onSubmit={submit}>
            {ssoEnabled && (
              <p style={{ color: 'var(--muted,#6b7280)' }}>
                Local sign-in is reserved for local-only {appName} accounts and the break-glass admin account.
              </p>
            )}
            <label htmlFor="login-identifier"><RequiredFieldLabel>Email or Username</RequiredFieldLabel></label>
            <input id="login-identifier" className="input" value={email} onChange={e=>setEmail(e.target.value)} autoFocus required />
            <label htmlFor="login-password"><RequiredFieldLabel>Password</RequiredFieldLabel></label>
            <input id="login-password" className="input" type="password" value={password} onChange={e=>setPassword(e.target.value)} required />
            {displayError && <p role="alert" aria-live="assertive" style={{color:'#b91c1c'}}>{displayError}</p>}
            <div style={{marginTop:'.75rem', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <button className="btn" type="submit" disabled={busy}>
                {busy ? 'Signing in...' : 'Login'}
              </button>
              {ssoEnabled && (
                <button className="btn secondary" type="button" onClick={toggleLocalAdmin}>
                  Back to {ssoDisplayName} sign-in
                </button>
              )}
            </div>
          </form>
        )}
        {showPasswordForm && mfaToken && (
          <form onSubmit={submitMfa}>
            <p style={{ color: 'var(--muted,#6b7280)' }}>
              Enter the current six-digit code from your authenticator app to finish signing in.
            </p>
            <label htmlFor="login-mfa-code"><RequiredFieldLabel>Verification Code</RequiredFieldLabel></label>
            <input
              id="login-mfa-code"
              className="input"
              value={mfaCode}
              onChange={e => setMfaCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              autoFocus
              required
            />
            <label style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: '.75rem' }}>
              <input
                type="checkbox"
                checked={rememberBrowser}
                onChange={e => setRememberBrowser(e.target.checked)}
              />
              Trust this browser for 30 days
            </label>
            {displayError && <p role="alert" aria-live="assertive" style={{color:'#b91c1c'}}>{displayError}</p>}
            <div style={{marginTop:'.75rem', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <button className="btn" type="submit" disabled={busy}>
                {busy ? 'Verifying...' : 'Verify'}
              </button>
              <button className="btn secondary" type="button" onClick={cancelMfa} disabled={busy}>
                Back
              </button>
            </div>
          </form>
        )}
        {!showPasswordForm && displayError && <p role="alert" aria-live="assertive" style={{color:'#b91c1c', marginTop: 12}}>{displayError}</p>}
      </div>
      {(!ssoEnabled || ssoRegistrationPrompt) && (
        <>
          {!ssoRegistrationPrompt && (
            <button
              type="button"
              style={{ marginTop: 12, background: 'none', border: 'none', color: '#2563eb', cursor: 'pointer', padding: 0 }}
              onClick={toggleRegister}
            >
              {showRegister ? 'Hide registration form' : "Don't have an account? Register here"}
            </button>
          )}
          {allowRegistration && (
        <div className="card" style={{ marginTop: 16 }}>
          <h4>Request an Account</h4>
          {ssoRegistrationPrompt && (
            <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
              Your {ssoDisplayName} account was verified, but you are not registered in DiscoveryOne yet. Submit this request and an administrator can approve your account and assign the correct group.
            </p>
          )}
          <form onSubmit={submitRegistration}>
            <label htmlFor="register-name"><RequiredFieldLabel>Full Name</RequiredFieldLabel></label>
            <input
              id="register-name"
              className="input"
              value={registerName}
              onChange={e => setRegisterName(e.target.value)}
              placeholder="First Last"
              required
            />
            <label htmlFor="register-email"><RequiredFieldLabel>Email</RequiredFieldLabel></label>
            <input
              id="register-email"
              className="input"
              type="email"
              value={registerEmail}
              onChange={e => setRegisterEmail(e.target.value)}
              placeholder="name@example.com"
              required
            />
            {registerError && <p role="alert" aria-live="assertive" style={{ color: '#b91c1c' }}>{registerError}</p>}
            {registerStatus && <p role="status" aria-live="polite" style={{ color: '#047857' }}>{registerStatus}</p>}
            <div style={{ marginTop: '.75rem' }}>
              <button className="btn" type="submit" disabled={registerBusy}>
                {registerBusy ? 'Submitting...' : 'Submit Request'}
              </button>
            </div>
          </form>
        </div>
          )}
        </>
      )}
    </div>
  )
}
