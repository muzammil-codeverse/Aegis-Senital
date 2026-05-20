import { useCallback, useEffect, useMemo, useState } from 'react'
import MapCommandCenter from '../components/gis/MapCommandCenter'
import CommandPageHeader from '../components/layout/CommandPageHeader'
import { useAuth } from '../hooks/useAuth'
import { useCameraGeoProfiles } from '../hooks/useCameraGeoProfiles'
import { useGisMap } from '../hooks/useGisMap'
import { useSimulationSources } from '../hooks/useSimulationSources'

export default function MapOperationsPage() {
  const auth = useAuth()
  const [filters, setFilters] = useState({})
  const apiFilters = useMemo(() => {
    const o = {}
    if (filters.severity) o.severity = filters.severity
    if (filters.source_type) o.source_type = filters.source_type
    if (filters.case_id) o.case_id = filters.case_id
    return o
  }, [filters])

  const authReady = Boolean(auth.ready ?? !auth.loading)
  const canReadGis = authReady && auth.authenticated && auth.hasPermission('gis:read')
  const gisMap = useGisMap({ enabled: canReadGis, filters: apiFilters, pollMs: 45_000 })
  const profiles = useCameraGeoProfiles({ enabled: canReadGis, pollMs: 0 })
  const simulation = useSimulationSources({ enabled: canReadGis && auth.hasPermission('system:read'), pollMs: 45_000 })

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const cid = window.sessionStorage.getItem('aegis.map.case_id')
      if (cid) {
        setFilters(f => ({ ...f, case_id: cid }))
        window.sessionStorage.removeItem('aegis.map.case_id')
      }
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  const refreshAll = useCallback(async () => {
    await gisMap.refreshLayers()
    await profiles.refresh()
  }, [gisMap, profiles])

  const onSaveCamera = useCallback(
    async (cameraId, payload) => {
      await profiles.save(cameraId, payload)
      await refreshAll()
    },
    [profiles, refreshAll],
  )

  if (!canReadGis) {
    return <p className="muted">You do not have gis:read permission.</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <CommandPageHeader
        eyebrow="Geospatial"
        title="Map Operations"
        description="GIS command surface for cameras, events, simulated drone trail/FOV, mission routes, and fixed-camera handoff overlays. Data visibility remains RBAC-scoped."
        badges={['Layer toggles', 'Drone mission overlays', 'Operational overlays']}
      />
      {gisMap.error && <p className="error-text">{gisMap.error}</p>}
      <MapCommandCenter
        gisConfig={gisMap.config}
        layers={gisMap.layers}
        simulationCameras={simulation.cameras}
        simulationDrones={simulation.drones}
        canWriteGis={auth.hasPermission('gis:write')}
        onSaveCamera={onSaveCamera}
        filters={filters}
        onFiltersChange={setFilters}
      />
    </div>
  )
}
