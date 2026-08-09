import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const readSource = relativePath => readFileSync(
  new URL(relativePath, import.meta.url),
  'utf8',
)

test('dashboard metrics share one compact uniform tile grid', () => {
  const widgets = readSource('../../src/pages/DashboardWidgets.jsx')
  const styles = readSource('../../src/styles.css')
  const statGroups = widgets.match(/className="dashboard-stat-grid"/g) || []

  assert.equal(statGroups.length, 8)
  assert.match(widgets, /className="dashboard-stat__label"/)
  assert.match(widgets, /className="dashboard-stat__value"/)
  assert.match(styles, /\.dashboard-stat-grid\s*{[^}]*grid-template-columns: repeat\(auto-fill, 104px\)/s)
  assert.match(styles, /\.dashboard-stat\s*{[^}]*width: 104px;[^}]*height: 68px;/s)
  assert.match(styles, /\.dashboard-stat__label\s*{[^}]*font-size: 11px;/s)
  assert.match(styles, /\.dashboard-stat__value\s*{[^}]*font-size: 19px;/s)
})
