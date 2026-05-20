import { useEffect, useMemo, useState } from 'react'
import CameraFovLayer from './CameraFovLayer'
import CameraGeoProfileDrawer from './CameraGeoProfileDrawer'
import CameraMarkerLayer from './CameraMarkerLayer'
import CaseMarkerLayer from './CaseMarkerLayer'
import DronePathLayer from './DronePathLayer'
import EventMapDrawer from './EventMapDrawer'
import EventMarkerLayer from './EventMarkerLayer'
import GeofenceLayer from './GeofenceLayer'
import HandoffArrowLayer from './HandoffArrowLayer'
import MapFilterPanel from './MapFilterPanel'
import MapProviderCanvas from './MapProviderCanvas'
import MissionRouteLayer from './MissionRouteLayer'
import NearbyCamerasPanel from './NearbyCamerasPanel'
import RiskHeatmapLayer from './RiskHeatmapLayer'

export default function MapCommandCenter({
  gisConfig,
  layers,
  simulationCameras = [],
  simulationDrones = [],
  canWriteGis,
  onSaveCamera,
  filters,
  onFiltersChange,
}) {
  const [selectedCamera, setSelectedCamera] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)

  const provider = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_MAP_PROVIDER) || gisConfig?.provider || 'local_mock'
  const baseLayers = useMemo(() => layers || {}, [layers])
  const simulationLayer = useMemo(
    () => buildSimulationLayer(simulationCameras, simulationDrones, gisConfig),
    [gisConfig, simulationCameras, simulationDrones],
  )
  const usingSimulationFallback = (baseLayers.cameras || []).length === 0 && simulationLayer.cameras.length > 0
  const effectiveLayers = useMemo(
    () => (usingSimulationFallback ? { ...baseLayers, ...simulationLayer } : baseLayers),
    [baseLayers, simulationLayer, usingSimulationFallback],
  )
  const cameras = useMemo(() => effectiveLayers.cameras || [], [effectiveLayers])

  const profileForDrawer = useMemo(() => {
    if (!selectedCamera) return null
    return cameras.find(c => c.camera_id === selectedCamera) || null
  }, [cameras, selectedCamera])

  const refLat = profileForDrawer?.latitude ?? cameras[0]?.latitude ?? gisConfig?.map?.default_center?.latitude ?? 30.1575
  const refLon = profileForDrawer?.longitude ?? cameras[0]?.longitude ?? gisConfig?.map?.default_center?.longitude ?? 71.5249

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const id = window.sessionStorage.getItem('aegis.map.camera_id')
      if (id) {
        setSelectedCamera(id)
        window.sessionStorage.removeItem('aegis.map.camera_id')
      }
    }, 0)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <div className="page-grid" style={{ gridTemplateColumns: '1fr 280px', gap: 12 }}>
      <section className="panel" style={{ padding: 0 }}>
        <div className="panel-header" style={{ padding: '12px 16px' }}>
          <div>
            <p className="eyebrow">GIS</p>
            <h2>Map operations - camera coverage, drone routes, and handoff overlays</h2>
          </div>
        </div>
        <div style={{ height: 480, position: 'relative' }}>
          <MapProviderCanvas provider={provider} mapConfig={gisConfig} cameras={cameras}>
            {ctx => (
              <>
                <RiskHeatmapLayer cells={effectiveLayers?.heatmap_cells} project={ctx.project} />
                <GeofenceLayer geofences={effectiveLayers?.geofences} project={ctx.project} />
                <CameraFovLayer fovs={effectiveLayers?.camera_fovs} project={ctx.project} />
                <DronePathLayer paths={effectiveLayers?.drone_paths} project={ctx.project} />
                <MissionRouteLayer
                  activePaths={effectiveLayers?.active_mission_paths}
                  completedPaths={effectiveLayers?.completed_mission_paths}
                  project={ctx.project}
                />
                <HandoffArrowLayer handoffs={effectiveLayers?.fixed_camera_handoffs} project={ctx.project} />
                <EventMarkerLayer
                  markers={effectiveLayers?.event_markers}
                  project={ctx.project}
                  onSelect={setSelectedEvent}
                />
                <CaseMarkerLayer markers={effectiveLayers?.case_markers} project={ctx.project} />
                <CameraMarkerLayer
                  cameras={cameras}
                  project={ctx.project}
                  onSelect={setSelectedCamera}
                />
              </>
            )}
          </MapProviderCanvas>
        </div>
        <p className="muted" style={{ padding: '8px 16px 12px', fontSize: '0.75rem' }}>
          {usingSimulationFallback
            ? 'Local simulation map: GIS camera geometry is empty, so simulated city camera and drone positions are shown.'
            : 'Candidate event locations derive from camera geo profiles, simulated drone telemetry, and mission overlays. Operator review required for enforcement actions.'}
        </p>
      </section>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <MapFilterPanel value={filters} onChange={onFiltersChange} />
        <NearbyCamerasPanel latitude={refLat} longitude={refLon} fallbackItems={cameras} />
        <div className="panel" style={{ padding: 12, fontSize: '0.72rem' }}>
          <p className="eyebrow">Stream status</p>
          <div className="button-row" style={{ marginBottom: 8 }}>
            <span className="state-chip">active routes: {(effectiveLayers?.active_mission_paths || []).length}</span>
            <span className="state-chip">handoff arrows: {(effectiveLayers?.fixed_camera_handoffs || []).length}</span>
            {usingSimulationFallback ? <span className="state-chip">local simulation map</span> : null}
          </div>
          <ul style={{ paddingLeft: 16 }}>
            {cameras.slice(0, 8).map(c => (
              <li key={c.camera_id}>
                {c.camera_id}: {effectiveLayers?.stream_status_by_camera?.[c.camera_id]?.state || effectiveLayers?.stream_status_by_camera?.[c.camera_id]?.status || c.status || 'ready'}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <CameraGeoProfileDrawer
        open={Boolean(selectedCamera)}
        profile={profileForDrawer}
        canWrite={canWriteGis}
        onClose={() => setSelectedCamera(null)}
        onSave={async form => {
          await onSaveCamera?.(form.camera_id, {
            ...form,
            latitude: Number(form.latitude),
            longitude: Number(form.longitude),
            altitude_meters: form.altitude_meters === '' || form.altitude_meters == null ? null : Number(form.altitude_meters),
            heading_degrees: Number(form.heading_degrees),
            fov_degrees: Number(form.fov_degrees),
            coverage_radius_meters: Number(form.coverage_radius_meters),
            region: form.region || null,
            floor_level: form.floor_level || null,
          })
          setSelectedCamera(null)
        }}
      />
      <EventMapDrawer open={Boolean(selectedEvent)} marker={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  )
}

function buildSimulationLayer(simulationCameras = [], simulationDrones = [], gisConfig = null) {
  const center = gisConfig?.map?.default_center || { latitude: 30.1575, longitude: 71.5249 }
  const toLatLon = location => {
    const x = Number(location?.x ?? 0)
    const y = Number(location?.y ?? 0)
    return {
      latitude: Number(center.latitude || 30.1575) + ((y - 250) * 0.00001),
      longitude: Number(center.longitude || 71.5249) + ((x - 350) * 0.00001),
    }
  }
  const cameras = (simulationCameras || []).map(camera => {
    const position = toLatLon(camera.location)
    return {
      camera_id: camera.camera_id,
      name: camera.name,
      status: camera.status || 'online',
      priority: camera.priority || 'normal',
      heading_degrees: camera.orientation?.yaw ?? 0,
      fov_degrees: camera.coverage?.fov_degrees ?? 90,
      coverage_radius_meters: camera.coverage?.range_meters ?? 50,
      metadata: {
        source_type: camera.source_type,
        simulated: true,
        zone_id: camera.zone_id,
        zone_name: camera.zone_name,
      },
      ...position,
    }
  })
  const dronePaths = (simulationDrones || [])
    .map(drone => {
      const position = toLatLon(drone.current_location)
      return {
        path_id: `${drone.drone_id}-local`,
        drone_id: drone.drone_id,
        points: [position],
        status: drone.status || 'standby',
      }
    })
  const streamStatus = Object.fromEntries(cameras.map(camera => [camera.camera_id, { status: camera.status || 'ready' }]))
  return {
    cameras,
    drone_paths: dronePaths,
    stream_status_by_camera: streamStatus,
    heatmap_cells: [],
    geofences: [],
    camera_fovs: cameras.map(camera => ({
      camera_id: camera.camera_id,
      latitude: camera.latitude,
      longitude: camera.longitude,
      heading_degrees: camera.heading_degrees,
      fov_degrees: camera.fov_degrees,
      radius_meters: camera.coverage_radius_meters,
    })),
    active_mission_paths: [],
    completed_mission_paths: [],
    fixed_camera_handoffs: [],
    event_markers: [],
    case_markers: [],
  }
}
