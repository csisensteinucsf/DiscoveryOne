import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import { sessionDeadlineMs, sessionExpiryDelayMs } from '../../src/lib/sessionExpiry.js'

test('session deadline uses the earlier absolute or idle expiry', () => {
  const now = Date.parse('2026-08-18T12:00:00Z')
  const activity = now - 5 * 60 * 1000
  const user = {
    session_expires_at: '2026-08-18T14:00:00Z',
    session_idle_timeout_minutes: 30,
  }

  assert.equal(sessionDeadlineMs(user, activity), now + 25 * 60 * 1000)
  assert.equal(sessionExpiryDelayMs(user, activity, now), 25 * 60 * 1000)
})

test('session activity extends only the idle deadline and never the absolute deadline', () => {
  const now = Date.parse('2026-08-18T12:00:00Z')
  const user = {
    session_expires_at: '2026-08-18T12:45:00Z',
    session_idle_timeout_minutes: 30,
  }

  assert.equal(sessionDeadlineMs(user, now), now + 30 * 60 * 1000)
  assert.equal(sessionDeadlineMs(user, now + 20 * 60 * 1000), now + 45 * 60 * 1000)
  assert.equal(sessionExpiryDelayMs(user, now - 60 * 60 * 1000, now), 0)
  assert.equal(sessionExpiryDelayMs({}, now, now), null)
})

test('expired-session handling uses a hard login redirect and tracks authenticated activity', () => {
  const auth = readFileSync(new URL('../../src/auth.jsx', import.meta.url), 'utf8')
  const fetchWrapper = readFileSync(new URL('../../src/utils/csrfFetch.js', import.meta.url), 'utf8')

  assert.equal(auth.includes('window.location.replace(target)'), true)
  assert.equal(auth.includes('sessionExpiryDelayMs(user, sessionActivityAt)'), true)
  assert.equal(auth.includes('AUTH_ACTIVITY_EVENT'), true)
  assert.equal(fetchWrapper.includes('else notifyAuthActivity(input)'), true)
})
