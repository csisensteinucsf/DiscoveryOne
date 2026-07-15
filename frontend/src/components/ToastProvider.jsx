import { createContext, useCallback, useContext, useId, useMemo, useState } from 'react'

const ToastContext = createContext({ showToast: () => {} })
let idCounter = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const remove = useCallback((id) => {
    setToasts(prev => prev.filter(toast => toast.id !== id))
  }, [])

  const showToast = useCallback((message, options = {}) => {
    if (!message) return
    const { variant = 'info', duration = 4500 } = options
    const id = ++idCounter
    setToasts(prev => [...prev, { id, message, variant }])
    if (duration !== Infinity) {
      window.setTimeout(() => remove(id), duration)
    }
  }, [remove])

  const value = useMemo(() => ({ showToast }), [showToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastRegion toasts={toasts} onClose={remove} />
    </ToastContext.Provider>
  )
}

function ToastRegion({ toasts, onClose }) {
  const regionId = useId()
  if (!toasts.length) return null
  return (
    <div
      id={regionId}
      className="toast-region"
      role="region"
      aria-live="polite"
      aria-atomic="true"
    >
      {toasts.map(toast => (
        <div key={toast.id} className={`toast toast-${toast.variant}`} role="status">
          <span>{toast.message}</span>
          <button type="button" className="toast-dismiss" onClick={() => onClose(toast.id)} aria-label="Dismiss notification">
            ×
          </button>
        </div>
      ))}
    </div>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
