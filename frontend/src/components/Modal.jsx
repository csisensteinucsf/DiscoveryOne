import { useEffect, useId, useRef } from 'react'

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])'

export default function Modal({
  open = true,
  title,
  onClose,
  children,
  footer,
  width = 720,
  titleId,
  dismissOnBackdrop = false,
  bodyStyle,
}) {
  const backdropRef = useRef(null)
  const dialogRef = useRef(null)
  const previouslyFocused = useRef(null)
  const latestOnClose = useRef(onClose)
  const headingId = titleId || useId()

  useEffect(() => {
    latestOnClose.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!open) return
    previouslyFocused.current = document.activeElement
    const focusable = dialogRef.current?.querySelectorAll(FOCUSABLE)
    focusable && focusable[0]?.focus()

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        latestOnClose.current?.()
      } else if (event.key === 'Tab') {
        const list = dialogRef.current?.querySelectorAll(FOCUSABLE)
        if (!list || list.length === 0) return
        const first = list[0]
        const last = list[list.length - 1]
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      previouslyFocused.current?.focus?.()
    }
  }, [open])

  if (!open) return null

  const stop = (e) => e.stopPropagation()

  return (
    <div
      ref={backdropRef}
      className="modal-backdrop"
      role="presentation"
      onClick={dismissOnBackdrop ? onClose : undefined}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className="modal"
        style={{ maxWidth: width, width: '100%' }}
        ref={dialogRef}
        onClick={stop}
      >
        <div className="modal-header">
          <h3 id={headingId} style={{ margin: 0 }}>{title}</h3>
        </div>
        <div className="modal-body" style={bodyStyle}>
          {children}
        </div>
        {footer && (
          <div className="modal-footer">
            {footer}
          </div>
        )}
      </div>
    </div>
  )
}
