import { useCallback, useState } from 'react'
import { slaCache } from './caseDetailUtils.js'

const emptySlaStatus = { ntp_overdue: [], consent_overdue: [], config: {} }

export function useCaseDetailSla({ apiBase, caseId }) {
  const [slaStatus, setSlaStatus] = useState(() => slaCache.get(caseId) || emptySlaStatus)
  const [slaLoading, setSlaLoading] = useState(false)
  const [slaError, setSlaError] = useState(null)

  const loadSlaStatus = useCallback(async () => {
    if (!caseId) return
    setSlaLoading(true)
    setSlaError(null)
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/sla_status`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text() || 'Unable to load SLA status')
      const data = await res.json()
      const nextSla = {
        ntp_overdue: Array.isArray(data?.ntp_overdue) ? data.ntp_overdue : [],
        consent_overdue: Array.isArray(data?.consent_overdue) ? data.consent_overdue : [],
        config: data?.config || {},
      }
      setSlaStatus(nextSla)
      slaCache.set(caseId, nextSla)
    } catch (err) {
      setSlaError(err?.message || 'Unable to load SLA status')
    } finally {
      setSlaLoading(false)
    }
  }, [apiBase, caseId])

  return {
    slaStatus,
    slaLoading,
    slaError,
    loadSlaStatus,
  }
}