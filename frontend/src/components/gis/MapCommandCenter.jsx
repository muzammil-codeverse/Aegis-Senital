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
  const usingDemoFallback = (baseLayers.cameras || []).length === 0 && simulationLayer.cameras.length === 0
  const demoLayer = useMemo(() => usingDemoFallback ? buildDemoLayer(gisConfig) : null, [gisConfig, usingDemoFallback])
  const effectiveLayers = useMemo(
    () => usingDemoFallback && demoLayer
      ? { ...baseLayers, ...demoLayer }
      : usingSimulationFallback
      ? { ...baseLayers, ...simulationLayer }
      : baseLayers,
    [baseLayers, demoLayer, simulationLayer, usingDemoFallback, usingSimulationFallback],
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
          {usingDemoFallback
            ? 'Exhibition demo map: 16 simulated cameras, 3 drone positions, and suspect path are shown. Start AirSim or the exhibition scenario for live data.'
            : usingSimulationFallback
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
            {usingDemoFallback ? <span className="state-chip" style={{ color: '#60a5fa' }}>exhibition demo map</span> : null}
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

// Exhibition demo layout: 16 cameras, 3 drones, suspect path, active incident marker.
// Shown when no API data and no simulation cameras are available.
function buildDemoLayer(gisConfig = null) {
  const baseLat = Number(gisConfig?.map?.default_center?.latitude || 30.1575)
  const baseLon = Number(gisConfig?.map?.default_center?.longitude || 71.5249)
  const d = (dlat, dlon) => ({ latitude: baseLat + dlat, longitude: baseLon + dlon })

  const cameras = [
    { id: 'CAM-BANK-01',    zone: 'bank',    pos: d(0.0000, 0.0000), heading: 180 },
    { id: 'CAM-BANK-02',    zone: 'bank',    pos: d(0.0002, 0.0001), heading: 270 },
    { id: 'CAM-MARKET-01',  zone: 'market',  pos: d(0.0005, 0.0010), heading: 90  },
    { id: 'CAM-MARKET-02',  zone: 'market',  pos: d(0.0007, 0.0012), heading: 0   },
    { id: 'CAM-MARKET-03',  zone: 'market',  pos: d(0.0009, 0.0015), heading: 45  },
    { id: 'CAM-ROAD-01',    zone: 'road',    pos: d(0.0012, 0.0018), heading: 135 },
    { id: 'CAM-ROAD-02',    zone: 'road',    pos: d(0.0015, 0.0020), heading: 180 },
    { id: 'CAM-ROAD-03',    zone: 'road',    pos: d(0.0018, 0.0022), heading: 225 },
    { id: 'CAM-PARKING-01', zone: 'parking', pos: d(0.0020, 0.0030), heading: 90  },
    { id: 'CAM-PARKING-02', zone: 'parking', pos: d(0.0022, 0.0033), heading: 315 },
    { id: 'CAM-ALLEY-01',   zone: 'alley',   pos: d(0.0016, 0.0025), heading: 270 },
    { id: 'CAM-ALLEY-02',   zone: 'alley',   pos: d(0.0018, 0.0028), heading: 180 },
    { id: 'CAM-GATE-01',    zone: 'gate',    pos: d(0.0025, 0.0035), heading: 0   },
    { id: 'CAM-GATE-02',    zone: 'gate',    pos: d(0.0027, 0.0037), heading: 90  },
    { id: 'CAM-CORNER-01',  zone: 'corner',  pos: d(0.0010, 0.0005), heading: 315 },
    { id: 'CAM-CORNER-02',  zone: 'corner',  pos: d(0.0013, 0.0008), heading: 45  },
  ].map(c => ({
    camera_id: c.id,
    name: c.id,
    status: 'online',
    priority: c.zone === 'bank' ? 'high' : 'normal',
    heading_degrees: c.heading,
    fov_degrees: 90,
    coverage_radius_meters: 60,
    metadata: { simulated: true, zone: c.zone, exhibition: true },
    latitude: c.pos.latitude,
    longitude: c.pos.longitude,
  }))

  // Suspect path: bank → market → road → alley → parking
  const suspectPath = [
    d(0.0000, 0.0000),
    d(0.0006, 0.0011),
    d(0.0013, 0.0019),
    d(0.0017, 0.0026),
    d(0.0021, 0.0032),
  ]

  // DRONE-ALPHA route follows suspect path from above
  const droneAlphaPath = suspectPath.map((pt, i) => ({
    latitude: pt.latitude + 0.0001,
    longitude: pt.longitude,
  }))

  return {
    cameras,
    drone_paths: [
      { path_id: 'DRONE-ALPHA-path', drone_id: 'DRONE-ALPHA', points: droneAlphaPath, status: 'tracking' },
      { path_id: 'DRONE-BETA-path',  drone_id: 'DRONE-BETA',  points: [d(0.0030, 0.0010), d(0.0032, 0.0015)], status: 'standby' },
      { path_id: 'DRONE-GAMMA-path', drone_id: 'DRONE-GAMMA', points: [d(-0.0005, 0.0020), d(-0.0003, 0.0025)], status: 'standby' },
    ],
    stream_status_by_camera: Object.fromEntries(cameras.map(c => [c.camera_id, { status: 'ready' }])),
    heatmap_cells: [],
    geofences: [],
    camera_fovs: cameras.map(c => ({
      camera_id: c.camera_id,
      latitude: c.latitude,
      longitude: c.longitude,
      heading_degrees: c.heading_degrees,
      fov_degrees: c.fov_degrees,
      radius_meters: c.coverage_radius_meters,
    })),
    active_mission_paths: [
      { path_id: 'DRONE-ALPHA-mission', drone_id: 'DRONE-ALPHA', points: droneAlphaPath, status: 'active' },
    ],
    completed_mission_paths: [],
    fixed_camera_handoffs: [
      { handoff_id: 'ho-1', from_camera_id: 'CAM-BANK-01',    to_camera_id: 'CAM-MARKET-01',  from: d(0.0000, 0.0000), to: d(0.0005, 0.0010) },
      { handoff_id: 'ho-2', from_camera_id: 'CAM-MARKET-03',  to_camera_id: 'CAM-ROAD-01',    from: d(0.0009, 0.0015), to: d(0.0012, 0.0018) },
      { handoff_id: 'ho-3', from_camera_id: 'CAM-ROAD-02',    to_camera_id: 'CAM-ALLEY-01',   from: d(0.0015, 0.0020), to: d(0.0016, 0.0025) },
      { handoff_id: 'ho-4', from_camera_id: 'CAM-ALLEY-02',   to_camera_id: 'CAM-PARKING-01', from: d(0.0018, 0.0028), to: d(0.0020, 0.0030) },
    ],
    event_markers: [
      {
        marker_id: 'inc-001',
        latitude: d(0.0021, 0.0032).latitude,
        longitude: d(0.0021, 0.0032).longitude,
        severity: 'critical',
        label: 'Suspect last seen — Parking Zone',
        event_type: 'person_detection',
        timestamp: new Date().toISOString(),
      },
    ],
    case_markers: [],
  }
}
