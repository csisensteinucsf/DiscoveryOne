import { useEffect, useRef } from 'react'

export default function RichTextEditor({
  value,
  onChange,
  placeholder = 'Compose…',
  ariaLabel,
  ariaLabelledBy,
  id,
  editorRef: externalRef = null,
  onSelectionChange,
}) {
  const editorRef = useRef(null)
  const sizeRef = useRef(null)
  const colorRef = useRef(null)
  const highlightColor = '#fef08a'

  useEffect(() => {
    const el = editorRef.current
    if (!el) return
    if (document.activeElement !== el) {
      el.innerHTML = value || ''
    }
  }, [value])

  const exec = (command, arg) => {
    document.execCommand(command, false, arg)
    editorRef.current?.focus()
  }

  const applyFontSize = (event) => {
    const size = event.target.value
    if (!size) return
    exec('fontSize', size)
    event.target.value = ''
  }

  const applyColor = (event) => {
    const color = event.target.value
    if (!color) return
    exec('foreColor', color)
  }

  const applyHighlight = () => {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return
    const range = sel.getRangeAt(0)
    if (range.collapsed) return
    const tmp = document.createElement('div')
    tmp.appendChild(range.cloneContents())
    const html = tmp.innerHTML || sel.toString()
    const style = `background-color:${highlightColor};padding:0 2px;`
    document.execCommand('insertHTML', false, `<mark data-highlight="1" style="${style}">${html}</mark>`)
    handleInput()
  }

  const clearHighlight = () => {
    const el = editorRef.current
    if (!el) return
    const bgPattern = /background-color:\s*#?fef08a/i
    let html = el.innerHTML || ''
    html = html.replace(/<mark\b[^>]*>/gi, '').replace(/<\/mark>/gi, '')
    html = html.replace(/<span\b[^>]*>/gi, (m) => (bgPattern.test(m) ? '' : m))
    html = html.replace(/<\/span>/gi, (m, offset, src) => {
      // Drop closing span only if we dropped its opener for highlight
      const before = src.slice(0, offset)
      const openCount = (before.match(/<span\b[^>]*>/gi) || []).length
      const closeCount = (before.match(/<\/span>/gi) || []).length
      return closeCount < openCount ? '' : m
    })
    el.innerHTML = html
    handleInput()
  }

  const handleInput = () => {
    if (!onChange) return
    const html = editorRef.current?.innerHTML || ''
    onChange(html)
  }

  const handleSelection = () => {
    if (typeof onSelectionChange !== 'function') return
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return
    try {
      const range = sel.getRangeAt(0).cloneRange()
      onSelectionChange(range)
    } catch {
      /* ignore */
    }
  }

  return (
    <div style={rootStyle}>
      <div style={toolbarStyle}>
        <button type="button" style={btnStyle} onClick={() => exec('bold')}><strong>B</strong></button>
        <button type="button" style={btnStyle} onClick={() => exec('italic')}><em>I</em></button>
        <button type="button" style={btnStyle} onClick={() => exec('underline')}><span style={{ textDecoration: 'underline' }}>U</span></button>
        <button type="button" style={btnStyle} onClick={() => exec('insertUnorderedList')}>• List</button>
        <button type="button" style={btnStyle} onClick={() => exec('insertOrderedList')}>1. List</button>
        <select ref={sizeRef} defaultValue="" onChange={applyFontSize} style={selectStyle}>
          <option value="" disabled>Font size</option>
          <option value="2">Small</option>
          <option value="3">Normal</option>
          <option value="4">Large</option>
          <option value="5">XL</option>
        </select>
        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
          Color
          <input ref={colorRef} type="color" defaultValue="#0f172a" onChange={applyColor} />
        </label>
        <button type="button" style={btnStyle} onClick={applyHighlight} title="Highlight selection">
          <span style={{ background: highlightColor, padding: '0 4px', borderRadius: 3 }}>Highlight</span>
        </button>
        <button type="button" style={btnStyle} onClick={clearHighlight} title="Clear highlight">
          Clear highlight
        </button>
      </div>
      <div style={{ position: 'relative' }}>
        <div
          id={id}
          ref={(node) => {
            editorRef.current = node
            if (externalRef) {
              externalRef.current = node
            }
          }}
          style={editorStyle}
          contentEditable
          role="textbox"
          aria-multiline="true"
          aria-label={ariaLabelledBy ? undefined : (ariaLabel || placeholder)}
          aria-labelledby={ariaLabelledBy}
          tabIndex={0}
          onInput={handleInput}
          onFocus={handleSelection}
          onKeyUp={handleSelection}
          onMouseUp={handleSelection}
        />
        {(!value || value === '<br>') && (
          <div
            style={{
              position: 'absolute',
              top: 12,
              left: 12,
              pointerEvents: 'none',
              color: '#9ca3af',
              fontSize: 14,
            }}
          >
            {placeholder}
          </div>
        )}
      </div>
    </div>
  )
}

const rootStyle = {
  border: '1px solid var(--border,#e5e7eb)',
  borderRadius: 12,
  overflow: 'hidden',
}

const toolbarStyle = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 6,
  padding: 6,
  background: 'var(--card,#0f172a)',
  borderBottom: '1px solid var(--border,#e5e7eb)',
}

const btnStyle = {
  border: '1px solid var(--border,#d1d5db)',
  background: 'var(--card,#0f172a)',
  borderRadius: 6,
  padding: '4px 8px',
  fontSize: 13,
  cursor: 'pointer',
  color: 'var(--text,#e5e7eb)',
}

const selectStyle = {
  border: '1px solid var(--border,#d1d5db)',
  borderRadius: 6,
  padding: '4px 8px',
  fontSize: 13,
  background: 'var(--card,#0f172a)',
  color: 'var(--text,#e5e7eb)',
  cursor: 'pointer',
}

const editorStyle = {
  minHeight: 220,
  padding: 12,
  fontSize: 14,
  fontFamily: 'inherit',
  outline: 'none',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  overflowWrap: 'break-word',
  width: '100%',
  background: 'var(--card,#0f172a)',
  color: 'var(--text,#e5e7eb)',
}
