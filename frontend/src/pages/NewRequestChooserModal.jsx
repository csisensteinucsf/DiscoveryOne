import { useEffect, useMemo, useState } from 'react'
import Modal from '../components/Modal.jsx'
import RequiredFieldLabel from '../components/RequiredFieldLabel.jsx'

export default function NewRequestChooserModal({ apiBase = '/api', onClose, onContinue }) {
  const [target, setTarget] = useState('new')
  const [requestType, setRequestType] = useState('custodian')
  const [matters, setMatters] = useState([])
  const [query, setQuery] = useState('')
  const [selectedMatter, setSelectedMatter] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetch(apiBase + '/cases', { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Unable to load matters.')
        return response.json()
      })
      .then(data => {
        if (cancelled) return
        const rows = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : [])
        setMatters(rows.filter(matter => !matter.closed))
      })
      .catch(loadError => { if (!cancelled) setError(loadError?.message || 'Unable to load matters.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [apiBase])

  const matches = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return matters.slice(0, 12)
    return matters
      .filter(matter => [matter.name, matter.legal_case_name, matter.matter_number]
        .some(field => String(field || '').toLowerCase().includes(value)))
      .slice(0, 12)
  }, [matters, query])

  const continueRequest = () => {
    setSubmitted(true)
    if (target === 'new') {
      onContinue({ mode: 'new_case' })
      return
    }
    if (!selectedMatter) return
    onContinue({ mode: requestType, caseId: selectedMatter.id, caseName: selectedMatter.name })
  }

  return (
    <Modal
      open
      title="New Request"
      onClose={onClose}
      width={660}
      footer={(
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" className="btn secondary" onClick={onClose}>Cancel</button>
          <button type="button" className="btn" onClick={continueRequest}>Continue</button>
        </div>
      )}
    >
      <div className="new-request-chooser">
        <div className="new-request-chooser__target" role="radiogroup" aria-label="Request target">
          <label className={target === 'new' ? 'selected' : ''}>
            <input type="radio" name="request-target" checked={target === 'new'} onChange={() => setTarget('new')} />
            <span><strong>New matter</strong><small>Submit a new matter for review and approval.</small></span>
          </label>
          <label className={target === 'existing' ? 'selected' : ''}>
            <input type="radio" name="request-target" checked={target === 'existing'} onChange={() => setTarget('existing')} />
            <span><strong>Existing matter</strong><small>Add custodians or request searches for a matter you can access.</small></span>
          </label>
        </div>

        {target === 'existing' && (
          <>
            <label className="field">
              <RequiredFieldLabel>Select a matter</RequiredFieldLabel>
              <input
                className={submitted && !selectedMatter ? 'input-error' : ''}
                type="search"
                value={query}
                placeholder="Type a matter name or number..."
                autoComplete="off"
                onChange={event => {
                  setQuery(event.target.value)
                  if (selectedMatter && event.target.value !== selectedMatter.name) setSelectedMatter(null)
                }}
              />
            </label>
            <div className="new-request-chooser__results" role="listbox" aria-label="Matching matters">
              {loading ? <p className="muted">Loading matters...</p> : matches.map(matter => (
                <button
                  type="button"
                  role="option"
                  aria-selected={selectedMatter?.id === matter.id}
                  className={selectedMatter?.id === matter.id ? 'selected' : ''}
                  key={matter.id}
                  onClick={() => { setSelectedMatter(matter); setQuery(matter.name || '') }}
                >
                  <span>{matter.name}</span>
                  <small>{matter.matter_number || matter.legal_case_name || 'Active matter'}</small>
                </button>
              ))}
              {!loading && !matches.length && <p className="muted">No matching matters.</p>}
            </div>
            <fieldset className="new-request-chooser__type">
              <legend>What would you like to request?</legend>
              <label><input type="radio" name="existing-request-type" checked={requestType === 'custodian'} onChange={() => setRequestType('custodian')} /> Add custodians</label>
              <label><input type="radio" name="existing-request-type" checked={requestType === 'search'} onChange={() => setRequestType('search')} /> Search request</label>
            </fieldset>
            {submitted && !selectedMatter && <p className="missing-required-message">Missing required fields.</p>}
          </>
        )}
        {error && <div className="alert error">{error}</div>}
      </div>
    </Modal>
  )
}