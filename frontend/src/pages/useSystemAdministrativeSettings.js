import { useCallback, useEffect, useRef, useState } from 'react'

const BRANDING_DEFAULTS = {
  app_name: 'DiscoveryOne',
  app_tagline: 'eDiscovery Case Manager',
}

const DEPLOYMENT_DEFAULTS = {
  app_base_url: '',
  allowed_hosts: '',
}

const ACCOUNT_REVIEW_DEFAULTS = {
  enabled: true,
  interval_days: 120,
  check_interval_hours: 12,
  last_sent_at: null,
}

const NTP_SETTINGS_DEFAULTS = {
  archive_bcc_address: '',
  archive_copy_required: false,
  reserved_archive_bcc_addresses: '',
  reminder_interval_days: 14,
  reminder_duration_days: 90,
  reminder_loop_seconds: 900,
}

export function useSystemAdministrativeSettings({
  apiBase,
  isSysAdmin,
  canManageBranding,
  loadTemplates,
}) {
  const [logos, setLogos] = useState([])
  const [activeLogo, setActiveLogo] = useState(null)
  const [status, setStatus] = useState(null)
  const [selectedFileName, setSelectedFileName] = useState('No file chosen')
  const [brandingText, setBrandingText] = useState(BRANDING_DEFAULTS)
  const [brandingTextSaving, setBrandingTextSaving] = useState(false)
  const [deploymentSettings, setDeploymentSettings] = useState(DEPLOYMENT_DEFAULTS)
  const [deploymentSaving, setDeploymentSaving] = useState(false)
  const [deploymentStatus, setDeploymentStatus] = useState(null)
  const [accountReviewSettings, setAccountReviewSettings] = useState(ACCOUNT_REVIEW_DEFAULTS)
  const [accountReviewStatus, setAccountReviewStatus] = useState(null)
  const [accountReviewSaving, setAccountReviewSaving] = useState(false)
  const [ntpSettings, setNtpSettings] = useState(NTP_SETTINGS_DEFAULTS)
  const [ntpSettingsStatus, setNtpSettingsStatus] = useState(null)
  const [ntpSettingsSaving, setNtpSettingsSaving] = useState(false)
  const statusTimerRef = useRef(null)

  useEffect(() => () => {
    if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
  }, [])

  const flash = useCallback((message) => {
    setStatus(message)
    if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
    statusTimerRef.current = window.setTimeout(() => setStatus(null), 3000)
  }, [])

  const resetAdministrativeSettings = useCallback(() => {
    setActiveLogo(null)
    setLogos([])
    setBrandingText({ ...BRANDING_DEFAULTS })
    setDeploymentSettings({ ...DEPLOYMENT_DEFAULTS })
    setDeploymentStatus(null)
    setAccountReviewSettings({ ...ACCOUNT_REVIEW_DEFAULTS })
    setAccountReviewStatus(null)
    setNtpSettings({ ...NTP_SETTINGS_DEFAULTS })
    setNtpSettingsStatus(null)
  }, [])

  const applyAdministrativeSettings = useCallback((data = {}) => {
    const activeId = data.active_logo !== undefined ? data.active_logo : (data.active_logo_id ?? null)
    setActiveLogo(activeId)
    setLogos(Array.isArray(data.logos) ? data.logos : [])

    const branding = data.branding || {}
    setBrandingText({
      app_name: branding.app_name || data.app_name || BRANDING_DEFAULTS.app_name,
      app_tagline: branding.app_tagline || data.app_tagline || BRANDING_DEFAULTS.app_tagline,
    })

    const deployment = data.deployment || {}
    setDeploymentSettings({
      app_base_url: deployment.app_base_url || '',
      allowed_hosts: Array.isArray(deployment.allowed_hosts) ? deployment.allowed_hosts.join(', ') : '',
    })

    const accountReview = data.account_review || ACCOUNT_REVIEW_DEFAULTS
    setAccountReviewSettings({
      enabled: accountReview.enabled !== false,
      interval_days: accountReview.interval_days ?? ACCOUNT_REVIEW_DEFAULTS.interval_days,
      check_interval_hours: accountReview.check_interval_hours ?? ACCOUNT_REVIEW_DEFAULTS.check_interval_hours,
      last_sent_at: accountReview.last_sent_at || null,
    })

    const ntp = data.ntp || NTP_SETTINGS_DEFAULTS
    setNtpSettings({
      archive_bcc_address: ntp.archive_bcc_address || '',
      archive_copy_required: !!ntp.archive_copy_required,
      reserved_archive_bcc_addresses: ntp.reserved_archive_bcc_addresses || '',
      reminder_interval_days: ntp.reminder_interval_days ?? NTP_SETTINGS_DEFAULTS.reminder_interval_days,
      reminder_duration_days: ntp.reminder_duration_days ?? NTP_SETTINGS_DEFAULTS.reminder_duration_days,
      reminder_loop_seconds: ntp.reminder_loop_seconds ?? NTP_SETTINGS_DEFAULTS.reminder_loop_seconds,
    })
  }, [])

  const refreshAdministrativeSettings = useCallback(async () => {
    if (!isSysAdmin) {
      resetAdministrativeSettings()
      return
    }
    const response = await fetch(apiBase + '/system/settings', { credentials: 'include' })
    if (!response.ok) return
    applyAdministrativeSettings(await response.json())
  }, [apiBase, isSysAdmin, applyAdministrativeSettings, resetAdministrativeSettings])

  const updateAccountReviewSetting = useCallback((key, value) => {
    setAccountReviewSettings(previous => ({ ...previous, [key]: value }))
  }, [])

  const saveAccountReviewSettings = useCallback(async () => {
    if (!isSysAdmin) return
    setAccountReviewSaving(true)
    setAccountReviewStatus(null)
    try {
      const payload = {
        enabled: accountReviewSettings.enabled !== false,
        interval_days: Number(accountReviewSettings.interval_days) || ACCOUNT_REVIEW_DEFAULTS.interval_days,
        check_interval_hours: Number(accountReviewSettings.check_interval_hours) || ACCOUNT_REVIEW_DEFAULTS.check_interval_hours,
      }
      const response = await fetch(apiBase + '/system/account_review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      const next = data?.account_review || payload
      setAccountReviewSettings({
        enabled: next.enabled !== false,
        interval_days: next.interval_days ?? ACCOUNT_REVIEW_DEFAULTS.interval_days,
        check_interval_hours: next.check_interval_hours ?? ACCOUNT_REVIEW_DEFAULTS.check_interval_hours,
        last_sent_at: next.last_sent_at || null,
      })
      setAccountReviewStatus('Account review settings saved.')
    } catch (error) {
      setAccountReviewStatus(error?.message || 'Unable to save account review settings.')
    } finally {
      setAccountReviewSaving(false)
    }
  }, [apiBase, isSysAdmin, accountReviewSettings])

  const saveNtpSettings = useCallback(async () => {
    if (!isSysAdmin) return
    setNtpSettingsSaving(true)
    setNtpSettingsStatus(null)
    try {
      const payload = {
        archive_bcc_address: (ntpSettings.archive_bcc_address || '').trim().toLowerCase(),
        archive_copy_required: !!ntpSettings.archive_copy_required,
        reserved_archive_bcc_addresses: (ntpSettings.reserved_archive_bcc_addresses || '').trim().toLowerCase(),
        reminder_interval_days: Number(ntpSettings.reminder_interval_days) || NTP_SETTINGS_DEFAULTS.reminder_interval_days,
        reminder_duration_days: Number(ntpSettings.reminder_duration_days) || NTP_SETTINGS_DEFAULTS.reminder_duration_days,
        reminder_loop_seconds: Number(ntpSettings.reminder_loop_seconds) || NTP_SETTINGS_DEFAULTS.reminder_loop_seconds,
      }
      const response = await fetch(apiBase + '/system/ntp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      const next = data?.ntp || {}
      setNtpSettings({
        archive_bcc_address: next.archive_bcc_address || '',
        archive_copy_required: !!next.archive_copy_required,
        reserved_archive_bcc_addresses: next.reserved_archive_bcc_addresses || '',
        reminder_interval_days: next.reminder_interval_days ?? NTP_SETTINGS_DEFAULTS.reminder_interval_days,
        reminder_duration_days: next.reminder_duration_days ?? NTP_SETTINGS_DEFAULTS.reminder_duration_days,
        reminder_loop_seconds: next.reminder_loop_seconds ?? NTP_SETTINGS_DEFAULTS.reminder_loop_seconds,
      })
      setNtpSettingsStatus('NTP settings saved.')
      await loadTemplates()
    } catch (error) {
      console.error(error)
      setNtpSettingsStatus(error?.message || 'Unable to save NTP archive settings.')
    } finally {
      setNtpSettingsSaving(false)
    }
  }, [apiBase, isSysAdmin, ntpSettings, loadTemplates])

  const signalBrandingUpdate = useCallback(() => {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('branding:update'))
  }, [])

  const activateLogo = useCallback(async (logoId, message) => {
    if (!canManageBranding) {
      flash('Only system administrators can change branding.')
      return
    }
    try {
      const response = await fetch(apiBase + '/system/logos/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ logo_id: logoId ?? null }),
      })
      if (!response.ok) throw new Error('select_failed')
      await refreshAdministrativeSettings()
      flash(message || (logoId ? 'Active logo updated.' : 'Default logo restored.'))
      signalBrandingUpdate()
    } catch {
      flash('Unable to update logo selection.')
    }
  }, [apiBase, canManageBranding, flash, refreshAdministrativeSettings, signalBrandingUpdate])

  const saveDeploymentSettings = useCallback(async () => {
    if (!canManageBranding || deploymentSaving) return
    setDeploymentSaving(true)
    setDeploymentStatus(null)
    try {
      const payload = {
        app_base_url: (deploymentSettings.app_base_url || '').trim(),
        allowed_hosts: String(deploymentSettings.allowed_hosts || '')
          .split(',')
          .map(value => value.trim())
          .filter(Boolean),
      }
      const response = await fetch(apiBase + '/system/deployment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json().catch(() => ({}))
      const next = data.deployment || payload
      setDeploymentSettings({
        app_base_url: next.app_base_url || '',
        allowed_hosts: Array.isArray(next.allowed_hosts) ? next.allowed_hosts.join(', ') : '',
      })
      setDeploymentStatus('Deployment settings saved.')
    } catch (error) {
      setDeploymentStatus(error?.message || 'Unable to save deployment settings.')
    } finally {
      setDeploymentSaving(false)
    }
  }, [apiBase, canManageBranding, deploymentSaving, deploymentSettings])

  const saveBrandingText = useCallback(async () => {
    if (!canManageBranding || brandingTextSaving) return
    setBrandingTextSaving(true)
    try {
      const payload = {
        app_name: (brandingText.app_name || '').trim() || BRANDING_DEFAULTS.app_name,
        app_tagline: (brandingText.app_tagline || '').trim(),
      }
      const response = await fetch(apiBase + '/system/branding/text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error('branding_text_failed')
      const data = await response.json().catch(() => ({}))
      const next = data.branding || payload
      setBrandingText({
        app_name: next.app_name || payload.app_name,
        app_tagline: next.app_tagline || payload.app_tagline,
      })
      flash('Brand text saved.')
      signalBrandingUpdate()
    } catch {
      flash('Unable to save brand text.')
    } finally {
      setBrandingTextSaving(false)
    }
  }, [apiBase, canManageBranding, brandingText, brandingTextSaving, flash, signalBrandingUpdate])

  const onUploadLogo = useCallback(async (event) => {
    if (!canManageBranding) {
      flash('Only system administrators can change branding.')
      return
    }
    const file = event.target.files?.[0]
    if (!file) return
    setSelectedFileName(file.name)
    const body = new FormData()
    body.append('file', file)
    try {
      const response = await fetch(apiBase + '/system/logos/upload', {
        method: 'POST',
        body,
        credentials: 'include',
      })
      if (!response.ok) throw new Error('upload_failed')
      const data = await response.json().catch(() => ({}))
      const newId = data?.logo?.id
      if (newId) {
        await activateLogo(newId, 'Logo uploaded and activated.')
      } else {
        await refreshAdministrativeSettings()
        flash('Logo uploaded. Select it below to activate.')
      }
      setSelectedFileName('No file chosen')
      if (event.target) event.target.value = ''
    } catch {
      flash('Unable to upload logo.')
    }
  }, [apiBase, canManageBranding, activateLogo, flash, refreshAdministrativeSettings])

  const onSelectLogo = useCallback(async (id) => {
    await activateLogo(id)
  }, [activateLogo])

  const onResetLogo = useCallback(async () => {
    await activateLogo(null, 'Default logo restored.')
  }, [activateLogo])

  const onDeleteLogo = useCallback(async (id) => {
    if (!canManageBranding) {
      flash('Only system administrators can change branding.')
      return
    }
    const response = await fetch(apiBase + '/system/logos/' + id, {
      method: 'DELETE',
      credentials: 'include',
    })
    if (response.ok) {
      await refreshAdministrativeSettings()
      flash('Logo deleted.')
      signalBrandingUpdate()
    } else {
      flash('Unable to delete logo.')
    }
  }, [apiBase, canManageBranding, flash, refreshAdministrativeSettings, signalBrandingUpdate])

  return {
    logos,
    activeLogo,
    status,
    selectedFileName,
    brandingText,
    setBrandingText,
    brandingTextSaving,
    deploymentSettings,
    setDeploymentSettings,
    deploymentSaving,
    deploymentStatus,
    accountReviewSettings,
    accountReviewStatus,
    accountReviewSaving,
    ntpSettings,
    setNtpSettings,
    ntpSettingsStatus,
    ntpSettingsSaving,
    flash,
    resetAdministrativeSettings,
    applyAdministrativeSettings,
    updateAccountReviewSetting,
    saveAccountReviewSettings,
    saveNtpSettings,
    saveDeploymentSettings,
    saveBrandingText,
    onUploadLogo,
    onSelectLogo,
    onResetLogo,
    onDeleteLogo,
  }
}
