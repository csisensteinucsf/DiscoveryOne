import { useEffect, useMemo, useState } from 'react'
import { firstToken, toSentenceCase } from './casesUtils.js'

const STORAGE_KEYS = {
  yearsOpen: 'cases:years:open',
  yearsClosed: 'cases:years:closed',
  lettersOpen: 'cases:letters:open',
  lettersClosed: 'cases:letters:closed',
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

export function useCasesGrouping({ openCases, closedCases, stats, analysts, analystsById, caseSortMode }) {
  const [showFilters, setShowFilters] = useState(false)
  const [caseSort, setCaseSort] = useState({ key: 'name', dir: 'asc' })
  const [caseFilters, setCaseFilters] = useState({
    name: '',
    legal: '',
    analyst: '',
    requestor: '',
  })

  const resetCaseFilters = () => {
    setCaseFilters({ name: '', legal: '', analyst: '', requestor: '' })
    setCaseSort({ key: 'name', dir: 'asc' })
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
    let arr = [...list].filter(c => {
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

      return nameHit && legalHit && analystHit && requestorHit
    })

    const key = caseSort.key
    const direction = caseSort.dir === 'desc' ? -1 : 1
    const getValue = (c) => {
      if (key === 'name') return (c.name || '').toLowerCase()
      if (key === 'legal') return (c.legal_case_name || '').toLowerCase()
      if (key === 'analyst') return analystName(c.analyst_id).toLowerCase()
      if (key === 'requestor') return (c.requestor || '').toLowerCase()
      if (key === 'created') return new Date(c.created_at || 0).getTime()
      return (c.name || '').toLowerCase()
    }
    arr.sort((a, b) => (getValue(a) < getValue(b) ? -1 : getValue(a) > getValue(b) ? 1 : 0) * direction)

    return arr
  }

  const getYear = (c) => {
    const match = (c.name || '').match(/^\s*(\d{4})/)
    if (match) return Number(match[1])
    try {
      return new Date(c.created_at).getFullYear()
    } catch {
      return new Date().getFullYear()
    }
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
      const keyOf = (c) => (sortLabel(c) || '').toLowerCase()
      const letters = Array.from(letterMap.keys()).sort().map(letter => ({
        letter,
        items: letterMap.get(letter).sort((a, b) => keyOf(a).localeCompare(keyOf(b))),
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

  const toggleYear = (which, year) => {
    const key = String(year)
    if (which === 'open') {
      setExpandedYearsOpen(prev => {
        const next = new Set(prev)
        next.has(key) ? next.delete(key) : next.add(key)
        return next
      })
    } else {
      setExpandedYearsClosed(prev => {
        const next = new Set(prev)
        next.has(key) ? next.delete(key) : next.add(key)
        return next
      })
    }
  }

  const letterKey = (year, letter) => `${year}:${letter}`

  const toggleLetter = (which, year, letter) => {
    const key = letterKey(year, letter)
    if (which === 'open') {
      setExpandedLettersOpen(prev => {
        const next = new Set(prev)
        next.has(key) ? next.delete(key) : next.add(key)
        return next
      })
    } else {
      setExpandedLettersClosed(prev => {
        const next = new Set(prev)
        next.has(key) ? next.delete(key) : next.add(key)
        return next
      })
    }
  }

  const openFiltered = useMemo(() => applyFiltersSort(openCases), [openCases, stats, caseFilters, caseSort, analysts])
  const closedFiltered = useMemo(() => applyFiltersSort(closedCases), [closedCases, stats, caseFilters, caseSort, analysts])
  const openGroups = useMemo(() => groupByYear(openFiltered), [openFiltered])
  const closedGroups = useMemo(() => groupByYear(closedFiltered), [closedFiltered])

  return {
    showFilters,
    setShowFilters,
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
    openGroups,
    closedGroups,
  }
}
