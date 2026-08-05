import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('auth normalization retains saved UI preferences', () => {
  const authSource = readSource('../../src/auth.jsx')

  assert.match(authSource, /ui_preferences: payload\.ui_preferences/)
})

test('Cases refreshes the current user after saving visible columns', () => {
  const casesSource = readSource('../../src/pages/Cases.jsx')

  assert.match(casesSource, /const \{ user, refreshUser \} = useAuth\(\)/)
  assert.match(casesSource, /cases_visible_columns: next[\s\S]*?await refreshUser\(\)/)
})
