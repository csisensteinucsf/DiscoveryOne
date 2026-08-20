const csvCell = value => {
  let text = value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value)
  if (/^[=+\-@]/.test(text)) text = `'${text}`
  return `"${text.replaceAll('"', '""')}"`
}

const sourceStateFlags = status => {
  const normalized = String(status || 'not_started').trim().toLowerCase().replaceAll(' ', '_')
  return {
    active: normalized === 'active' ? 'Yes' : 'No',
    pending: normalized === 'pending' ? 'Yes' : 'No',
    failed: normalized === 'failed' ? 'Yes' : 'No',
    released: normalized === 'released' ? 'Yes' : 'No',
  }
}

export function timelineForHold(row, holdId, isTech = false, techHoldKeySet = new Set()) {
  return (Array.isArray(row?.timeline) ? row.timeline : []).filter(event => {
    if (isTech && !techHoldKeySet.has(event?.hold_key)) return false
    const eventHoldId = event?.details?.hold_id ?? event?.details?.raw_details?.hold_id
    return eventHoldId == null || String(eventHoldId) === String(holdId)
  })
}

export function buildPreservationDetailCsv({ hold, detailRows = [], isTech = false, techHoldKeySet = new Set() }) {
  const headers = [
    'Record Type', 'Hold', 'Hold Status', 'Custodian', 'Custodian Email', 'Source', 'State',
    'Active', 'Pending', 'Failed', 'Released', 'Automation', 'Provider Reference', 'Last Error',
    'Updated At', 'Event Time', 'Action', 'Actor', 'Summary', 'Details',
  ]
  const detailByCustodianId = new Map(
    detailRows.map(row => [String(row?.id), row]),
  )
  const records = []

  for (const member of hold?.custodians || []) {
    const custodianName = member?.name || member?.email || 'Unnamed custodian'
    const detail = detailByCustodianId.get(String(member?.custodian_id))
    for (const source of member?.preservation_sources || []) {
      const flags = sourceStateFlags(source?.status)
      records.push([
        'Current status', hold?.name, hold?.status, custodianName, member?.email,
        source?.source_label || source?.source_key, source?.status,
        flags.active, flags.pending, flags.failed, flags.released,
        source?.automation_ready ? 'Ready' : 'Manual', source?.provider_reference,
        source?.last_error, source?.updated_at, '', '', '', '', '',
      ])
    }

    for (const event of timelineForHold(detail, hold?.id, isTech, techHoldKeySet)) {
      records.push([
        'Timeline event', hold?.name, hold?.status, custodianName, member?.email,
        event?.hold_label || event?.hold_key, event?.state,
        '', '', '', '', '', '', '', '', event?.created_at,
        event?.action, event?.actor, event?.summary || event?.message, event?.details,
      ])
    }
  }

  return [headers, ...records]
    .map(row => row.map(csvCell).join(','))
    .join('\r\n') + '\r\n'
}

export function downloadPreservationDetailCsv(csv, holdName = 'hold') {
  const safeHoldName = String(holdName || 'hold')
    .trim()
    .replace(/[^a-z0-9._-]+/gi, '-')
    .replace(/^-+|-+$/g, '') || 'hold'
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `preservation-detail-${safeHoldName}.csv`
  link.click()
  URL.revokeObjectURL(url)
}