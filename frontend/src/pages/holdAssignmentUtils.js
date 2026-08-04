export function normalizeOptionalHoldIds(values) {
  return [...new Set(
    (Array.isArray(values) ? values : [])
      .map(Number)
      .filter(value => Number.isFinite(value) && value > 0)
  )]
}

export function buildCustodianWorkflowQuery(mode, holdIds = []) {
  const params = new URLSearchParams({
    action: 'custodians',
    mode: mode === 'import' ? 'import' : 'add',
  })
  const normalized = normalizeOptionalHoldIds(holdIds)
  if (normalized.length) params.set('hold_ids', normalized.join(','))
  return params
}
