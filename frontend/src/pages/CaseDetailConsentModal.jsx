import Modal from '../components/Modal.jsx'
import { Badge, Button, Field, Select, TextInput } from './caseDetailControls.jsx'
import { formatNameRaw } from './caseDetailUtils.js'
import { consentStatusLabel, isConsentUnavailableForRequest, normalizeConsentStatus } from './custodianStatusCatalog.js'

export default function CaseDetailConsentModal({
  open,
  onClose,
  consentFormInline,
  setConsentFormInline,
  consentHolds,
  consentHoldId,
  setConsentHoldId,
  consentAutoSearches,
  consentAutoSearchId,
  setConsentAutoSearchId,
  autoAddConsentFromSearch,
  consentSearch,
  setConsentSearch,
  addAllAvailableConsents,
  filteredConsentCustodians,
  custodians,
  consentReceivedIds,
  consentReceivedEmails,
  consentSelection,
  setConsentSelection,
  consentSelectedRecipients,
  sendSelectedConsents,
  consentSendBusy,
  esignDisplayName = 'e-signature provider',
  esignEnvelopeName = 'request',
}) {
  if (!open) return null
  return (
<Modal
          open
          title={`Send consent with ${esignDisplayName}`}
          onClose={onClose}
          style={{ maxWidth: 720 }}
        >
          <Field label="Hold" hint="Consent status and completion are tracked independently for the selected hold.">
            <Select value={consentHoldId} onChange={event => setConsentHoldId(event.target.value)}>
              <option value="">{consentHolds.length ? 'Select a Hold' : 'No active Holds'}</option>
              {consentHolds.map(hold => (
                <option key={hold.id} value={String(hold.id)}>
                  {hold.name} ({hold.custodian_count || 0} custodians)
                </option>
              ))}
            </Select>
          </Field>
          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <Field label="Record type" hint="Kinds of records that require access (required).">
              <TextInput
                value={consentFormInline.recordType}
                onChange={(e) => setConsentFormInline(prev => ({ ...prev, recordType: e.target.value }))}
                placeholder="e.g., Email, Box data"
              />
            </Field>
            <Field label="Date from" hint="Beginning date range; defaults to not specified if blank.">
              <TextInput
                value={consentFormInline.dateFrom}
                onChange={(e) => setConsentFormInline(prev => ({ ...prev, dateFrom: e.target.value }))}
                placeholder="Not specified"
              />
            </Field>
            <Field label="Date to" hint="End date range; defaults to not specified if blank.">
              <TextInput
                value={consentFormInline.dateTo}
                onChange={(e) => setConsentFormInline(prev => ({ ...prev, dateTo: e.target.value }))}
                placeholder="Not specified"
              />
            </Field>
          </div>
          <Field label="Optional message to recipients">
            <textarea
              rows={3}
              value={consentFormInline.message}
              onChange={(e) => setConsentFormInline(prev => ({ ...prev, message: e.target.value }))}
              style={{ width: '100%', border: '1px solid #dce0e5', borderRadius: 10, padding: 10 }}
              placeholder={`Any extra context to include in the ${esignDisplayName} request.`}
            />
          </Field>
          <div style={{ marginTop: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <div style={{ fontWeight: 600 }}>Custodians</div>
              <div style={{ fontSize: 12, color: '#6b7280' }}>
                Select one or more custodians. Each will receive an individual {esignEnvelopeName}.
              </div>
            </div>
            {consentAutoSearches.length > 0 && (
              <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <Select value={consentAutoSearchId} onChange={e => setConsentAutoSearchId(e.target.value)}>
                  {consentAutoSearches.map(s => (
                    <option key={`consent-search-${s.id}`} value={String(s.id)}>
                      {`${s.name} (${s.eligibleCount} eligible)`}
                    </option>
                  ))}
                </Select>
                <Button
                  variant="subtle"
                  type="button"
                  onClick={() => autoAddConsentFromSearch(consentAutoSearchId)}
                  disabled={!consentAutoSearchId}
                >
                  {'Auto add from ' + (consentAutoSearches.find(s => String(s.id) === String(consentAutoSearchId))?.name || 'search')}
                </Button>
              </div>
            )}
            <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                type="search"
                value={consentSearch}
                onChange={(e) => setConsentSearch(e.target.value)}
                placeholder="Search custodians by name or email"
                style={{ flex: '1 1 260px', border: '1px solid var(--border, #d1d5db)', borderRadius: 10, padding: '8px 12px', fontSize: 12, background: 'var(--card,#fff)', color:'var(--text,#0f172a)' }}
              />
              <Button type="button" variant="secondary" onClick={addAllAvailableConsents} disabled={!filteredConsentCustodians.length}>
                All available custodians
              </Button>
            </div>
            <div style={{ marginTop: 10, border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 10, maxHeight: 220, overflow: 'auto', background: 'var(--card,#f8fafc)' }}>
              {custodians.length ? (
                filteredConsentCustodians.length ? (
                  <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                    {filteredConsentCustodians.map(c => {
                      const idNum = Number(c.id)
                      const normalizedEmail = (c.email || '').trim().toLowerCase()
                      const consentStatus = normalizeConsentStatus(c.consent_status)
                      const completedByStatus = isConsentUnavailableForRequest(consentStatus)
                      const alreadyReceived = completedByStatus || consentReceivedIds.has(idNum) || (normalizedEmail && consentReceivedEmails.has(normalizedEmail))
                      const unavailable = alreadyReceived || !Number.isFinite(idNum)
                      const checked = Number.isFinite(idNum) && consentSelection.has(idNum)
                      return (
                        <label
                          key={`consent-${c.id}`}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            padding: 8,
                            border: '1px solid var(--border,#e5e7eb)',
                            borderRadius: 10,
                            background: unavailable ? 'var(--table-header-bg,#f8fafc)' : 'var(--card,#fff)',
                            opacity: unavailable ? 0.6 : 1,
                            cursor: unavailable ? 'not-allowed' : 'pointer',
                          }}
                        >
                          <input
                            type="checkbox"
                            disabled={unavailable}
                            checked={checked}
                            onChange={() => setConsentSelection(prev => {
                              const next = new Set(prev)
                              if (!Number.isFinite(idNum) || unavailable) return next
                              if (next.has(idNum)) next.delete(idNum)
                              else next.add(idNum)
                              return next
                            })}
                          />
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <Badge variant="orange" compact>{c.email || 'No email'}</Badge>
                            <span style={{ fontSize: 12, color: '#475467' }}>{formatNameRaw(c.name) || 'Unnamed custodian'}</span>
                            {completedByStatus ? <span style={{ fontSize: 11, color: '#9ca3af' }}>{consentStatusLabel(consentStatus)} - consent complete</span> : null}
                            {!completedByStatus && alreadyReceived ? <span style={{ fontSize: 11, color: '#9ca3af' }}>Consent already received</span> : null}
                          </div>
                        </label>
                      )
                    })}
                  </div>
            ) : (
              <p style={{ margin: 0, color: '#6b7280' }}>No custodians match your search.</p>
            )
          ) : (
            <p style={{ margin: 0, color: '#6b7280' }}>Add custodians to this case to send consent requests.</p>
          )}
        </div>
      </div>
      <div style={{ marginTop: 12, border: '1px dashed var(--border,#d1d5db)', borderRadius: 10, padding: 10, background: 'var(--table-header-bg,#f8fafc)' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: '#475467' }}>Selected for send ({consentSelectedRecipients.length})</div>
        {consentSelectedRecipients.length ? (
          <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {consentSelectedRecipients.map(c => (
              <Badge key={`consent-selected-${c.id}`} variant="info" compact>{(c.email || '').trim() || formatNameRaw(c.name) || ('Custodian ' + c.id)}</Badge>
            ))}
          </div>
        ) : (
          <div style={{ marginTop: 6, fontSize: 12, color: '#9ca3af' }}>No custodians selected yet.</div>
        )}
      </div>      <div className="row" style={{ justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
        <Button onClick={sendSelectedConsents} disabled={consentSendBusy || !custodians.length || !consentSelectedRecipients.length} className={consentSendBusy ? 'btn-pulse' : ''}>
          {consentSendBusy ? 'Sending...' : (`Send with ${esignDisplayName} (` + consentSelectedRecipients.length + ')')}
        </Button>
        <Button variant="ghost" onClick={onClose} disabled={consentSendBusy}>
          Cancel
        </Button>
      </div>
        </Modal>
  )
}
