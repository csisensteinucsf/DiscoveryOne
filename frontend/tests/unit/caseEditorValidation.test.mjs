import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  findInvalidFormControls,
  findMissingRequiredControls,
  optionalDateValue,
} from '../../src/pages/casesUtils.js'

const control = ({
  required = false,
  disabled = false,
  valueMissing = false,
  valid = true,
} = {}) => ({
  required,
  disabled,
  validity: { valueMissing },
  checkValidity: () => valid,
})

test('missing required controls exclude optional, valid, and disabled fields', () => {
  const missing = control({ required: true, valueMissing: true, valid: false })
  const validRequired = control({ required: true })
  const optional = control({ valueMissing: true, valid: false })
  const disabled = control({ required: true, disabled: true, valueMissing: true, valid: false })

  assert.deepEqual(
    findMissingRequiredControls({ elements: [missing, validRequired, optional, disabled] }),
    [missing],
  )
})

test('invalid controls preserve non-missing browser validation', () => {
  const valid = control()
  const invalidEmail = control({ valid: false })
  const disabledInvalid = control({ disabled: true, valid: false })

  assert.deepEqual(
    findInvalidFormControls({ elements: [valid, invalidEmail, disabledInvalid] }),
    [invalidEmail],
  )
})

test('blank optional case dates are serialized as null', () => {
  assert.equal(optionalDateValue(''), null)
  assert.equal(optionalDateValue('   '), null)
  assert.equal(optionalDateValue(null), null)
  assert.equal(optionalDateValue(undefined), null)
  assert.equal(optionalDateValue('2026-08-05'), '2026-08-05')

  const casesSource = readFileSync(
    new URL('../../src/pages/Cases.jsx', import.meta.url),
    'utf8',
  )
  assert.match(casesSource, /start_date: optionalDateValue\(form\.start_date\)/)
})

test('New Case uses compact required markers and bottom-of-modal error feedback', () => {
  const modalSource = readFileSync(
    new URL('../../src/pages/CaseModals.jsx', import.meta.url),
    'utf8',
  )
  const customFieldSource = readFileSync(
    new URL('../../src/pages/CaseCustomFieldsEditor.jsx', import.meta.url),
    'utf8',
  )
  const styles = readFileSync(
    new URL('../../src/styles.css', import.meta.url),
    'utf8',
  )

  assert.doesNotMatch(modalSource, /\(optional\)|fieldSuffix/)
  assert.doesNotMatch(customFieldSource, /\(optional\)|\(required\)/)
  assert.match(modalSource, /RequiredFieldLabel/)
  assert.match(modalSource, />missing required fields</)
  assert.match(modalSource, /case-editor-two-column/)
  assert.match(styles, /data-show-missing-required='true'/)
})
