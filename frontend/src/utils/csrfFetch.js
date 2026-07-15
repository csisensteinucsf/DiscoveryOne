const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

function getCookieValue(name) {
  if (typeof document === 'undefined') return null
  const prefix = `${name}=`
  const match = document.cookie
    .split('; ')
    .find((part) => part.startsWith(prefix))
  return match ? decodeURIComponent(match.slice(prefix.length)) : null
}

function requestMethod(init) {
  return String(init?.method || 'GET').toUpperCase()
}

export function installCsrfFetch() {
  if (typeof window === 'undefined' || typeof window.fetch !== 'function') return
  if (window.__discoveryOneCsrfFetchInstalled) return
  window.__discoveryOneCsrfFetchInstalled = true

  const originalFetch = window.fetch.bind(window)
  window.fetch = (input, init = {}) => {
    const nextInit = { ...init }
    const method = requestMethod(nextInit)
    const headers = new Headers(nextInit.headers || {})
    const csrf = getCookieValue('csrf')

    if (csrf && !SAFE_METHODS.has(method) && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRF-Token', csrf)
    }
    nextInit.headers = headers
    if (!nextInit.credentials) {
      nextInit.credentials = 'include'
    }
    return originalFetch(input, nextInit)
  }
}
