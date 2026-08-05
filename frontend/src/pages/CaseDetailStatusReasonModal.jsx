import { useEffect, useId, useState } from 'react'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'

export default function CaseDetailStatusReasonModal({
  request,
  onClose,
  onSubmit,
  busy = false,
}) {
  const formId = useId()
  const inputId = useId()
  const [reason, setReason] = useState('')
  const [showMissingRequired, setShowMissingRequired] = useState(false)

  useEffect(() => {
    setReason(request?.initialReason || '')
    setShowMissingRequired(false)
  }, [request])

  const submitReason = event => {
    event.preventDefault()
    const trimmedReason = reason.trim()
    if (!trimmedReason) {
      setShowMissingRequired(true)
      return
    }
    onSubmit(trimmedReason)
  }

  return (
    <Modal
      open={!!request}
      title={request?.title || 'Status reason'}
      onClose={onClose}
      width={520}
      footer={(
        <div className="case-editor-footer">
          {showMissingRequired ? (
            <div className="case-editor-missing-required" role="alert">A reason is required.</div>
          ) : null}
          <div className="case-editor-footer__actions">
            <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
            <button type="submit" form={formId} className="btn" disabled={busy}>
              {busy ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
      )}
    >
      <form
        id={formId}
        className="case-editor-form"
        data-show-missing-required={showMissingRequired ? 'true' : 'false'}
        onSubmit={submitReason}
      >
        <label htmlFor={inputId}>
          <RequiredFieldLabel>{request?.question || 'Reason'}</RequiredFieldLabel>
        </label>
        <textarea
          id={inputId}
          className="input"
          rows={3}
          value={reason}
          onChange={event => {
            setReason(event.target.value)
            if (showMissingRequired && event.target.value.trim()) setShowMissingRequired(false)
          }}
          required
          aria-required="true"
          aria-invalid={showMissingRequired && !reason.trim()}
        />
      </form>
    </Modal>
  )
}
