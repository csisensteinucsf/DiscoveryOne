import { AddCustodiansModal, ImportCustodiansModal } from './CaseDetailCustodianModals.jsx'
import SelectD1CustodiansModal from './SelectD1CustodiansModal.jsx'

export default function CaseDetailCustodianEntryModals({
  showCustodianModal,
  custodianModalMode,
  setShowCustodianModal,
  setCustodianModalMode,
  apiBase,
  caseId,
  namedHolds,
  targetHoldIds,
  setTargetHoldIds,
  reloadNamedHolds,
  employeeIdLabel,
  lookupInputPlaceholder,
  personLookupEnabled,
  importWorking,
  importDone,
  importTotal,
  setImportWorking,
  submitCustodianBatch,
  setCustodians,
  custodians,
  showToast,
  addCustodiansWorking,
  addCustodiansWorkingRef,
  setAddCustodiansWorking,
}) {
  if (!showCustodianModal) return null


  if (custodianModalMode === 'directory') {
    return (
      <SelectD1CustodiansModal
        apiBase={apiBase}
        caseId={caseId}
        holds={namedHolds}
        selectedHoldIds={targetHoldIds}
        onSelectedHoldIdsChange={setTargetHoldIds}
        onHoldCreated={reloadNamedHolds}
        existingCustodians={custodians}
        saving={addCustodiansWorking}
        onClose={() => {
          if (addCustodiansWorkingRef.current) return
          setShowCustodianModal(false)
          setCustodianModalMode('add')
        }}
        onSwitchToAdd={() => setCustodianModalMode('add')}
        onSwitchToImport={() => setCustodianModalMode('import')}
        onSave={async rows => {
          if (addCustodiansWorkingRef.current) return
          addCustodiansWorkingRef.current = true
          setAddCustodiansWorking(true)
          try {
            const result = await submitCustodianBatch(rows)
            if (result.created.length) {
              setCustodians(previous => [...previous, ...result.created])
              await reloadNamedHolds?.()
            }
            const totalDuplicates = result.localDuplicateCount + result.duplicateCount
            if (result.failedCount > 0) {
              const firstError = result.errors.find(Boolean)
              showToast(firstError || 'One or more selected custodians could not be added.', { variant: 'error' })
              return
            }
            showToast(`Added ${result.createdCount} custodian${result.createdCount === 1 ? '' : 's'}${totalDuplicates ? `; skipped ${totalDuplicates} duplicate${totalDuplicates === 1 ? '' : 's'}` : ''}.`)
            setShowCustodianModal(false)
            setCustodianModalMode('add')
          } catch (error) {
            showToast(error?.message || 'Failed to add selected custodians.', { variant: 'error' })
          } finally {
            addCustodiansWorkingRef.current = false
            setAddCustodiansWorking(false)
          }
        }}
      />
    )
  }

  if (custodianModalMode === 'import') {
    return (
      <ImportCustodiansModal
        apiBase={apiBase}
        caseId={caseId}
        holds={namedHolds}
        selectedHoldIds={targetHoldIds}
        onSelectedHoldIdsChange={setTargetHoldIds}
        onHoldCreated={reloadNamedHolds}
        employeeIdLabel={employeeIdLabel}
        personLookupEnabled={personLookupEnabled}
        progress={{ working: importWorking, done: importDone, total: importTotal }}
        onClose={() => { setShowCustodianModal(false); setCustodianModalMode('add'); setImportWorking(false); }}
        onSwitchToAdd={() => setCustodianModalMode('add')}
        onSwitchToDirectory={() => setCustodianModalMode('directory')}
        onImport={async (rows) => {
          setImportWorking(true)
          try {
            const result = await submitCustodianBatch(rows)
            if (result.created.length) {
              setCustodians(prev => [...prev, ...result.created])
              await reloadNamedHolds?.()
            }
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
      caseId={caseId}
      holds={namedHolds}
      selectedHoldIds={targetHoldIds}
      onSelectedHoldIdsChange={setTargetHoldIds}
      onHoldCreated={reloadNamedHolds}
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
      onSwitchToDirectory={() => {
        if (addCustodiansWorkingRef.current) return
        setCustodianModalMode('directory')
      }}
      onSave={async (rows) => {
        if (addCustodiansWorkingRef.current) return
        addCustodiansWorkingRef.current = true
        setAddCustodiansWorking(true)
        try {
          const result = await submitCustodianBatch(rows)
          if (result.created.length) {
            setCustodians(prev => [...prev, ...result.created])
            await reloadNamedHolds?.()
          }
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
