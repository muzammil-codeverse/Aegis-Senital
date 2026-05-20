import { useCallback, useEffect, useState } from 'react'
import { getSimulationDashboardFeeds, getSimulationDrones } from '../api/simulationApi'
import { listVisualCameras, snapshotImageUrl } from '../api/visualScenarioApi'
import { normalizeError } from '../api/client'
import { DASHBOARD_POLL_MS } from '../config'
import { useAuthGate } from './useAuthenticatedQuery'

export function useSimulationSources({ pollMs = DASHBOARD_POLL_MS, enabled = true } = {}) {
  const gate = useAuthGate('system:read', { enabled })
  const [cameras, setCameras] = useState([])
  const [drones, setDrones] = useState([])
  const [visualCameras, setVisualCameras] = useState([])
  const [snapshotCount, setSnapshotCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!gate.enabled) {
      setLoading(gate.reason === 'checking')
      setError(gate.reason && gate.reason !== 'disabled' && gate.reason !== 'checking' ? gate.message : null)
      setCameras([])
      setDrones([])
      setVisualCameras([])
      setSnapshotCount(0)
      return { cameras: [], drones: [] }
    }
    try {
      const [feedsRes, dronesRes, visualRes] = await Promise.all([
        getSimulationDashboardFeeds(),
        getSimulationDrones(),
        listVisualCameras().catch(() => []),
      ])
      const visualById = Object.fromEntries(
        (Array.isArray(visualRes) ? visualRes : []).map(camera => [camera.camera_id, camera]),
      )
      // Map dashboard feed entries to a shape compatible with existing CameraCard
      const mappedCameras = (feedsRes.items || []).map(feed => ({
        ...(visualById[feed.camera_id]?.snapshot_path || visualById[feed.camera_id]?.snapshot_url
          ? {
              snapshotUrl: snapshotImageUrl(feed.camera_id, visualById[feed.camera_id]?.last_capture_at || Date.now()),
              visualSnapshot: {
                ...visualById[feed.camera_id],
                imageUrl: snapshotImageUrl(feed.camera_id, visualById[feed.camera_id]?.last_capture_at || Date.now()),
              },
            }
          : {
              visualSnapshot: visualById[feed.camera_id] || null,
            }),
        // Base CameraCard-compatible fields
        camera_id: feed.camera_id,
        name: feed.name,
        zone: feed.zone_id,
        status: feed.status,
        priority: feed.priority,
        enabled: true,
        // Simulation-specific enrichment
        zone_id: feed.zone_id,
        zone_name: feed.zone_name,
        district: feed.district,
        location: feed.location || null,
        orientation: feed.orientation || null,
        coverage: feed.coverage || null,
        source_type: feed.source_type,
        feed_uri: feed.feed_uri,
        supported_detections: feed.supported_detections || [],
        dashboard_pinned: feed.dashboard_pinned || false,
        last_observation_at: feed.last_observation_at || visualById[feed.camera_id]?.last_capture_at || null,
        simulated: true,
        sim_metadata: feed.metadata || {},
      }))
      setCameras(mappedCameras)
      setDrones(dronesRes.items || [])
      setVisualCameras(Array.isArray(visualRes) ? visualRes : [])
      setSnapshotCount((Array.isArray(visualRes) ? visualRes : []).filter(cam => cam?.snapshot_path || cam?.snapshot_url).length)
      setError(null)
      return { cameras: mappedCameras, drones: dronesRes.items || [] }
    } catch (err) {
      setError(normalizeError(err))
      return { cameras: [], drones: [] }
    } finally {
      setLoading(false)
    }
  }, [gate.enabled, gate.message, gate.reason])

  useEffect(() => {
    const load = () => { refresh() }
    const initial = window.setTimeout(load, 0)
    const timer = gate.enabled ? window.setInterval(refresh, pollMs) : null
    return () => {
      window.clearTimeout(initial)
      if (timer) window.clearInterval(timer)
    }
  }, [gate.enabled, pollMs, refresh])

  return {
    cameras,
    drones,
    visualCameras,
    snapshotCount,
    loading,
    error,
    authGate: gate,
    refresh,
  }
}
