import { Power, RotateCw, X } from 'lucide-react'

export default function SystemBackendRestartModal({ open, busy, requested, status, onClose, onRestart }) {
  if (!open) return null

  return (
    <div className="modal-backdrop" onMouseDown={event => event.target === event.currentTarget && !busy && onClose()}>
      <div className="modal backend-restart-modal" role="dialog" aria-modal="true" aria-labelledby="backend-restart-title">
        <div className="modal-header">
          <div className="backend-restart-modal__heading">
            <span className="backend-restart-modal__icon"><RotateCw size={22} aria-hidden="true" /></span>
            <div>
              <h2 id="backend-restart-title">{requested ? 'Backend restarting' : 'Restart the backend?'}</h2>
              <p>{requested ? 'DiscoveryOne should be available again shortly.' : 'Some integration workers load connection settings when the backend starts.'}</p>
            </div>
          </div>
          {!requested && (
            <button type="button" className="integration-icon-button" onClick={onClose} aria-label="Close restart dialog" disabled={busy}>
              <X size={19} aria-hidden="true" />
            </button>
          )}
        </div>
        <div className="modal-body backend-restart-modal__body">
          {requested ? (
            <div className="backend-restart-modal__progress"><RotateCw size={24} aria-hidden="true" />Waiting for the backend container to restart…</div>
          ) : (
            <>
              <p>This briefly interrupts access for all users. Docker Compose and supported NAS installations restart the backend container automatically.</p>
              <p className="backend-restart-modal__note">This restarts the current backend container. It does not rebuild application images or deploy new code.</p>
            </>
          )}
          {status && <div className={`backend-restart-modal__status${requested ? '' : ' is-error'}`}>{status}</div>}
        </div>
        {!requested && (
          <div className="modal-footer backend-restart-modal__footer">
            <button type="button" className="btn secondary" onClick={onClose} disabled={busy}>Not now</button>
            <button type="button" className="btn danger" onClick={onRestart} disabled={busy}>
              <Power size={16} aria-hidden="true" />
              {busy ? 'Requesting restart' : 'Restart backend'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
