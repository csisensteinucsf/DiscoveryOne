import FileDropZone from '../components/FileDropZone.jsx'

export function SystemBackupsPanel({
  active,
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  backupHealth,
  backupsLoading,
  runScheduledBackup,
  custodianLookupBusy,
  runFullCustodianLookup,
  loadBackups,
  backupStatus,
  backupSettings,
  updateBackupSetting,
  saveBackupSettings,
  backupSettingsSaving,
  backupSettingsStatus,
  custodianLookupStatus,
  lastBackup,
  describeBackupType,
  restoreInputRef,
  onRestoreFileChange,
  runRestore,
  restoreBusy,
  restoreFile,
  restoreStatus,
  restoreKey,
  setRestoreKey,
}) {
  if (!active) return null
  if (!isSysAdmin) return adminOnlyCard('Only system administrators can manage backups.')

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>Database Backups</div>
      <p style={{ color: 'var(--muted,#6b7280)' }}>
        Automatic backups use the schedule stored in System settings and are encrypted on disk. Run an ad hoc snapshot before major changes or restore from an encrypted dump.
      </p>
      {backupHealth?.warning && (
        <div
          style={{
            margin: '8px 0 16px',
            padding: '8px 12px',
            borderRadius: 6,
            background: 'rgba(185,28,28,0.12)',
            color: '#b91c1c',
            fontWeight: 600,
          }}
        >
          {backupHealth.warning}
        </div>
      )}
      <div style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 8, padding: 12, marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Backup Schedule</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 700 }}>
            <input
              type="checkbox"
              checked={backupSettings?.automatic_enabled !== false}
              onChange={e => updateBackupSetting('automatic_enabled', e.target.checked)}
              style={{ marginTop: 3 }}
            />
            <span>
              Run automatic backups
              <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
                When enabled, the backend scheduler creates encrypted backups on the configured cadence.
              </span>
            </span>
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Backup interval hours
            <input
              className="input"
              type="number"
              min="1"
              max="168"
              step="1"
              value={backupSettings?.interval_hours ?? 6}
              onChange={e => updateBackupSetting('interval_hours', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              How often scheduled backups should run. Changes apply to the next scheduler cycle.
            </span>
          </label>
          <label style={{ display: 'block', fontWeight: 700 }}>
            Retention hours
            <input
              className="input"
              type="number"
              min="1"
              max="8760"
              step="1"
              value={backupSettings?.retention_hours ?? 48}
              onChange={e => updateBackupSetting('retention_hours', e.target.value)}
              style={{ marginTop: 6 }}
            />
            <span style={{ display: 'block', color: 'var(--muted,#6b7280)', fontSize: 13, fontWeight: 400, marginTop: 4 }}>
              Backups older than this are removed after a successful backup run.
            </span>
          </label>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
          <button className="btn secondary" type="button" onClick={saveBackupSettings} disabled={backupSettingsSaving}>
            {backupSettingsSaving ? 'Saving' : 'Save Backup Schedule'}
          </button>
          {backupSettingsStatus && (
            <span style={{ color: backupSettingsStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
              {backupSettingsStatus}
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <button className="btn secondary" onClick={runScheduledBackup} disabled={backupsLoading}>
          {backupsLoading ? 'Running' : 'Run Backup Now'}
        </button>
        <button className="btn secondary" onClick={runFullCustodianLookup} disabled={custodianLookupBusy}>
          {custodianLookupBusy ? 'Running lookup' : 'Full Custodian Lookup and Update'}
        </button>
        <button className="btn ghost" onClick={loadBackups} disabled={backupsLoading}>Refresh Status</button>
        {backupStatus && <span style={{ color: 'var(--muted,#6b7280)' }}>{backupStatus}</span>}
        {custodianLookupStatus && <span style={{ color: 'var(--muted,#6b7280)' }}>{custodianLookupStatus}</span>}
      </div>
      <div>
        {backupsLoading ? (
          <div>Loading backup status</div>
        ) : lastBackup ? (
          <div style={{ color: 'var(--text)' }}>
            <div>Last backup recorded: <strong>{new Date(lastBackup.created_at).toLocaleString()}</strong></div>
            <div style={{ color: 'var(--muted,#6b7280)' }}>Type: {describeBackupType(lastBackup.label)}</div>
          </div>
        ) : (
          <div style={{ color: 'var(--muted,#6b7280)' }}>
            Backups located in /backup folder. No successful backups recorded yet.
          </div>
        )}
      </div>
      <div style={{ marginTop: 8, color: 'var(--muted,#6b7280)' }}>
        Backups are stored on the host in the /backup directory.
      </div>
      <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--border,#e5e7eb)' }}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Restore From Backup</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginBottom: 8 }}>
          Upload an encrypted backup. Restoring immediately replaces the entire current database.
        </p>
        <FileDropZone
          disabled={restoreBusy}
          onFiles={(files) => onRestoreFileChange({ target: { files } })}
          prompt="Drag and drop an encrypted backup here"
        >
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
            <label className="btn secondary" style={{ cursor: 'pointer' }}>
              Choose Backup
              <input
                type="file"
                ref={restoreInputRef}
                style={{ display: 'none' }}
                onChange={onRestoreFileChange}
              />
            </label>
            <button className="btn danger" onClick={runRestore} disabled={restoreBusy || !restoreFile}>
              {restoreBusy ? 'Restoring' : 'Restore Now'}
            </button>
            {restoreStatus && <span style={{ color: 'var(--muted,#6b7280)' }}>{restoreStatus}</span>}
          </div>
        </FileDropZone>
        <div style={{ marginTop: 12, maxWidth: 360 }}>
          <label style={{ display: 'block', marginBottom: 4 }}>Encryption Key</label>
          <input type="password" value={restoreKey} onChange={(e) => setRestoreKey(e.target.value)} placeholder="Base64 key" />
          <small style={{ color: 'var(--muted,#6b7280)' }}>Leave blank to use the server-configured key.</small>
        </div>
      </div>
    </div>
  )
}

export function SystemBrandingPanel({
  active,
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  labelStyle,
  canManageBranding,
  onUploadLogo,
  selectedFileName,
  brandingText,
  setBrandingText,
  saveBrandingText,
  brandingTextSaving,
  deploymentSettings,
  setDeploymentSettings,
  saveDeploymentSettings,
  deploymentSaving,
  deploymentStatus,
  activeLogo,
  onResetLogo,
  logos,
  onSelectLogo,
  onDeleteLogo,
}) {
  if (!active) return null
  if (!isSysAdmin) return adminOnlyCard('Only system administrators can change branding.')

  const defaultLogoUrl = '/img/D1_Logo.png'

  return (
    <div className="card">
      <div style={titleStyle}>Branding</div>
      <div style={labelStyle}>Brand Text</div>
      <div className="form-grid" style={{ marginBottom: 16 }}>
        <label>
          App Name
          <input
            className="input"
            value={brandingText?.app_name || ''}
            onChange={e => setBrandingText(prev => ({ ...(prev || {}), app_name: e.target.value }))}
            disabled={!canManageBranding || brandingTextSaving}
            placeholder="DiscoveryOne"
          />
          <small style={{ color: 'var(--muted,#6b7280)' }}>Shown in the app shell, login screen, browser title, and notification templates.</small>
        </label>
        <label>
          App Tagline
          <input
            className="input"
            value={brandingText?.app_tagline || ''}
            onChange={e => setBrandingText(prev => ({ ...(prev || {}), app_tagline: e.target.value }))}
            disabled={!canManageBranding || brandingTextSaving}
            placeholder="eDiscovery Case Manager"
          />
          <small style={{ color: 'var(--muted,#6b7280)' }}>Shown under the app name in the sidebar.</small>
        </label>
      </div>
      <button className="btn secondary" onClick={saveBrandingText} disabled={!canManageBranding || brandingTextSaving}>
        {brandingTextSaving ? 'Saving Brand Text' : 'Save Brand Text'}
      </button>
      <div style={{ ...labelStyle, marginTop: 24 }}>Deployment Links</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        These settings control the public HTTPS links DiscoveryOne places in emails, SSO redirects, approvals, and workflow notifications. They are stored in System settings so the app does not require APP_BASE_URL or APP_ALLOWED_HOSTS values in the .env file.
      </p>
      <div className="form-grid" style={{ marginBottom: 16 }}>
        <label>
          Public App URL
          <input
            className="input"
            value={deploymentSettings?.app_base_url || ''}
            onChange={e => setDeploymentSettings(prev => ({ ...(prev || {}), app_base_url: e.target.value }))}
            disabled={!canManageBranding || deploymentSaving}
            placeholder="https://discoveryone.example.edu"
          />
          <small style={{ color: 'var(--muted,#6b7280)' }}>Must use HTTPS. This is the base URL used in generated links and redirects.</small>
        </label>
        <label>
          Allowed Hosts
          <input
            className="input"
            value={deploymentSettings?.allowed_hosts || ''}
            onChange={e => setDeploymentSettings(prev => ({ ...(prev || {}), allowed_hosts: e.target.value }))}
            disabled={!canManageBranding || deploymentSaving}
            placeholder="discoveryone.example.edu, discoveryone.local"
          />
          <small style={{ color: 'var(--muted,#6b7280)' }}>Comma-separated hostnames that DiscoveryOne may trust when constructing links from incoming requests.</small>
        </label>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 20 }}>
        <button className="btn secondary" onClick={saveDeploymentSettings} disabled={!canManageBranding || deploymentSaving}>
          {deploymentSaving ? 'Saving Deployment Settings' : 'Save Deployment Settings'}
        </button>
        {deploymentStatus && (
          <span style={{ color: deploymentStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
            {deploymentStatus}
          </span>
        )}
      </div>

      <div style={{ ...labelStyle, marginTop: 20 }}>Brand Logo</div>
      <FileDropZone
        disabled={!canManageBranding}
        onFiles={(files) => onUploadLogo({ target: { files } })}
        prompt="Drag and drop a brand logo here"
      >
        <label className="btn secondary" style={{ display:'inline-block', cursor: canManageBranding ? 'pointer' : 'not-allowed', opacity: canManageBranding ? 1 : 0.6 }}>
          Choose File
          <input type="file" onChange={onUploadLogo} style={{ display:'none' }} disabled={!canManageBranding} />
        </label>
        <span style={{ marginLeft: 8, color:'var(--muted,#6b7280)' }}>{selectedFileName}</span>
      </FileDropZone>

      <div style={{ display:'flex', gap:32, alignItems:'center', marginTop:16, flexWrap:'wrap' }}>
        <div key="default-logo" style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:8 }}>
          <img src={defaultLogoUrl} alt="Default logo" style={{ height:60, objectFit:'contain' }} />
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <label>
              <input type="radio" name="activeLogo" checked={!activeLogo} onChange={onResetLogo} disabled={!canManageBranding} />
              Default
            </label>
          </div>
        </div>
        {logos.length === 0 && (
          <div style={{ color:'var(--muted,#6b7280)' }}>No custom logos uploaded yet.</div>
        )}
        {logos.map(l => (
          <div key={l.id || l.filename} style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:8 }}>
            <img src={l.url} alt={l.name || 'Uploaded logo'} style={{ height:60, objectFit:'contain' }} />
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <label><input type="radio" name="activeLogo" checked={activeLogo === l.id} onChange={() => onSelectLogo(l.id)} disabled={!canManageBranding} /> Selected</label>
              <button className="btn danger" onClick={() => onDeleteLogo(l.id)} disabled={!canManageBranding}>Delete</button>
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 12 }}>
        <button className="btn secondary" onClick={onResetLogo} disabled={!canManageBranding || !activeLogo}>Use Default Logo</button>
      </div>
    </div>
  )
}
