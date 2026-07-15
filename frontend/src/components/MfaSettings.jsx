import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../auth.jsx'
import { useToast } from './ToastProvider.jsx'

const cardTitleStyle = { fontSize: 20, fontWeight: 700, marginBottom: 12 }

export default function MfaSettings({ apiBase }) {
  const { refreshUser, user } = useAuth()
  const { showToast } = useToast()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const isRequestor = role === 'requestor'
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [setupSecret, setSetupSecret] = useState(null)
  const [setupCode, setSetupCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [showDisableForm, setShowDisableForm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [deviceBusy, setDeviceBusy] = useState(null)
  const allowSetup = status?.allow_setup !== false

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/auth/mfa/status`, { credentials: 'include' })
      if (!res.ok) throw new Error('status_failed')
      const data = await res.json()
      setStatus(data)
    } catch (err) {
      console.error(err)
      setStatus(null)
      setError('Unable to load MFA status. Try again in a moment.')
    } finally {
      setLoading(false)
    }
  }, [apiBase])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const beginSetup = async () => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/auth/mfa/setup/start`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setSetupSecret(data)
      setSetupCode('')
      showToast('TOTP secret generated. Scan the QR code to continue.', { variant: 'info' })
    } catch (err) {
      console.error(err)
      setError('Unable to start MFA setup.')
    } finally {
      setBusy(false)
    }
  }

  const confirmSetup = async () => {
    if (!setupSecret || !setupCode.trim()) {
      setError('Enter the 6-digit code from your authenticator app.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/auth/mfa/setup/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ code: setupCode.trim() })
      })
      if (!res.ok) throw new Error(await res.text())
      await refreshUser()
      await fetchStatus()
      setSetupSecret(null)
      setSetupCode('')
      setShowDisableForm(false)
      showToast('Authenticator enabled.', { variant: 'success' })
    } catch (err) {
      console.error(err)
      setError('Verification failed. Double-check the code and try again.')
    } finally {
      setBusy(false)
    }
  }

  const disableMfa = async () => {
    if (!disableCode.trim()) {
      setError('Enter a valid authenticator code to disable MFA.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/auth/mfa/disable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ code: disableCode.trim() }),
      })
      if (!res.ok) throw new Error(await res.text())
      await refreshUser()
      await fetchStatus()
      setDisableCode('')
      setShowDisableForm(false)
      showToast('Authenticator disabled.', { variant: 'info' })
    } catch (err) {
      console.error(err)
      setError('Unable to disable MFA. Confirm the code and try again.')
    } finally {
      setBusy(false)
    }
  }

  const revokeDevice = async (id) => {
    setDeviceBusy(id)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/auth/mfa/trusted_devices/${id}`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok) throw new Error(await res.text())
      await fetchStatus()
      showToast('Trusted browser removed.', { variant: 'success' })
    } catch (err) {
      console.error(err)
      setError('Unable to remove the selected browser.')
    } finally {
      setDeviceBusy(null)
    }
  }

  const formatDate = (val) => {
    if (!val) return '—'
    try {
      return new Date(val).toLocaleString()
    } catch {
      return val
    }
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={cardTitleStyle}>Two-Factor Authentication (TOTP)</div>
      {error && <p style={{ color: '#b91c1c', marginTop: 0 }}>{error}</p>}
      {loading ? (
        <p style={{ color: 'var(--muted,#6b7280)' }}>Loading security settings…</p>
      ) : (
        <>
          <p style={{ color: 'var(--muted,#6b7280)' }}>
            Protect your account with 2FA. New browsers must confirm with a code unless they are marked as trusted.
          </p>
          <p style={{ color: 'var(--muted,#6b7280)' }}>
            The preferred way to add a TOTP code is to open your Duo Mobile App and hit the + to add an account.
            Then you can use the code from your Duo mobile app to login.
          </p>
          {!allowSetup && (
            <p style={{ color: '#b45309', fontWeight: 600 }}>
              MFA is not available for this account. Use another administrative account for enrollment.
            </p>
          )}
          {allowSetup && !status?.enabled && !setupSecret && (
            <button className="btn" type="button" onClick={beginSetup} disabled={busy}>
              {busy ? 'Preparing…' : 'Enable Authenticator'}
            </button>
          )}

          {allowSetup && setupSecret && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--border,#e5e7eb)', paddingTop: 16 }}>
              <h4 style={{ margin: '0 0 8px' }}>Scan this QR code</h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16 }}>
                {setupSecret?.qr_data_url ? (
                  <img src={setupSecret.qr_data_url} alt="Authenticator QR" width={160} height={160} style={{ borderRadius: 4, border: '1px solid var(--border,#d1d5db)' }} />
                ) : (
                  <div style={{ width: 160, height: 160, borderRadius: 4, border: '1px dashed var(--border,#d1d5db)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted,#6b7280)', textAlign: 'center', padding: 8 }}>
                    QR preview unavailable. Enter the secret manually.
                  </div>
                )}
                <div>
                  <p style={{ margin: '0 0 4px' }}>Or add the secret manually:</p>
                  <code style={{ display: 'inline-block', padding: '4px 8px', background: '#111827', color: '#f9fafb' }}>{setupSecret.secret}</code>
                </div>
              </div>
              <label style={{ display: 'block', marginTop: 12 }}>Enter 6-digit code</label>
              <input
                className="input"
                value={setupCode}
                onChange={e => setSetupCode(e.target.value)}
                inputMode="numeric"
                pattern="[0-9]*"
              />
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn" type="button" onClick={confirmSetup} disabled={busy || !setupCode.trim()}>
                  {busy ? 'Verifying…' : 'Verify & Enable'}
                </button>
                <button className="btn secondary" type="button" onClick={() => { setSetupSecret(null); setSetupCode('') }} disabled={busy}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {allowSetup && status?.enabled && !setupSecret && !isRequestor && (
            <div style={{ marginTop: 16 }}>
              <p style={{ color: 'var(--success,#059669)', marginBottom: 8 }}>Authenticator is currently <strong>enabled</strong>.</p>
              {!showDisableForm ? (
                <button className="btn secondary" type="button" onClick={() => setShowDisableForm(true)}>
                  Disable Authenticator
                </button>
              ) : (
                <div style={{ marginTop: 8 }}>
                  <label>Confirm with a 6-digit code</label>
                  <input
                    className="input"
                    value={disableCode}
                    onChange={e => setDisableCode(e.target.value)}
                    inputMode="numeric"
                    pattern="[0-9]*"
                  />
                  <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button className="btn" type="button" onClick={disableMfa} disabled={busy || !disableCode.trim()}>
                      {busy ? 'Disabling…' : 'Confirm Disable'}
                    </button>
                    <button className="btn secondary" type="button" onClick={() => { setShowDisableForm(false); setDisableCode('') }} disabled={busy}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {allowSetup && status?.enabled && !setupSecret && (
            <div style={{ marginTop: 24 }}>
              <h4 style={{ marginBottom: 8 }}>Trusted Browsers</h4>
              <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
                These browsers will skip the second step until the token expires or you revoke access.
              </p>
              {status?.trusted_devices?.length ? (
                <div className="table-responsive">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Browser</th>
                        <th>Last Used</th>
                        <th>Expires</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {status.trusted_devices.map(dev => (
                        <tr key={dev.id}>
                          <td>{dev.label || dev.user_agent || 'Browser'}</td>
                          <td>{formatDate(dev.last_used_at)}</td>
                          <td>{formatDate(dev.expires_at)}</td>
                          <td>
                            <button
                              className="btn secondary"
                              type="button"
                              onClick={() => revokeDevice(dev.id)}
                              disabled={deviceBusy === dev.id}
                            >
                              {deviceBusy === dev.id ? 'Removing…' : 'Remove'}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p style={{ color: 'var(--muted,#6b7280)' }}>No trusted browsers yet.</p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
