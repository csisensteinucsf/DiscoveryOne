export default function SystemNtpPanel({
  titleStyle,
  isSysAdmin,
  canManageNtp,
  ntpSettings,
  setNtpSettings,
  saveNtpSettings,
  ntpSettingsSaving,
  ntpSettingsStatus,
  ntpTemplates,
  ntpTemplatesLoading,
  openTemplateModal,
  copyTemplate,
  deleteTemplate,
  templateAccessible,
  templateDeletable,
  formatGroupLabel,
}) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>NTP Templates</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        Create reusable Notice to Preserve email templates. Supported placeholders include{' '}
        <code>{'{{case_name}}'}</code>, <code>{'{{legal_case_name}}'}</code>, <code>{'{{custodian_name}}'}</code>, <code>{'{{custodian_email}}'}</code>, <code>{'{{requestor}}'}</code>, <code>{'{{ack_link}}'}</code>, <code>{'{{claimant}}'}</code>, <code>{'{{reason}}'}</code>, <code>{'{{outside_counsel1}}'}</code>, <code>{'{{outside_counsel2}}'}</code>, <code>{'{{outside_counsel3}}'}</code>, <code>{'{{outside_counsel_firm}}'}</code>.
      </p>
      {isSysAdmin && (
        <div style={{ marginBottom: 12, padding: 12, border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, background: 'var(--card,#f8fafc)' }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>NTP Settings</div>
          <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13, marginBottom: 12 }}>
            Configure Notice to Preserve archive copies and reminder cadence from stored System settings. External acknowledgement bridges are configured in the System Integrations section.
          </div>
          <div className="form-grid">
            <label>
              Archive BCC address
              <input
                type="email"
                value={ntpSettings.archive_bcc_address || ''}
                onChange={e => setNtpSettings(prev => ({ ...prev, archive_bcc_address: e.target.value }))}
                placeholder="archive-mailbox@example.edu"
              />
              <small style={{ color: 'var(--muted,#6b7280)' }}>This address receives an archive copy of all NTPs.</small>
            </label>
            <label>
              Reserved archive BCC addresses
              <input
                value={ntpSettings.reserved_archive_bcc_addresses || ''}
                onChange={e => setNtpSettings(prev => ({ ...prev, reserved_archive_bcc_addresses: e.target.value }))}
                placeholder="archive-mailbox@example.edu,records@example.edu"
              />
              <small style={{ color: 'var(--muted,#6b7280)' }}>Comma-separated addresses users cannot add manually to template BCC fields.</small>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
              <input
                type="checkbox"
                checked={!!ntpSettings.archive_copy_required}
                onChange={e => setNtpSettings(prev => ({ ...prev, archive_copy_required: e.target.checked }))}
              />
              Require archive copy delivery
            </label>
            <label>
              Default reminder interval days
              <input type="number" min="1" max="365" value={ntpSettings.reminder_interval_days ?? 14} onChange={e => setNtpSettings(prev => ({ ...prev, reminder_interval_days: e.target.value }))} />
            </label>
            <label>
              Default reminder duration days
              <input type="number" min="1" max="3650" value={ntpSettings.reminder_duration_days ?? 90} onChange={e => setNtpSettings(prev => ({ ...prev, reminder_duration_days: e.target.value }))} />
            </label>
            <label>
              Reminder scheduler check seconds
              <input type="number" min="30" max="86400" value={ntpSettings.reminder_loop_seconds ?? 900} onChange={e => setNtpSettings(prev => ({ ...prev, reminder_loop_seconds: e.target.value }))} />
            </label>
          </div>
          <div style={{ marginTop: 12 }}>
            <button className="btn secondary" onClick={saveNtpSettings} disabled={ntpSettingsSaving}>
              {ntpSettingsSaving ? 'Saving' : 'Save NTP Settings'}
            </button>
          </div>
          {ntpSettingsStatus && <div style={{ marginTop: 6, color: 'var(--muted,#6b7280)', fontSize: 12 }}>{ntpSettingsStatus}</div>}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <button className="btn" onClick={() => openTemplateModal(null)}>
          New Template
        </button>
        {ntpTemplatesLoading && <span style={{ color: 'var(--muted,#6b7280)' }}>Loading</span>}
      </div>
      {ntpTemplates.length === 0 ? (
        <p style={{ color: 'var(--muted,#6b7280)' }}>
          {canManageNtp
            ? 'No templates created yet.'
            : 'No templates are currently assigned to your group.'}
        </p>
      ) : (
        <div className="table-responsive">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Subject</th>
                {canManageNtp && <th>Groups</th>}
                <th>Updated</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {ntpTemplates.map(tpl => (
                <tr key={tpl.id}>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span>{tpl.name}</span>
                      {tpl.is_default && (
                        <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 999, background: '#dcfce7', color: '#166534', fontWeight: 700 }}>
                          Default
                        </span>
                      )}
                    </div>
                  </td>
                  <td>{tpl.subject}</td>
                  {canManageNtp && (
                    <td>
                      {tpl.groups?.length ? (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {tpl.groups.map(group => (
                            <span
                              key={`${tpl.id}-${group}`}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                padding: '2px 8px',
                                borderRadius: 999,
                                background: 'var(--chip-bg,#e0f2fe)',
                                color: 'var(--chip-text,#0369a1)',
                                fontSize: 12,
                              }}
                            >
                              {formatGroupLabel(group)}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ color: 'var(--muted,#6b7280)' }}>Admins/analysts only</span>
                      )}
                    </td>
                  )}
                  <td>{tpl.updated_at ? new Date(tpl.updated_at).toLocaleString() : ''}</td>
                  <td style={{ textAlign: 'right', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                    {templateAccessible(tpl) && (
                      <button className="btn secondary compact" onClick={() => openTemplateModal(tpl)}>Edit</button>
                    )}
                    {templateAccessible(tpl) && (
                      <button className="btn compact" onClick={() => copyTemplate(tpl)}>Copy</button>
                    )}
                    {templateDeletable(tpl) && (
                      <button className="btn danger compact" onClick={() => deleteTemplate(tpl)}>Delete</button>
                    )}
                    {!templateAccessible(tpl) && !templateDeletable(tpl) && (
                      <span style={{ color: 'var(--muted,#6b7280)' }}>No access</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
