import { separatedStatusLabel } from './caseDetailUtils.js'
import { customPreservationEntry, holdMetaFromPreservationSources, isCustomHoldKey } from './preservationCatalog.js'

const fileSafe = (value) => (
  (value || '')
    .replace(/[^a-z0-9\-_]+/gi, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '') || 'case'
)

const csvCell = (value) => `"${String(value).replace(/"/g, '""')}"`

const holdStatus = (has, pending, failed, released) => {
  if (failed) return 'Failed'
  if (pending) return 'Pending'
  if (has) return 'Completed'
  if (released) return 'Released'
  return 'False'
}


const holdColumnName = (label) => `Holds_${String(label || 'Hold')
  .replace(/[^a-z0-9]+/gi, '_')
  .replace(/_+/g, '_')
  .replace(/^_+|_+$/g, '') || 'Hold'}`

const holdStateForMeta = (custodian, meta) => {
  const key = meta?.key || ''
  if (isCustomHoldKey(key)) {
    const entry = customPreservationEntry(custodian, key)
    return holdStatus(entry?.active, entry?.pending, entry?.failed, entry?.released)
  }
  return holdStatus(
    custodian?.[key],
    custodian?.[`${key}_pending`],
    custodian?.[`${key}_failed`],
    custodian?.[`${key}_released`],
  )
}

const holdIsRequestedForMeta = (custodian, meta) => holdStateForMeta(custodian, meta) !== 'False'

const describeSearchesForCustodian = (searches, custodianId) => {
  const assigned = (searches || []).filter(search => {
    const ids = (search.custodianIds ?? search.custodian_ids ?? []).map(Number)
    return ids.includes(Number(custodianId))
  })
  const sortNames = (list) => list.map(name => name || '').filter(Boolean).sort((a, b) => a.localeCompare(b))
  const assignedNames = sortNames(assigned.map(search => search.name || ''))
  const completedNames = sortNames(
    assigned
      .filter(search => (search.status_search ?? search.status?.search ?? 'not performed') === 'performed')
      .map(search => search.name || '')
  )
  const deliveredNames = sortNames(
    assigned
      .filter(search => {
        const state = String(search.status_delivery ?? search.status?.delivery ?? 'not performed').toLowerCase()
        return state === 'performed' || state === 'not required'
      })
      .map(search => search.name || '')
  )
  return {
    assigned: assignedNames.join('; '),
    completed: completedNames.join('; '),
    delivered: deliveredNames.join('; '),
  }
}

export function exportCustodiansCsv({ caseData, custodians = [], searches = [], holdMeta }) {
  if (!caseData) return
  const configuredHoldMeta = Array.isArray(holdMeta) && holdMeta.length
    ? holdMeta
    : holdMetaFromPreservationSources(caseData?.preservation_sources)
  const holdHeaders = configuredHoldMeta.map(meta => holdColumnName(meta.label))
  const rows = [
    [
      'Name', 'Email', 'Separated_Status',
      ...holdHeaders, 'Any_Hold',
      'NTP_Status', 'Consent_Status',
      'Search_Done', 'Export_Done', 'Delivered_Done',
      'Searches_Assigned', 'Searches_Completed', 'Searches_Delivered',
    ],
    ...custodians.map(custodian => {
      const holdValues = configuredHoldMeta.map(meta => holdStateForMeta(custodian, meta))
      const anyHold = configuredHoldMeta.some(meta => holdIsRequestedForMeta(custodian, meta))
      const searchLists = describeSearchesForCustodian(searches, custodian.id)
      return [
        custodian.name || '',
        custodian.email || '',
        separatedStatusLabel(custodian),
        ...holdValues,
        anyHold ? 'yes' : 'no',
        custodian.ntp_status || 'not sent',
        custodian.consent_status || 'not sent',
        !!custodian.search_done,
        !!custodian.export_done,
        !!custodian.delivered_done,
        searchLists.assigned,
        searchLists.completed,
        searchLists.delivered,
      ]
    }),
  ]
  const csv = rows.map(row => row.map(csvCell).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${fileSafe(caseData?.name)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
