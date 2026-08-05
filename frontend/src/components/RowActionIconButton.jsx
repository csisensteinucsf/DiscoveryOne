import { Pencil, Trash2 } from 'lucide-react'

function RowActionIconButton({ icon: Icon, label, danger = false, title, ...buttonProps }) {
  return (
    <button
      {...buttonProps}
      type="button"
      className={'icon-button row-action-icon' + (danger ? ' is-danger' : '')}
      title={title || label}
      aria-label={label}
    >
      <Icon size={16} aria-hidden="true" />
    </button>
  )
}

export function EditIconButton({ label = 'Edit', ...buttonProps }) {
  return <RowActionIconButton {...buttonProps} icon={Pencil} label={label} />
}

export function DeleteIconButton({ label = 'Delete', ...buttonProps }) {
  return <RowActionIconButton {...buttonProps} icon={Trash2} label={label} danger />
}
