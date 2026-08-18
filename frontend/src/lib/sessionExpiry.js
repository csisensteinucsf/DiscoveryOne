const MINUTE_MS = 60 * 1000

export function sessionDeadlineMs(user, lastActivityAt) {
  if (!user) return null
  const deadlines = []
  const absoluteExpiry = Date.parse(user.session_expires_at || '')
  if (Number.isFinite(absoluteExpiry)) deadlines.push(absoluteExpiry)

  const idleMinutes = Number(user.session_idle_timeout_minutes || 0)
  const activityTime = Number(lastActivityAt || 0)
  if (idleMinutes > 0 && Number.isFinite(activityTime) && activityTime > 0) {
    deadlines.push(activityTime + idleMinutes * MINUTE_MS)
  }
  return deadlines.length ? Math.min(...deadlines) : null
}

export function sessionExpiryDelayMs(user, lastActivityAt, now = Date.now()) {
  const deadline = sessionDeadlineMs(user, lastActivityAt)
  return deadline === null ? null : Math.max(0, deadline - now)
}
