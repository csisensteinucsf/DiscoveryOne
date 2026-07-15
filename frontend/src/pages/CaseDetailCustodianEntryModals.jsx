import { AddCustodiansModal, ImportCustodiansModal } from './CaseDetailCustodianModals.jsx'

export default function CaseDetailCustodianEntryModals({
  showCustodianModal,
  custodianModalMode,
  setShowCustodianModal,
  setCustodianModalMode,
  apiBase,
  employeeIdLabel,
  lookupInputPlaceholder,
  personLookupEnabled,
  importWorking,
  importDone,
  importTotal,
  setImportWorking,
  submitCustodianBatch,
  setCustodians,
  showToast,
  addCustodiansWorking,
  addCustodiansWorkingRef,
  setAddCustodiansWorking,
}) {
  if (!showCustodianModal) return null

  if (custodianModalMode === 'import') {
    return (
      <ImportCustodiansModal
        apiBase={apiBase}
        employeeIdLabel={employeeIdLabel}
        personLookupEnabled={personLookupEnabled}
        progress={{ working: importWorking, done: importDone, total: importTotal }}
        onClose={() => { setShowCustodianModal(false); setCustodianModalMode('add'); setImportWorking(false); }}
        onSwitchToAdd={() => setCustodianModalMode('add')}
        onImport={async (rows) => {
          setImportWorking(true)
          try {
            const result = await submitCustodianBatch(rows)
            if (result.created.length) setCustodians(prev => [...prev, ...result.created])
            const totalDup = result.localDuplicateCount + result.duplicateCount
            if (result.failedCount > 0) {
              const firstError = result.errors.find(Boolean)
              if (firstError) {
                showToast(`Imported ${result.createdCount} row${result.createdCount===1?'':'s'}, ${result.failedCount} failed. First error: ${firstError}`, { variant: 'error' })
              } else {
                showToast(`Imported ${result.createdCount} row${result.createdCount===1?'':'s'}, ${result.failedCount} failed.`, { variant: 'warn' })
              }
              if (totalDup > 0) showToast(`Skipped ${totalDup} duplicate${totalDup===1?'':'s'}`)
              return
            }
            showToast(`Imported ${result.createdCount} row${result.createdCount===1?'':'s'}${totalDup>0?`, skipped ${totalDup} duplicate${totalDup===1?'':'s'}`:''}`)
            setShowCustodianModal(false)
            setCustodianModalMode('add')
          } catch (e) {
            showToast(e?.message || 'Import failed.', { variant: 'error' })
          } finally {
            setImportWorking(false)
          }
        }}
      />
    )
  }

  return (
    <AddCustodiansModal
      apiBase={apiBase}
      employeeIdLabel={employeeIdLabel}
      lookupInputPlaceholder={lookupInputPlaceholder}
      personLookupEnabled={personLookupEnabled}
      saving={addCustodiansWorking}
      onClose={() => {
        if (addCustodiansWorkingRef.current) return
        setShowCustodianModal(false)
        setCustodianModalMode('add')
      }}
      onSwitchToImport={() => {
        if (addCustodiansWorkingRef.current) return
        setCustodianModalMode('import')
      }}
      onSave={async (rows) => {
        if (addCustodiansWorkingRef.current) return
        addCustodiansWorkingRef.current = true
        setAddCustodiansWorking(true)
        try {
          const result = await submitCustodianBatch(rows)
          if (result.created.length) setCustodians(prev => [...prev, ...result.created])
          const totalDup = result.localDuplicateCount + result.duplicateCount
          if (totalDup > 0) showToast(`Skipped ${totalDup} duplicate email${totalDup===1?'' : 's'}`)
          if (result.failedCount > 0) {
            const firstError = result.errors.find(Boolean)
            if (firstError) {
              showToast(`Added ${result.createdCount} custodian${result.createdCount===1?'' : 's'}, ${result.failedCount} failed. First error: ${firstError}`, { variant: 'error' })
            } else {
              showToast(`Added ${result.createdCount} custodian${result.createdCount===1?'' : 's'}, ${result.failedCount} failed.`, { variant: 'warn' })
            }
            return
          }
          setShowCustodianModal(false)
          setCustodianModalMode('add')
        } catch (e) {
          showToast(e?.message || 'Failed to add custodians.', { variant: 'error' })
        } finally {
          addCustodiansWorkingRef.current = false
          setAddCustodiansWorking(false)
        }
      }}
    />
  )
}
