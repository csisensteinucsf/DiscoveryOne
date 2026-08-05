import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  nextCaseTemplateSortOrder,
  mergeSavedCaseTemplate,
  reorderCaseTemplates,
  templateOrderUpdates,
} from '../../src/pages/caseTemplateOrder.js'

const templates = [
  { id: 1, name: 'One', sort_order: 100 },
  { id: 2, name: 'Two', sort_order: 100 },
  { id: 3, name: 'Three', sort_order: 200 },
]

test('templates can be dropped before or after another template', () => {
  assert.deepEqual(
    reorderCaseTemplates(templates, 3, 1, 'before').map(template => template.id),
    [3, 1, 2],
  )
  assert.deepEqual(
    reorderCaseTemplates(templates, 1, 3, 'after').map(template => template.id),
    [2, 3, 1],
  )
})

test('drag ordering uses stable internal values and places new templates last', () => {
  assert.deepEqual(templateOrderUpdates(templates), [
    { id: 1, sort_order: 10 },
    { id: 2, sort_order: 20 },
    { id: 3, sort_order: 30 },
  ])
  assert.equal(nextCaseTemplateSortOrder(templates), 210)
})

test('template management exposes a drag handle instead of numeric order controls', () => {
  const source = readFileSync(
    new URL('../../src/pages/SystemCaseTemplatesPanel.jsx', import.meta.url),
    'utf8',
  )

  assert.match(source, /GripVertical/)
  assert.match(source, /Drag to reorder/)
  assert.doesNotMatch(source, /Display order/)
  assert.doesNotMatch(source, /<th>Order<\/th>/)
})

test('saved templates replace their list entry without a second reload', () => {
  const updated = mergeSavedCaseTemplate(
    templates.map(template => ({ ...template, is_default: template.id === 1 })),
    { id: 2, name: 'Two updated', sort_order: 100, is_default: true },
  )

  assert.deepEqual(updated.map(template => template.id), [1, 2, 3])
  assert.equal(updated.find(template => template.id === 1).is_default, false)
})
