export default function CaseDetailHoldSelector({
  holds,
  selectedHoldId,
  onSelect,
  ariaLabel = 'Select a Hold',
}) {
  const holdList = Array.isArray(holds) ? holds : []
  if (holdList.length < 2) return null

  return (
    <div className="case-detail-hold-selector" role="group" aria-label={ariaLabel}>
      {holdList.map((hold, index) => {
        const holdId = String(hold.id)
        const isSelected = holdId === String(selectedHoldId)
        return (
          <button
            key={holdId}
            type="button"
            className={'case-detail-hold-selector__button' + (isSelected ? ' is-active' : '')}
            aria-pressed={isSelected}
            onClick={() => onSelect(hold.id)}
          >
            {hold.name || 'Hold ' + (index + 1)}
          </button>
        )
      })}
    </div>
  )
}
