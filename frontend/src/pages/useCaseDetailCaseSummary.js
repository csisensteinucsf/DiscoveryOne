import { useCallback, useMemo, useState } from 'react'

export function useCaseDetailCaseSummary({ apiBase, caseId, showToast }) {
  const [showCaseSummaryModal, setShowCaseSummaryModal] = useState(false)
  const [caseSummary, setCaseSummary] = useState({ loading: false, error: null, data: null, emailing: false })

  const caseSummaryData = caseSummary?.data || null
  const caseSummarySections = caseSummaryData?.sections || {}
  const caseSummaryAi = caseSummaryData?.ai || {}
  const caseSummaryNeedsAttention = Array.isArray(caseSummaryData?.needs_attention) ? caseSummaryData.needs_attention : []
  const caseSummaryAiAttention = useMemo(() => {
    return Array.isArray(caseSummaryAi?.attention_items) && caseSummaryAi.attention_items.length
      ? caseSummaryAi.attention_items
      : caseSummaryNeedsAttention.map(item => item?.message).filter(Boolean)
  }, [caseSummaryAi, caseSummaryNeedsAttention])
  const caseSummaryAiActions = Array.isArray(caseSummaryAi?.recommended_actions) ? caseSummaryAi.recommended_actions : []
  const caseSummaryAiHighlights = Array.isArray(caseSummaryAi?.progress_highlights) ? caseSummaryAi.progress_highlights : []

  const loadCaseSummary = useCallback(async () => {
    if (!caseId) return
    setCaseSummary(prev => ({ ...prev, loading: true, error: null }))
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/summary`, { credentials: 'include' })
      const raw = await res.text().catch(() => '')
      let data = null
      try {
        data = raw ? JSON.parse(raw) : null
      } catch {
        data = null
      }
      if (!res.ok) {
        const detail = (data && typeof data === 'object' ? data.detail : null) || raw || 'Unable to load case summary'
        throw new Error(detail)
      }
      if (!data || typeof data !== 'object') {
        throw new Error('Invalid case summary response')
      }
      setCaseSummary(prev => ({ ...prev, loading: false, error: null, data }))
    } catch (err) {
      setCaseSummary(prev => ({ ...prev, loading: false, error: err?.message || 'Unable to load case summary' }))
    }
  }, [apiBase, caseId])

  const openCaseSummary = useCallback(() => {
    setShowCaseSummaryModal(true)
    loadCaseSummary()
  }, [loadCaseSummary])

  const emailCaseSummaryToSelf = useCallback(async () => {
    if (!caseId) return
    setCaseSummary(prev => ({ ...prev, emailing: true }))
    try {
      const res = await fetch(`${apiBase}/cases/${caseId}/summary/email`, {
        method: 'POST',
        credentials: 'include',
      })
      const raw = await res.text().catch(() => '')
      let data = null
      try {
        data = raw ? JSON.parse(raw) : null
      } catch {
        data = null
      }
      if (!res.ok) {
        const detail = (data && typeof data === 'object' ? data.detail : null) || raw || 'Unable to email case summary'
        throw new Error(detail)
      }
      const recipient = (data && typeof data === 'object' ? data.recipient : '') || ''
      showToast(recipient ? `Case summary emailed to ${recipient}.` : 'Case summary emailed to your account.', { variant: 'success' })
    } catch (err) {
      showToast(err?.message || 'Unable to email case summary', { variant: 'error' })
    } finally {
      setCaseSummary(prev => ({ ...prev, emailing: false }))
    }
  }, [apiBase, caseId, showToast])

  return {
    showCaseSummaryModal,
    setShowCaseSummaryModal,
    caseSummary,
    caseSummaryData,
    caseSummarySections,
    caseSummaryAi,
    caseSummaryAiAttention,
    caseSummaryAiActions,
    caseSummaryAiHighlights,
    loadCaseSummary,
    openCaseSummary,
    emailCaseSummaryToSelf,
  }
}