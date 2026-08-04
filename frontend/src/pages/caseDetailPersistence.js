import { apiBase, readSessionJSON, writeSessionJSON } from './caseDetailUtils.js'

// ---------- Notes local storage ----------
function lsKeyForNotes(caseId){ return `ediscovery:case:${caseId}:notes` }
function loadNotes(caseId){
  const parsed = readSessionJSON(lsKeyForNotes(caseId), [])
  return Array.isArray(parsed) ? parsed : []
}
function saveNotes(caseId,arr){ writeSessionJSON(lsKeyForNotes(caseId), arr || []) }
function mapNoteForUI(n){
  // normalize possible API or LS shapes
  return {
    id: n.id || n.note_id || n.uuid || (crypto?.randomUUID ? crypto.randomUUID() : ('id_'+Math.random().toString(36).slice(2))),
    body: String(n.body ?? n.text ?? '').trim(),
    format: n.format || 'plain',
    author: n.author || n.author_name || null,
    created_at: n.created_at || n.createdAt || new Date().toISOString(),
    updated_at: n.updated_at || n.updatedAt || n.created_at || new Date().toISOString(),
    is_pinned: !!(n.is_pinned || n.pinned)
  }
}
// ---------- Server-first persistence for Notes (fallback to local) ----------
function toApiNote(n){
  return {
    body: (n.body ?? '').trim() || null,
    format: n.format || 'plain',
    is_pinned: !!n.is_pinned
  }
}
function fromApiNote(n){ return mapNoteForUI(n || {}) }
async function serverLoadNotes(caseId){
  const data = await tryFetchJSON(`${apiBase}/cases/${caseId}/notes`)
  return Array.isArray(data) ? data.map(fromApiNote) : null
}
async function serverCreateNote(caseId, payload){
  const body = JSON.stringify(toApiNote(payload))
  const created = await tryFetchJSON(`${apiBase}/cases/${caseId}/notes`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body
  })
  return created ? fromApiNote(created) : null
}
async function serverUpdateNote(caseId, id, payload){
  const body = JSON.stringify(toApiNote(payload))
  const updated = await tryFetchJSON(`${apiBase}/cases/${caseId}/notes/${id}`, {
    method:'PUT', headers:{'Content-Type':'application/json'}, body
  })
  return updated ? fromApiNote(updated) : null
}
async function serverDeleteNote(caseId, id) {
  try {
    // if tryFetchJSON throws on non-2xx, reaching here means success (200/204)
    await tryFetchJSON(`${apiBase}/cases/${caseId}/notes/${id}`, { method: 'DELETE' });
    return true;
  } catch (e) {
    console.error('serverDeleteNote failed:', e);
    return false;
  }
}
// ---------- Server-first persistence for Searches (fallback to local) ----------
// Shape mappers: UI <-> API
const SEARCH_QUERY_MARKER = 'Provider Query:'

function splitSearchAdditional(additionalValue) {
  const raw = typeof additionalValue === 'string' ? additionalValue.trim() : ''
  if (!raw) return { searchOverview: '', providerQuery: '', purviewKql: '' }
  const markerMatch = raw.match(/(?:^|\n)\s*(?:Provider Query|Purview KQL):\s*/i)
  if (!markerMatch || markerMatch.index == null) {
    return { searchOverview: raw, providerQuery: '', purviewKql: '' }
  }
  const markerIndex = markerMatch.index
  const markerLength = markerMatch[0].length
  const searchOverview = raw.slice(0, markerIndex).trim()
  const providerQuery = raw.slice(markerIndex + markerLength).trim()
  return { searchOverview, providerQuery, purviewKql: providerQuery }
}

function combineSearchAdditional({ searchOverview, providerQuery, purviewKql }) {
  const overview = typeof searchOverview === 'string' ? searchOverview.trim() : ''
  const rawQuery = typeof providerQuery === 'string' ? providerQuery : purviewKql
  const query = typeof rawQuery === 'string' ? rawQuery.trim() : ''
  if (overview && query) return `${overview}\n\n${SEARCH_QUERY_MARKER}\n${query}`
  if (query) return `${SEARCH_QUERY_MARKER}\n${query}`
  return overview
}

function normalizeSearchDraftFields(searchLike) {
  const parsed = splitSearchAdditional(searchLike?.additional)
  const searchOverview = typeof searchLike?.searchOverview === 'string'
    ? searchLike.searchOverview
    : parsed.searchOverview
  const providerQuery = typeof searchLike?.providerQuery === 'string'
    ? searchLike.providerQuery
    : (typeof searchLike?.purviewKql === 'string' ? searchLike.purviewKql : parsed.providerQuery)
  const additional = combineSearchAdditional({ searchOverview, providerQuery })
  return { searchOverview, providerQuery, purviewKql: providerQuery, additional }
}

function toApiSearch(s) {
  const noneIfBlank = (x) => (typeof x === 'string' && x.trim() === '') ? null : x;
  const normalized = normalizeSearchDraftFields(s)
  return {
    name: s.name ?? '',
    keywords: noneIfBlank(s.keywords ?? null),
    senders: noneIfBlank(s.senders ?? null),
    recipients: noneIfBlank(s.recipients ?? null),
    date_from: noneIfBlank((s.date_from ?? s.dateFrom) ?? null),
    date_to: noneIfBlank((s.date_to ?? s.dateTo) ?? null),
    additional: noneIfBlank(normalized.additional ?? null),
    status_search: s.status_search ?? 'not performed',
    status_export: s.status_export ?? 'not performed',
    status_delivery: s.status_delivery ?? 'not performed',
    custodian_ids: (s.custodian_ids ?? s.custodianIds ?? []).map(Number),
    hold_ids: (s.hold_ids ?? s.holdIds ?? []).map(Number),
  };
}
function fromApiSearch(s) {
  const normalized = normalizeSearchDraftFields({ additional: s.additional ?? null })
  return {
    id: s.id,
    name: s.name ?? '',
    keywords: s.keywords ?? '',
    additional: normalized.additional || null,
    searchOverview: normalized.searchOverview || '',
    providerQuery: normalized.providerQuery || '',
    purviewKql: normalized.purviewKql || '',
    senders: s.senders ?? null,
    recipients: s.recipients ?? null,
    dateFrom: s.date_from ?? null,
    dateTo: s.date_to ?? null,
    status_search: s.status_search ?? 'not performed',
    status_export: s.status_export ?? 'not performed',
    status_delivery: s.status_delivery ?? 'not performed',
    export_without_consent: !!s.export_without_consent,
    pushed_to_provider: !!s.pushed_to_provider || !!s.provider_search_id || !!s.pushed_to_purview || !!s.purview_search_id,
    provider: s.provider ?? null,
    provider_search_id: s.provider_search_id ?? s.purview_search_id ?? null,
    provider_search_name: s.provider_search_name ?? s.purview_search_name ?? null,
    provider_case_id: s.provider_case_id ?? s.purview_case_id ?? null,
    pushed_to_purview: !!s.pushed_to_purview || !!s.purview_search_id,
    purview_search_id: s.purview_search_id ?? null,
    purview_search_name: s.purview_search_name ?? null,
    purview_case_id: s.purview_case_id ?? null,
    custodianIds: (s.custodian_ids ?? []).map(Number),
    holdIds: (s.hold_ids ?? []).map(Number),
    holdStatuses: Array.isArray(s.hold_statuses) ? s.hold_statuses : [],
  };
}
function isSearchPushedToProvider(search) {
  return !!search?.pushed_to_provider
    || !!String(search?.provider_search_id || '').trim()
    || !!search?.pushed_to_purview
    || !!String(search?.purview_search_id || '').trim()
}
function isSearchPushedToPurview(search) {
  return isSearchPushedToProvider(search)
}
function mergeSearchClientState(serverSearches, cachedSearches) {
  const cachedById = new Map((cachedSearches || []).map(search => [Number(search?.id), search]))
  return (serverSearches || []).map(search => {
    const cached = cachedById.get(Number(search?.id))
    if (!cached || !isSearchPushedToProvider(cached)) return search
    return {
      ...search,
      pushed_to_provider: true,
      provider: cached?.provider || search?.provider || null,
      provider_search_id: cached?.provider_search_id || cached?.purview_search_id || search?.provider_search_id || search?.purview_search_id || null,
      provider_search_name: cached?.provider_search_name || cached?.purview_search_name || search?.provider_search_name || search?.purview_search_name || null,
      provider_case_id: cached?.provider_case_id || cached?.purview_case_id || search?.provider_case_id || search?.purview_case_id || null,
      pushed_to_purview: true,
      purview_search_id: cached?.purview_search_id || search?.purview_search_id || null,
      purview_search_name: cached?.purview_search_name || search?.purview_search_name || null,
      purview_case_id: cached?.purview_case_id || search?.purview_case_id || null,
    }
  })
}
async function tryFetchJSON(url, options) {
  try {
    const r = await fetch(url, { credentials:'include', ...options })
    if (!r.ok) throw new Error('HTTP ' + r.status)
    if (r.status === 204) return {} // delete ok
    return await r.json()
  } catch {
    return null
  }
}
async function serverLoadSearches(caseId) {
  const data = await tryFetchJSON(`${apiBase}/cases/${caseId}/searches`)
  return Array.isArray(data) ? data.map(fromApiSearch) : null
}
async function serverCreateSearch(caseId, payload) {
  const body = JSON.stringify(toApiSearch(payload))
  const created = await tryFetchJSON(`${apiBase}/cases/${caseId}/searches`, {
    method:'POST', headers:{'Content-Type':'application/json'}, body
  })
  return created ? fromApiSearch(created) : null
}
async function serverUpdateSearch(caseId, id, payload) {
  const body = JSON.stringify(toApiSearch(payload))
  const updated = await tryFetchJSON(`${apiBase}/cases/${caseId}/searches/${id}`, {
    method:'PUT', headers:{'Content-Type':'application/json'}, body
  })
  return updated ? fromApiSearch(updated) : null
}
async function serverDeleteSearch(caseId, id) {
  return await tryFetchJSON(`${apiBase}/cases/${caseId}/searches/${id}`, { method:'DELETE' })
}
async function serverPushSearchToProvider(caseId, id, payload = {}) {
  const res = await fetch(`${apiBase}/cases/${caseId}/searches/${id}/push_to_provider`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
  const raw = await res.text().catch(() => '')
  let data = null
  try {
    data = raw ? JSON.parse(raw) : null
  } catch {
    data = null
  }
  if (!res.ok) {
    const detail = (data && typeof data === 'object' ? data.detail : null) || raw || `HTTP ${res.status}`
    throw new Error(detail)
  }
  return data && typeof data === 'object' ? data : {}
}

async function serverPushSearchToPurview(caseId, id, payload = {}) {
  return serverPushSearchToProvider(caseId, id, payload)
}

async function serverSuggestSearches(caseId, payload) {
  const res = await fetch(`${apiBase}/cases/${caseId}/searches/ai_suggest`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
  })
  const raw = await res.text().catch(() => '')
  let data = null
  try {
    data = raw ? JSON.parse(raw) : null
  } catch {
    data = null
  }
  if (!res.ok) {
    const detail = (data && typeof data === 'object' ? data.detail : null) || raw || `HTTP ${res.status}`
    throw new Error(detail)
  }
  if (!data || typeof data !== 'object') {
    throw new Error('Invalid AI search suggestion response')
  }
  return data
}

function aiSuggestionToDraft(suggestion) {
  const kql = String(suggestion?.kql || '').trim()
  const normalized = normalizeSearchDraftFields({
    searchOverview: suggestion?.additional || '',
    providerQuery: kql,
  })
  return {
    id: null,
    name: '',
    keywords: suggestion?.keywords || '',
    senders: suggestion?.senders || '',
    recipients: suggestion?.recipients || '',
    dateFrom: suggestion?.date_from || '',
    dateTo: suggestion?.date_to || '',
    additional: normalized.additional,
    searchOverview: normalized.searchOverview,
    providerQuery: normalized.providerQuery,
    purviewKql: normalized.purviewKql,
    custodianIds: Array.isArray(suggestion?.custodian_ids) ? suggestion.custodian_ids.map(Number).filter(Number.isFinite) : [],
    holdIds: Array.isArray(suggestion?.hold_ids) ? suggestion.hold_ids.map(Number).filter(Number.isFinite) : [],
    status: { search: 'not performed', export: 'not performed', delivery: 'not performed' },
    status_search: 'not performed',
    status_export: 'not performed',
    status_delivery: 'not performed',
  }
}

export {
  lsKeyForNotes,
  loadNotes,
  saveNotes,
  mapNoteForUI,
  toApiNote,
  fromApiNote,
  serverLoadNotes,
  serverCreateNote,
  serverUpdateNote,
  serverDeleteNote,
  splitSearchAdditional,
  combineSearchAdditional,
  normalizeSearchDraftFields,
  toApiSearch,
  fromApiSearch,
  isSearchPushedToProvider,
  isSearchPushedToPurview,
  mergeSearchClientState,
  tryFetchJSON,
  serverLoadSearches,
  serverCreateSearch,
  serverUpdateSearch,
  serverDeleteSearch,
  serverPushSearchToProvider,
  serverPushSearchToPurview,
  serverSuggestSearches,
  aiSuggestionToDraft
}
