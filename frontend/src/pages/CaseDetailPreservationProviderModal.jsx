import Modal from '../components/Modal.jsx'
import { Badge, Button, Field, InlineSpinner, Select } from './caseDetailControls.jsx'
import { formatNameRaw } from './caseDetailUtils.js'

export default function CaseDetailPreservationProviderModal({
  open,
  onClose,
  caseData,
  purviewStatus,
  purviewCreating,
  handleCreatePurviewCase,
  purviewExportCheckBusy,
  checkPurviewExports,
  purviewHoldBusy,
  preservationHolds,
  preservationHoldId,
  setPreservationHoldId,
  purviewHoldOptions,
  setPurviewHoldOptions,
  selectAllPurviewHoldTargets,
  setPurviewHoldSelection,
  custodians,
  purviewHoldMap,
  purviewSelectedSources,
  purviewHoldSelection,
  togglePurviewHoldSelection,
  applyPurviewHolds,
  purviewHoldResults,
  custodianLabelById,
  providerName = 'Preservation provider',
  exportCheckEnabled = false,
}) {
  if (!open) return null
  return (
<Modal
          open
          title={providerName}
          onClose={onClose}
          width={760}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button variant="ghost" onClick={onClose}>Close</Button>
            </div>
          )}
        >
          <div style={{ display: 'grid', gap: 16 }}>
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>Matter</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    {providerName} matter name: {(caseData?.name || '').trim() || 'Unnamed case'}
                  </div>
                </div>
                {purviewStatus.enabled === false ? (
                  <Badge variant="danger" compact>Not configured</Badge>
                ) : purviewStatus.case_exists ? (
                  <Badge variant="success" compact>Exists</Badge>
                ) : (
                  <Badge variant="warn" compact>Not created</Badge>
                )}
              </div>
              {purviewStatus.loading && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#6b7280', marginTop: 8 }}>
                  <InlineSpinner size={12} />
                  Checking {providerName} status...
                </div>
              )}
              {purviewStatus.error && (
                <div style={{ fontSize: 12, color: '#b91c1c', marginTop: 8 }}>{purviewStatus.error}</div>
              )}
              {!purviewStatus.error && purviewStatus.detail && (
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>{purviewStatus.detail}</div>
              )}
              {(purviewStatus.provider_case_id || purviewStatus.purview_case_id) && (
                <div style={{ fontSize: 12, color: '#475467', marginTop: 6 }}>
                  Matter ID: {purviewStatus.provider_case_id || purviewStatus.purview_case_id}
                </div>
              )}
              <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Button
                  onClick={handleCreatePurviewCase}
                  disabled={purviewCreating || purviewStatus.case_exists || purviewStatus.enabled === false}
                >
                  {purviewCreating ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <InlineSpinner size={12} />
                      Creating...
                    </span>
                  ) : 'Create case'}
                </Button>
                {exportCheckEnabled && (
                  <Button
                    variant="subtle"
                    onClick={checkPurviewExports}
                    disabled={purviewExportCheckBusy || purviewStatus.enabled === false || !purviewStatus.case_exists}
                  >
                    {purviewExportCheckBusy ? (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                        <InlineSpinner size={12} />
                        Checking...
                      </span>
                    ) : 'Check for exports'}
                  </Button>
                )}
              </div>
            </div>
            <div style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>Preservation</div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    Add custodians to the {providerName} matter and apply email and/or OneDrive preservation.
                  </div>
                </div>
                {!purviewStatus.case_exists && (
                  <Badge variant="warn" compact>Create case first</Badge>
                )}
              </div>
              <Field label="Named hold" hint="The external preservation policy and tracked status are isolated to this hold.">
                <Select value={preservationHoldId} onChange={event => setPreservationHoldId(event.target.value)}>
                  <option value="">{preservationHolds.length ? 'Select an active Hold' : 'No active Holds'}</option>
                  {preservationHolds.map(hold => (
                    <option key={hold.id} value={String(hold.id)}>
                      {hold.name} ({hold.custodian_count || 0} custodians)
                    </option>
                  ))}
                </Select>
              </Field>
              {purviewHoldBusy && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#6b7280', marginTop: 6 }}>
                  <InlineSpinner size={12} />
                  Applying preservation updates...
                </div>
              )}
              <div style={{ marginTop: 10, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={purviewHoldOptions.email}
                    onChange={(e) => setPurviewHoldOptions(prev => ({ ...prev, email: e.target.checked }))}
                  />
                  Email preservation
                </label>
                <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={purviewHoldOptions.onedrive}
                    onChange={(e) => setPurviewHoldOptions(prev => ({ ...prev, onedrive: e.target.checked }))}
                  />
                  OneDrive preservation
                </label>
              </div>
              <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Button variant="subtle" onClick={selectAllPurviewHoldTargets} disabled={!purviewStatus.case_exists || purviewHoldBusy}>
                  Select all missing preservation
                </Button>
                <Button variant="ghost" onClick={() => setPurviewHoldSelection(new Set())} disabled={purviewHoldBusy}>
                  Clear selection
                </Button>
              </div>
              <div style={{ marginTop: 10, maxHeight: 260, overflowY: 'auto', border: '1px solid #e5e7eb', borderRadius: 10 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead style={{ background: 'rgba(0,0,0,.03)' }}>
                    <tr>
                      <th style={{ textAlign: 'left', padding: 8 }}>Select</th>
                      <th style={{ textAlign: 'left', padding: 8 }}>Name</th>
                      <th style={{ textAlign: 'left', padding: 8 }}>Email</th>
                      <th style={{ textAlign: 'left', padding: 8 }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(custodians || []).map(c => {
                      const rawEmail = String(c?.email || '').trim()
                      const email = rawEmail.toLowerCase()
                      const missingEmail = !email || email === 'noemail' || email === 'unmatched'
                      const status = purviewHoldMap.get(email) || { mailbox: false, site: false }
                      const emailHold = !!status.mailbox
                      const siteHold = !!status.site
                      const needsMailbox = purviewSelectedSources.includes('mailbox') && !emailHold
                      const needsSite = purviewSelectedSources.includes('site') && !siteHold
                      const selectable = purviewStatus.case_exists && !missingEmail && (needsMailbox || needsSite)
                      const checked = purviewHoldSelection.has(Number(c.id))
                      return (
                        <tr key={`purview-hold-${c.id}`} style={{ borderTop: '1px solid #e5e7eb' }}>
                          <td style={{ padding: 8 }}>
                            <input
                              type="checkbox"
                              checked={checked}
                              disabled={!selectable}
                              onChange={() => togglePurviewHoldSelection(c.id)}
                            />
                          </td>
                          <td style={{ padding: 8 }}>{formatNameRaw(c.name) || '-'}</td>
                          <td style={{ padding: 8 }}>{rawEmail || '-'}</td>
                          <td style={{ padding: 8 }}>
                            {missingEmail ? (
                              <Badge variant="danger" compact>Missing email</Badge>
                            ) : (
                              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                <Badge variant={emailHold ? 'success' : 'warn'} compact>Email</Badge>
                                <Badge variant={siteHold ? 'success' : 'warn'} compact>OneDrive</Badge>
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <Button
                  onClick={applyPurviewHolds}
                  disabled={!purviewStatus.case_exists || purviewHoldBusy || purviewHoldSelection.size === 0 || purviewSelectedSources.length === 0}
                >
                  {purviewHoldBusy ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                      <InlineSpinner size={12} />
                      Applying...
                    </span>
                  ) : `Apply preservation (${purviewHoldSelection.size})`}
                </Button>
              </div>
              {purviewHoldResults.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Last preservation run</div>
                  <div style={{ display: 'grid', gap: 6 }}>
                    {purviewHoldResults.map((row, idx) => {
                      const status = row?.status || 'unknown'
                      const name = custodianLabelById.get(Number(row?.custodian_id)) || row?.email || 'Custodian'
                      const meta = {
                        on_hold: { variant: 'success', label: 'Preserved' },
                        already_on_hold: { variant: 'info', label: 'Already preserved' },
                        missing_email: { variant: 'danger', label: 'Missing email' },
                        onedrive_missing: { variant: 'warn', label: 'OneDrive not found' },
                        partial_hold: { variant: 'warn', label: 'Partial preservation' },
                        error: { variant: 'danger', label: 'Error' },
                        not_found: { variant: 'warn', label: 'Not found' },
                      }[status] || { variant: 'default', label: status }
                      return (
                        <div key={`purview-result-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <Badge variant={meta.variant} compact>{meta.label}</Badge>
                          <span style={{ fontSize: 12, color: '#475467' }}>{name}</span>
                          {row?.message ? (
                            <span style={{ fontSize: 11, color: '#9ca3af' }}>{row.message}</span>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </Modal>
  )
}
