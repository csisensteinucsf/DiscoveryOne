import { useCallback, useState } from 'react'

export function useSystemClamavMonitor({ apiBase, isSysAdmin }) {
  const [clamavMonitor, setClamavMonitor] = useState(null)
  const [clamavLoading, setClamavLoading] = useState(false)
  const [clamavStatus, setClamavStatus] = useState(null)

  const loadClamavMonitor = useCallback(async () => {
    if (!isSysAdmin) return
    setClamavLoading(true)
    setClamavStatus(null)
    try {
      const res = await fetch(`${apiBase}/system/clamav?days=30`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setClamavMonitor(data)
    } catch (err) {
      console.error(err)
      setClamavMonitor(null)
      setClamavStatus('Unable to load ClamAV monitor.')
    } finally {
      setClamavLoading(false)
    }
  }, [apiBase, isSysAdmin])

  return {
    clamavMonitor,
    clamavLoading,
    clamavStatus,
    loadClamavMonitor,
  }
}