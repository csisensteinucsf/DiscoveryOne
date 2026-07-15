export function collectEntryEmails(entry, custodianEmailById = new Map()) {
  if (!entry) return []
  const emails = []
  const seen = new Set()
  const addEmail = (value) => {
    const email = (value || '').trim()
    if (!email) return
    const key = email.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    emails.push(email)
  }
  const addCustodian = (custodian) => {
    if (!custodian) return
    const direct = (custodian.email || '').trim()
    if (direct) {
      addEmail(direct)
      return
    }
    const id = Number(custodian.id)
    if (Number.isFinite(id)) {
      const found = custodianEmailById.get(id)
      if (found) addEmail(found)
    }
  }
  addCustodian({ id: entry.custodian_id, email: entry.custodian_email })
  const bulk = Array.isArray(entry.bulk_custodians) ? entry.bulk_custodians : []
  bulk.forEach(item => addCustodian({ id: item?.id, email: item?.email }))
  return emails
}

export async function copyEntryCustodianEmails(entry, { custodianEmailById, showToast }) {
  const emails = collectEntryEmails(entry, custodianEmailById)
  const payload = emails.join(', ')
  if (!payload) {
    showToast('No custodian emails for this ticket.', { variant: 'warn' })
    return
  }
  try {
    await navigator.clipboard.writeText(payload)
    showToast(`Copied ticket custodians: ${emails.length} email${emails.length === 1 ? '' : 's'}`)
  } catch {
    const fallback = document.createElement('textarea')
    fallback.value = payload
    document.body.appendChild(fallback)
    fallback.select()
    try {
      document.execCommand('copy')
      showToast(`Copied ticket custodians: ${emails.length} email${emails.length === 1 ? '' : 's'}`)
    } catch {
      showToast(`Copy failed. Here is the list:\n${payload}`, { variant: 'error' })
    } finally {
      document.body.removeChild(fallback)
    }
  }
}
