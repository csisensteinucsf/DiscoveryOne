import { useCallback, useEffect, useRef, useState } from 'react'

const templateDefaults = {
  name: '',
  subject: '',
  body: '',
  description: '',
  cc: '',
  groups: [],
  is_default: false,
  high_importance: false,
}

const templateVariables = [
  '{{case_name}}',
  '{{legal_case_name}}',
  '{{custodian_name}}',
  '{{custodian_email}}',
  '{{requestor}}',
  '{{ack_link}}',
  '{{ack_link_text}}',
  '{{ack_link_url}}',
  '{{claimant}}',
  '{{reason}}',
  '{{outside_counsel1}}',
  '{{outside_counsel2}}',
  '{{outside_counsel3}}',
  '{{outside_counsel_firm}}',
]

export function useSystemNtpTemplates({
  apiBase,
  canManageNtp,
  canRequestorManageNtp,
  isRequestor,
  userGroup,
  normalizeGroupValue,
  showToast,
}) {
  const [ntpTemplates, setNtpTemplates] = useState([])
  const [ntpTemplatesLoading, setNtpTemplatesLoading] = useState(false)
  const [ntpGroupOptions, setNtpGroupOptions] = useState([])
  const [ntpGroupInput, setNtpGroupInput] = useState('')
  const [templateForm, setTemplateForm] = useState({ ...templateDefaults })
  const templateBodyRef = useRef(null)
  const templateSelectionRef = useRef(null)
  const [showVarModal, setShowVarModal] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState(null)
  const [showTemplateModal, setShowTemplateModal] = useState(false)
  const [templateSaving, setTemplateSaving] = useState(false)
  const [templateStatus, setTemplateStatus] = useState(null)

  const addGroupOption = useCallback((value) => {
    const norm = normalizeGroupValue(value)
    if (!norm) return null
    setNtpGroupOptions(prev => (prev.includes(norm) ? prev : [...prev, norm].sort()))
    return norm
  }, [normalizeGroupValue])

  const addTemplateGroup = useCallback((value) => {
    const norm = addGroupOption(value)
    if (!norm) return
    setTemplateForm(prev => (prev.groups.includes(norm) ? prev : { ...prev, groups: [...prev.groups, norm] }))
  }, [addGroupOption])

  const captureTemplateSelection = useCallback(() => {
    try {
      const sel = window.getSelection()
      if (!sel || sel.rangeCount === 0) return
      const range = sel.getRangeAt(0)
      const editorEl = templateBodyRef.current
      if (!editorEl) return
      if (!editorEl.contains(range.commonAncestorContainer)) return
      templateSelectionRef.current = range.cloneRange()
    } catch {
      /* ignore */
    }
  }, [])

  const insertTemplateVariable = useCallback((token) => {
    const el = templateBodyRef.current
    if (el) {
      el.focus()
      let range = templateSelectionRef.current
      if (!range) {
        const sel = window.getSelection()
        if (sel && sel.rangeCount > 0) {
          range = sel.getRangeAt(0).cloneRange()
        }
      }
      if (range && el.contains(range.commonAncestorContainer)) {
        const textNode = document.createTextNode(token)
        range.deleteContents()
        range.insertNode(textNode)
        const newRange = document.createRange()
        newRange.setStartAfter(textNode)
        newRange.collapse(true)
        const sel = window.getSelection()
        if (sel) {
          sel.removeAllRanges()
          sel.addRange(newRange)
        }
        templateSelectionRef.current = newRange.cloneRange()
        setTemplateForm(prev => ({ ...prev, body: el.innerHTML || '' }))
        return
      }
    }
    setTemplateForm(prev => ({ ...prev, body: (prev.body || '') + token }))
  }, [])

  const removeTemplateGroup = useCallback((value) => {
    const norm = normalizeGroupValue(value)
    setTemplateForm(prev => ({ ...prev, groups: prev.groups.filter(g => g !== norm) }))
  }, [normalizeGroupValue])

  const toggleTemplateGroupOption = useCallback((value) => {
    const norm = normalizeGroupValue(value)
    if (!norm) return
    setTemplateForm(prev => (
      prev.groups.includes(norm)
        ? { ...prev, groups: prev.groups.filter(g => g !== norm) }
        : { ...prev, groups: [...prev.groups, norm] }
    ))
    addGroupOption(norm)
  }, [addGroupOption, normalizeGroupValue])

  const handleAddGroupInput = useCallback(() => {
    if (!ntpGroupInput.trim()) return
    addTemplateGroup(ntpGroupInput)
    setNtpGroupInput('')
  }, [addTemplateGroup, ntpGroupInput])

  const templateAccessible = useCallback((tpl) => {
    if (!tpl) return false
    if (canManageNtp) return true
    return canRequestorManageNtp && !!userGroup
  }, [canManageNtp, canRequestorManageNtp, userGroup])

  const templateDeletable = useCallback((tpl) => {
    if (!tpl) return false
    if (canManageNtp) return true
    return Boolean(
      canRequestorManageNtp &&
      userGroup &&
      Array.isArray(tpl.groups) &&
      tpl.groups.length === 1 &&
      tpl.groups[0] === userGroup
    )
  }, [canManageNtp, canRequestorManageNtp, userGroup])

  const loadTemplates = useCallback(async () => {
    setNtpTemplatesLoading(true)
    try {
      const res = await fetch(`${apiBase}/ntp/templates`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      const mapped = (Array.isArray(data) ? data : []).map(item => ({
        ...item,
        groups: Array.isArray(item.groups)
          ? item.groups.map(normalizeGroupValue).filter(Boolean)
          : [],
      }))
      setNtpTemplates(mapped)
    } catch {
      setNtpTemplates([])
    } finally {
      setNtpTemplatesLoading(false)
    }
  }, [apiBase, normalizeGroupValue])

  const loadNtpGroups = useCallback(async () => {
    if (!canManageNtp) {
      setNtpGroupOptions([])
      return
    }
    try {
      const res = await fetch(`${apiBase}/ntp/groups`, { credentials: 'include' })
      if (!res.ok) throw new Error()
      const data = await res.json()
      const groups = Array.isArray(data?.groups)
        ? data.groups.map(normalizeGroupValue).filter(Boolean)
        : []
      setNtpGroupOptions([...new Set(groups)].sort())
    } catch {
      setNtpGroupOptions([])
    }
  }, [apiBase, canManageNtp, normalizeGroupValue])

  useEffect(() => {
    loadTemplates()
    loadNtpGroups()
  }, [loadTemplates, loadNtpGroups])

  const nextTemplateVersionName = useCallback((baseName) => {
    const original = (baseName || '').trim()
    const existing = new Set((ntpTemplates || []).map(t => ((t?.name || '').trim().toLowerCase())).filter(Boolean))
    const m = original.match(/^(.*?)(?:\s*[-]?\s*v(\d+))$/i)
    const prefix = (m?.[1] || original).trim() || 'Template'
    let version = 2
    if (m?.[2]) {
      const parsed = Number.parseInt(m[2], 10)
      if (!Number.isNaN(parsed)) version = parsed + 1
    }
    while (version < 999) {
      const candidate = `${prefix} - v${version}`
      if (!existing.has(candidate.toLowerCase())) return candidate
      version += 1
    }
    return `${prefix} - v${Date.now()}`
  }, [ntpTemplates])

  const openTemplateModal = useCallback((tpl = null) => {
    const tplGroups = Array.isArray(tpl?.groups) ? tpl.groups.map(normalizeGroupValue).filter(Boolean) : []
    if (tpl) {
      setEditingTemplate(tpl)
      setTemplateForm({
        name: tpl.name || '',
        subject: tpl.subject || '',
        body: tpl.body || '',
        description: tpl.description || '',
        cc: tpl.cc || '',
        groups: tplGroups,
        is_default: !!tpl.is_default,
        high_importance: !!tpl.high_importance,
      })
    } else {
      setEditingTemplate(null)
      const base = { ...templateDefaults }
      if (canRequestorManageNtp && userGroup) {
        base.groups = [userGroup]
      }
      setTemplateForm(base)
    }
    if (tplGroups.length) {
      setNtpGroupOptions(prev => {
        const next = new Set(prev)
        tplGroups.forEach(g => next.add(g))
        return Array.from(next).sort()
      })
    }
    setTemplateStatus(null)
    setNtpGroupInput('')
    setShowTemplateModal(true)
  }, [canRequestorManageNtp, normalizeGroupValue, userGroup])

  const copyTemplate = useCallback((tpl) => {
    if (!tpl) return
    const tplGroups = Array.isArray(tpl?.groups) ? tpl.groups.map(normalizeGroupValue).filter(Boolean) : []
    const groups = canManageNtp ? tplGroups : (userGroup ? [userGroup] : [])
    setEditingTemplate(null)
    setTemplateForm({
      name: nextTemplateVersionName(tpl.name || ''),
      subject: tpl.subject || '',
      body: tpl.body || '',
      description: tpl.description || '',
      cc: tpl.cc || '',
      groups,
      is_default: false,
      high_importance: !!tpl.high_importance,
    })
    if (tplGroups.length) {
      setNtpGroupOptions(prev => {
        const next = new Set(prev)
        tplGroups.forEach(g => next.add(g))
        return Array.from(next).sort()
      })
    }
    setTemplateStatus(null)
    setNtpGroupInput('')
    setShowTemplateModal(true)
  }, [canManageNtp, nextTemplateVersionName, normalizeGroupValue, userGroup])

  const closeTemplateModal = useCallback(() => {
    setShowTemplateModal(false)
    setEditingTemplate(null)
    setTemplateForm({ ...templateDefaults })
    setTemplateStatus(null)
    setNtpGroupInput('')
  }, [])

  const saveTemplate = useCallback(async () => {
    if (isRequestor && !userGroup) {
      setTemplateStatus('Requestor accounts need a requestor group before creating templates. Ask an admin to set your group.')
      return
    }
    if (!templateForm.name.trim() || !templateForm.subject.trim() || !templateForm.body.trim()) {
      setTemplateStatus('Name, subject, and body are required.')
      return
    }
    setTemplateSaving(true)
    setTemplateStatus(null)
    try {
      const normalizeEmails = (raw) => (raw || '')
        .split(',')
        .map(addr => addr.trim())
        .filter(Boolean)
        .join(', ')
      const description = (templateForm.description || '').trim()
      const payload = {
        name: templateForm.name.trim(),
        subject: templateForm.subject.trim(),
        body: templateForm.body,
        description: description || null,
        cc: normalizeEmails(templateForm.cc) || null,
        is_default: !!templateForm.is_default,
        high_importance: !!templateForm.high_importance,
        groups: Array.isArray(templateForm.groups) ? templateForm.groups : [],
      }
      const isEdit = Boolean(editingTemplate)
      const url = isEdit ? `${apiBase}/ntp/templates/${editingTemplate.id}` : `${apiBase}/ntp/templates`
      const method = isEdit ? 'PUT' : 'POST'
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast(`Template ${isEdit ? 'updated' : 'created'}.`, { variant: 'success' })
      closeTemplateModal()
      await loadTemplates()
      await loadNtpGroups()
    } catch (err) {
      setTemplateStatus(err?.message || 'Unable to save template.')
    } finally {
      setTemplateSaving(false)
    }
  }, [apiBase, closeTemplateModal, editingTemplate, isRequestor, loadNtpGroups, loadTemplates, showToast, templateForm, userGroup])

  const deleteTemplate = useCallback(async (tpl) => {
    if (!tpl) return
    if (!window.confirm(`Delete template "${tpl.name}"?`)) return
    try {
      const res = await fetch(`${apiBase}/ntp/templates/${tpl.id}`, { method: 'DELETE', credentials: 'include' })
      if (!res.ok) throw new Error(await res.text())
      showToast('Template deleted.', { variant: 'info' })
      await loadTemplates()
      await loadNtpGroups()
    } catch (err) {
      showToast(err?.message || 'Failed to delete template.', { variant: 'error' })
    }
  }, [apiBase, loadNtpGroups, loadTemplates, showToast])

  return {
    ntpTemplates,
    ntpTemplatesLoading,
    ntpGroupOptions,
    ntpGroupInput,
    setNtpGroupInput,
    templateForm,
    setTemplateForm,
    templateBodyRef,
    templateSelectionRef,
    showVarModal,
    setShowVarModal,
    editingTemplate,
    showTemplateModal,
    templateSaving,
    templateStatus,
    templateVariables,
    captureTemplateSelection,
    insertTemplateVariable,
    removeTemplateGroup,
    toggleTemplateGroupOption,
    handleAddGroupInput,
    templateAccessible,
    templateDeletable,
    loadTemplates,
    loadNtpGroups,
    openTemplateModal,
    copyTemplate,
    closeTemplateModal,
    saveTemplate,
    deleteTemplate,
  }
}