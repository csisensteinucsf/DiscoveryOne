import { useCallback, useState } from 'react'
import { MASKED_SECRET_VALUE, secretInputValue } from './systemUtils.js'

const smtpDefaults = {
  host: '',
  port: 587,
  username: '',
  password: '',
  from_address: '',
  use_tls: true,
  use_ssl: false,
  timeout_seconds: 15,
}

const notificationsDefaults = {
  teams: {
    webhook_url: '',
    webhook_configured: false,
    clear_webhook: false,
    has_env_override: false,
    events: {},
  },
  email: { events: {} },
  search_delivery_reminders: { enabled: true, interval_days: 7, loop_seconds: 3600, batch_size: 25 },
  consent_notifications: {
    completed_email_enabled: true,
    weekly_pending_enabled: true,
    weekly_weekday: 4,
    weekly_hour: 8,
    weekly_minute: 0,
    weekly_timezone: 'UTC',
  },
}

const teamsFromResponse = (teams = {}) => ({
  webhook_url: secretInputValue(teams.webhook_url),
  webhook_configured: teams.webhook_url === MASKED_SECRET_VALUE || !!teams.webhook_configured,
  clear_webhook: false,
  has_env_override: !!teams.has_env_override,
  events: teams.events || {},
})

export function useSystemMessagingWorkflow({ apiBase, isSysAdmin }) {
  const [smtpForm, setSmtpForm] = useState(smtpDefaults)
  const [smtpSaving, setSmtpSaving] = useState(false)
  const [smtpStatus, setSmtpStatus] = useState(null)
  const [testEmail, setTestEmail] = useState('')
  const [testStatus, setTestStatus] = useState(null)
  const [testBusy, setTestBusy] = useState(false)
  const [notifications, setNotifications] = useState(notificationsDefaults)
  const [notificationsStatus, setNotificationsStatus] = useState(null)
  const [notificationsSaving, setNotificationsSaving] = useState(false)

  const applySmtpSettings = useCallback((smtp) => {
    if (smtp) {
      setSmtpForm({
        host: smtp.host || '',
        port: smtp.port ?? 587,
        username: smtp.username || '',
        password: secretInputValue(smtp.password),
        from_address: smtp.from_address || '',
        use_tls: smtp.use_tls !== false,
        use_ssl: !!smtp.use_ssl,
        timeout_seconds: smtp.timeout_seconds ?? 15,
      })
    } else {
      setSmtpForm({ ...smtpDefaults })
    }
  }, [])

  const loadNotifications = useCallback(async () => {
    if (!isSysAdmin) {
      setNotifications({ ...notificationsDefaults })
      return
    }
    setNotificationsStatus(null)
    try {
      const res = await fetch(`${apiBase}/system/notifications`, { credentials: 'include' })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const teams = data?.teams || {}
      const email = data?.email || {}
      const searchDeliveryReminders = data?.search_delivery_reminders || notificationsDefaults.search_delivery_reminders
      const consentNotifications = data?.consent_notifications || notificationsDefaults.consent_notifications
      setNotifications({
        teams: teamsFromResponse(teams),
        email: {
          events: email.events || {},
        },
        search_delivery_reminders: {
          enabled: searchDeliveryReminders.enabled !== false,
          interval_days: searchDeliveryReminders.interval_days ?? 7,
          loop_seconds: searchDeliveryReminders.loop_seconds ?? 3600,
          batch_size: searchDeliveryReminders.batch_size ?? 25,
        },
        consent_notifications: {
          completed_email_enabled: consentNotifications.completed_email_enabled !== false,
          weekly_pending_enabled: consentNotifications.weekly_pending_enabled !== false,
          weekly_weekday: consentNotifications.weekly_weekday ?? 4,
          weekly_hour: consentNotifications.weekly_hour ?? 8,
          weekly_minute: consentNotifications.weekly_minute ?? 0,
          weekly_timezone: consentNotifications.weekly_timezone || 'UTC',
        },
      })
    } catch (err) {
      console.error(err)
      setNotificationsStatus('Unable to load notification settings.')
      setNotifications({ ...notificationsDefaults })
    }
  }, [apiBase, isSysAdmin])

  const updateSmtpField = (key, value) => {
    setSmtpForm(prev => ({ ...prev, [key]: value }))
  }

  const updateTeamsWebhook = (value) => {
    setNotifications(prev => ({
      ...prev,
      teams: { ...(prev.teams || {}), webhook_url: value, clear_webhook: false },
    }))
  }

  const clearTeamsWebhook = () => {
    setNotifications(prev => ({
      ...prev,
      teams: {
        ...(prev.teams || {}),
        webhook_url: '',
        webhook_configured: false,
        clear_webhook: true,
      },
    }))
  }

  const updateEventEnabled = (key, enabled) => {
    setNotifications(prev => {
      const events = { ...((prev.teams || {}).events || {}) }
      const existing = events[key] || {}
      events[key] = { ...existing, enabled }
      return { ...prev, teams: { ...(prev.teams || {}), events } }
    })
  }

  const updateEventTemplate = (key, template) => {
    setNotifications(prev => {
      const events = { ...((prev.teams || {}).events || {}) }
      const existing = events[key] || {}
      events[key] = { ...existing, template }
      return { ...prev, teams: { ...(prev.teams || {}), events } }
    })
  }


  const updateEmailEventEnabled = (key, enabled) => {
    setNotifications(prev => {
      const events = { ...((prev.email || {}).events || {}) }
      const existing = events[key] || {}
      events[key] = { ...existing, enabled }
      return { ...prev, email: { ...(prev.email || {}), events } }
    })
  }

  const updateEmailEventSubject = (key, subject) => {
    setNotifications(prev => {
      const events = { ...((prev.email || {}).events || {}) }
      const existing = events[key] || {}
      events[key] = { ...existing, subject }
      return { ...prev, email: { ...(prev.email || {}), events } }
    })
  }

  const updateEmailEventBody = (key, body) => {
    setNotifications(prev => {
      const events = { ...((prev.email || {}).events || {}) }
      const existing = events[key] || {}
      events[key] = { ...existing, body }
      return { ...prev, email: { ...(prev.email || {}), events } }
    })
  }

  const updateSearchDeliveryReminderSetting = (key, value) => {
    setNotifications(prev => ({
      ...prev,
      search_delivery_reminders: {
        ...(prev.search_delivery_reminders || notificationsDefaults.search_delivery_reminders),
        [key]: value,
      },
    }))
  }

  const updateConsentNotificationSetting = (key, value) => {
    setNotifications(prev => ({
      ...prev,
      consent_notifications: {
        ...(prev.consent_notifications || notificationsDefaults.consent_notifications),
        [key]: value,
      },
    }))
  }
  const saveSmtpSettings = async () => {
    if (!isSysAdmin) return
    setSmtpSaving(true)
    setSmtpStatus(null)
    try {
      const payload = {
        host: (smtpForm.host || '').trim(),
        port: Number(smtpForm.port) || 587,
        username: (smtpForm.username || '').trim(),
        password: smtpForm.password || '',
        from_address: (smtpForm.from_address || '').trim(),
        use_tls: !!smtpForm.use_tls && !smtpForm.use_ssl,
        use_ssl: !!smtpForm.use_ssl,
        timeout_seconds: Number(smtpForm.timeout_seconds) || 15,
      }
      const res = await fetch(`${apiBase}/system/smtp`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const next = data.smtp || {}
      setSmtpForm({
        host: next.host || '',
        port: next.port ?? 587,
        username: next.username || '',
        password: '',
        from_address: next.from_address || '',
        use_tls: next.use_tls !== false,
        use_ssl: !!next.use_ssl,
        timeout_seconds: next.timeout_seconds ?? 15,
      })
      setSmtpStatus('SMTP settings saved.')
    } catch (err) {
      console.error(err)
      setSmtpStatus('Unable to save SMTP settings.')
    } finally {
      setSmtpSaving(false)
    }
  }

  const saveNotifications = async () => {
    if (!isSysAdmin) return
    setNotificationsSaving(true)
    setNotificationsStatus(null)
    try {
      const payload = {
        teams: {
          webhook_url: (notifications.teams?.webhook_url || '').trim(),
          clear_webhook: !!notifications.teams?.clear_webhook,
          events: {},
        },
        email: {
          events: {},
        },
        search_delivery_reminders: {
          enabled: notifications.search_delivery_reminders?.enabled !== false,
          interval_days: Number(notifications.search_delivery_reminders?.interval_days) || 7,
          loop_seconds: Number(notifications.search_delivery_reminders?.loop_seconds) || 3600,
          batch_size: Number(notifications.search_delivery_reminders?.batch_size) || 25,
        },
        consent_notifications: {
          completed_email_enabled: notifications.consent_notifications?.completed_email_enabled !== false,
          weekly_pending_enabled: notifications.consent_notifications?.weekly_pending_enabled !== false,
          weekly_weekday: Number(notifications.consent_notifications?.weekly_weekday ?? 4),
          weekly_hour: Number(notifications.consent_notifications?.weekly_hour ?? 8),
          weekly_minute: Number(notifications.consent_notifications?.weekly_minute ?? 0),
          weekly_timezone: (notifications.consent_notifications?.weekly_timezone || 'UTC').trim(),
        },
      }
      Object.entries(notifications.teams?.events || {}).forEach(([key, meta]) => {
        payload.teams.events[key] = {
          enabled: !!meta?.enabled,
          template: (meta?.template || '').trim(),
        }
      })
      Object.entries(notifications.email?.events || {}).forEach(([key, meta]) => {
        payload.email.events[key] = {
          enabled: !!meta?.enabled,
          subject: (meta?.subject || '').trim(),
          body: (meta?.body || '').trim(),
        }
      })
      const res = await fetch(`${apiBase}/system/notifications`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const teams = data?.teams || {}
      const email = data?.email || {}
      const searchDeliveryReminders = data?.search_delivery_reminders || notificationsDefaults.search_delivery_reminders
      const consentNotifications = data?.consent_notifications || notificationsDefaults.consent_notifications
      setNotifications({
        teams: teamsFromResponse(teams),
        email: {
          events: email.events || {},
        },
        search_delivery_reminders: {
          enabled: searchDeliveryReminders.enabled !== false,
          interval_days: searchDeliveryReminders.interval_days ?? 7,
          loop_seconds: searchDeliveryReminders.loop_seconds ?? 3600,
          batch_size: searchDeliveryReminders.batch_size ?? 25,
        },
        consent_notifications: {
          completed_email_enabled: consentNotifications.completed_email_enabled !== false,
          weekly_pending_enabled: consentNotifications.weekly_pending_enabled !== false,
          weekly_weekday: consentNotifications.weekly_weekday ?? 4,
          weekly_hour: consentNotifications.weekly_hour ?? 8,
          weekly_minute: consentNotifications.weekly_minute ?? 0,
          weekly_timezone: consentNotifications.weekly_timezone || 'UTC',
        },
      })
      setNotificationsStatus('Notification settings saved.')
    } catch (err) {
      console.error(err)
      setNotificationsStatus(err?.message || 'Unable to save notification settings.')
    } finally {
      setNotificationsSaving(false)
    }
  }

  const sendTestEmail = async () => {
    if (!isSysAdmin) return
    const trimmed = (testEmail || '').trim()
    if (!trimmed) {
      setTestStatus('Enter a destination email first.')
      return
    }
    setTestBusy(true)
    setTestStatus('Sending test email')
    try {
      const res = await fetch(`${apiBase}/system/email/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ to: trimmed }),
      })
      if (!res.ok) throw new Error(await res.text())
      setTestStatus('Test email sent successfully.')
      setTestEmail('')
    } catch (err) {
      console.error(err)
      setTestStatus('Test email failed. Check SMTP settings and logs.')
    } finally {
      setTestBusy(false)
    }
  }

  return {
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
    loadNotifications,
    applySmtpSettings,
  }
}

