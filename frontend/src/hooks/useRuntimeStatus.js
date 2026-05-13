import { startTransition, useCallback, useEffect, useState } from 'react'
import { getFusionHealth } from '../api/droneFusionApi'
import { listMissions } from '../api/droneMissionApi'
import { droneSimulationApi } from '../api/droneSimulationApi'
import { getGisConfig } from '../api/gisApi'
import { investigationApi } from '../api/investigationApi'
import { getLlmStatus } from '../api/llmApi'
import { getSystemHealth } from '../api/metricsApi'
import { fetchGovernanceLimitations, fetchPromotionPolicy } from '../api/modelGovernanceApi'
import { normalizeRuntimeTone } from '../styles/commandCenterTheme'
import { useAuth } from './useAuth'

function section(key, label, status, summary, extra = {}) {
  return {
    key,
    label,
    status: normalizeRuntimeTone(status),
    summary,
    ...extra,
  }
}

function sectionFromHealthCheck(key, label, check) {
  if (!check) return section(key, label, 'unknown', 'No health data reported')
  return section(key, label, check.status || check.state || 'unknown', check.detail || check.message || label)
}

function statusWeight(status) {
  if (status === 'critical') return 3
  if (status === 'degraded') return 2
  if (status === 'ok') return 1
  return 0
}

function sectionFromApiError(key, label, error, networkAsCritical = false) {
  const status = error?.status
  if (status === 401) return section(key, label, 'degraded', 'Please sign in to view this subsystem')
  if (status === 403) return section(key, label, 'degraded', 'Access denied for this subsystem')
  if (status === 404) return section(key, label, 'degraded', 'Subsystem endpoint unavailable in this build')
  if (status === 503) return section(key, label, 'degraded', 'Subsystem reported degraded readiness')
  if (!status) return section(key, label, networkAsCritical ? 'critical' : 'degraded', 'Backend unavailable')
  return section(key, label, 'critical', error?.message || `${label} unavailable`)
}

export function useRuntimeStatus({ pollMs = 20000 } = {}) {
  const auth = useAuth()
  const [state, setState] = useState({
    loading: true,
    error: null,
    overall: 'unknown',
    generatedAt: null,
    byKey: {},
    items: [],
  })

  const refresh = useCallback(async () => {
    if (!auth.authenticated) {
      setState({
        loading: false,
        error: null,
        overall: 'unknown',
        generatedAt: Date.now(),
        byKey: {},
        items: [],
      })
      return
    }
    const sections = []
    try {
      const system = await getSystemHealth()
      sections.push(section('system', 'Backend', system.status || 'unknown', system.error || 'Backend health'))
      sections.push(sectionFromHealthCheck('database', 'Database', system.checks?.database))
      sections.push(sectionFromHealthCheck('redis', 'Redis', system.checks?.redis))

      if (auth.hasPermission('gis:read')) {
        try {
          const gis = await getGisConfig()
          const item = gis.item || {}
          sections.push(section('gis', 'GIS', 'ok', item.provider || item.detail || 'GIS provider configured'))
        } catch (error) {
          sections.push(sectionFromApiError('gis', 'GIS', error))
        }
      }

      if (auth.hasPermission('drone:read')) {
        try {
          const drone = await droneSimulationApi.getStatus()
          const item = drone.item || {}
          sections.push(section(
            'droneSimulation',
            'Drone Simulation',
            item?.health?.status || item?.status || (item?.active_session ? 'active' : 'unknown'),
            item?.detail || item?.health?.detail || (item?.active_session ? 'Simulated session active' : 'Simulator reachable'),
          ))
        } catch (error) {
          sections.push(sectionFromApiError('droneSimulation', 'Drone Simulation', error))
        }
        try {
          const missions = await listMissions({ limit: 20 })
          const active = (missions.items || []).filter(item => ['executing', 'paused', 'approved'].includes(String(item.status || '').toLowerCase()))
          sections.push(section(
            'droneMission',
            'Drone Mission',
            active.length > 0 ? 'ok' : 'degraded',
            active.length > 0 ? `${active.length} simulated mission(s) active or staged` : 'No active simulated mission session exposed',
            { count: active.length },
          ))
        } catch (error) {
          sections.push(sectionFromApiError('droneMission', 'Drone Mission', error))
        }
      }

      if (auth.hasPermission('drone_fusion:read')) {
        try {
          const fusion = await getFusionHealth()
          const item = fusion.item || {}
          sections.push(section(
            'droneFusion',
            'Drone Fusion',
            item.status || item.health || 'ok',
            item.detail || item.message || 'Fusion service reachable',
          ))
        } catch (error) {
          sections.push(sectionFromApiError('droneFusion', 'Drone Fusion', error))
        }
      }

      if (auth.hasPermission('investigation:read')) {
        try {
          const investigation = await investigationApi.listHypotheses({ limit: 10 })
          const pending = (investigation.items || []).filter(item => String(item.review_status || 'pending').toLowerCase() === 'pending')
          sections.push(section(
            'investigation',
            'Investigation',
            'ok',
            pending.length > 0 ? `${pending.length} evidence-backed hypothesis review item(s)` : 'No pending hypothesis reviews',
            { count: pending.length },
          ))
        } catch (error) {
          sections.push(sectionFromApiError('investigation', 'Investigation', error))
        }
      }

      if (auth.hasPermission('model:read')) {
        try {
          const [policy, limitations] = await Promise.all([
            fetchPromotionPolicy(),
            fetchGovernanceLimitations(),
          ])
          const limitationItems = limitations.limitations || []
          const blocking = limitationItems.filter(item => item?.severity === 'high' || item?.status === 'blocked')
          const fileWritesEnabled = policy?.promotion_policy?.enable_file_writes !== false
          sections.push(section(
            'modelGovernance',
            'Model Governance',
            blocking.length > 0 || !fileWritesEnabled ? 'degraded' : 'ok',
            !fileWritesEnabled
              ? 'Promotion disabled while file writes are locked'
              : blocking.length > 0
                ? `${blocking.length} governance blocker(s) require review`
                : 'Governance checks available',
            { count: blocking.length },
          ))
        } catch (error) {
          sections.push(sectionFromApiError('modelGovernance', 'Model Governance', error))
        }
      }

      if (auth.hasPermission('llm:read')) {
        try {
          const llm = await getLlmStatus()
          const item = llm.item || {}
          sections.push(section(
            'llm',
            'OpenAI / LLM',
            item.status || 'unknown',
            item.detail || item.active_provider || 'LLM status available',
          ))
        } catch (error) {
          sections.push(sectionFromApiError('llm', 'OpenAI / LLM', error))
        }
      }

      const overall = sections.reduce((worst, item) => {
        return statusWeight(item.status) > statusWeight(worst) ? item.status : worst
      }, 'ok')

      startTransition(() => {
        setState({
          loading: false,
          error: null,
          overall,
          generatedAt: Date.now(),
          byKey: Object.fromEntries(sections.map(item => [item.key, item])),
          items: sections,
        })
      })
    } catch (error) {
      setState(current => ({
        ...current,
        loading: false,
        error: error?.status === 401 ? 'Please sign in.' : (error?.message || 'Unable to load runtime status'),
      }))
    }
  }, [auth.authenticated, auth.hasPermission])

  useEffect(() => {
    if (!auth.authenticated) return undefined
    refresh()
    const timer = window.setInterval(refresh, pollMs)
    return () => window.clearInterval(timer)
  }, [auth.authenticated, pollMs, refresh])

  return {
    ...state,
    refresh,
  }
}
