export const AUTH_EXPIRED_EVENT = 'discoveryone:auth-expired'
export const AUTH_ACTIVITY_EVENT = 'discoveryone:auth-activity'
export const AUTH_SYNC_CHANNEL = 'discoveryone:auth-sync'
export const AUTH_SYNC_STORAGE_KEY = 'discoveryone:auth-sync'

const PUBLIC_AUTH_PATHS = new Set([
  '/api/auth/config',
  '/api/auth/token',
  '/api/auth/mfa/verify',
  '/api/auth/logout',
  '/api/auth/register_request',
  '/api/auth/password/forgot',
  '/api/auth/password/reset',
  '/api/setup/status',
  '/api/setup/complete',
])

function apiPath(input) {
  const raw = typeof input === 'string' ? input : input?.url || ''
  if (!raw) return ''
  try {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
    return new URL(raw, origin).pathname
  } catch {
    return raw.split('?')[0]
  }
}

export function isProtectedApiRequest(input) {
  const path = apiPath(input)
  if (!path.startsWith('/api/')) return false
  if (PUBLIC_AUTH_PATHS.has(path)) return false
  if (path.startsWith('/api/auth/oidc/')) return false
  return true
}

export function notifyAuthExpired(input, status = 401) {
  if (typeof window === 'undefined' || !isProtectedApiRequest(input)) return
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT, {
    detail: { url: typeof input === 'string' ? input : input?.url || '', status },
  }))
}

export function notifyAuthActivity(input) {
  if (typeof window === 'undefined' || !isProtectedApiRequest(input)) return
  window.dispatchEvent(new CustomEvent(AUTH_ACTIVITY_EVENT, {
    detail: { url: typeof input === 'string' ? input : input?.url || '', at: Date.now() },
  }))
}

function responseRequestId(response) {
  return response?.headers?.get?.('X-Request-ID') || ''
}

async function responseDetail(response) {
  try {
    const payload = await response.clone().json()
    if (typeof payload?.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
    if (Array.isArray(payload?.detail) && payload.detail.length) {
      return payload.detail
        .map((item) => item?.msg || item?.message || String(item))
        .join(', ')
    }
  } catch {
    // Fall through to a plain-text response.
  }
  try {
    return (await response.clone().text()).trim()
  } catch {
    return ''
  }
}

export class ApiError extends Error {
  constructor(message, { status = 0, requestId = '', cause = null } = {}) {
    super(message, cause ? { cause } : undefined)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
  }
}

export async function apiErrorFromResponse(response, fallback = 'Request failed.') {
  const detail = await responseDetail(response)
  const requestId = responseRequestId(response)
  const status = Number(response?.status || 0)
  const suffix = [status ? `HTTP ${status}` : '', requestId ? `request ${requestId}` : '']
    .filter(Boolean)
    .join(', ')
  return new ApiError(`${detail || fallback}${suffix ? ` (${suffix})` : ''}`, { status, requestId })
}

export function networkApiError(error, fallback = 'Unable to reach DiscoveryOne.') {
  if (error instanceof ApiError) return error
  const detail = String(error?.message || '').trim()
  const message = detail && detail.toLowerCase() !== 'failed to fetch'
    ? `${fallback} ${detail}`
    : `${fallback} Check the server connection and try again.`
  return new ApiError(message, { cause: error })
}

export async function apiFetch(input, init, { errorMessage = 'Request failed.' } = {}) {
  let response
  try {
    response = await fetch(input, init)
  } catch (error) {
    throw networkApiError(error, errorMessage)
  }
  if (!response.ok) throw await apiErrorFromResponse(response, errorMessage)
  return response
}
