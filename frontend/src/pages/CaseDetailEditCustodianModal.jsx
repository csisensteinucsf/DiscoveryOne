import Modal from '../components/Modal.jsx'
import { Field, TextInput, Button, Badge } from './caseDetailControls.jsx'
import {
  CONSENT_NOT_REQUIRED_DEFAULT_REASON,
  consentNotRequiredAutoReason,
  employmentBadges,
  employmentEndDateColor,
  lookupPersonName,
} from './caseDetailUtils.js'
import { normalizeConsentStatus } from './custodianStatusCatalog.js'

export default function CaseDetailEditCustodianModal({
  editing,
  setEditing,
  editSaveBusy,
  onSaveEditCustodian,
  editLookupBusy,
  runEditPersonLookup,
  editLookupOptions,
  setEditLookupOptions,
  applyEditMatch,
  caseData,
  editingConsentNotRequired,
  editingConsentAutoReason,
}) {
  if (!editing) return null
  const editingConsentIsAwoc = normalizeConsentStatus(editing.consent_status) === 'awoc'

  return (
    <Modal
      open
      title="Edit Custodian"
      onClose={editSaveBusy ? () => {} : () => setEditing(null)}
      width={520}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <Button variant="ghost" onClick={() => setEditing(null)} disabled={editSaveBusy}>Cancel</Button>
          <Button onClick={() => onSaveEditCustodian(editing)} disabled={editSaveBusy || !String(editing.name || '').trim()}>
            {editSaveBusy ? 'Saving...' : 'Save'}
          </Button>
        </div>
      )}
    >
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: 8, alignItems: 'start' }}>
        <Field label="Name">
          <TextInput value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })} autoFocus disabled={editSaveBusy} />
        </Field>
        <Field label="Email">
          <TextInput value={editing.email || ''} onChange={e => setEditing({ ...editing, email: e.target.value })} disabled={editSaveBusy} />
          <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>Person lookup fills in name/email from the selected match. You can edit either field before saving.</div>
        </Field>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4, flexWrap: 'wrap' }}>
        <Button variant="secondary" onClick={runEditPersonLookup} disabled={editLookupBusy || editSaveBusy}>
          {editLookupBusy ? 'Looking up...' : 'Person lookup'}
        </Button>
        {employmentBadges(editing).map((b, idx) => (
          <Badge key={`edit-badge-${idx}`} variant={b.variant} compact title={b.title}>{b.label}</Badge>
        ))}
      </div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 12, color: '#475467' }}>
        <input
          type="checkbox"
          checked={!!editing.person_lookup_overridden}
          disabled={editSaveBusy}
          onChange={(e) => setEditing({ ...editing, person_lookup_overridden: e.target.checked })}
        />
        Mark as unmatched (needs review)
      </label>
      {editing.name_email_review_required ? (
        <div style={{ marginTop: 8, fontSize: 12, color: '#92400e' }}>
          Name/email review flag: {editing.name_email_review_reason || 'mismatch suspected'}
        </div>
      ) : null}
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 12, color: '#475467' }}>
        <input
          type="checkbox"
          checked={!!editing.is_claimant}
          disabled={editSaveBusy}
          onChange={(e) => {
            const checked = !!e.target.checked
            const next = { ...editing, is_claimant: checked }
            const nextAutoReason = consentNotRequiredAutoReason(caseData?.claimant, next, { forceClaimant: checked })
            if (nextAutoReason && !editingConsentIsAwoc) {
              next.consent_status = 'implied'
              next.consent_not_required_reason = nextAutoReason
            }
            setEditing(next)
          }}
        />
        Mark as claimant (shows claimant badge)
      </label>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, fontSize: 12, color: '#475467' }}>
        <input
          type="checkbox"
          checked={editingConsentNotRequired}
          disabled={editingConsentIsAwoc || !!editingConsentAutoReason || editSaveBusy}
          onChange={(e) => {
            const checked = !!e.target.checked
            setEditing(prev => {
              const current = prev || {}
              if (!checked) {
                const priorStatus = String(current.consent_status || '').trim().toLowerCase()
                return {
                  ...current,
                  consent_status: ['na', 'implied'].includes(priorStatus) ? 'not sent' : (current.consent_status || 'not sent'),
                  consent_not_required_reason: 'retaliation',
                }
              }
              return {
                ...current,
                consent_status: 'implied',
                consent_not_required_reason: String(current.consent_not_required_reason || '').trim() || CONSENT_NOT_REQUIRED_DEFAULT_REASON,
              }
            })
          }}
        />
        Consent is implied
      </label>
      {editingConsentIsAwoc ? (
        <div style={{ marginTop: 6, fontSize: 12, color: '#475467' }}>
          AWOC is managed by the uploaded AWOC consent document. Remove or replace that document to change this status.
        </div>
      ) : null}
      {editingConsentNotRequired ? (
        <Field
          label="Implied consent reason"
          hint={editingConsentAutoReason ? 'Auto-set based on claimant/separated status.' : 'Provide a short reason.'}
        >
          <TextInput
            value={editingConsentAutoReason || editing.consent_not_required_reason || ''}
            onChange={e => setEditing({ ...editing, consent_not_required_reason: e.target.value })}
            disabled={!!editingConsentAutoReason || editSaveBusy}
            placeholder="e.g., third-party system data only"
          />
        </Field>
      ) : null}
      {editLookupOptions?.matches?.length > 1 && (
        <div style={{ marginTop: 12, border: '1px solid #e2e8f0', borderRadius: 8, padding: 10, background: '#f8fafc' }}>
          <div style={{ fontSize: 12, color: '#475467', marginBottom: 6 }}>Select the correct person:</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {editLookupOptions.matches.map((m, idx) => {
              const selected = editLookupOptions.selection === idx
              const end = m.employee_end_date
              const badge = employmentBadges({ employment_end_date: end })
              const personId = m.employee_id || m.external_id
              return (
                <label key={`edit-match-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <input
                    type="radio"
                    name="edit-lookup"
                    checked={selected}
                    onChange={() => {
                      setEditLookupOptions(prev => ({ ...(prev || {}), selection: idx }))
                      applyEditMatch(m)
                    }}
                  />
                  <div>
                    <div style={{ fontWeight: 600 }}>{lookupPersonName(m)}{personId ? ` (${personId})` : ''}</div>
                    <div style={{ fontSize: 12, color: '#475467' }}>
                      {m.department_name ? `Dept: ${m.department_name}` : 'Dept: -'}
                      {end ? <> | End: <span style={{ color: employmentEndDateColor({ employment_end_date: end }), fontWeight: 700 }}>{end}</span></> : ''}
                      {m.email ? ` | Email: ${m.email}` : ''}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    {badge.map((b, bi) => (
                      <Badge key={`edit-match-badge-${idx}-${bi}`} variant={b.variant} compact title={b.title}>{b.label}</Badge>
                    ))}
                  </div>
                </label>
              )
            })}
          </div>
        </div>
      )}
    </Modal>
  )
}
