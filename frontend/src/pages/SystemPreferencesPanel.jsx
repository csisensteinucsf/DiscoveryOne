const themeOptions = [
  { id: 'light', label: 'Light', desc: 'Bright interface similar to default mode.' },
  { id: 'dark', label: 'Dark', desc: 'Low-glare view that matches dark OS themes.' },
  { id: 'system', label: 'Match device', desc: 'Follow your computer or browser theme automatically.' },
]

export default function SystemPreferencesPanel({
  titleStyle,
  userTheme,
  themeSaving,
  updateThemePreference,
  caseSortMode,
  caseSortSaving,
  updateCaseSortPreference,
}) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={titleStyle}>User Preferences</div>
      <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
        Choose the display mode for your user. The preference is saved to your profile and sticks across browsers and restarts.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 12 }}>
        {themeOptions.map((opt) => (
          <label key={opt.id} style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12, display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
            <input
              type="radio"
              name="theme"
              checked={userTheme === opt.id}
              onChange={() => updateThemePreference(opt.id)}
              disabled={themeSaving}
              style={{ marginTop: 4 }}
            />
            <span>
              <div style={{ fontWeight: 700 }}>{opt.label}</div>
              <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>{opt.desc}</div>
            </span>
          </label>
        ))}
      </div>
      {themeSaving && <div style={{ marginTop: 8, color: 'var(--muted,#6b7280)' }}>Saving preference</div>}
      <div style={{ marginTop: 16, borderTop: '1px solid var(--border,#e5e7eb)', paddingTop: 14 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Cases Page Sorting</div>
        <p style={{ color: 'var(--muted,#6b7280)', marginTop: 0 }}>
          Choose whether cases are sorted by eDiscovery case name or legal case name within the year/letter groups.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 12 }}>
          <label style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12, display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
            <input
              type="radio"
              name="case_sort_mode"
              checked={caseSortMode === 'ediscovery'}
              onChange={() => updateCaseSortPreference('ediscovery')}
              disabled={caseSortSaving}
              style={{ marginTop: 4 }}
            />
            <span>
              <div style={{ fontWeight: 700 }}>eDiscovery case name</div>
              <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>Uses the internal case name (e.g., D1 case naming).</div>
            </span>
          </label>
          <label style={{ border: '1px solid var(--border,#e5e7eb)', borderRadius: 10, padding: 12, display: 'flex', gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
            <input
              type="radio"
              name="case_sort_mode"
              checked={caseSortMode === 'legal'}
              onChange={() => updateCaseSortPreference('legal')}
              disabled={caseSortSaving}
              style={{ marginTop: 4 }}
            />
            <span>
              <div style={{ fontWeight: 700 }}>Legal case name</div>
              <div style={{ color: 'var(--muted,#6b7280)', fontSize: 13 }}>Uses the legal case name when present; falls back to internal name.</div>
            </span>
          </label>
        </div>
        {caseSortSaving && <div style={{ marginTop: 8, color: 'var(--muted,#6b7280)' }}>Saving preference</div>}
      </div>
    </div>
  )
}