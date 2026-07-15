const CACHE_TTL_MS = 30000
const settingsCache = new Map()

function cacheKey(apiBase) {
  return (apiBase || '/api').replace(/\/$/, '') || '/api'
}

export function invalidateSystemSettingsCache(apiBase = '/api') {
  settingsCache.delete(cacheKey(apiBase))
}

export async function fetchSystemSettings(apiBase = '/api', { force = false } = {}) {
  const key = cacheKey(apiBase)
  const now = Date.now()
  const cached = settingsCache.get(key)

  if (!force && cached?.data && cached.expiresAt > now) {
    return cached.data
  }

  if (!force && cached?.inflight) {
    return cached.inflight
  }

  const inflight = fetch(`${key}/system/settings`, { credentials: 'include' })
    .then(async (res) => {
      if (!res.ok) {
        throw new Error('Unable to load system settings')
      }
      const data = await res.json()
      settingsCache.set(key, { data, expiresAt: Date.now() + CACHE_TTL_MS, inflight: null })
      return data
    })
    .catch((err) => {
      const current = settingsCache.get(key)
      if (current?.data) {
        // Keep stale cache briefly so dependent UI can continue rendering.
        settingsCache.set(key, { data: current.data, expiresAt: Date.now() + 5000, inflight: null })
        return current.data
      }
      settingsCache.delete(key)
      throw err
    })

  settingsCache.set(key, {
    data: cached?.data || null,
    expiresAt: cached?.expiresAt || 0,
    inflight,
  })

  return inflight
}
