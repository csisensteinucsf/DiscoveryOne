export const EMPLOYMENT_STATUS_OPTIONS = ['Active', 'Inactive']

export function normalizeEmploymentStatus(value) {
  const text = String(value || '').trim()
  const normalized = text.toLowerCase()
  if (!normalized) return ''
  if (normalized === 'active') return 'Active'
  if (normalized === 'inactive' || normalized.startsWith('separated')) return 'Inactive'
  return text
}

export function isEmploymentStatusOption(value) {
  const normalized = normalizeEmploymentStatus(value)
  return !normalized || EMPLOYMENT_STATUS_OPTIONS.includes(normalized)
}

export default function CustodianEmploymentStatusSelect({ value, onChange, ...props }) {
  const normalized = normalizeEmploymentStatus(value)
  const unsupported = normalized && !EMPLOYMENT_STATUS_OPTIONS.includes(normalized)
  return (
    <select
      {...props}
      className={'input' + (props.className ? ` ${props.className}` : '')}
      value={normalized}
      onChange={event => onChange(event.target.value)}
    >
      <option value="">Not specified</option>
      {unsupported ? <option value={normalized} disabled>{normalized} (select Active or Inactive)</option> : null}
      {EMPLOYMENT_STATUS_OPTIONS.map(option => <option key={option} value={option}>{option}</option>)}
    </select>
  )
}