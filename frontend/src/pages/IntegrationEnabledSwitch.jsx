export default function IntegrationEnabledSwitch({ enabled, disabled = false, onChange, compact = false }) {
  return (
    <label className={`integration-enabled-switch${compact ? ' is-compact' : ''}`}>
      <input
        type="checkbox"
        checked={enabled}
        disabled={disabled}
        onChange={event => onChange(event.target.checked)}
        aria-label={`${enabled ? 'Disable' : 'Enable'} integration`}
      />
      <span className="integration-enabled-switch__track" aria-hidden="true">
        <span className="integration-enabled-switch__thumb" />
      </span>
      <span className="integration-enabled-switch__label">{enabled ? 'Enabled' : 'Disabled'}</span>
    </label>
  )
}
