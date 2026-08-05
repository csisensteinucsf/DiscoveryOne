import { useEffect } from 'react'

function missingRequiredControls(form) {
  if (!form?.elements) return []
  return Array.from(form.elements).filter(control => (
    control?.required &&
    !control.disabled &&
    control.validity?.valueMissing
  ))
}

function updateFeedback(form) {
  if (!form) return
  if (missingRequiredControls(form).length) {
    form.dataset.requiredFeedback = 'true'
  } else {
    delete form.dataset.requiredFeedback
  }
}

export default function RequiredFormFeedback() {
  useEffect(() => {
    const onInvalid = (event) => {
      if (!event.target?.required || !event.target.validity?.valueMissing) return
      const form = event.target.form
      if (!form) return
      event.preventDefault()
      form.dataset.requiredFeedback = 'true'
      window.requestAnimationFrame(() => missingRequiredControls(form)[0]?.focus?.())
    }
    const onInput = (event) => {
      if (!event.target?.form?.dataset.requiredFeedback) return
      updateFeedback(event.target.form)
    }
    const onReset = (event) => {
      delete event.target?.dataset?.requiredFeedback
    }

    document.addEventListener('invalid', onInvalid, true)
    document.addEventListener('input', onInput, true)
    document.addEventListener('change', onInput, true)
    document.addEventListener('reset', onReset, true)
    return () => {
      document.removeEventListener('invalid', onInvalid, true)
      document.removeEventListener('input', onInput, true)
      document.removeEventListener('change', onInput, true)
      document.removeEventListener('reset', onReset, true)
    }
  }, [])

  return null
}
