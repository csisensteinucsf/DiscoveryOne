import test from 'node:test'
import assert from 'node:assert/strict'

import { ApiError, apiFetch, isProtectedApiRequest } from '../../src/lib/apiClient.js'
import { saveUserRequest } from '../../src/lib/userApi.js'

test('protected API detection excludes public authentication endpoints', () => {
  assert.equal(isProtectedApiRequest('/api/cases'), true)
  assert.equal(isProtectedApiRequest('/api/users'), true)
  assert.equal(isProtectedApiRequest('/api/auth/token'), false)
  assert.equal(isProtectedApiRequest('/api/auth/logout'), false)
  assert.equal(isProtectedApiRequest('/api/auth/oidc/login'), false)
  assert.equal(isProtectedApiRequest('/assets/index.js'), false)
})

test('network failures retain operation context', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }

  await assert.rejects(
    () => apiFetch('/api/cases', {}, { errorMessage: 'Unable to load cases.' }),
    (error) => {
      assert.ok(error instanceof ApiError)
      assert.match(error.message, /^Unable to load cases\./)
      assert.match(error.message, /Check the server connection/)
      return true
    },
  )
})

test('user creation failures include backend detail, HTTP status, and request ID', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: 'Email is already registered' }),
    { status: 409, headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req-user-123' } },
  )

  await assert.rejects(
    () => saveUserRequest('/api', { payload: { email: 'duplicate@example.edu' } }),
    (error) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.status, 409)
      assert.equal(error.requestId, 'req-user-123')
      assert.equal(error.message, 'Email is already registered (HTTP 409, request req-user-123)')
      return true
    },
  )
})

test('user creation network failures are actionable', async (t) => {
  const originalFetch = globalThis.fetch
  t.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch') }

  await assert.rejects(
    () => saveUserRequest('/api', { payload: { email: 'new@example.edu' } }),
    (error) => {
      assert.ok(error instanceof ApiError)
      assert.match(error.message, /^Unable to create user\./)
      assert.match(error.message, /Check the server connection/)
      return true
    },
  )
})