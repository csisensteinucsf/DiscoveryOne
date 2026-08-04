export default function CaseRequestSearchSection({
  visible,
  searchIncluded,
  isNewCase,
  isSearch,
  form,
  setForm,
  autofillNonce,
  caseContext,
  additionalVersaSearches,
  setAdditionalVersaSearches,
  setSearchRequestsFinalized,
  searchRequestsFinalized,
  totalSearchCount,
}) {
  if (!visible || !searchIncluded) return null

  return (
    <div className="form-section">
      <div className="form-section__title">
        {(isNewCase || isSearch) ? 'AI-Powered Search Builder' : 'Search details'}
      </div>
      <div className="form-section__body">
        {(isNewCase || isSearch) ? (
          <VersaSearchFields
            form={form}
            setForm={setForm}
            autofillNonce={autofillNonce}
            caseContext={caseContext}
            additionalVersaSearches={additionalVersaSearches}
            setAdditionalVersaSearches={setAdditionalVersaSearches}
            setSearchRequestsFinalized={setSearchRequestsFinalized}
            searchIncluded={searchIncluded}
            totalSearchCount={totalSearchCount}
            searchRequestsFinalized={searchRequestsFinalized}
            isSearch={isSearch}
          />
        ) : (
          <StructuredSearchFields
            form={form}
            setForm={setForm}
            autofillNonce={autofillNonce}
            caseContext={caseContext}
            isSearch={isSearch}
            setSearchRequestsFinalized={setSearchRequestsFinalized}
            searchRequestsFinalized={searchRequestsFinalized}
            totalSearchCount={totalSearchCount}
          />
        )}
      </div>
    </div>
  )
}

function VersaSearchFields({
  form,
  setForm,
  autofillNonce,
  caseContext,
  additionalVersaSearches,
  setAdditionalVersaSearches,
  setSearchRequestsFinalized,
  searchIncluded,
  totalSearchCount,
  searchRequestsFinalized,
  isSearch,
}) {
  return (
    <>
      <p style={{ marginTop: 0, marginBottom: 10, color: '#475569', fontSize: 13 }}>
        Enter your requirements or desired outcomes for a search. Use natural language. For multiple/distinct search requests, hit submit search and then select YES when asked if you have additional searches
      </p>
      <label style={{ display: 'block' }}>
        <span>Search requirements / outcomes</span>
        <textarea
          rows={7}
          autoComplete="off"
          name={`field-${autofillNonce}-${caseContext?.id || 'new'}-versa-req`}
          value={form.versa_search_requirements || ''}
          onChange={(e) => {
            const value = e.target.value
            setForm((prev) => ({ ...prev, versa_search_requirements: value }))
            setSearchRequestsFinalized(false)
          }}
        />
      </label>
      {additionalVersaSearches.map((entry, idx) => (
        <label key={`versa-search-${idx}`} style={{ display: 'block', marginTop: 12 }}>
          <span>{`Additional search request ${idx + 2}`}</span>
          <textarea
            rows={7}
            autoComplete="off"
            name={`field-${autofillNonce}-${caseContext?.id || 'new'}-versa-req-${idx + 2}`}
            value={entry}
            onChange={(e) => {
              const value = e.target.value
              setAdditionalVersaSearches((prev) => prev.map((item, itemIdx) => itemIdx === idx ? value : item))
              setSearchRequestsFinalized(false)
            }}
          />
          <div style={{ marginTop: 6, display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn ghost"
              type="button"
              onClick={() => {
                setAdditionalVersaSearches((prev) => prev.filter((_, itemIdx) => itemIdx !== idx))
                setSearchRequestsFinalized(false)
              }}
            >
              Remove search request
            </button>
          </div>
        </label>
      ))}
      {searchIncluded && totalSearchCount > 0 && (
        <p style={{ marginBottom: 0, color: '#475569', fontSize: 12 }}>
          {searchRequestsFinalized
            ? (isSearch
              ? 'Search requests captured. Click Submit Request to send the combined request.'
              : 'Search requests captured. Click Submit Request to finish the case intake.')
            : 'Click Submit Search Request to capture this search and decide whether to add another.'}
        </p>
      )}
    </>
  )
}

function StructuredSearchFields({
  form,
  setForm,
  autofillNonce,
  caseContext,
  isSearch,
  setSearchRequestsFinalized,
  searchRequestsFinalized,
  totalSearchCount,
}) {
  const updateSearchField = (field, value) => {
    setForm((prev) => ({ ...prev, search: { ...prev.search, [field]: value } }))
    if (isSearch) setSearchRequestsFinalized(false)
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 12 }}>
      {!!form.searches?.length && (
        <div style={{ gridColumn: '1 / -1', border: '1px solid #dbe2ea', borderRadius: 10, padding: 12, background: '#f8fafc' }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Queued search requests ({form.searches.length})</div>
          <div style={{ display: 'grid', gap: 8 }}>
            {form.searches.map((entry, idx) => (
              <QueuedSearchCard
                key={`queued-search-${idx}`}
                entry={entry}
                index={idx}
                setForm={setForm}
                setSearchRequestsFinalized={setSearchRequestsFinalized}
              />
            ))}
          </div>
        </div>
      )}
      <label style={{ gridColumn: '1 / -1' }}>
        <span>Keywords</span>
        <textarea rows={5} autoComplete="off" name={`field-${autofillNonce}-${caseContext?.id || 'new'}-search-kw`} value={form.search.keywords} onChange={(e) => updateSearchField('keywords', e.target.value)} />
      </label>
      <label>
        <span>Senders</span>
        <textarea rows={3} autoComplete="off" name={`field-${autofillNonce}-${caseContext?.id || 'new'}-search-snd`} value={form.search.senders} onChange={(e) => updateSearchField('senders', e.target.value)} />
      </label>
      <label>
        <span>Recipients</span>
        <textarea rows={3} autoComplete="off" name={`field-${autofillNonce}-${caseContext?.id || 'new'}-search-rcp`} value={form.search.recipients} onChange={(e) => updateSearchField('recipients', e.target.value)} />
      </label>
      <label style={{ gridColumn: '1 / -1' }}>
        <span>Date Range</span>
        <div className="row" style={{ gap: 6 }}>
          <input style={{ flex: 1, minWidth: 0, height: 44 }} type="date" autoComplete="off" name={`field-${autofillNonce}-${caseContext?.id || 'new'}-search-from`} value={form.search.date_from} onChange={(e) => updateSearchField('date_from', e.target.value)} />
          <input style={{ flex: 1, minWidth: 0, height: 44 }} type="date" autoComplete="off" name={`field-${autofillNonce}-${caseContext?.id || 'new'}-search-to`} value={form.search.date_to} onChange={(e) => updateSearchField('date_to', e.target.value)} />
        </div>
      </label>
      <label style={{ gridColumn: '1 / -1' }}>
        <span>Additional Instructions</span>
        <textarea rows={6} autoComplete="off" name={`field-${autofillNonce}-${caseContext?.id || 'new'}-search-extra`} value={form.search.additional} onChange={(e) => updateSearchField('additional', e.target.value)} />
      </label>
      {isSearch && totalSearchCount > 0 && (
        <div style={{ gridColumn: '1 / -1', color: '#475569', fontSize: 12 }}>
          {searchRequestsFinalized
            ? 'Search requests captured. Click Submit Request to send the combined request.'
            : 'Click Submit Search Request to capture this search and decide whether to add another.'}
        </div>
      )}
    </div>
  )
}

function QueuedSearchCard({ entry, index, setForm, setSearchRequestsFinalized }) {
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 10, background: '#fff' }}>
      <div style={{ fontSize: 12, color: '#475569', marginBottom: 6 }}>Search request {index + 1}</div>
      <div style={{ whiteSpace: 'pre-wrap', color: '#111827', fontSize: 13 }}>
        {[
          entry.keywords ? `Keywords: ${entry.keywords}` : '',
          entry.senders ? `Senders: ${entry.senders}` : '',
          entry.recipients ? `Recipients: ${entry.recipients}` : '',
          entry.date_from || entry.date_to ? `Date Range: ${entry.date_from || '-'} to ${entry.date_to || '-'}` : '',
          entry.additional ? `Additional: ${entry.additional}` : '',
        ].filter(Boolean).join('\n') || 'No details'}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
        <button
          className="btn ghost"
          type="button"
          onClick={() => {
            setForm((prev) => ({
              ...prev,
              searches: (Array.isArray(prev.searches) ? prev.searches : []).filter((_, itemIdx) => itemIdx !== index),
            }))
            setSearchRequestsFinalized(false)
          }}
        >
          Remove
        </button>
      </div>
    </div>
  )
}
