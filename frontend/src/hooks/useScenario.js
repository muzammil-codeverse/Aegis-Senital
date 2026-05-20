import { useCallback, useEffect, useState } from 'react'
import {
  cancelScenario,
  getActiveScenarioRun,
  getRunTimeline,
  listScenarios,
  pauseScenario,
  resetScenario,
  resumeScenario,
  startScenario,
  stepScenario,
} from '../api/scenarioApi'
import { normalizeError } from '../api/client'
import { useAuthGate } from './useAuthenticatedQuery'

const POLL_MS = 3000

export function useScenario({ enabled = true } = {}) {
  const gate = useAuthGate('system:read', { enabled })
  const [scenarios, setScenarios] = useState([])
  const [activeRun, setActiveRun] = useState(null)
  const [timeline, setTimeline] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [actionError, setActionError] = useState(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setScenarios([])
      setActiveRun(null)
      return
    }
    try {
      const [scenariosRes, runRes] = await Promise.all([
        listScenarios(),
        getActiveScenarioRun(),
      ])
      setScenarios(scenariosRes.items || [])
      setActiveRun(runRes.active_run || null)
      setError(null)
    } catch (err) {
      setError(normalizeError(err))
    } finally {
      setLoading(false)
    }
  }, [gate.enabled, gate.message, gate.reason])

  const refreshTimeline = useCallback(async () => {
    if (!gate.enabled) return
    try {
      const res = await getRunTimeline()
      setTimeline(res.items || [])
    } catch {
      // non-critical
    }
  }, [gate.enabled])

  useEffect(() => {
    const load = () => { refresh() }
    const initial = window.setTimeout(load, 0)
    const timer = gate.enabled ? window.setInterval(refresh, POLL_MS) : null
    return () => {
      window.clearTimeout(initial)
      if (timer) window.clearInterval(timer)
    }
  }, [gate.enabled, refresh])

  useEffect(() => {
    if (activeRun && (activeRun.state === 'running' || activeRun.state === 'paused')) {
      const load = () => { refreshTimeline() }
      const initial = window.setTimeout(load, 0)
      const timer = window.setInterval(refreshTimeline, POLL_MS)
      return () => {
        window.clearTimeout(initial)
        window.clearInterval(timer)
      }
    }
  }, [activeRun, refreshTimeline])

  const withAction = useCallback(async (fn) => {
    setActionLoading(true)
    setActionError(null)
    try {
      const result = await fn()
      await refresh()
      return result
    } catch (err) {
      setActionError(normalizeError(err))
      return null
    } finally {
      setActionLoading(false)
    }
  }, [refresh])

  const start = useCallback((scenarioId, mode = 'step') => {
    return withAction(() => startScenario({ scenarioId, mode }))
  }, [withAction])

  const step = useCallback(() => {
    return withAction(() => stepScenario())
  }, [withAction])

  const pause = useCallback(() => {
    return withAction(() => pauseScenario())
  }, [withAction])

  const resume = useCallback(() => {
    return withAction(() => resumeScenario())
  }, [withAction])

  const cancel = useCallback(() => {
    return withAction(() => cancelScenario())
  }, [withAction])

  const reset = useCallback(() => {
    return withAction(async () => {
      await resetScenario()
      setTimeline([])
    })
  }, [withAction])

  return {
    scenarios,
    activeRun,
    timeline,
    loading,
    error,
    actionLoading,
    actionError,
    authGate: gate,
    refresh,
    start,
    step,
    pause,
    resume,
    cancel,
    reset,
  }
}
