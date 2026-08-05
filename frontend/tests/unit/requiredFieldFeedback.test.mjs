import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'

const sourceRoot = new URL('../../src/', import.meta.url)

function jsxFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => (
    entry.isDirectory()
      ? jsxFiles(new URL(`${entry.name}/`, directory))
      : entry.name.endsWith('.jsx') ? [new URL(entry.name, directory)] : []
  ))
}

test('input-facing JSX no longer labels fields as optional', () => {
  for (const file of jsxFiles(sourceRoot)) {
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /\boptional\b/i, file.pathname)
  }
})

test('native required forms use app-level inline feedback', () => {
  const feedback = readFileSync(new URL('../../src/components/RequiredFormFeedback.jsx', import.meta.url), 'utf8')
  const app = readFileSync(new URL('../../src/App.jsx', import.meta.url), 'utf8')
  const styles = readFileSync(new URL('../../src/styles.css', import.meta.url), 'utf8')

  assert.match(feedback, /document\.addEventListener\('invalid', onInvalid, true\)/)
  assert.match(feedback, /event\.preventDefault\(\)/)
  assert.match(feedback, /form\.dataset\.requiredFeedback = 'true'/)
  assert.match(app, /<RequiredFormFeedback \/>/)
  assert.match(styles, /form\[data-required-feedback='true'\]::after/)
  assert.match(styles, /content: 'Missing required fields'/)
})

test('Edit Case uses required markers and missing-field feedback', () => {
  const source = readFileSync(new URL('../../src/pages/CaseDetailModals.jsx', import.meta.url), 'utf8')

  assert.doesNotMatch(source, /\boptional\b/i)
  assert.match(source, /form="edit-case-form"/)
  assert.match(source, /RequiredFieldLabel/)
  assert.match(source, /findMissingRequiredControls/)
  assert.match(source, /Missing required fields/)
  assert.match(source, /onSubmit={handleSubmit}/)
})

test('required markers use one nonbreaking label component everywhere', () => {
  const labelSource = readFileSync(new URL('../../src/components/RequiredFieldLabel.jsx', import.meta.url), 'utf8')
  const styles = readFileSync(new URL('../../src/styles.css', import.meta.url), 'utf8')

  assert.match(labelSource, /\\u00A0\*/)
  assert.match(styles, /\.case-editor-required-mark\s*{[^}]*white-space: nowrap/s)
  for (const file of jsxFiles(sourceRoot)) {
    if (file.pathname.endsWith('/RequiredFieldLabel.jsx')) continue
    const source = readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /case-editor-required-mark/, file.pathname)
  }
})
