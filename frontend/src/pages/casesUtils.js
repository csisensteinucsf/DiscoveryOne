export const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/i
export const isValidEmail = (value) => EMAIL_REGEX.test((value || '').trim())
export const defaultCaseForm = (closureNagDays = 180) => ({
  name: '',
  legal_case_name: '',
  servicenow_inc_number: '',
  claimant: '',
  matter_number: '',
  internal_counsel: '',
  outside_counsel: '',
  description: '',
  start_date: '',
  requestor: '',
  analyst_id: '',
  additional_requestors: '',
  closure_nag_days: closureNagDays,
  closed: false,
  is_private: false,
})

export const looksLikeEmail = (value) => EMAIL_REGEX.test((value || '').trim())

export const toSentenceCase = (value) => {
  const t = (value || '').trim()
  if (!t) return ''
  return t.charAt(0).toUpperCase() + t.slice(1).toLowerCase()
}

export const firstToken = (value) => {
  const v = (value || '').trim()
  if (!v) return ''
  const [token] = v.split(/[.@\s_-]+/).filter(Boolean)
  return token || v
}

export const nameFromEmail = (value) => {
  const email = (value || '').trim()
  if (!email) return ''
  const local = (email.split('@')[0] || '').trim()
  if (!local) return ''
  const parts = local.split(/[._\s-]+/).filter(Boolean)
  if (!parts.length) return ''
  const [first, ...rest] = parts
  const firstName = toSentenceCase(first)
  const lastName = rest.map(toSentenceCase).join(' ')
  return [firstName, lastName].filter(Boolean).join(' ')
}

export const normalizeGroupValue = (value) => (value || '').trim().toLowerCase()
export const formatGroupLabel = (value) => {
  const normalized = normalizeGroupValue(value)
  if (!normalized) return ''
  return normalized
    .split(' ')
    .filter(Boolean)
    .map(part => (part.length <= 3 ? part.toUpperCase() : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ')
}

export const formatUserName = (person) => {
  if (!person) return ''
  const first = toSentenceCase(person.first_name || '')
  const last = toSentenceCase(person.last_name || '')
  if (first && last) return `${first} ${last}`
  if (first) return first
  if (last) return last
  const username = (person.username || '').trim()
  if (username && !looksLikeEmail(username)) return toSentenceCase(username)
  const fromEmail = nameFromEmail(person.email || username)
  return fromEmail
}

export const displayNameFromEmail = (email, lookup) => {
  const key = (email || '').trim().toLowerCase()
  if (!key) return ''
  const user = lookup.get(key)
  const name = formatUserName(user)
  if (name) return name
  const derived = nameFromEmail(key)
  return derived || ''
}


