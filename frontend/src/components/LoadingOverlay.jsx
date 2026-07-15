import React from 'react'

/**
 * Reusable full-screen loading overlay with spinner and status text.
 */
if (typeof document !== 'undefined' && !document.getElementById('d1-loading-style')) {
  const style = document.createElement('style')
  style.id = 'd1-loading-style'
  style.textContent = `
    @keyframes d1spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
    @keyframes d1pulse { 0%, 100% { opacity: 0.5; } 50% { opacity: 1; } }
  `
  document.head.appendChild(style)
}

export default function LoadingOverlay({ visible, title = 'Working...', subtitle = "This can take a few seconds. Please do not close the window." }) {
  if (!visible) return null
  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(15, 23, 42, 0.55)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      backdropFilter: 'blur(2px)',
    }}>
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        background: 'white',
        padding: '16px 20px',
        borderRadius: 12,
        boxShadow: '0 12px 30px rgba(0,0,0,0.2)',
        minWidth: 220,
      }}>
        <div style={{
          width: 54,
          height: 54,
          borderRadius: '50%',
          border: '5px solid #e2e8f0',
          borderTopColor: '#0EA5E9',
          animation: 'd1spin 0.9s linear infinite',
        }} />
        <div style={{ fontWeight: 700, color: '#0f172a' }}>{title}</div>
        <div style={{ fontSize: 12, color: '#475569', textAlign: 'center', animation: 'd1pulse 1.4s ease-in-out infinite' }}>
          {subtitle}
        </div>
      </div>
    </div>
  )
}
