import { SearchAiBuilderModal, SearchModal } from './CaseDetailSearchEditorModals.jsx'

export default function CaseDetailSearchModals({
  showSearchAiModal,
  canUseSearchAi,
  caseId,
  caseData,
  custodians,
  setShowSearchAiModal,
  applyAiSearchSuggestion,
  createSearchesFromAiSuggestions,
  showSearchModal,
  editingSearch,
  suggestedSearchName,
  isRequestor,
  setShowSearchModal,
  setEditingSearch,
  saveSearchDraft,
  searchQueryLabel,
}) {
  return (
    <>
      {showSearchAiModal && canUseSearchAi && (
        <SearchAiBuilderModal
          caseId={caseId}
          caseData={caseData}
          custodians={custodians}
          onClose={() => setShowSearchAiModal(false)}
          onUseSuggestion={applyAiSearchSuggestion}
          onCreateSuggestions={createSearchesFromAiSuggestions}
          searchQueryLabel={searchQueryLabel}
        />
      )}
      {showSearchModal && editingSearch && (
        <SearchModal
          mode={editingSearch.id ? 'edit' : 'create'}
          draft={editingSearch}
          suggestedName={suggestedSearchName()}
          readOnly={isRequestor}
          custodians={custodians}
          onClose={() => { setShowSearchModal(false); setEditingSearch(null) }}
          onSave={saveSearchDraft}
          searchQueryLabel={searchQueryLabel}
        />
      )}
    </>
  )
}
