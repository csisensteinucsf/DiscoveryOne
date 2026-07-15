import { EditCaseModal } from './CaseDetailModals.jsx'
import { isValidEmail } from './caseDetailUtils.js'

export default function CaseDetailEditCaseModal({
  open,
  caseData,
  analystOptions,
  requestorOptions,
  onClose,
  updateCase,
  setCaseData,
  showToast,
  defaultClosureNagDays = 180,
}) {
  if (!open) return null

  return (
    <EditCaseModal
      initial={{
        name: caseData?.name || '',
        legal_case_name: caseData?.legal_case_name || '',
        servicenow_inc_number: caseData?.servicenow_inc_number || '',
        claimant: caseData?.claimant || '',
        analyst_id: caseData?.analyst_id || null,
        requestor: caseData?.requestor || '',
        requestors: caseData?.requestors || [],
        closed: !!caseData?.closed,
        is_private: !!caseData?.is_private,
        closure_nag_days: caseData?.closure_nag_days ?? defaultClosureNagDays,
      }}
      analysts={analystOptions}
      requestorOptions={requestorOptions}
      onClose={onClose}
      onSave={async (form) => {
        try {
          const trimmed = (form.requestor || '').trim()
          const trimmedClaimant = (form.claimant || '').trim()
          if (trimmed && !isValidEmail(trimmed)) {
            showToast('Requestor must be a valid email address', { variant: 'warn' })
            return
          }
          const extraRequestors = (form.additional_requestors || '')
            .split(',')
            .map(v => v.trim())
            .filter(Boolean)
          for (const addr of extraRequestors) {
            if (!isValidEmail(addr)) {
              showToast(`Invalid additional requestor email: ${addr}`, { variant: 'warn' })
              return
            }
          }
          const requestorsPayload = []
          if (trimmed) requestorsPayload.push({ email: trimmed, is_primary: true })
          extraRequestors.forEach(email => {
            if (!requestorsPayload.find(r => (r.email || '').toLowerCase() === email.toLowerCase())) {
              requestorsPayload.push({ email, is_primary: false })
            }
          })
          const closureDaysRaw = form.closure_nag_days
          const closureDays = (closureDaysRaw === '' || closureDaysRaw === null || closureDaysRaw === undefined)
            ? undefined
            : Number(closureDaysRaw)
          const patch = {
            name: form.name,
            legal_case_name: form.legal_case_name,
            servicenow_inc_number: null,
            claimant: trimmedClaimant || null,
            ler_representative: null,
            requestor: trimmed || null,
            requestors: requestorsPayload.length ? requestorsPayload : undefined,
            analyst_id: form.analyst_id ?? null,
            closed: !!form.closed,
            is_private: !!form.is_private,
            closure_nag_days: Number.isFinite(closureDays) ? closureDays : undefined,
          }
          const updated = await updateCase(patch)
          onClose()
          setCaseData(updated)
          showToast('Case updated.', { variant: 'success' })
        } catch (e) {
          showToast('Failed to update case: ' + e.message, { variant: 'error' })
        }
      }}
    />
  )
}
