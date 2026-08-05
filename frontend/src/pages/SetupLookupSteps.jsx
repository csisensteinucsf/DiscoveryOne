import { FieldHelp } from './SetupCoreSteps.jsx'
import PersonLookupFieldMappings from './PersonLookupFieldMappings.jsx'

const fieldHelpStyle = { display: 'block', marginTop: 4, color: 'var(--muted,#6b7280)', fontSize: 13, lineHeight: 1.35 }

export function PreservationStep({
  form,
  builtInPreservation,
  togglePreservationSource,
  update,
  customSources,
}) {
  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 10 }}>
        {builtInPreservation.map(([key, label]) => (
          <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600 }}>
            <input type="checkbox" checked={!!form.preservation_sources[key]} onChange={() => togglePreservationSource(key)} />
            {label}
          </label>
        ))}
      </div>
      <div style={fieldHelpStyle}>These checkboxes choose which built-in preservation sources your team tracks. Email, OneDrive, Box, and Slack are selected by default; every source can be changed later in System.</div>
      <label>
        What other preservation sources would you like to track?
        <textarea
          className="input"
          rows={4}
          value={form.custom_preservation_sources}
          onChange={e => update('custom_preservation_sources', e.target.value)}
          placeholder=""
        />
        <FieldHelp>Enter any additional systems your team needs to track, separated by commas or new lines; each entry becomes its own configured preservation source.</FieldHelp>
      </label>
      {customSources.length > 0 && (
        <div style={{ color: 'var(--muted,#6b7280)' }}>
          Additional sources: {customSources.map(item => item.label).join(', ')}
        </div>
      )}
    </div>
  )
}

export function PersonLookupStep({
  form,
  setPersonLookupEnabled,
  updateProvider,
  updateIntegrationConfig,
}) {
  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <label style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontWeight: 700 }}>
        <input
          type="checkbox"
          checked={!!form.enabled_integrations.person_lookup}
          onChange={e => setPersonLookupEnabled(e.target.checked)}
          style={{ marginTop: 4 }}
        />
        <span>
          Enable person lookup
          <FieldHelp>When enabled, DiscoveryOne can search a configured identity source instead of requiring staff to manually type custodian details for every case.</FieldHelp>
        </span>
      </label>

      <div className="form-grid">
        <label>
          Lookup Provider
          <select
            className="input"
            value={form.integrations.person_lookup_provider}
            onChange={e => updateProvider('person_lookup_provider', e.target.value)}
            disabled={!form.enabled_integrations.person_lookup}
          >
            <option value="none">None/manual entry</option>
            <option value="csv">CSV/static directory file</option>
            <option value="http">IDP/HR API</option>
          </select>
          <FieldHelp>Select manual entry if your team will type custodian details, CSV/static for a mounted directory export, or IDP/HR API for a live identity or HR endpoint.</FieldHelp>
        </label>
        <label>
          Connection Fields
          <textarea
            className="input"
            rows={4}
            readOnly
            value={
              form.integrations.person_lookup_provider === 'http'
                ? 'Lookup API URL\nHTTP method\nQuery and email parameters\nResults path\nAuth header and value'
                : 'CSV file path'
            }
          />
          <FieldHelp>Enter these values here or later in System. API lookup expects JSON results, while CSV lookup reads a mounted directory export.</FieldHelp>
        </label>
      </div>      {form.integrations.person_lookup_provider === 'csv' && (
        <label>
          CSV File Path
          <input className="input" value={form.integration_configs.person_lookup?.csv_path || ''} onChange={e => updateIntegrationConfig('person_lookup', 'csv_path', e.target.value)} placeholder="/data/system/person_lookup/people.csv" />
          <FieldHelp>This mounted path is saved by DiscoveryOne and used by the CSV/static lookup provider.</FieldHelp>
        </label>
      )}
      {form.integrations.person_lookup_provider === 'http' && (
        <div className="form-grid">
          <label>
            Lookup API URL
            <input className="input" value={form.integration_configs.person_lookup?.http_url || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_url', e.target.value)} placeholder="https://idp.example.edu/people/search" />
            <FieldHelp>This endpoint receives the lookup query and returns matching people as JSON.</FieldHelp>
          </label>
          <label>
            HTTP Method
            <select className="input" value={form.integration_configs.person_lookup?.http_method || 'GET'} onChange={e => updateIntegrationConfig('person_lookup', 'http_method', e.target.value)}>
              <option value="GET">GET</option>
              <option value="POST">POST</option>
            </select>
            <FieldHelp>Choose how DiscoveryOne sends lookup parameters to the identity endpoint.</FieldHelp>
          </label>
          <label>
            Query Parameter
            <input className="input" value={form.integration_configs.person_lookup?.http_query_param || 'query'} onChange={e => updateIntegrationConfig('person_lookup', 'http_query_param', e.target.value)} placeholder="query" />
            <FieldHelp>This is the request parameter that receives a name, email address, or Employee ID.</FieldHelp>
          </label>
          <label>
            Email Parameter
            <input className="input" value={form.integration_configs.person_lookup?.http_email_param || 'email'} onChange={e => updateIntegrationConfig('person_lookup', 'http_email_param', e.target.value)} placeholder="email" />
            <FieldHelp>This request parameter receives an explicit email address when one is available; leave it blank if the endpoint does not use one.</FieldHelp>
          </label>
          <label>
            Results Path
            <input className="input" value={form.integration_configs.person_lookup?.http_results_path || 'results'} onChange={e => updateIntegrationConfig('person_lookup', 'http_results_path', e.target.value)} placeholder="results" />
            <FieldHelp>Use a dot-separated JSON path to the result list, or leave it empty when the response itself is the list.</FieldHelp>
          </label>
          <label>
            Timeout Seconds
            <input className="input" type="number" min="1" max="120" value={form.integration_configs.person_lookup?.http_timeout_seconds ?? 10} onChange={e => updateIntegrationConfig('person_lookup', 'http_timeout_seconds', e.target.value)} />
            <FieldHelp>Maximum time DiscoveryOne waits for each identity API request.</FieldHelp>
          </label>
          <label>
            Auth Header
            <input className="input" value={form.integration_configs.person_lookup?.http_auth_header || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_auth_header', e.target.value)} placeholder="Authorization" />
            <FieldHelp>Use this when your IDP or HR API requires a token header.</FieldHelp>
          </label>
          <label>
            Auth Value
            <input className="input" type="password" value={form.integration_configs.person_lookup?.http_auth_value || ''} onChange={e => updateIntegrationConfig('person_lookup', 'http_auth_value', e.target.value)} placeholder="Bearer ..." />
            <FieldHelp>This secret is encrypted before DiscoveryOne stores it.</FieldHelp>
          </label>
        </div>
      )}
      {form.enabled_integrations.person_lookup && form.integrations.person_lookup_provider !== 'none' && (
        <PersonLookupFieldMappings
          config={form.integration_configs.person_lookup}
          onChange={(field, value) => updateIntegrationConfig('person_lookup', field, value)}
        />
      )}
      <div style={{ color: 'var(--muted,#6b7280)', lineHeight: 1.5 }}>
        The lookup source should provide stable identity data for custodians and employees: display name, first/middle/last name, email, Employee ID, department, title, separation date, and separation status. DiscoveryOne normalizes those values into a common person record, then stores the selected custodian details on the case records that use them.
      </div>
      <div style={{ color: 'var(--muted,#6b7280)', lineHeight: 1.5 }}>
        For IDP/HR API lookup, point the lookup API URL at an endpoint that accepts a query and returns a JSON list of people. DiscoveryOne reads common field names such as display_name, email, employee_id, department, title, separation_date, and separation_status. The source system remains the system of record; DiscoveryOne only saves the values needed for legal hold and case workflows after a person is selected.
      </div>
    </div>
  )
}
