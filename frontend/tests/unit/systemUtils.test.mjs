import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

import { normalizeGroupValue } from '../../src/pages/systemUtils.js'

test('group normalization is provided by a stable shared utility', () => {
  assert.equal(normalizeGroupValue('  Legal Operations  '), 'legal operations')
  assert.equal(normalizeGroupValue(null), '')
})

test('System does not recreate the NTP group normalizer during render', async () => {
  const source = await readFile(new URL('../../src/pages/System.jsx', import.meta.url), 'utf8')

  assert.match(source, /import \{ normalizeGroupValue \} from '\.\/systemUtils\.js'/)
  assert.doesNotMatch(source, /\bconst normalizeGroupValue\s*=/)
})
