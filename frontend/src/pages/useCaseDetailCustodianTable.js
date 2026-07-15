import { useCallback, useMemo, useState } from 'react'

const DEFAULT_FILTERS = {
  name: '',
  email: '',
  holds: 'all',
  ntp: 'all',
  consent: 'all',
}

function ntpRank(value) {
  const status = (value || 'not sent').toLowerCase()
  if (status === 'acknowledged') return 2
  if (status === 'sent') return 1
  if (status === 'na') return -1
  return 0
}

function consentRank(value) {
  return ({
    na: -1,
    'not sent': 0,
    sent: 1,
    received: 2,
  }[(value || 'not sent').toLowerCase()] ?? 0)
}

export function useCaseDetailCustodianTable({
  custodians,
  searches,
  requestEntries,
  isTech,
  techTicketCategorySet,
  normalizeEmail,
  hasAnyHold,
  holdMetaForView,
  holdState,
}) {
  const [showCustFilters, setShowCustFilters] = useState(false)
  const [custSort, setCustSort] = useState({ key: 'name', dir: 'asc' })
  const [badgeSort, setBadgeSort] = useState(null)
  const [custFilters, setCustFilters] = useState(DEFAULT_FILTERS)

  const progressFor = useCallback((custodianId, field) => {
    const custodianIdNumber = Number(custodianId)
    const relevant = (searches || []).filter(search => {
      const ids = (search.custodianIds ?? search.custodian_ids ?? []).map(Number)
      return ids.includes(custodianIdNumber)
    })
    const total = relevant.length
    if (!total) return { total: 0, done: 0, pct: 0 }
    const done = relevant.filter(search => {
      const value = String(
        search.status?.[field]
        ?? search['status_' + field]
        ?? 'not performed'
      ).toLowerCase()
      if (field === 'delivery') return value === 'performed' || value === 'not required'
      return value === 'performed'
    }).length
    return { total, done, pct: done / total }
  }, [searches])

  const techCustodianKeys = useMemo(() => {
    if (!isTech) return null
    const keys = new Set()
    const addKey = (id, email) => {
      if (Number.isFinite(Number(id))) keys.add('id:' + Number(id))
      const emailKey = normalizeEmail(email)
      if (emailKey) keys.add('email:' + emailKey)
    }

    ;(requestEntries || []).forEach(entry => {
      if (!entry || !techTicketCategorySet.has(entry.category)) return
      addKey(entry.custodian_id, entry.custodian_email)
      const bulk = Array.isArray(entry.bulk_custodians) ? entry.bulk_custodians : []
      bulk.forEach(item => {
        if (item) addKey(item.id, item.email)
      })
    })
    return keys
  }, [isTech, requestEntries, techTicketCategorySet, normalizeEmail])

  const hasStatusBadge = useCallback((custodian, label) => {
    const normalizedLabel = (label || '').toUpperCase()
    if (normalizedLabel === 'HOLD') {
      return (holdMetaForView || []).some(({ key }) => {
        const state = holdState(custodian, key)
        return !!(state.active || state.pending || state.failed)
      })
    }
    if (normalizedLabel === 'NTP') {
      return ['sent', 'acknowledged'].includes(custodian.ntp_status || 'not sent')
    }
    if (normalizedLabel === 'CONSENT') {
      return ['sent', 'received'].includes(custodian.consent_status || 'not sent')
    }
    if (normalizedLabel === 'SEARCH') return progressFor(custodian.id, 'search').total > 0
    if (normalizedLabel === 'EXPORT') return progressFor(custodian.id, 'export').total > 0
    if (normalizedLabel === 'DELIVERED') return progressFor(custodian.id, 'delivery').total > 0
    return false
  }, [holdMetaForView, holdState, progressFor])

  const visibleCustodians = useMemo(() => {
    let list = Array.isArray(custodians) ? [...custodians] : []
    if (isTech && techCustodianKeys) {
      list = list.filter(custodian => {
        const idKey = Number.isFinite(Number(custodian.id)) ? 'id:' + Number(custodian.id) : ''
        const emailKey = custodian.email ? 'email:' + normalizeEmail(custodian.email) : ''
        return (idKey && techCustodianKeys.has(idKey)) || (emailKey && techCustodianKeys.has(emailKey))
      })
    }

    if (custFilters.name.trim()) {
      const query = custFilters.name.toLowerCase()
      list = list.filter(custodian => (custodian.name || '').toLowerCase().includes(query))
    }
    if (custFilters.email.trim()) {
      const query = custFilters.email.toLowerCase()
      list = list.filter(custodian => (custodian.email || '').toLowerCase().includes(query))
    }
    if (custFilters.holds !== 'all') {
      const shouldHaveHold = custFilters.holds === 'has'
      list = list.filter(custodian => hasAnyHold(custodian) === shouldHaveHold)
    }
    if (!isTech && custFilters.ntp !== 'all') {
      const status = String(custFilters.ntp || '').toLowerCase()
      list = list.filter(custodian => String(custodian.ntp_status || 'not sent').toLowerCase() === status)
    }
    if (!isTech && custFilters.consent !== 'all') {
      const status = String(custFilters.consent || '').toLowerCase()
      list = list.filter(custodian => String(custodian.consent_status || 'not sent').toLowerCase() === status)
    }

    const direction = custSort.dir === 'desc' ? -1 : 1
    list.sort((left, right) => {
      if (badgeSort) {
        const leftMatch = hasStatusBadge(left, badgeSort) ? 0 : 1
        const rightMatch = hasStatusBadge(right, badgeSort) ? 0 : 1
        if (leftMatch !== rightMatch) return leftMatch - rightMatch
      }

      const sortKey = isTech && ['ntp', 'consent'].includes(custSort.key) ? 'name' : custSort.key
      let leftValue
      let rightValue
      switch (sortKey) {
        case 'name':
          leftValue = (left.name || '').toLowerCase()
          rightValue = (right.name || '').toLowerCase()
          break
        case 'email':
          leftValue = (left.email || '').toLowerCase()
          rightValue = (right.email || '').toLowerCase()
          break
        case 'holds':
          leftValue = hasAnyHold(left) ? 1 : 0
          rightValue = hasAnyHold(right) ? 1 : 0
          break
        case 'ntp':
          leftValue = ntpRank(left.ntp_status)
          rightValue = ntpRank(right.ntp_status)
          break
        case 'consent':
          leftValue = consentRank(left.consent_status)
          rightValue = consentRank(right.consent_status)
          break
        default:
          leftValue = 0
          rightValue = 0
      }
      if (leftValue < rightValue) return -1 * direction
      if (leftValue > rightValue) return direction
      return 0
    })
    return list
  }, [
    custodians,
    custFilters,
    custSort,
    badgeSort,
    isTech,
    techCustodianKeys,
    normalizeEmail,
    hasAnyHold,
    hasStatusBadge,
  ])

  const toggleSort = useCallback((key) => {
    setCustSort(previous => (
      previous.key === key
        ? { ...previous, dir: previous.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: 'asc' }
    ))
  }, [])

  const resetFilters = useCallback(() => {
    setCustFilters({ ...DEFAULT_FILTERS })
    setCustSort({ key: 'name', dir: 'asc' })
  }, [])

  const onBadgeClick = useCallback((label) => {
    setBadgeSort(previous => (previous === label ? null : label))
  }, [])

  return {
    showCustFilters,
    setShowCustFilters,
    custFilters,
    setCustFilters,
    custSort,
    toggleSort,
    resetFilters,
    visibleCustodians,
    techCustodianKeys,
    progressFor,
    onBadgeClick,
    custodianCount: isTech ? visibleCustodians.length : (custodians || []).length,
    custodianColumnCount: isTech ? 3 : 7,
  }
}