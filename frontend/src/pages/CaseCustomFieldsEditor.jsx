import {
  formatCustomFieldValue,
  withCustomFieldValue,
} from './caseCustomFields.js'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'

function CustomFieldInput({ field, onChange }) {
  const value = field?.value ?? (field?.field_type === 'checkbox' ? false : '')
  if (field.field_type === 'textarea') {
    return <textarea className="input" rows={3} value={value} required={field.required} onChange={event => onChange(event.target.value)} />
  }
  if (field.field_type === 'select') {
    return (
      <select className="input" value={value} required={field.required} onChange={event => onChange(event.target.value)}>
        <option value="">Select an option</option>
        {(field.options || []).map(option => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }
  if (field.field_type === 'checkbox') {
    return (
      <span className="custom-case-field__checkbox">
        <input type="checkbox" checked={!!value} onChange={event => onChange(event.target.checked)} />
        <span>{value ? 'Yes' : 'No'}</span>
      </span>
    )
  }
  return (
    <input
      className="input"
      type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'}
      value={value}
      required={field.required}
      onChange={event => onChange(event.target.value)}
    />
  )
}

export default function CaseCustomFieldsEditor({ customFields, onChange }) {
  const entries = Object.entries(customFields || {})
  if (!entries.length) return null
  return (
    <section className="custom-case-fields">
      <h4>Additional case information</h4>
      <div className="custom-case-fields__grid">
        {entries.map(([key, field]) => (
          <label key={key} className={field.field_type === 'textarea' ? 'custom-case-field custom-case-field--wide' : 'custom-case-field'}>
            <RequiredFieldLabel required={field.required}>
              {field.label}
            </RequiredFieldLabel>
            <CustomFieldInput
              field={field}
              onChange={value => onChange(withCustomFieldValue(customFields, key, value))}
            />
          </label>
        ))}
      </div>
    </section>
  )
}

export function CustomFieldReadout({ field }) {
  return <>{formatCustomFieldValue(field)}</>
}
