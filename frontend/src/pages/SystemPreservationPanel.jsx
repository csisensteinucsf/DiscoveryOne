import { BUILT_IN_PRESERVATION, CASE_NAMING_OPTIONS } from './systemUtils.js'

export function SystemPreservationPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  preservationSourcePayload,
  customPreservationInput,
  setCustomPreservationInput,
  customPreservationSources,
  togglePreservationSource,
  savePreservationSources,
  preservationSaving,
  preservationStatus,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can configure preservation sources.')
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>Preservation Sources</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        Choose the sources DiscoveryOne tracks for holds and preservation coverage. These can be changed after setup without rerunning the setup wizard.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, marginBottom: 14 }}>
        {BUILT_IN_PRESERVATION.map(([key, label]) => {
          const item = preservationSourcePayload.find(source => source.key === key)
          return (
            <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
              <input type="checkbox" checked={!!item?.enabled} onChange={() => togglePreservationSource(key)} />
              {label}
            </label>
          )
        })}
      </div>
      <label style={{ display: 'block', fontWeight: 700 }}>
        Additional preservation sources
        <textarea
          className="input"
          rows={4}
          value={customPreservationInput}
          onChange={e => setCustomPreservationInput(e.target.value)}
          placeholder=""
          style={{ marginTop: 6 }}
        />
      </label>
      <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13, marginTop: 6 }}>
        Enter one source per line or separate sources with commas. Custom sources are tracked as configured preservation sources.
      </div>
      {customPreservationSources.length > 0 && (
        <div style={{ color: 'var(--muted,#6b7280)', marginTop: 10 }}>
          Additional sources: {customPreservationSources.map(item => item.label).join(', ')}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
        <button className="btn secondary" onClick={savePreservationSources} disabled={preservationSaving}>
          {preservationSaving ? 'Saving' : 'Save Preservation Sources'}
        </button>
        {preservationStatus && (
          <span style={{ color: preservationStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
            {preservationStatus}
          </span>
        )}
      </div>
    </div>
  )
}

export function SystemCaseNamingPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  caseNamingMode,
  setCaseNamingMode,
  saveCaseNaming,
  caseNamingSaving,
  caseNamingStatus,
  caseClosureSettings,
  updateCaseClosureSetting,
  saveCaseClosureSettings,
  caseClosureSaving,
  caseClosureStatus,
  caseStatusSettings,
  updateCaseStatusSetting,
  saveCaseStatusSettings,
  caseStatusSaving,
  caseStatusStatus,
  caseRequestSettings,
  updateCaseRequestSetting,
  saveCaseRequestSettings,
  caseRequestSaving,
  caseRequestStatus,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can configure case naming.')
  }

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>eDiscovery Matter Naming</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        Choose how DiscoveryOne names new eDiscovery matters. Existing matter names are not changed when this setting is updated.
      </p>
      <div style={{ display: 'grid', gap: 12 }}>
        {CASE_NAMING_OPTIONS.map(([mode, label, description]) => (
          <label
            key={mode}
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              padding: '12px 14px',
              border: '1px solid var(--border,#d1d5db)',
              borderRadius: 8,
              background: caseNamingMode === mode ? '#eefdf8' : 'var(--panel,#fff)',
            }}
          >
            <input
              type="radio"
              name="case_naming_mode"
              checked={caseNamingMode === mode}
              onChange={() => setCaseNamingMode(mode)}
              style={{ marginTop: 3 }}
            />
            <span>
              <strong>{label}</strong>
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, lineHeight: 1.35, marginTop: 4 }}>
                {description}
              </span>
            </span>
          </label>
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
        <button className="btn secondary" onClick={saveCaseNaming} disabled={caseNamingSaving}>
          {caseNamingSaving ? 'Saving' : 'Save Case Naming'}
        </button>
        {caseNamingStatus && (
          <span style={{ color: caseNamingStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
            {caseNamingStatus}
          </span>
        )}
      </div>

      <div style={{ borderTop: '1px solid var(--border,#d1d5db)', marginTop: 22, paddingTop: 18 }}>
        <div style={titleStyle}>Case Status SLA Thresholds</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          These values control when the matter SLA tab flags NTP acknowledgements and consent requests as overdue. They are stored in System settings so each deployment can use its own legal operations expectations without editing the .env file.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <label style={{ display: 'block', fontWeight: 700 }}>
            NTP acknowledgement days
            <input
              className="input"
              type="number"
              min="1"
              max="3650"
              step="1"
              value={caseStatusSettings?.ntp_ack_days ?? 7}
              onChange={e => updateCaseStatusSetting('ntp_ack_days', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              Number of days after an NTP is sent before an unacknowledged custodian is marked overdue on the matter SLA tab.
            </span>
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Consent completion days
            <input
              className="input"
              type="number"
              min="1"
              max="3650"
              step="1"
              value={caseStatusSettings?.consent_received_days ?? 7}
              onChange={e => updateCaseStatusSetting('consent_received_days', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              Number of days after a consent request is sent before an incomplete consent is marked overdue on the matter SLA tab.
            </span>
          </label>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
          <button className="btn secondary" onClick={saveCaseStatusSettings} disabled={caseStatusSaving}>
            {caseStatusSaving ? 'Saving' : 'Save Case Status SLA Settings'}
          </button>
          {caseStatusStatus && (
            <span style={{ color: caseStatusStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
              {caseStatusStatus}
            </span>
          )}
        </div>
      </div>

      <div style={{ borderTop: '1px solid var(--border,#d1d5db)', marginTop: 22, paddingTop: 18 }}>
        <div style={titleStyle}>Case Request Policy</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          These values control request intake cleanup, requestor visibility, automatic hold behavior, and Purview approval timing. They are stored in System settings so each deployment can tune request workflows without editing the .env file.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 700 }}>
            <input
              type="checkbox"
              checked={!!caseRequestSettings?.requestor_stats_show_global}
              onChange={e => updateCaseRequestSetting('requestor_stats_show_global', e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Show global pending count to requestors
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                When off, requestors only see their own pending request count.
              </span>
            </span>
          </label>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 700 }}>
            <input
              type="checkbox"
              checked={!!caseRequestSettings?.hold_automation_allow_override}
              onChange={e => updateCaseRequestSetting('hold_automation_allow_override', e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Allow automated holds for manually overridden custodians
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                When off, custodians with overridden or unmatched lookup data require manual review before automation proceeds.
              </span>
            </span>
          </label>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 700 }}>
            <input
              type="checkbox"
              checked={!!caseRequestSettings?.auto_rubrik_restore_for_separated_email_holds}
              onChange={e => updateCaseRequestSetting('auto_rubrik_restore_for_separated_email_holds', e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Auto-create Rubrik restore preservation for separated email custodians
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                Off by default for universal deployments. Enable only if your organization uses Rubrik restore tickets for separated custodians with email preservation.
              </span>
            </span>
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Pending cleanup days
            <input className="input" type="number" min="1" max="3650" value={caseRequestSettings?.pending_cleanup_days ?? 30} onChange={e => updateCaseRequestSetting('pending_cleanup_days', e.target.value)} style={{ marginTop: 6 }} />
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Cleanup interval hours
            <input className="input" type="number" min="1" max="168" value={caseRequestSettings?.pending_cleanup_interval_hours ?? 12} onChange={e => updateCaseRequestSetting('pending_cleanup_interval_hours', e.target.value)} style={{ marginTop: 6 }} />
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Preservation status email delay seconds
            <input className="input" type="number" min="0" max="86400" value={caseRequestSettings?.hold_status_email_delay_seconds ?? 300} onChange={e => updateCaseRequestSetting('hold_status_email_delay_seconds', e.target.value)} style={{ marginTop: 6 }} />
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Preservation auto-apply attempts
            <input className="input" type="number" min="1" max="20" value={caseRequestSettings?.preservation_auto_apply_max_attempts ?? 3} onChange={e => updateCaseRequestSetting('preservation_auto_apply_max_attempts', e.target.value)} style={{ marginTop: 6 }} />
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Preservation retry delay seconds
            <input className="input" type="number" min="0" max="3600" value={caseRequestSettings?.preservation_auto_apply_delay_seconds ?? 2} onChange={e => updateCaseRequestSetting('preservation_auto_apply_delay_seconds', e.target.value)} style={{ marginTop: 6 }} />
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Preservation status wait seconds
            <input className="input" type="number" min="0" max="86400" value={caseRequestSettings?.preservation_status_max_seconds ?? 90} onChange={e => updateCaseRequestSetting('preservation_status_max_seconds', e.target.value)} style={{ marginTop: 6 }} />
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Preservation status poll interval seconds
            <input className="input" type="number" min="1" max="3600" value={caseRequestSettings?.preservation_status_interval_seconds ?? 5} onChange={e => updateCaseRequestSetting('preservation_status_interval_seconds', e.target.value)} style={{ marginTop: 6 }} />
          </label>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
          <button className="btn secondary" onClick={saveCaseRequestSettings} disabled={caseRequestSaving}>
            {caseRequestSaving ? 'Saving' : 'Save Case Request Policy'}
          </button>
          {caseRequestStatus && (
            <span style={{ color: caseRequestStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
              {caseRequestStatus}
            </span>
          )}
        </div>
      </div>

      <div style={{ borderTop: '1px solid var(--border,#d1d5db)', marginTop: 22, paddingTop: 18 }}>
        <div style={titleStyle}>Case Status Notifications</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          These values control the matter status notifications sent to requestors. New cases use the default interval unless a matter-specific value is entered, while the scheduler interval and batch size control how often DiscoveryOne checks for due notifications and how many it sends per pass.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Default notification interval days
            <input
              className="input"
              type="number"
              min="1"
              max="3650"
              step="1"
              value={caseClosureSettings?.default_nag_days ?? 180}
              onChange={e => updateCaseClosureSetting('default_nag_days', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              Number of days after case creation, and between later notifications, before DiscoveryOne asks the requestor for a matter status update.
            </span>
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Scheduler interval seconds
            <input
              className="input"
              type="number"
              min="300"
              max="86400"
              step="60"
              value={caseClosureSettings?.loop_seconds ?? 3600}
              onChange={e => updateCaseClosureSetting('loop_seconds', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              How often the backend wakes up to look for matter status notifications that are due. The default is once per hour.
            </span>
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Notification batch size
            <input
              className="input"
              type="number"
              min="1"
              max="500"
              step="1"
              value={caseClosureSettings?.batch_size ?? 25}
              onChange={e => updateCaseClosureSetting('batch_size', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              Maximum number of matter status notification emails DiscoveryOne sends during one scheduler pass.
            </span>
          </label>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 18, flexWrap: 'wrap' }}>
          <button className="btn secondary" onClick={saveCaseClosureSettings} disabled={caseClosureSaving}>
            {caseClosureSaving ? 'Saving' : 'Save Matter Closure Settings'}
          </button>
          {caseClosureStatus && (
            <span style={{ color: caseClosureStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
              {caseClosureStatus}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
