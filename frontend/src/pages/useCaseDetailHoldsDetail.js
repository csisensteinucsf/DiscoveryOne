import { useCallback, useMemo, useState } from 'react'

export function useCaseDetailHoldsDetail({ apiBase, caseId }) {
  const [holdsDetail, setHoldsDetail] = useState({ loading: false, error: null, data: null })

  const loadHoldsDetail = useCallback(async () => {
    if (!caseId) return
    setHoldsDetail(prev => ({ ...prev, loading: true, error: null }))
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/holds_detail`, { credentials: 'include' })
      const raw = await res.text().catch(() => '')
      let data = null
      try {
        data = raw ? JSON.parse(raw) : null
      } catch {
        data = null
      }
      if (!res.ok) {
        const detail = (data && typeof data === 'object' ? data.detail : null) || raw || 'Unable to load holds detail'
        throw new Error(detail)
      }
      if (!data || typeof data !== 'object') {
        throw new Error('Invalid holds detail response')
      }
      setHoldsDetail({ loading: false, error: null, data })
    } catch (err) {
      setHoldsDetail(prev => ({ ...prev, loading: false, error: err?.message || 'Unable to load holds detail' }))
    }
  }, [apiBase, caseId])

  const holdsDetailRows = useMemo(
    () => (Array.isArray(holdsDetail?.data?.custodians) ? holdsDetail.data.custodians : []),
    [holdsDetail]
  )
  const holdsDetailTotals = useMemo(
    () => (holdsDetail?.data?.totals && typeof holdsDetail.data.totals === 'object' ? holdsDetail.data.totals : { custodians: 0, events: 0 }),
    [holdsDetail]
  )

  return {
    holdsDetail,
    holdsDetailRows,
    holdsDetailTotals,
    loadHoldsDetail,
  }
}