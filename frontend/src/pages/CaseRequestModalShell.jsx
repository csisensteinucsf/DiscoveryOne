import Modal from '../components/Modal.jsx'

export function CaseRequestModalShell({
  sectionTitle,
  onClose,
  wideModal,
  useWizard,
  step,
  handleBack,
  canAdvanceFromStep1,
  canAdvanceFromStep2,
  canSubmit,
  primaryActionLabel,
  handleFormSubmit,
  autofillNonce,
  error,
  children,
}) {
  return (
    <Modal
      open
      title={sectionTitle}
      onClose={onClose}
      width={wideModal ? 980 : 720}
      footer={(
        <>
          <button className="btn ghost" type="button" onClick={onClose}>Cancel</button>
          {useWizard && step > 1 && (
            <button className="btn secondary" type="button" onClick={handleBack}>
              Back
            </button>
          )}
          <button
            className="btn"
            type="submit"
            form="case-request-form"
            disabled={useWizard ? (step === 1 ? !canAdvanceFromStep1 : step === 2 ? !canAdvanceFromStep2 : !canSubmit) : !canSubmit}
          >
            {primaryActionLabel}
          </button>
        </>
      )}
    >
      <form id="case-request-form" autoComplete="off" onSubmit={handleFormSubmit} style={{ maxHeight: wideModal ? '86vh' : '70vh', overflowY: 'auto' }}>
        <input type="text" name={`fake-${autofillNonce}`} style={{ position: 'absolute', opacity: 0, pointerEvents: 'none', height: 0, width: 0 }} autoComplete="off" tabIndex="-1" aria-hidden="true" />
        {useWizard && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, color: '#475569', fontSize: 13 }}>
            <strong style={{ color: '#0f172a' }}>Step {step} of 3</strong>
            <span aria-hidden="true"></span>
            <span>Custodians  preservation/NTP/consent  search (optional)</span>
          </div>
        )}
        {children}
        {error && <div className="error" role="alert">{error}</div>}
      </form>
    </Modal>
  )
}

export function CaseRequestUnmatchedModal({
  open,
  count,
  onClose,
}) {
  if (!open || count <= 0) return null

  return (
    <Modal
      open
      title="Person lookup unmatched"
      onClose={onClose}
      width={480}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn" onClick={onClose}>OK</button>
        </div>
      )}
    >
      <p style={{ marginTop: 0, color: '#111827' }}>
        Person lookup was not able to match one or more custodians to a configured identity record.
        Unmatched persons are highlighted in yellow.
      </p>
    </Modal>
  )
}
