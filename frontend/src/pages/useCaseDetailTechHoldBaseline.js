import { useCallback, useContext, useEffect, useRef } from 'react'
import { UNSAFE_NavigationContext } from 'react-router-dom'
import { customPreservationEntry, isCustomHoldKey } from './caseDetailUtils.js'

const HOLD_LEAVE_MESSAGE = 'These edits are not saved. Are you sure you want to leave the page?'

export function useCaseDetailTechHoldBaseline({
  custodians,
  isTech,
  holdKeysForTech,
  setHoldsDirty,
  holdsDirty,
}) {
  const holdsBaselineReady = useRef(false)
  const savedHoldMap = useRef(new Map())
  const { navigator } = useContext(UNSAFE_NavigationContext)

  const buildHoldState = useCallback((custodian) => {
    const state = {}
    holdKeysForTech.forEach((key) => {
      if (isCustomHoldKey(key)) {
        const entry = customPreservationEntry(custodian, key)
        state[key] = !!entry?.active
        state[`${key}_pending`] = !!entry?.pending
        state[`${key}_failed`] = !!entry?.failed
        state[`${key}_released`] = !!entry?.released
      } else {
        state[key] = !!custodian?.[key]
        state[`${key}_pending`] = !!custodian?.[`${key}_pending`]
        state[`${key}_failed`] = !!custodian?.[`${key}_failed`]
        state[`${key}_released`] = !!custodian?.[`${key}_released`]
      }
    })
    return state
  }, [holdKeysForTech])

  const setHoldBaseline = useCallback((list) => {
    if (!isTech) return
    const next = new Map()
    ;(list || []).forEach((custodian) => {
      next.set(custodian.id, buildHoldState(custodian))
    })
    savedHoldMap.current = next
    holdsBaselineReady.current = true
    setHoldsDirty(false)
  }, [buildHoldState, isTech, setHoldsDirty])

  const hasHoldChanges = useCallback((list) => {
    if (!isTech) return false
    const baseline = savedHoldMap.current
    for (const custodian of (list || [])) {
      const base = baseline.get(custodian.id) || {}
      for (const key of holdKeysForTech) {
        const state = isCustomHoldKey(key)
          ? {
              [key]: !!customPreservationEntry(custodian, key)?.active,
              [`${key}_pending`]: !!customPreservationEntry(custodian, key)?.pending,
              [`${key}_failed`]: !!customPreservationEntry(custodian, key)?.failed,
              [`${key}_released`]: !!customPreservationEntry(custodian, key)?.released,
            }
          : {
              [key]: !!custodian?.[key],
              [`${key}_pending`]: !!custodian?.[`${key}_pending`],
              [`${key}_failed`]: !!custodian?.[`${key}_failed`],
              [`${key}_released`]: !!custodian?.[`${key}_released`],
            }
        if (!!state[key] !== !!base[key]) return true
        if (!!state[`${key}_pending`] !== !!base[`${key}_pending`]) return true
        if (!!state[`${key}_failed`] !== !!base[`${key}_failed`]) return true
        if (!!state[`${key}_released`] !== !!base[`${key}_released`]) return true
      }
    }
    return false
  }, [holdKeysForTech, isTech])

  useEffect(() => {
    if (!isTech) return
    if (!holdsBaselineReady.current) {
      setHoldBaseline(custodians)
      return
    }
    setHoldsDirty(hasHoldChanges(custodians))
  }, [custodians, hasHoldChanges, isTech, setHoldBaseline, setHoldsDirty])

  useEffect(() => {
    if (!isTech || !holdsDirty) return
    const handler = (event) => {
      event.preventDefault()
      event.returnValue = HOLD_LEAVE_MESSAGE
      return HOLD_LEAVE_MESSAGE
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [holdsDirty, isTech])

  useEffect(() => {
    if (!isTech || !holdsDirty) return
    if (!navigator?.block) return
    const unblock = navigator.block((tx) => {
      const ok = window.confirm(HOLD_LEAVE_MESSAGE)
      if (ok) {
        unblock()
        tx.retry()
      }
    })
    return unblock
  }, [holdsDirty, isTech, navigator])

  return { buildHoldState, setHoldBaseline, savedHoldMap, holdsBaselineReady }
}