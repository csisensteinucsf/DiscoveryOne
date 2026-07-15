import { useCallback, useRef, useState } from 'react'

export function useSystemBackupsWorkflow({ apiBase, isSysAdmin }) {
  const [lastBackup, setLastBackup] = useState(null)
  const [backupHealth, setBackupHealth] = useState(null)
  const [backupsLoading, setBackupsLoading] = useState(false)
  const [backupStatus, setBackupStatus] = useState(null)
  const [backupSettings, setBackupSettings] = useState({ automatic_enabled: true, interval_hours: 6, retention_hours: 48 })
  const [backupSettingsStatus, setBackupSettingsStatus] = useState(null)
  const [backupSettingsSaving, setBackupSettingsSaving] = useState(false)
  const [restoreFile, setRestoreFile] = useState(null)
  const [restoreStatus, setRestoreStatus] = useState(null)
  const [restoreBusy, setRestoreBusy] = useState(false)
  const [restoreKey, setRestoreKey] = useState('')
  const restoreInputRef = useRef(null)

  const loadBackups = useCallback(async () => {
    if (!isSysAdmin) return
    setBackupsLoading(true)
    try {
      const res = await fetch(`${apiBase}/system/backups`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setLastBackup(data.last_backup || null)
      setBackupHealth(data.backup_encryption || null)
      if (data.backup_settings) {
        setBackupSettings({
          automatic_enabled: data.backup_settings.automatic_enabled !== false,
          interval_hours: data.backup_settings.interval_hours ?? 6,
          retention_hours: data.backup_settings.retention_hours ?? 48,
        })
      }
    } catch {
      setLastBackup(null)
      setBackupHealth(null)
    } finally {
      setBackupsLoading(false)
    }
  }, [apiBase, isSysAdmin])

  const updateBackupSetting = (key, value) => {
    setBackupSettings(prev => ({ ...prev, [key]: value }))
  }

  const saveBackupSettings = async () => {
    if (!isSysAdmin) return
    setBackupSettingsSaving(true)
    setBackupSettingsStatus(null)
    try {
      const payload = {
        automatic_enabled: backupSettings.automatic_enabled !== false,
        interval_hours: Number(backupSettings.interval_hours) || 6,
        retention_hours: Number(backupSettings.retention_hours) || 48,
      }
      const res = await fetch(`${apiBase}/system/backups/settings`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const next = data?.backup_settings || payload
      setBackupSettings({
        automatic_enabled: next.automatic_enabled !== false,
        interval_hours: next.interval_hours ?? 6,
        retention_hours: next.retention_hours ?? 48,
      })
      setBackupSettingsStatus('Backup settings saved.')
    } catch (err) {
      setBackupSettingsStatus(err?.message || 'Unable to save backup settings.')
    } finally {
      setBackupSettingsSaving(false)
    }
  }

  const describeBackupType = (label) => {
    const normalized = (label || '').toLowerCase()
    if (normalized.includes('adhoc') || normalized === 'manual') {
      return 'Ad hoc'
    }
    return 'Scheduled'
  }

  const runScheduledBackup = async () => {
    if (!isSysAdmin) return
    setBackupStatus('Running backup')
    try {
      const res = await fetch(`${apiBase}/system/backups/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ label: 'adhoc' }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setBackupStatus(`Backup created: ${data.name}`)
      setLastBackup({
        name: data.name,
        created_at: data.created_at,
        label: data.label || 'manual',
      })
      await loadBackups()
    } catch (err) {
      console.error(err)
      setBackupStatus('Backup failed')
    }
  }

  const onRestoreFileChange = (e) => {
    const file = e.target.files?.[0] || null
    setRestoreFile(file)
    setRestoreStatus(file ? `${file.name} selected` : null)
  }

  const runRestore = async () => {
    if (!restoreFile) {
      setRestoreStatus('Choose a backup file first.')
      return
    }
    const confirmation = window.prompt(
      'THIS WILL REPLACE THE ENTIRE DATABASE\n\nType RESTORE if you are sure.'
    )
    if ((confirmation || '').trim() !== 'RESTORE') {
      setRestoreStatus('Restore cancelled.')
      return
    }
    setRestoreBusy(true)
    setRestoreStatus('Restoring backup')
    try {
      const fd = new FormData()
      fd.append('file', restoreFile)
      fd.append('confirm_restore', 'RESTORE')
      const trimmedKey = restoreKey.trim()
      if (trimmedKey) {
        fd.append('encryption_key', trimmedKey)
      }
      const res = await fetch(`${apiBase}/system/backups/restore`, {
        method: 'POST',
        credentials: 'include',
        body: fd,
      })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(text || 'restore_failed')
      }
      setRestoreStatus('Restore completed. The service may take a moment to refresh.')
      setRestoreFile(null)
      setRestoreKey('')
      if (restoreInputRef.current) restoreInputRef.current.value = ''
    } catch (err) {
      console.error(err)
      const msg = err?.message || 'Restore failed.'
      setRestoreStatus(`Restore failed: ${msg}`)
    } finally {
      setRestoreBusy(false)
    }
  }

  return {
    lastBackup,
    backupHealth,
    backupsLoading,
    backupStatus,
    backupSettings,
    updateBackupSetting,
    saveBackupSettings,
    backupSettingsSaving,
    backupSettingsStatus,
    loadBackups,
    runScheduledBackup,
    describeBackupType,
    restoreInputRef,
    onRestoreFileChange,
    runRestore,
    restoreBusy,
    restoreFile,
    restoreStatus,
    restoreKey,
    setRestoreKey,
  }
}