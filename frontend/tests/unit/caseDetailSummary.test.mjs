import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('case metadata is grouped into a semantic responsive summary', () => {
  const source = readSource('../../src/pages/CaseDetailHeader.jsx')
  const styles = readSource('../../src/styles.css')

  assert.match(source, /<section className="case-detail-summary" aria-label="Case summary">/)
  assert.match(source, /<h3>Case details<\/h3>/)
  assert.match(source, /<h3>People &amp; access<\/h3>/)
  assert.match(source, /<dl className="case-detail-summary__list">/)
  assert.match(source, /<SummaryItem label="Requestors" wide>/)
  assert.match(source, /<h3>Additional information<\/h3>/)
  assert.match(source, /<h3>Additional notes \/ comments<\/h3>/)

  assert.match(styles, /\.case-detail-summary\s*{[^}]*grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/s)
  assert.match(styles, /@media \(max-width: 900px\)[\s\S]*?\.case-detail-summary\s*{[^}]*grid-template-columns: 1fr/s)
})
