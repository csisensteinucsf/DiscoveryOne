export const CUSTOM_FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'textarea', label: 'Long text' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'checkbox', label: 'Checkbox' },
  { value: 'select', label: 'Dropdown' },
]

export function createCustomFieldDefinition(existing = []) {
  const keys = new Set((existing || []).map(field => field?.key).filter(Boolean))
  let index = keys.size + 1
  let key = `custom_field_${index}`
  while (keys.has(key)) {
    index += 1
    key = `custom_field_${index}`
  }
  return {
    key,
    label: '',
    field_type: 'text',
    required: false,
    options: [],
    default_value: null,
  }
}

export function customFieldsFromDefinitions(definitions = [], existing = {}) {
  return Object.fromEntries((definitions || []).filter(field => field?.key).map(definition => {
    const current = existing?.[definition.key]
    const hasCurrentValue = current && typeof current === 'object'
      ? Object.prototype.hasOwnProperty.call(current, 'value')
      : current !== undefined
    const currentValue = current && typeof current === 'object' ? current.value : current
    const fallback = definition.default_value ?? (definition.field_type === 'checkbox' ? false : '')
    return [definition.key, {
      label: definition.label || definition.key,
      field_type: definition.field_type || 'text',
      required: !!definition.required,
      options: Array.isArray(definition.options) ? definition.options : [],
      value: hasCurrentValue ? currentValue : fallback,
    }]
  }))
}

export function normalizeStoredCustomFields(customFields = {}) {
  if (!customFields || typeof customFields !== 'object' || Array.isArray(customFields)) return {}
  return Object.fromEntries(Object.entries(customFields).filter(([, field]) => field && typeof field === 'object').map(([key, field]) => [
    key,
    {
      label: field.label || key.replaceAll('_', ' '),
      field_type: field.field_type || 'text',
      required: !!field.required,
      options: Array.isArray(field.options) ? field.options : [],
      value: field.value ?? (field.field_type === 'checkbox' ? false : ''),
    },
  ]))
}
export function customFieldValues(customFields = {}) {
  if (!customFields || typeof customFields !== 'object' || Array.isArray(customFields)) return {}
  return Object.fromEntries(Object.entries(customFields).map(([key, field]) => [
    key,
    field && typeof field === 'object' ? field.value : field,
  ]))
}


export function withCustomFieldValue(customFields, key, value) {
  const current = customFields?.[key]
  if (!current) return customFields || {}
  return {
    ...customFields,
    [key]: { ...current, value },
  }
}

export function formatCustomFieldValue(field) {
  if (!field) return '-'
  if (field.field_type === 'checkbox') return field.value ? 'Yes' : 'No'
  if (field.value === null || field.value === undefined || field.value === '') return '-'
  return String(field.value)
}
