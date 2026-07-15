export function SystemSmtpPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  smtpForm,
  updateSmtpField,
  saveSmtpSettings,
  smtpSaving,
  smtpStatus,
  testEmail,
  setTestEmail,
  sendTestEmail,
  testBusy,
  testStatus,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can update SMTP settings.')
  }

  return (
    <div className="card" style={{ marginBottom: 16, display: 'grid', gap: 12 }}>
      <div style={titleStyle}>SMTP Settings</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        These values are stored securely on the server and are authoritative after first-time setup. SMTP host, credentials, sender, TLS mode, and timeout can all be changed here without editing server files.
      </p>
      <div className="form-grid">
        <label>
          Host
          <input value={smtpForm.host} onChange={e => updateSmtpField('host', e.target.value)} placeholder="smtp.corp.local" />
        </label>
        <label>
          Port
          <input
            type="number"
            value={smtpForm.port}
            onChange={e => updateSmtpField('port', e.target.value)}
            min="1"
          />
        </label>
        <label>
          Timeout Seconds
          <input
            type="number"
            value={smtpForm.timeout_seconds ?? 15}
            onChange={e => updateSmtpField('timeout_seconds', e.target.value)}
            min="1"
            max="300"
          />
        </label>
        <label>
          From Address
          <input type="email" value={smtpForm.from_address} onChange={e => updateSmtpField('from_address', e.target.value)} placeholder="ediscovery@company.com" />
        </label>
        <label>
          Username
          <input value={smtpForm.username} onChange={e => updateSmtpField('username', e.target.value)} placeholder="optional" />
        </label>
        <label>
          Password
          <input type="password" value={smtpForm.password} onChange={e => updateSmtpField('password', e.target.value)} placeholder="Leave blank to keep saved password" />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
          <input type="checkbox" checked={!!smtpForm.use_tls && !smtpForm.use_ssl} onChange={e => updateSmtpField('use_tls', e.target.checked)} disabled={!!smtpForm.use_ssl} />
          Use STARTTLS
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
          <input type="checkbox" checked={!!smtpForm.use_ssl} onChange={e => updateSmtpField('use_ssl', e.target.checked)} />
          Use SMTP over SSL
        </label>
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <button className="btn secondary" onClick={saveSmtpSettings} disabled={smtpSaving}>
          {smtpSaving ? 'Saving' : 'Save Settings'}
        </button>
        {smtpStatus && <span style={{ color: 'var(--muted,#6b7280)' }}>{smtpStatus}</span>}
      </div>
      <div style={{ marginTop: 12 }}>
        <label style={{ display: 'block', marginBottom: 8 }}>Send Test Email</label>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <input
            type="email"
            value={testEmail}
            onChange={e => setTestEmail(e.target.value)}
            placeholder="recipient@company.com"
            style={{ flex: '1 1 240px' }}
          />
          <button className="btn" onClick={sendTestEmail} disabled={testBusy}>
            {testBusy ? 'Sending' : 'Send Test'}
          </button>
        </div>
        {testStatus && <div style={{ marginTop: 6, color: 'var(--muted,#6b7280)' }}>{testStatus}</div>}
      </div>
    </div>
  )
}

export function SystemNotificationsPanel({
  isSysAdmin,
  adminOnlyCard,
  titleStyle,
  notifications,
  updateTeamsWebhook,
  clearTeamsWebhook,
  updateEventEnabled,
  updateEventTemplate,
  updateEmailEventEnabled,
  updateEmailEventSubject,
  updateEmailEventBody,
  updateSearchDeliveryReminderSetting,
  updateConsentNotificationSetting,
  saveNotifications,
  notificationsSaving,
  notificationsStatus,
}) {
  if (!isSysAdmin) {
    return adminOnlyCard('Only system administrators can configure notifications.')
  }

  const teamsPlaceholdersByEvent = {
    case_request_submitted: '{request_type}, {case_label}, {requestor}, {status}, {link}',
    admin_help: '{identifier}, {ip}, {note}',
    registration_request: '{name}, {email}',
    malware_upload_detected: '{filename}, {user}, {ip}',
    consent_completed: '{case_label}, {custodian_name}, {custodian_email}, {status}, {case_link}, {envelope_id}',
    ticket_assigned: '{ticket}, {ticket_category}, {assigned_to}, {status}, {custodians}, {case_link}, {ticket_link}',
    ticket_completed: '{ticket}, {ticket_category}, {status}, {custodians}, {case_link}, {ticket_link}',
  }
  const emailPlaceholdersByEvent = {
    admin_help: '{app_name}, {identifier}, {ip}, {note}',
    registration_request_admins: '{app_name}, {name}, {email}',
    registration_invite: '{app_name}, {name}, {action_text}, {expires_hours}, {link}, {sso_display_name}',
    registration_ready: '{app_name}, {name}, {sso_display_name}, {login_link}',
    registration_decline: '{app_name}, {name}, {reason}',
    registration_existing_account: '{app_name}, {username}, {access_guidance}, {sso_display_name}',
  }
  const categoryOrder = ['Requests', 'Consent', 'Tickets', 'Accounts', 'Security', 'System', 'General']
  const groupEvents = (events = {}) => {
    const grouped = {}
    Object.entries(events || {}).forEach(([key, meta]) => {
      const category = (meta?.category || 'General') || 'General'
      if (!grouped[category]) grouped[category] = []
      grouped[category].push([key, meta])
    })
    Object.values(grouped).forEach(items => {
      items.sort((a, b) => {
        const aLabel = (a[1]?.label || a[0] || '').toString()
        const bLabel = (b[1]?.label || b[0] || '').toString()
        return aLabel.localeCompare(bLabel)
      })
    })
    return grouped
  }
  const sortedCategories = (grouped) => Object.keys(grouped).sort((a, b) => {
    const ai = categoryOrder.indexOf(a)
    const bi = categoryOrder.indexOf(b)
    if (ai === -1 && bi === -1) return a.localeCompare(b)
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  })
  const teamsGrouped = groupEvents(notifications.teams?.events || {})
  const emailGrouped = groupEvents(notifications.email?.events || {})
  const weekdayOptions = [
    ['0', 'Monday'],
    ['1', 'Tuesday'],
    ['2', 'Wednesday'],
    ['3', 'Thursday'],
    ['4', 'Friday'],
    ['5', 'Saturday'],
    ['6', 'Sunday'],
  ]

  return (
    <div className="card" style={{ marginBottom: 16, display: 'grid', gap: 16 }}>
      <div style={titleStyle}>Notifications</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        Configure email and Teams notification text from stored settings. These templates let each deployment use its own app name, support language, and account workflow wording without code changes.
      </p>

      <div style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Search Delivery Reminders</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          DiscoveryOne can remind the assigned analyst when exported searches have not been marked delivered or not required. These values are stored in System settings and no longer need to be edited in the .env file.
        </p>
        <div className="form-grid">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={notifications.search_delivery_reminders?.enabled !== false}
              onChange={e => updateSearchDeliveryReminderSetting('enabled', e.target.checked)}
            />
            Enable search delivery reminders
          </label>
          <label>
            Reminder interval days
            <input
              className="input"
              type="number"
              min="1"
              max="365"
              value={notifications.search_delivery_reminders?.interval_days ?? 7}
              onChange={e => updateSearchDeliveryReminderSetting('interval_days', e.target.value)}
            />
          </label>
          <label>
            Scheduler check seconds
            <input
              className="input"
              type="number"
              min="300"
              max="86400"
              value={notifications.search_delivery_reminders?.loop_seconds ?? 3600}
              onChange={e => updateSearchDeliveryReminderSetting('loop_seconds', e.target.value)}
            />
          </label>
          <label>
            Batch size
            <input
              className="input"
              type="number"
              min="1"
              max="500"
              value={notifications.search_delivery_reminders?.batch_size ?? 25}
              onChange={e => updateSearchDeliveryReminderSetting('batch_size', e.target.value)}
            />
          </label>
        </div>
      </div>

      <div style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Consent Notifications</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          Configure analyst consent completion emails and weekly pending consent summaries. These values are stored in System settings and are no longer set with CONSENT_* values in the .env file.
        </p>
        <div className="form-grid">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={notifications.consent_notifications?.completed_email_enabled !== false}
              onChange={e => updateConsentNotificationSetting('completed_email_enabled', e.target.checked)}
            />
            Email the analyst when a consent is completed
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            <input
              type="checkbox"
              checked={notifications.consent_notifications?.weekly_pending_enabled !== false}
              onChange={e => updateConsentNotificationSetting('weekly_pending_enabled', e.target.checked)}
            />
            Send weekly pending consent summaries
          </label>
          <label>
            Weekly summary day
            <select
              className="input"
              value={String(notifications.consent_notifications?.weekly_weekday ?? 4)}
              onChange={e => updateConsentNotificationSetting('weekly_weekday', e.target.value)}
            >
              {weekdayOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>
            Weekly summary hour
            <input
              className="input"
              type="number"
              min="0"
              max="23"
              value={notifications.consent_notifications?.weekly_hour ?? 8}
              onChange={e => updateConsentNotificationSetting('weekly_hour', e.target.value)}
            />
          </label>
          <label>
            Weekly summary minute
            <input
              className="input"
              type="number"
              min="0"
              max="59"
              value={notifications.consent_notifications?.weekly_minute ?? 0}
              onChange={e => updateConsentNotificationSetting('weekly_minute', e.target.value)}
            />
          </label>
          <label>
            Weekly summary timezone
            <input
              className="input"
              value={notifications.consent_notifications?.weekly_timezone || 'UTC'}
              onChange={e => updateConsentNotificationSetting('weekly_timezone', e.target.value)}
              placeholder="America/Los_Angeles"
            />
          </label>
        </div>
      </div>

      <div style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Email Templates</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          Toggle account emails and edit their subjects and bodies. Placeholders are shown for each template and are filled when the email is sent.
        </p>
        <div style={{ display: 'grid', gap: 16 }}>
          {sortedCategories(emailGrouped).map(category => (
            <div key={category} style={{ display: 'grid', gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--muted,#6b7280)' }}>{category}</div>
              {emailGrouped[category].map(([key, meta]) => (
                <div key={key} style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 8, padding: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                      <input
                        type="checkbox"
                        checked={meta?.enabled !== false}
                        onChange={e => updateEmailEventEnabled(key, e.target.checked)}
                      />
                      {meta?.label || key.replace(/_/g, ' ')}
                    </label>
                    <div style={{ color: 'var(--muted,#6b7280)', fontSize: 12 }}>
                      Placeholders: {emailPlaceholdersByEvent[key] || '{app_name}'}
                    </div>
                  </div>
                  <label style={{ display: 'block', marginTop: 10, fontWeight: 600 }}>
                    Subject
                    <input
                      className="input"
                      value={meta?.subject || ''}
                      onChange={e => updateEmailEventSubject(key, e.target.value)}
                      style={{ marginTop: 6 }}
                    />
                  </label>
                  <label style={{ display: 'block', marginTop: 10, fontWeight: 600 }}>
                    Body
                    <textarea
                      className="input"
                      rows={5}
                      value={meta?.body || ''}
                      onChange={e => updateEmailEventBody(key, e.target.value)}
                      style={{ width: '100%', marginTop: 6, resize: 'vertical', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}
                    ></textarea>
                  </label>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 8 }}>Teams Messages</div>
        <label>
          Teams Webhook URL
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="password"
              value={notifications.teams?.webhook_url || ''}
              onChange={e => updateTeamsWebhook(e.target.value)}
              placeholder={notifications.teams?.webhook_configured ? 'Configured - leave blank to keep' : 'https://...'}
              disabled={notifications.teams?.has_env_override}
            />
            {notifications.teams?.webhook_configured && !notifications.teams?.has_env_override && (
              <button type="button" className="btn secondary" onClick={clearTeamsWebhook}>
                Remove
              </button>
            )}
          </div>
          <small style={{ color: 'var(--muted,#6b7280)' }}>
            {notifications.teams?.has_env_override
              ? 'Using a temporary pre-setup webhook from the server environment.'
              : notifications.teams?.webhook_configured
                ? 'A webhook is configured. Leave this blank to keep it, enter a new HTTPS URL to replace it, or click Remove.'
                : 'Paste the HTTPS incoming webhook URL for the Teams channel that should receive alerts.'}
          </small>
        </label>
        <p style={{ color: 'var(--muted,#6b7280)' }}>
          Check the events to send to Teams and edit the message. Available placeholders are noted per event.
        </p>
        <div style={{ display: 'grid', gap: 16 }}>
          {sortedCategories(teamsGrouped).map(category => (
            <div key={category} style={{ display: 'grid', gap: 12 }}>
              <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--muted,#6b7280)' }}>{category}</div>
              {teamsGrouped[category].map(([key, meta]) => (
                <div key={key} style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 8, padding: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
                      <input
                        type="checkbox"
                        checked={!!meta?.enabled}
                        onChange={e => updateEventEnabled(key, e.target.checked)}
                      />
                      {meta?.label || key.replace(/_/g, ' ')}
                    </label>
                    <div style={{ color: 'var(--muted,#6b7280)', fontSize: 12 }}>
                      Placeholders: {teamsPlaceholdersByEvent[key] || 'see message'}
                    </div>
                  </div>
                  <textarea
                    rows={3}
                    value={meta?.template || ''}
                    onChange={e => updateEventTemplate(key, e.target.value)}
                    style={{ width: '100%', marginTop: 8, resize: 'vertical' }}
                  ></textarea>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button className="btn secondary" onClick={saveNotifications} disabled={notificationsSaving}>
          {notificationsSaving ? 'Saving..' : 'Save Notification Settings'}
        </button>
        {notificationsStatus && (
          <span style={{ color: notificationsStatus.toLowerCase().includes('unable') ? '#b91c1c' : 'var(--muted,#6b7280)' }}>
            {notificationsStatus}
          </span>
        )}
      </div>
    </div>
  )
}
