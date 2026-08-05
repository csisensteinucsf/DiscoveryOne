import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  createCustomFieldDefinition,
  customFieldsFromDefinitions,
  customFieldValues,
  formatCustomFieldValue,
  normalizeStoredCustomFields,
  withCustomFieldValue,
} from '../../src/pages/caseCustomFields.js'

test('template custom-field definitions produce typed form defaults and API values', () => {
  const definitions = [
    {
      key: 'business_unit',
      label: 'Business unit',
      field_type: 'select',
      required: true,
      options: ['Legal', 'HR'],
      default_value: 'Legal',
    },
    {
      key: 'urgent',
      label: 'Urgent',
      field_type: 'checkbox',
      required: false,
      options: [],
      default_value: null,
    },
  ]

  const fields = customFieldsFromDefinitions(definitions)
  assert.equal(fields.business_unit.value, 'Legal')
  assert.equal(fields.business_unit.required, true)
  assert.equal(fields.urgent.value, false)
  assert.deepEqual(customFieldValues(fields), { business_unit: 'Legal', urgent: false })
})

test('stored custom fields preserve false and zero values', () => {
  const normalized = normalizeStoredCustomFields({
    urgent: { label: 'Urgent', field_type: 'checkbox', value: false },
    volume: { label: 'Volume', field_type: 'number', value: 0 },
  })

  assert.equal(normalized.urgent.value, false)
  assert.equal(normalized.volume.value, 0)
  assert.equal(formatCustomFieldValue(normalized.urgent), 'No')
  assert.equal(formatCustomFieldValue(normalized.volume), '0')
})

test('custom field updates are immutable and generated keys remain unique', () => {
  const fields = customFieldsFromDefinitions([
    { key: 'custom_field_1', label: 'One', field_type: 'text' },
    { key: 'custom_field_3', label: 'Three', field_type: 'text' },
  ])
  const updated = withCustomFieldValue(fields, 'custom_field_1', 'Changed')

  assert.equal(fields.custom_field_1.value, '')
  assert.equal(updated.custom_field_1.value, 'Changed')
  assert.equal(createCustomFieldDefinition([
    { key: 'custom_field_1' },
    { key: 'custom_field_3' },
  ]).key, 'custom_field_4')
})

test('template flags use compact Enabled and Default labels', () => {
  const source = readFileSync(
    new URL('../../src/pages/SystemCaseTemplatesPanel.jsx', import.meta.url),
    'utf8',
  )
  assert.doesNotMatch(source, /Use by default for new cases/)
  assert.match(source, /<span>Enabled<\/span>/)
  assert.match(source, /<span>Default<\/span>/)
  assert.match(source, /className="case-template-options"/)
})

test('template custom fields use clean aligned labeled controls', () => {
  const source = readFileSync(
    new URL('../../src/pages/SystemCaseTemplateCustomFields.jsx', import.meta.url),
    'utf8',
  )
  const panelSource = readFileSync(
    new URL('../../src/pages/SystemCaseTemplatesPanel.jsx', import.meta.url),
    'utf8',
  )
  const styles = readFileSync(new URL('../../src/styles.css', import.meta.url), 'utf8')

  assert.match(source, /<span>Default value<\/span>/)
  assert.match(source, /case-template-custom-field__required-control/)
  assert.match(source, /<DeleteIconButton/)
  assert.match(panelSource, /<RequiredFieldLabel>Template name<\/RequiredFieldLabel>/)
  assert.match(styles, /\.case-template-custom-field\s*{[^}]*grid-template-columns:/s)
})

test('template saves cannot leave the editor stuck in a busy state', () => {
  const source = readFileSync(
    new URL('../../src/pages/SystemCaseTemplatesPanel.jsx', import.meta.url),
    'utf8',
  )
  const saveBlock = source.slice(source.indexOf('const save = async'), source.indexOf('const remove = async'))

  assert.match(saveBlock, /new AbortController\(\)/)
  assert.match(saveBlock, /signal: controller\.signal/)
  assert.match(saveBlock, /catch \(error\)/)
  assert.match(saveBlock, /finally[\s\S]*?setBusy\(false\)/)
  assert.match(saveBlock, /mergeSavedCaseTemplate/)
  assert.doesNotMatch(saveBlock, /await load\(\)/)
  assert.match(source, /case-template-editor-status/)
})
