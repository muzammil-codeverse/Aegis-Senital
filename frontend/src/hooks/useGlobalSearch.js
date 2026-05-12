import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { getAlerts } from '../api/alertsApi'
import { getCameras } from '../api/camerasApi'
import { listCases } from '../api/caseApi'
import { listCorrelations } from '../api/droneFusionApi'
import { listMissions } from '../api/droneMissionApi'
import { getIdentityCandidates } from '../api/identityApi'
import { fetchGovernanceRegistry } from '../api/modelGovernanceApi'
import { listUploadedVideoSessions } from '../api/uploadedVideoApi'
import { getCommandPageMeta, getVisibleCommandNavigation } from '../navigation/commandNavigation'
import { useAuth } from './useAuth'

function includesQuery(value, query) {
  return String(value || '').toLowerCase().includes(query)
}

function makeRouteResult(item) {
  return {
    key: `route:${item.id}`,
    kind: 'route',
    label: item.label,
    description: item.description,
    route: item.id,
    meta: item.group,
  }
}

export function useGlobalSearch({ enabled, query }) {
  const auth = useAuth()
  const deferredQuery = useDeferredValue(query.trim().toLowerCase())
  const [sections, setSections] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const routeResults = useMemo(() => {
    const visible = getVisibleCommandNavigation(auth.hasPermission)
    const items = visible.flatMap(group => group.items.map(item => ({ ...item, group: group.group })))
    if (!deferredQuery) return items.map(makeRouteResult)
    return items
      .filter(item => includesQuery(item.label, deferredQuery) || includesQuery(item.description, deferredQuery) || includesQuery(item.id, deferredQuery))
      .map(makeRouteResult)
  }, [auth.hasPermission, deferredQuery])

  useEffect(() => {
    if (!enabled) return undefined
    let cancelled = false

    async function run() {
      setLoading(true)
      setError(null)
      const sectionsNext = []
      if (routeResults.length > 0) {
        sectionsNext.push({ title: 'Routes', items: routeResults.slice(0, 8) })
      }
      if (!deferredQuery) {
        startTransition(() => {
          if (!cancelled) {
            setSections(sectionsNext)
            setLoading(false)
          }
        })
        return
      }

      const tasks = []
      if (auth.hasPermission('case:read')) {
        tasks.push(
          listCases({ limit: 12 }).then(result => ({
            title: 'Cases',
            items: (result.items || [])
              .filter(item => includesQuery(item.case_id, deferredQuery) || includesQuery(item.title, deferredQuery) || includesQuery(item.description, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `case:${item.case_id}`,
                kind: 'case',
                label: item.title || item.case_id,
                description: item.description || 'Operator review required.',
                meta: item.case_id,
                route: 'cases',
                context: { caseId: item.case_id },
              })),
          })),
        )
      }
      if (auth.hasPermission('camera:read')) {
        tasks.push(
          getCameras().then(result => ({
            title: 'Cameras',
            items: (result.items || [])
              .filter(item => includesQuery(item.camera_id, deferredQuery) || includesQuery(item.display_name, deferredQuery) || includesQuery(item.location_name, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `camera:${item.camera_id}`,
                kind: 'camera',
                label: item.display_name || item.camera_id,
                description: item.location_name || item.status || 'Camera source',
                meta: item.camera_id,
                route: 'live-streams',
              })),
          })),
        )
      }
      if (auth.hasPermission('alert:read')) {
        tasks.push(
          getAlerts({ limit: 12 }).then(result => ({
            title: 'Alerts',
            items: (result.items || [])
              .filter(item => includesQuery(item.alert_id, deferredQuery) || includesQuery(item.title, deferredQuery) || includesQuery(item.description, deferredQuery) || includesQuery(item.severity, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `alert:${item.alert_id}`,
                kind: 'alert',
                label: item.title || item.alert_id,
                description: item.description || 'Operator review required.',
                meta: item.severity || 'alert',
                route: 'alerts',
              })),
          })),
        )
      }
      if (auth.hasPermission('uploaded_video:read')) {
        tasks.push(
          listUploadedVideoSessions().then(result => ({
            title: 'Uploaded Videos',
            items: (result.items || [])
              .filter(item => includesQuery(item.session_id, deferredQuery) || includesQuery(item.filename, deferredQuery) || includesQuery(item.status, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `video:${item.session_id}`,
                kind: 'uploaded_video',
                label: item.filename || item.session_id,
                description: item.status || 'Uploaded video session',
                meta: item.session_id,
                route: 'uploaded-video-analysis',
              })),
          })),
        )
      }
      if (auth.hasPermission('drone:read')) {
        tasks.push(
          listMissions({ limit: 12 }).then(result => ({
            title: 'Drone Missions',
            items: (result.items || [])
              .filter(item => includesQuery(item.mission_id, deferredQuery) || includesQuery(item.name, deferredQuery) || includesQuery(item.status, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `mission:${item.mission_id}`,
                kind: 'drone_mission',
                label: item.name || item.mission_id,
                description: `Simulated mission ${item.status || 'status unknown'}`,
                meta: item.mission_id,
                route: 'drone-operations',
              })),
          })),
        )
      }
      if (auth.hasPermission('drone_fusion:read')) {
        tasks.push(
          listCorrelations({ limit: 12 }).then(result => ({
            title: 'Fusion Correlations',
            items: (result.items || [])
              .filter(item => includesQuery(item.correlation_id, deferredQuery) || includesQuery(item.review_status, deferredQuery) || includesQuery(item.case_id, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `fusion:${item.correlation_id}`,
                kind: 'fusion',
                label: item.correlation_id,
                description: item.review_status || 'Candidate cross-source observation',
                meta: item.case_id || 'fusion',
                route: 'drone-fusion',
              })),
          })),
        )
      }
      if (auth.hasPermission('model:read')) {
        tasks.push(
          fetchGovernanceRegistry().then(result => ({
            title: 'Model Governance',
            items: (result.entries || [])
              .filter(item => includesQuery(item.model_id, deferredQuery) || includesQuery(item.name, deferredQuery) || includesQuery(item.status, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `model:${item.model_id}`,
                kind: 'model',
                label: item.name || item.model_id,
                description: item.status || 'Model governance entry',
                meta: item.model_id,
                route: 'model-governance',
              })),
          })),
        )
      }
      if (auth.hasPermission('identity:read')) {
        tasks.push(
          getIdentityCandidates({ limit: 12 }).then(result => ({
            title: 'Identity Candidates',
            items: (result.items || [])
              .filter(item => includesQuery(item.identity_candidate_id, deferredQuery) || includesQuery(item.display_name, deferredQuery) || includesQuery(item.review_status, deferredQuery))
              .slice(0, 6)
              .map(item => ({
                key: `identity:${item.identity_candidate_id}`,
                kind: 'identity_candidate',
                label: item.display_name || item.identity_candidate_id,
                description: item.review_status || 'Candidate identity requires operator review.',
                meta: item.identity_candidate_id,
                route: 'identities',
              })),
          })),
        )
      }

      const settled = await Promise.allSettled(tasks)
      for (const result of settled) {
        if (result.status === 'fulfilled' && result.value.items.length > 0) {
          sectionsNext.push(result.value)
        }
      }

      startTransition(() => {
        if (cancelled) return
        setSections(sectionsNext)
        setLoading(false)
      })
    }

    run().catch(err => {
      if (cancelled) return
      setError(err?.message || 'Search failed')
      setLoading(false)
    })

    return () => {
      cancelled = true
    }
  }, [auth.hasPermission, deferredQuery, enabled, routeResults])

  const flatResults = useMemo(() => sections.flatMap(section => section.items), [sections])

  function navigateForResult(result) {
    if (!result) return
    const meta = getCommandPageMeta(result.route)
    window.location.hash = meta.id === 'dashboard' ? '' : meta.id
  }

  return {
    sections,
    flatResults,
    loading,
    error,
    navigateForResult,
  }
}
