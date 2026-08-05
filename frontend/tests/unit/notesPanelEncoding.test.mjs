import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(
  new URL('../../src/components/NotesPanel.jsx', import.meta.url),
  'utf8',
)

test('Ticket Notes uses stable icons and contains no mojibake text', () => {
  assert.match(source, /import \{ Paperclip, X \} from 'lucide-react'/)
  assert.equal((source.match(/<Paperclip/g) || []).length, 3)
  assert.match(source, /<X size=\{14\}/)
  assert.doesNotMatch(source, /[\u00c3\u00e2\u00f0\u0178]/u)
  assert.match(source, /Uploading\.\.\./)
  assert.match(source, /Saving\.\.\./)
  assert.match(source, /Loading\.\.\./)
})
