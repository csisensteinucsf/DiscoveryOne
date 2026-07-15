import { useState } from 'react'

export function useSystemCustodianLookupWorkflow({ apiBase, isSysAdmin }) {
  const [custodianLookupBusy, setCustodianLookupBusy] = useState(false)
  const [custodianLookupStatus, setCustodianLookupStatus] = useState(null)

  const runFullCustodianLookup = async () => {
    if (!isSysAdmin) return
    const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

    setCustodianLookupBusy(true)
    setCustodianLookupStatus('Queueing full custodian lookup and update...')
    try {
      const res = await fetch(`${apiBase}/system/custodians/full_lookup?async=1`, {
        method: 'POST',
        credentials: 'include',
      })
      if (!res.ok) {
        const msg = await res.text().catch(() => '')
        throw new Error(msg || 'Lookup update failed')
      }
      const data = await res.json()
      const jobId = (data?.job_id || '').trim()

      if (!jobId) {
        if (data?.status === 'completed') {
          setCustodianLookupStatus(`Completed. Updated ${data.records_updated || 0} records across ${data.groups_updated || 0} custodians.`)
        } else if (data?.status === 'skipped') {
          setCustodianLookupStatus(data?.message || 'Lookup skipped.')
        } else {
          setCustodianLookupStatus(data?.message || 'Lookup finished with warnings.')
        }
        return
      }

      const shortId = jobId.slice(0, 8)
      setCustodianLookupStatus(`Queued (job ${shortId}). Starting...`)

      for (let attempt = 0; attempt < 600; attempt += 1) {
        await delay(1000)
        const jobRes = await fetch(`${apiBase}/system/jobs/${encodeURIComponent(jobId)}`, {
          credentials: 'include',
        })
        if (!jobRes.ok) {
          const msg = await jobRes.text().catch(() => '')
          throw new Error(msg || 'Unable to read lookup status')
        }
        const job = await jobRes.json()
        const status = (job?.status || '').toLowerCase()

        if (status === 'queued') {
          setCustodianLookupStatus(`Queued (job ${shortId})...`)
          continue
        }
        if (status === 'running') {
          setCustodianLookupStatus(`Running lookup (job ${shortId})...`)
          continue
        }
        if (status === 'failed') {
          throw new Error(job?.error || 'Lookup update failed.')
        }
        if (status === 'completed') {
          const summary = job?.result || {}
          if ((summary?.status || '').toLowerCase() === 'completed') {
            setCustodianLookupStatus(`Completed. Updated ${summary.records_updated || 0} records across ${summary.groups_updated || 0} custodians.`)
            return
          }
          if ((summary?.status || '').toLowerCase() === 'skipped') {
            setCustodianLookupStatus(summary?.message || 'Lookup skipped.')
            return
          }
          if ((summary?.status || '').toLowerCase() === 'failed') {
            throw new Error(summary?.message || summary?.error || 'Lookup update failed.')
          }
          setCustodianLookupStatus(summary?.message || 'Lookup finished.')
          return
        }
      }

      throw new Error('Lookup is still running. Check Runtime Health jobs and try again.')
    } catch (err) {
      console.error(err)
      setCustodianLookupStatus(err?.message || 'Lookup update failed.')
    } finally {
      setCustodianLookupBusy(false)
    }
  }

  return {
    custodianLookupBusy,
    custodianLookupStatus,
    runFullCustodianLookup,
  }
}