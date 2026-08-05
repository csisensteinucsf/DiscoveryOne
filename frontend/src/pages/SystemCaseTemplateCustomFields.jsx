import { Plus, Trash2 } from 'lucide-react'
import {
  CUSTOM_FIELD_TYPES,
  createCustomFieldDefinition,
} from './caseCustomFields.js'

function CustomDefaultInput({ field, onChange }) {
  const value = field.default_value ?? (field.field_type === 'checkbox' ? false : '')
  if (field.field_type === 'checkbox') {
    return (
      <select value={field.default_value === null || field.default_value === undefined ? '' : String(!!field.default_value)} onChange={event => onChange(event.target.value === '' ? null : event.target.value === 'true')}>
        <option value="">No default</option>
        <option value="false">No</option>
        <option value="true">Yes</option>
      </select>
    )
  }
  if (field.field_type === 'select') {
    return (
      <select value={value} onChange={event => onChange(event.target.value || null)}>
        <option value="">No default</option>
        {(field.options || []).map(option => <option key={option} value={option}>{option}</option>)}
      </select>
    )
  }
  if (field.field_type === 'textarea') {
    return <textarea rows={2} value={value} onChange={event => onChange(event.target.value || null)} />
  }
  return (
    <input
      type={field.field_type === 'number' ? 'number' : field.field_type === 'date' ? 'date' : 'text'}
      value={value}
      onChange={event => onChange(event.target.value || null)}
    />
  )
}

export default function SystemCaseTemplateCustomFields({ editor, setEditor }) {
  const fields = editor.custom_fields || []
  const addField = () => {
    setEditor(current => ({
      ...current,
      custom_fields: [...(current.custom_fields || []), createCustomFieldDefinition(current.custom_fields)],
    }))
  }
  const updateField = (index, changes) => {
    setEditor(current => ({
      ...current,
      custom_fields: (current.custom_fields || []).map((field, fieldIndex) => (
        fieldIndex === index ? { ...field, ...changes } : field
      )),
    }))
  }
  const removeField = index => {
    setEditor(current => ({
      ...current,
      custom_fields: (current.custom_fields || []).filter((_, fieldIndex) => fieldIndex !== index),
    }))
  }

  return (
    <section className="case-template-custom-fields">
      <div className="case-template-custom-fields__heading">
        <div>
          <strong>Custom fields</strong>
          <p>Add organization-specific information to this template and its New Case form.</p>
        </div>
        <button className="btn secondary compact" type="button" onClick={addField} disabled={fields.length >= 25}>
          <Plus size={15} /> Add Field
        </button>
      </div>
      {fields.map((field, index) => (
        <div className="case-template-custom-field" key={field.key}>
          <label>
            Field label
            <input value={field.label || ''} maxLength={120} onChange={event => updateField(index, { label: event.target.value })} placeholder="e.g., Business unit" />
          </label>
          <label>
            Type
            <select
              value={field.field_type || 'text'}
              onChange={event => updateField(index, {
                field_type: event.target.value,
                options: event.target.value === 'select' ? field.options || [] : [],
                default_value: null,
              })}
            >
              {CUSTOM_FIELD_TYPES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="case-template-option">
            <input type="checkbox" checked={!!field.required} onChange={event => updateField(index, { required: event.target.checked })} />
            <span>Required</span>
          </label>
          <label>
            Default
            <CustomDefaultInput field={field} onChange={defaultValue => updateField(index, { default_value: defaultValue })} />
          </label>
          <button className="icon-button" type="button" title="Remove custom field" aria-label={`Remove ${field.label || 'custom field'}`} onClick={() => removeField(index)}>
            <Trash2 size={16} />
          </button>
          {field.field_type === 'select' && (
            <label className="case-template-custom-field__options">
              Dropdown options
              <input
                value={(field.options || []).join(', ')}
                onChange={event => {
                  const options = event.target.value.split(',').map(option => option.trim()).filter(Boolean)
                  updateField(index, {
                    options,
                    default_value: options.includes(field.default_value) ? field.default_value : null,
                  })
                }}
                placeholder="Option one, Option two"
              />
            </label>
          )}
        </div>
      ))}
      {!fields.length && <div className="form-help">No custom fields added.</div>}
    </section>
  )
}
