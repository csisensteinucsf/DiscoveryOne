import { useSearchExportPush } from './useSearchExportPush.js'

// Compatibility wrapper for extensions that still import the legacy hook name.
export function usePurviewSearchPush(args) {
  const {
    searchExportModal,
    closeSearchExportModal,
    pushSearchToProvider,
  } = useSearchExportPush({
    ...args,
    provider: 'purview',
    providerLabel: 'Microsoft Purview',
  })
  return {
    purviewPushModal: searchExportModal,
    closePurviewPushModal: closeSearchExportModal,
    pushSearchToPurview: pushSearchToProvider,
  }
}