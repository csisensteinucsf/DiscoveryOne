import test from 'node:test'
import assert from 'node:assert/strict'

import {
  custodianDetailPath,
  dashboardDrilldownWidth,
  dashboardWidgetTitle,
  dashboardWidgetTypeLabel,
  mergePreservationDrilldownItems,
  shouldCompactDashboardDrilldown,
} from '../../src/pages/dashboardUtils.js'

test('preservation widget keeps internal keys but uses user-facing wording', () => {
  assert.equal(dashboardWidgetTitle({ type: 'hold_status', title: 'Holds' }), 'Preservation')
  assert.equal(dashboardWidgetTitle({ type: 'hold_status', title: 'My Sources' }), 'My Sources')
  assert.equal(dashboardWidgetTypeLabel('hold_status'), 'preservation status')
})

test('preservation drilldown merges active and pending rows for one custodian', () => {
  const active = [{
    case_id: 4,
    hold_id: 8,
    custodian_id: 12,
    custodian_name: 'Alex User',
    holds_active: { email: true },
    holds_pending: {},
  }]
  const pending = [{
    case_id: 4,
    hold_id: 8,
    custodian_id: 12,
    custodian_name: 'Alex User',
    holds_active: {},
    holds_pending: { slack: true },
  }]

  assert.deepEqual(mergePreservationDrilldownItems(active, pending), [{
    case_id: 4,
    hold_id: 8,
    custodian_id: 12,
    custodian_name: 'Alex User',
    holds_active: { email: true },
    holds_pending: { slack: true },
  }])
})

test('drilldown modal width shrinks for empty content and expands for tables', () => {
  assert.equal(dashboardDrilldownWidth('searches_list', 0), 480)
  assert.equal(dashboardDrilldownWidth('searches_list', 3), 1080)
  assert.equal(dashboardDrilldownWidth('unknown', 1), 760)
})

test('drilldown modal compacts only after loading confirms there are no items', () => {
  assert.equal(shouldCompactDashboardDrilldown(false, 0), true)
  assert.equal(shouldCompactDashboardDrilldown(true, 0), false)
  assert.equal(shouldCompactDashboardDrilldown(false, 1), false)
})

test('custodian detail target prefers email and falls back to name', () => {
  assert.equal(
    custodianDetailPath({ custodian_email: 'alex@example.edu', custodian_name: 'Alex User' }),
    '/custodians/detail?email=alex%40example.edu',
  )
  assert.equal(
    custodianDetailPath({ custodian_name: 'Alex User' }),
    '/custodians/detail?name=Alex+User',
  )
  assert.equal(custodianDetailPath({}), '')
})
