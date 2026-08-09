import { useState } from 'react'
import { Upload } from 'lucide-react'

export default function FileDropZone({
  children,
  onFiles,
  disabled = false,
  multiple = false,
  className = '',
  prompt,
}) {
  const [dragActive, setDragActive] = useState(false)

  const stopDrag = (event) => {
    event.preventDefault()
    event.stopPropagation()
  }

  const handleDragEnter = (event) => {
    stopDrag(event)
    if (!disabled && Array.from(event.dataTransfer?.types || []).includes('Files')) setDragActive(true)
  }

  const handleDragLeave = (event) => {
    stopDrag(event)
    if (!event.currentTarget.contains(event.relatedTarget)) setDragActive(false)
  }

  const handleDrop = (event) => {
    stopDrag(event)
    setDragActive(false)
    if (disabled) return
    const files = Array.from(event.dataTransfer?.files || [])
    if (!files.length) return
    onFiles?.(multiple ? files : files.slice(0, 1))
  }

  return (
    <div
      className={`file-drop-zone${dragActive ? ' is-drag-active' : ''}${disabled ? ' is-disabled' : ''}${className ? ` ${className}` : ''}`}
      onDragEnter={handleDragEnter}
      onDragOver={stopDrag}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}
      <div className="file-drop-zone__prompt">
        <Upload size={15} aria-hidden="true" />
        <span>{prompt || `Drag and drop ${multiple ? 'files' : 'a file'} here`}</span>
      </div>
    </div>
  )
}
