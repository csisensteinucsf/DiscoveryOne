const PERSON_FIELDS = [
  ['display_name', 'Display name', 'profile.displayName'],
  ['first_name', 'First name', 'profile.givenName'],
  ['middle_name', 'Middle name', 'profile.middleName'],
  ['last_name', 'Last name', 'profile.familyName'],
  ['email', 'Email', 'contact.primaryEmail'],
  ['external_id', 'Employee ID', 'employment.employeeId'],
  ['department', 'Department', 'employment.department'],
  ['title', 'Title', 'employment.title'],
  ['separation_date', 'Separation date', 'employment.endDate'],
  ['separation_status', 'Separation status', 'employment.status'],
]

export default function PersonLookupFieldMappings({ config = {}, onChange }) {
  return (
    <div style={{ display: 'grid', gap: 10, marginTop: 14 }}>
      <label style={{ maxWidth: 420 }}>
        Maximum custodians per lookup request
        <input
          className="input"
          type="number"
          min="1"
          max="1000"
          value={config?.max_custodians ?? 100}
          onChange={event => onChange('max_custodians', event.target.value)}
        />
      </label>
      <div>
        <h4 style={{ margin: '0 0 4px' }}>Response Field Mappings</h4>
        <p style={{ color: 'var(--muted,#6b7280)', margin: 0, lineHeight: 1.45 }}>
          Dot-separated paths map your directory fields into DiscoveryOne. Leave a field blank to use common names such as display_name, mail, employee_id, department, title, and separation_date.
        </p>
      </div>
      <div className="form-grid">
        {PERSON_FIELDS.map(([key, label, placeholder]) => (
          <label key={key}>
            {label} path
            <input
              className="input"
              value={config?.[`field_${key}`] || ''}
              onChange={event => onChange(`field_${key}`, event.target.value)}
              placeholder={placeholder}
            />
          </label>
        ))}
      </div>
    </div>
  )
}