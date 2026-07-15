import { useEffect, useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'

export default function Register({ apiBase }) {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [info, setInfo] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const ssoEnabled = !!info?.sso_enabled
  const ssoDisplayName = info?.sso_display_name || 'Single sign-on'

  useEffect(() => {
    if (!token) {
      setError('Registration link missing token.')
      setLoading(false)
      return
    }
    ;(async () => {
      try {
        const res = await fetch(`${apiBase}/auth/register/claim?token=${encodeURIComponent(token)}`)
        if (!res.ok) {
          const text = await res.text().catch(() => 'Invalid or expired link.')
          throw new Error(text || 'Invalid or expired link.')
        }
        const data = await res.json()
        setInfo(data)
      } catch (err) {
        setError(err?.message || 'Invalid or expired link.')
      } finally {
        setLoading(false)
      }
    })()
  }, [apiBase, token])

  const submit = async (e) => {
    e.preventDefault()
    if (!token) {
      setError('Registration link missing token.')
      return
    }
    if (!ssoEnabled && password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (!ssoEnabled && password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const res = await fetch(`${apiBase}/auth/register/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(ssoEnabled ? { token } : { token, password }),
      })
      if (!res.ok) {
        const text = await res.text().catch(() => 'Registration failed.')
        throw new Error(text || 'Registration failed.')
      }
      setStatus(ssoEnabled ? `Account activated. You can now sign in with ${ssoDisplayName}.` : 'Account created! You can now sign in with your credentials.')
      setPassword('')
      setConfirm('')
    } catch (err) {
      setError(err?.message || 'Registration failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wrap" style={{ maxWidth: 520 }}>
      <div className="card">
        <h3>Create Your Account</h3>
        {loading ? (
          <p>Loading...</p>
        ) : error ? (
          <p style={{ color: '#b91c1c' }}>{error}</p>
        ) : (
          <>
            <p style={{ color: 'var(--muted,#6b7280)' }}>
              {ssoEnabled
                ? `Welcome ${info?.name}. Activate your DiscoveryOne account, then sign in with ${ssoDisplayName}.`
                : `Welcome ${info?.name}. Set a new password to activate your local DiscoveryOne account.`}
            </p>
            <form onSubmit={submit}>
              {!ssoEnabled && (
                <>
                  <label htmlFor="register-password">New Password</label>
                  <input id="register-password" className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} minLength={8} required />
                  <label htmlFor="register-confirm">Confirm Password</label>
                  <input id="register-confirm" className="input" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} minLength={8} required />
                </>
              )}
              {error && <p role="alert" aria-live="assertive" style={{ color: '#b91c1c' }}>{error}</p>}
              {status && <p role="status" aria-live="polite" style={{ color: '#047857' }}>{status}</p>}
              <div style={{ marginTop: '.75rem' }}>
                <button className="btn" type="submit" disabled={busy}>
                  {busy ? 'Submitting...' : 'Activate Account'}
                </button>
                <Link to="/login" style={{ marginLeft: 16 }}>Back to login</Link>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
