import test from 'node:test'
import assert from 'node:assert/strict'
import {
  buildPreservationDetailCsv,
  timelineForHold,
} from '../../src/pages/preservationDetailCsv.js'

test('Preservation Detail CSV exports every custodian in the selected Hold', () => {
  const hold = {
    id: 7,
    name: 'Hold A',
    status: 'active',
    custodians: [
      {
        custodian_id: 11,
        name: 'Jane Doe',
        email: 'jane@example.test',
        preservation_sources: [{
          source_key: 'email',
          source_label: 'Email',
          status: 'active',
          automation_ready: true,
          provider_reference: 'ref-1',
          updated_at: '2026-08-20T10:00:00Z',
        }],
      },
      {
        custodian_id: 12,
        name: 'John Smith',
        email: 'john@example.test',
        preservation_sources: [{
          source_key: 'box',
          source_label: 'Box',
          status: 'pending',
          automation_ready: false,
        }],
      },
    ],
  }
  const detailRows = [
    {
      id: 11,
      timeline: [
        { hold_label: 'Email', state: 'active', summary: 'Applied', details: { raw_details: { hold_id: 7 } } },
        { hold_label: 'Email', state: 'released', summary: 'Other Hold', details: { raw_details: { hold_id: 8 } } },
      ],
    },
    {
      id: 12,
      timeline: [{ hold_label: 'Box', state: 'pending', summary: '=unsafe', details: { hold_id: 7 } }],
    },
  ]

  const csv = buildPreservationDetailCsv({ hold, detailRows })

  assert.match(csv, /Jane Doe/)
  assert.match(csv, /John Smith/)
  assert.match(csv, /Current status/)
  assert.match(csv, /Timeline event/)
  assert.match(csv, /Applied/)
  assert.doesNotMatch(csv, /Other Hold/)
  assert.match(csv, /'=unsafe/)
})

test('timelineForHold retains legacy events and excludes events assigned to another Hold', () => {
  const row = {
    timeline: [
      { id: 1, details: { hold_id: 4 } },
      { id: 2, details: { raw_details: { hold_id: 5 } } },
      { id: 3, details: {} },
    ],
  }

  assert.deepEqual(timelineForHold(row, 4).map(event => event.id), [1, 3])
})