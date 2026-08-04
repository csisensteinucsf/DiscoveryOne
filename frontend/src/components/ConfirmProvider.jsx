import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import Modal from './Modal.jsx'

const ConfirmContext = createContext({ confirm: async () => false })

export function ConfirmProvider({ children }) {
  const [dialog, setDialog] = useState(null)

  const confirm = useCallback((options = {}) => {
    return new Promise((resolve) => {
      setDialog({
        ...options,
        resolve: (result) => {
          setDialog(null)
          resolve(result)
        },
      })
    })
  }, [])

  const value = useMemo(() => ({ confirm }), [confirm])

  const close = () => {
    dialog?.resolve(false)
  }

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {dialog && (
        <Modal
          open
          title={dialog.title || 'Confirm action'}
          onClose={close}
          width={dialog.width || 420}
          footer={(
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              {!dialog.hideCancel && <button type="button" className="btn ghost" onClick={close}>
                {dialog.cancelLabel || 'Cancel'}
              </button>}
              <button
                type="button"
                className={`btn ${dialog.destructive ? 'danger' : ''}`}
                onClick={() => dialog.resolve(true)}
              >
                {dialog.confirmLabel || 'Continue'}
              </button>
            </div>
          )}
        >
          {dialog.description ? (
            <p style={{ margin: 0, color: 'var(--text, #1f2937)', lineHeight: 1.5 }}>{dialog.description}</p>
          ) : null}
          {dialog.extras || null}
        </Modal>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  const ctx = useContext(ConfirmContext)
  if (!ctx) {
    throw new Error('useConfirm must be used inside ConfirmProvider')
  }
  return ctx.confirm
}
