export default function RequiredFieldLabel({ children, required = true }) {
  return (
    <span className="case-editor-field-label">
      {children}
      {required ? (
        <span className="case-editor-required-mark" aria-hidden="true">{'\u00A0*'}</span>
      ) : null}
    </span>
  )
}
