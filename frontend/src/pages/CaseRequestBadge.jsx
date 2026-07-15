import { STATUS_COLORS } from './caseRequestsUtils.js'

export default function Badge({ status }) {
  const colors = STATUS_COLORS[status] || { bg: '#e5e7eb', fg: '#374151' }
  return (
    <span style={{
      fontSize: 12,
      padding: '3px 10px',
      borderRadius: 999,
      background: colors.bg,
      color: colors.fg,
      fontWeight: 600,
      textTransform: 'capitalize'
    }}>{status}</span>
  )
}
