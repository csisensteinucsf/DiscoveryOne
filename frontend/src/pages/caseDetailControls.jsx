export function Field({ label, children, hint }) {
  return (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div style={{ fontSize: 13, color: '#334155', marginBottom: 6 }}>{label}</div>
      {children}
      {hint ? <div style={{ fontSize: 12, color: '#6b7280', marginTop: 6 }}>{hint}</div> : null}
    </label>
  )
}
export function TextInput({ style, onFocus, onBlur, ...props }) {
  return (
    <input
      {...props}
      style={{
        width: '100%',
        padding: '10px 12px',
        borderRadius: 10,
        border: '1px solid #dce0e5',
        outline: 'none',
        boxShadow: '0 1px 0 rgba(0,0,0,0.02) inset',
        ...style,
      }}
      onFocus={(e) => {
        e.currentTarget.style.borderColor = '#3b82f6'
        if (typeof onFocus === 'function') onFocus(e)
      }}
      onBlur={(e) => {
        e.currentTarget.style.borderColor = '#dce0e5'
        if (typeof onBlur === 'function') onBlur(e)
      }}
    />
  )
}
export function Select(props) {
  return (
    <select
      {...props}
      style={{
        width: '100%',
        padding: '10px 12px',
        borderRadius: 10,
        border: '1px solid var(--border, #dce0e5)',
        outline: 'none',
        background: 'var(--card, #ffffff)',
        color: 'var(--text, #0f172a)',
        boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.04)',
      }}
      onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--accent, #3b82f6)')}
      onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--border, #dce0e5)')}
    />
  )
}
export function Button({ children, variant = 'primary', className, ...rest }) {
  const base = {
    padding: '10px 14px',
    borderRadius: 12,
    border: '1px solid transparent',
    cursor: 'pointer',
    fontWeight: 500,
    transition: 'background-color 120ms ease, border-color 120ms ease, color 120ms ease',
  }
  const styles = {
    primary: { ...base, background: '#2563eb', color: '#f8fafc', border: '1px solid #1d4ed8' },
    ghost: { ...base, background: '#f8fafc', color: '#1d4ed8', border: '1px solid #d0d7e2' },
    danger: { ...base, background: '#ef4444', color: 'white', border: '1px solid #dc2626' },
    subtle: { ...base, background: '#eef2f7', color: '#0f172a', border: '1px solid #d8dee9' }
  }
  const props = { ...rest }
  if (!props.type) props.type = 'button'
  return <button {...props} className={className} style={styles[variant] || styles.primary}>{children}</button>
}
export function InlineSpinner({ size = 14, color = '#0ea5e9' }) {
  return (
    <span
      aria-hidden="true"
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: '50%',
        border: `2px solid rgba(15,23,42,0.15)`,
        borderTopColor: color,
        animation: 'd1spin 0.9s linear infinite',
      }}
    />
  )
}
// Updated Badge: supports fractional fill & compact chips
export function Badge({ children, variant = 'default', half = false, fillPct = null, compact = false, ...rest }) {
  const readVar = (name, fallback) => {
    if (typeof document === 'undefined') return fallback
    const val = getComputedStyle(document.documentElement).getPropertyValue(name)
    return val && val.trim() ? val.trim() : fallback
  }
  const colors = {
    default: {
      bg: readVar('--badge-default-bg', '#eef2f7'),
      fg: readVar('--badge-default-fg', '#334155'),
      br: readVar('--badge-default-br', '#e5e7eb'),
      track: readVar('--badge-default-track', '#f8fafc'),
      fill: readVar('--badge-default-fill', '#94a3b8'),
    },
    info: {
      bg: readVar('--badge-info-bg', '#dbeafe'),
      fg: readVar('--badge-info-fg', '#1e40af'),
      br: readVar('--badge-info-br', '#bfdbfe'),
      track: readVar('--badge-info-track', '#eff6ff'),
      fill: readVar('--badge-info-fill', '#3b82f6'),
    },
    success: {
      bg: readVar('--badge-success-bg', '#dcfce7'),
      fg: readVar('--badge-success-fg', '#166534'),
      br: readVar('--badge-success-br', '#bbf7d0'),
      track: readVar('--badge-success-track', '#f0fdf4'),
      fill: readVar('--badge-success-fill', '#22c55e'),
    },
    warn: {
      bg: readVar('--badge-warn-bg', '#fef3c7'),
      fg: readVar('--badge-warn-fg', '#92400e'),
      br: readVar('--badge-warn-br', '#fde68a'),
      track: readVar('--badge-warn-track', '#fffbeb'),
      fill: readVar('--badge-warn-fill', '#f59e0b'),
    },
    danger: {
      bg: readVar('--badge-danger-bg', '#fee2e2'),
      fg: readVar('--badge-danger-fg', '#991b1b'),
      br: readVar('--badge-danger-br', '#fca5a5'),
      track: readVar('--badge-danger-track', '#fef2f2'),
      fill: readVar('--badge-danger-fill', '#ef4444'),
    },
    orange: {
      bg: readVar('--badge-orange-bg', '#ffe8cc'),
      fg: readVar('--badge-orange-fg', '#7c3a00'),
      br: readVar('--badge-orange-br', '#ffd0a6'),
      track: readVar('--badge-orange-track', '#fff7ed'),
      fill: readVar('--badge-orange-fill', '#f97316'),
    }, // email chips
  }
  const c = colors[variant] || colors.default
  let fillStop = 100
  if (half) {
    fillStop = 50
  } else if (fillPct !== null && fillPct >= 0 && fillPct <= 1) {
    fillStop = Math.round(fillPct * 100)
  }
  return (
    <span style={{ position: 'relative', width: 'fit-content', display: 'inline-flex', alignItems: 'center', fontSize: compact ? 11 : 11, fontWeight: 700, padding: compact ? '2px 6px' : '3px 8px', borderRadius: 999, border: `1px solid ${c.br}`, color: c.fg, background: c.track, lineHeight: 1, letterSpacing: 0.25, userSelect: 'none', cursor: (rest && rest.onClick) ? 'pointer' : 'default', boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)', overflow: 'hidden' }} {...rest}>
      <span aria-hidden="true" style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${fillStop}%`, minWidth: fillStop > 0 ? 3 : 0, background: c.fill, opacity: 0.55 }} />
      <span style={{ position: 'relative', zIndex: 1 }}>{children}</span>
    </span>
  )
}
