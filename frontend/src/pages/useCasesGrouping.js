import { useEffect, useMemo, useState } from 'react'
import { firstToken, toSentenceCase } from './casesUtils.js'

const STORAGE_KEYS = {
  yearsOpen: 'cases:years:open',
  yearsClosed: 'cases:years:closed',
  lettersOpen: 'cases:letters:open',
  lettersClosed: 'cases:letters:closed',
  groupCases: 'cases:group-by-year',
}

const loadSet = (key) => {
  if (typeof window === 'undefined') return new Set()
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    return new Set(Array.isArray(arr) ? arr : [])
  } catch {
    return new Set()
  }
}

const persistSet = (key, set) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(Array.from(set)))
  } catch {
    // Best-effort preference persistence.
  }
}

const loadBoolean = (key, fallback = false) => {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    return raw === null ? fallback : raw === 'true'
  } catch {
    return fallback
  }
}

export function useCasesGrouping({ openCases, closedCases, stats, analysts, analystsById, caseSortMode }) {
  const [groupCases, setGroupCases] = useState(() => loadBoolean(STORAGE_KEYS.groupCases, false))
  const [caseSort, setCaseSort] = useState({ key: 'created', dir: 'desc' })
  const [caseFilters, setCaseFilters] = useState({
    name: '',
    legal: '',
    analyst: '',
    requestor: '',
    matter: '',
    counsel: '',
    notes: '',
  })

  const resetCaseFilters = () => {
    setCaseFilters({ name: '', legal: '', analyst: '', requestor: '', matter: '', counsel: '', notes: '' })
    setCaseSort({ key: 'created', dir: 'desc' })
  }

  const toggleSort = (key) => {
    setCaseSort(current => ({
      key,
      dir: current.key === key && current.dir === 'asc' ? 'desc' : 'asc',
    }))
  }

  const analystName = (id) => analystsById.get(id) || ''
  const analystFirstName = (id) => {
    const person = (analysts || []).find(a => String(a.id) === String(id))
    const first = toSentenceCase(person?.first_name)
    if (first) return first
    const fromUsername = firstToken(person?.username || '')
    if (fromUsername) return toSentenceCase(fromUsername)
    const fallback = firstToken(person?.email || analystName(id))
    return toSentenceCase(fallback)
  }

  const applyFiltersSort = (list) => {
    const filters = caseFilters
    const arr = [...list].filter(c => {
      const name = (c.name || '').toLowerCase()
      const legal = (c.legal_case_name || '').toLowerCase()
      const requestorEmails = Array.isArray(c.requestors)
        ? c.requestors.map(r => (r?.email || '').toLowerCase()).filter(Boolean)
        : []
      const allRequestors = [c.requestor || '', ...requestorEmails].map(value => value.toLowerCase())

      const nameHit = (filters.name || '').trim()
        ? (name.includes(filters.name.toLowerCase()) || legal.includes(filters.name.toLowerCase()))
        : true
      const legalHit = (filters.legal || '').trim()
        ? legal.includes(filters.legal.toLowerCase())
        : true
      const analystHit = (filters.analyst || '').trim()
        ? analystName(c.analyst_id).toLowerCase().includes(filters.analyst.toLowerCase())
        : true
      const requestorHit = (filters.requestor || '').trim()
        ? allRequestors.some(email => email.includes(filters.requestor.toLowerCase()))
        : true
      const matterHit = (filters.matter || '').trim()
        ? (c.matter_number || c.servicenow_inc_number || '').toLowerCase().includes(filters.matter.toLowerCase())
        : true
      const counselHit = (filters.counsel || '').trim()
        ? (c.internal_counsel || c.uc_attorney || c.attorney || c.ler_representative || '').toLowerCase().includes(filters.counsel.toLowerCase())
        : true
      const notesHit = (filters.notes || '').trim()
        ? (c.description || '').toLowerCase().includes(filters.notes.toLowerCase())
        : true

      return nameHit && legalHit && analystHit && requestorHit && matterHit && counselHit && notesHit
    })

    const key = caseSort.key
    const direction = caseSort.dir === 'desc' ? -1 : 1
    const getValue = (c) => {
      if (key === 'name') return (c.name || c.legal_case_name || '').toLowerCase()
      if (key === 'legal') return (c.legal_case_name || '').toLowerCase()
      if (key === 'analyst') return analystName(c.analyst_id).toLowerCase()
      if (key === 'requestor') return (c.requestor || '').toLowerCase()
      if (key === 'created') return Date.parse(c.created_at || '') || 0
      if (key === 'start') return Date.parse(c.start_date || '') || 0
      if (key === 'updated') return Date.parse(c.updated_at || c.created_at || '') || 0
      if (key === 'attorney') {
        return (c.internal_counsel || c.uc_attorney || c.attorney || c.ler_representative || '').toLowerCase()
      }
      if (key === 'matter') return (c.matter_number || c.servicenow_inc_number || '').toLowerCase()
      if (key === 'notes') return (c.description || '').toLowerCase()
      if (key === 'hold') {
        const caseStats = stats[String(c.id)] || stats[c.id] || {}
        return Number(caseStats.namedHoldCount ?? caseStats.holdCount ?? caseStats.hold ?? 0)
      }
      return (c.name || '').toLowerCase()
    }

    arr.sort((a, b) => {
      const aValue = getValue(a)
      const bValue = getValue(b)
      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return (aValue - bValue) * direction
      }
      return String(aValue).localeCompare(String(bValue), undefined, {
        numeric: true,
        sensitivity: 'base',
      }) * direction
    })

    return arr
  }

  const getYear = (c) => {
    const match = (c.name || '').match(/^\s*(\d{4})/)
    if (match) return Number(match[1])
    const created = new Date(c.created_at || '')
    return Number.isNaN(created.getTime()) ? new Date().getFullYear() : created.getFullYear()
  }

  const sortLabel = (c) => {
    const name = (c?.name || '').trim()
    const legal = (c?.legal_case_name || '').trim()
    if (caseSortMode === 'legal') return legal || name
    return name
  }

  const getLetter = (c) => {
    const label = sortLabel(c)
    let remainder = label
    if (caseSortMode !== 'legal') {
      remainder = label.replace(/^\s*\d{4}[-\s]?/, '').trim()
      if (!remainder) remainder = label
    }
    const ch = (remainder[0] || '#').toUpperCase()
    return ch.match(/[A-Z]/) ? ch : '#'
  }

  const groupByYear = (list) => {
    const map = new Map()
    for (const c of list) {
      const year = getYear(c)
      const letter = getLetter(c)
      if (!map.has(year)) map.set(year, new Map())
      const letterMap = map.get(year)
      if (!letterMap.has(letter)) letterMap.set(letter, [])
      letterMap.get(letter).push(c)
    }
    const years = Array.from(map.keys()).sort((a, b) => (b || 0) - (a || 0))
    return years.map(year => {
      const letterMap = map.get(year)
      const letters = Array.from(letterMap.keys()).sort().map(letter => ({
        letter,
        items: letterMap.get(letter),
      }))
      const total = letters.reduce((sum, group) => sum + group.items.length, 0)
      return { year, letters, total }
    })
  }

  const [expandedYearsOpen, setExpandedYearsOpen] = useState(() => loadSet(STORAGE_KEYS.yearsOpen))
  const [expandedYearsClosed, setExpandedYearsClosed] = useState(() => loadSet(STORAGE_KEYS.yearsClosed))
  const [expandedLettersOpen, setExpandedLettersOpen] = useState(() => loadSet(STORAGE_KEYS.lettersOpen))
  const [expandedLettersClosed, setExpandedLettersClosed] = useState(() => loadSet(STORAGE_KEYS.lettersClosed))

  useEffect(() => { persistSet(STORAGE_KEYS.yearsOpen, expandedYearsOpen) }, [expandedYearsOpen])
  useEffect(() => { persistSet(STORAGE_KEYS.yearsClosed, expandedYearsClosed) }, [expandedYearsClosed])
  useEffect(() => { persistSet(STORAGE_KEYS.lettersOpen, expandedLettersOpen) }, [expandedLettersOpen])
  useEffect(() => { persistSet(STORAGE_KEYS.lettersClosed, expandedLettersClosed) }, [expandedLettersClosed])
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEYS.groupCases, String(groupCases))
    } catch {
      // Best-effort preference persistence.
    }
  }, [groupCases])

  const toggleYear = (which, year) => {
    const key = String(year)
    const update = which === 'open' ? setExpandedYearsOpen : setExpandedYearsClosed
    update(previous => {
      const next = new Set(previous)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const letterKey = (year, letter) => `${year}:${letter}`

  const toggleLetter = (which, year, letter) => {
    const key = letterKey(year, letter)
    const update = which === 'open' ? setExpandedLettersOpen : setExpandedLettersClosed
    update(previous => {
      const next = new Set(previous)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const openFiltered = useMemo(
    () => applyFiltersSort(openCases),
    [openCases, stats, caseFilters, caseSort, analysts, analystsById],
  )
  const closedFiltered = useMemo(
    () => applyFiltersSort(closedCases),
    [closedCases, stats, caseFilters, caseSort, analysts, analystsById],
  )
  const openGroups = useMemo(() => groupByYear(openFiltered), [openFiltered, caseSortMode])
  const closedGroups = useMemo(() => groupByYear(closedFiltered), [closedFiltered, caseSortMode])

  return {
    groupCases,
    setGroupCases,
    caseSort,
    setCaseSort,
    toggleSort,
    caseFilters,
    setCaseFilters,
    resetCaseFilters,
    analystFirstName,
    expandedYearsOpen,
    expandedYearsClosed,
    expandedLettersOpen,
    expandedLettersClosed,
    toggleYear,
    toggleLetter,
    letterKey,
    openFiltered,
    closedFiltered,
    openGroups,
    closedGroups,
  }
}