import { EditCaseModal } from './CaseDetailModals.jsx'
import { isValidEmail } from './caseDetailUtils.js'
import { customFieldValues, normalizeStoredCustomFields } from './caseCustomFields.js'

export default function CaseDetailEditCaseModal({
  open,
  caseData,
  analystOptions,
  requestorOptions,
  onClose,
  updateCase,
  setCaseData,
  showToast,
  useLegalCaseNameAsPrimary = false,
  matterTypes = [],
  internalCounselLabel = 'Internal Counsel',
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
        matter_number: caseData?.matter_number || '',
        campus: caseData?.campus || '',
        matter_type: caseData?.matter_type && matterTypes.includes(caseData.matter_type) ? caseData.matter_type : (caseData?.matter_type ? 'Other' : ''),
        matter_type_other: caseData?.matter_type && !matterTypes.includes(caseData.matter_type) ? caseData.matter_type : '',
        internal_counsel: caseData?.internal_counsel || '',
        outside_counsel: caseData?.outside_counsel || '',
        description: caseData?.description || '',
        start_date: caseData?.start_date || '',
        analyst_id: caseData?.analyst_id || null,
        requestor: caseData?.requestor || '',
        requestors: caseData?.requestors || [],
        closed: !!caseData?.closed,
        is_private: !!caseData?.is_private,
        is_test_case: !!caseData?.is_test_case,
        closure_nag_days: caseData?.closure_nag_days ?? defaultClosureNagDays,
        custom_fields: normalizeStoredCustomFields(caseData?.custom_fields),
      }}
      analysts={analystOptions}
      requestorOptions={requestorOptions}
      useLegalCaseNameAsPrimary={useLegalCaseNameAsPrimary}
      internalCounselLabel={internalCounselLabel}
      onClose={onClose}
      matterTypes={matterTypes}
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
            matter_number: (form.matter_number || '').trim() || null,
            internal_counsel: (form.internal_counsel || '').trim() || null,
            outside_counsel: (form.outside_counsel || '').trim() || null,
            description: (form.description || '').trim() || null,
            start_date: form.start_date || null,
            ler_representative: null,
            campus: (form.campus || '').trim() || null,
            matter_type: (form.matter_type === 'Other' ? form.matter_type_other : form.matter_type || '').trim() || null,
            requestor: trimmed || null,
            requestors: requestorsPayload.length ? requestorsPayload : undefined,
            analyst_id: form.analyst_id ?? null,
            closed: !!form.closed,
            is_private: !!form.is_private,
            is_test_case: !!form.is_test_case,
            closure_nag_days: Number.isFinite(closureDays) ? closureDays : undefined,
            custom_fields: customFieldValues(form.custom_fields),
          }
          const updated = await updateCase(patch)
          onClose()
          setCaseData(updated)
          showToast('Matter updated.', { variant: 'success' })
        } catch (e) {
          if (!e?.cancelled) showToast('Failed to update case: ' + e.message, { variant: 'error' })
        }
      }}
    />
  )
}
