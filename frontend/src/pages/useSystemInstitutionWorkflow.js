import { useCallback, useEffect, useState } from 'react'

const emptyInstitution = () => ({
  org_name: '',
  org_short_name: '',
  allowed_requestor_email_domains: '',
  requestor_email_exceptions: '',
  sso_display_name: 'Single sign-on',
  support_email: '',
})

const joinValues = value => (Array.isArray(value) ? value : [])
  .map(item => String(item || '').trim())
  .filter(Boolean)
  .join('\n')

const splitValues = value => String(value || '')
  .split(/[\n,]+/)
  .map(item => item.trim())
  .filter(Boolean)

const normalizeInstitution = data => ({
  ...emptyInstitution(),
  ...(data || {}),
  allowed_requestor_email_domains: joinValues(data?.allowed_requestor_email_domains),
  requestor_email_exceptions: joinValues(data?.requestor_email_exceptions),
})

export function useSystemInstitutionWorkflow({ apiBase, isSysAdmin }) {
  const [institutionSettings, setInstitutionSettings] = useState(emptyInstitution)
  const [institutionSaving, setInstitutionSaving] = useState(false)
  const [institutionStatus, setInstitutionStatus] = useState('')

  const loadInstitutionSettings = useCallback(async () => {
    if (!isSysAdmin) {
      setInstitutionSettings(emptyInstitution())
      return
    }
    setInstitutionStatus('')
    try {
      const response = await fetch(`${apiBase}/system/institution`, { credentials: 'include' })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      setInstitutionSettings(normalizeInstitution(data?.institution))
    } catch (error) {
      console.error(error)
      setInstitutionStatus(error?.message || 'Unable to load institution settings.')
    }
  }, [apiBase, isSysAdmin])

  useEffect(() => {
    loadInstitutionSettings()
  }, [loadInstitutionSettings])

  const updateInstitutionSetting = useCallback((key, value) => {
    setInstitutionSettings(previous => ({ ...previous, [key]: value }))
  }, [])

  const saveInstitutionSettings = useCallback(async () => {
    setInstitutionSaving(true)
    setInstitutionStatus('')
    try {
      const response = await fetch(`${apiBase}/system/institution`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          ...institutionSettings,
          allowed_requestor_email_domains: splitValues(institutionSettings.allowed_requestor_email_domains),
          requestor_email_exceptions: splitValues(institutionSettings.requestor_email_exceptions),
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      setInstitutionSettings(normalizeInstitution(data?.institution))
      setInstitutionStatus('Institution settings saved.')
    } catch (error) {
      console.error(error)
      setInstitutionStatus(error?.message || 'Unable to save institution settings.')
    } finally {
      setInstitutionSaving(false)
    }
  }, [apiBase, institutionSettings])

  return {
    institutionSettings,
    institutionSaving,
    institutionStatus,
    updateInstitutionSetting,
    saveInstitutionSettings,
    loadInstitutionSettings,
  }
}
