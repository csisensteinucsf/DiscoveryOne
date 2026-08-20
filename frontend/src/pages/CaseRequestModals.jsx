import Modal from '../components/Modal.jsx'

export function RequestDetailModal({ request, onClose, onApprove, onDecline, renderBody }) {
  if (!request) return null
  return (
    <Modal
      open
      title="Request Details"
      onClose={onClose}
      width={980}
      bodyStyle={{ maxHeight: '78vh', overflowY: 'auto' }}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, flexWrap: 'wrap' }}>
          {request.status === 'pending' && (
            <>
              <button
                type="button"
                className="btn danger"
                onClick={() => onDecline(request.id)}
              >
                Decline
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => onApprove(request.id)}
              >
                Approve
              </button>
            </>
          )}
          <button type="button" className="btn secondary" onClick={onClose}>Close</button>
        </div>
      )}
    >
      {renderBody(request)}
    </Modal>
  )
}

export function DeclineRequestModal({ target, reason, busy, onReasonChange, onClose, onSubmit }) {
  if (!target) return null
  return (
    <Modal
      open
      title="Decline request"
      onClose={onClose}
      width={520}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
          <button type="button" className="btn danger" onClick={onSubmit} disabled={busy}>
            {busy ? 'Declining' : 'Decline'}
          </button>
        </div>
      )}
    >
      <p style={{ marginTop: 0, color: '#475467' }}>Provide a reason for declining this request. This message is visible to the requestor.</p>
      <textarea
        rows={4}
        className="input"
        value={reason}
        onChange={(e) => onReasonChange(e.target.value)}
        placeholder="Explain why this request is being declined"
        style={{ resize: 'vertical', width: '100%' }}
      />
    </Modal>
  )
}

export function ApproveCaseRequestModal({ request, analystId, analysts, onAnalystChange, onClose, onConfirm }) {
  if (!request) return null
  return (
    <Modal
      open
      title="Approve new matter"
      onClose={onClose}
      width={520}
      footer={(
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose}>Cancel</button>
          <button
            type="button"
            className="btn"
            onClick={onConfirm}
            disabled={!analysts.length}
          >
            Approve
          </button>
        </div>
      )}
    >
      <p style={{ marginTop: 0, color: '#475467' }}>
        Select an analyst to assign to <strong>{request.case_name || 'this matter'}</strong> before approving.
      </p>
      <label style={{ display: 'block', marginBottom: 12 }}>
        <span style={{ display: 'block', marginBottom: 6, color: '#475467', fontWeight: 600 }}>Analyst</span>
        <select
          className="input"
          value={analystId}
          onChange={(e) => onAnalystChange(e.target.value)}
          style={{ width: '100%' }}
        >
          <option value="">Select analyst</option>
          {analysts.map(a => (
            <option key={a.id} value={a.id}>
              {`${a.first_name || ''} ${a.last_name || ''}`.trim() || a.username || a.email || `User ${a.id}`}
            </option>
          ))}
        </select>
      </label>
      {!analysts.length && (
        <p style={{ color: '#b91c1c', marginTop: 0 }}>No analysts available. Add one in System &gt; Users.</p>
      )}
    </Modal>
  )
}