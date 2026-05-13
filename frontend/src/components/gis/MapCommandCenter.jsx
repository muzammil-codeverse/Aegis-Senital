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
  canWriteGis,
  onSaveCamera,
  filters,
  onFiltersChange,
}) {
  const [selectedCamera, setSelectedCamera] = useState(null)
  const [selectedEvent, setSelectedEvent] = useState(null)

  const provider = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_MAP_PROVIDER) || gisConfig?.provider || 'local_mock'
  const cameras = layers?.cameras || []

  const profileForDrawer = useMemo(() => {
    if (!selectedCamera) return null
    return cameras.find(c => c.camera_id === selectedCamera) || null
  }, [cameras, selectedCamera])

  const refLat = profileForDrawer?.latitude ?? cameras[0]?.latitude ?? gisConfig?.map?.default_center?.latitude ?? 30.1575
  const refLon = profileForDrawer?.longitude ?? cameras[0]?.longitude ?? gisConfig?.map?.default_center?.longitude ?? 71.5249

  useEffect(() => {
    const id = window.sessionStorage.getItem('aegis.map.camera_id')
    if (id) {
      setSelectedCamera(id)
      window.sessionStorage.removeItem('aegis.map.camera_id')
    }
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
                <RiskHeatmapLayer cells={layers?.heatmap_cells} project={ctx.project} />
                <GeofenceLayer geofences={layers?.geofences} project={ctx.project} />
                <CameraFovLayer fovs={layers?.camera_fovs} project={ctx.project} />
                <DronePathLayer paths={layers?.drone_paths} project={ctx.project} />
                <MissionRouteLayer
                  activePaths={layers?.active_mission_paths}
                  completedPaths={layers?.completed_mission_paths}
                  project={ctx.project}
                />
                <HandoffArrowLayer handoffs={layers?.fixed_camera_handoffs} project={ctx.project} />
                <EventMarkerLayer
                  markers={layers?.event_markers}
                  project={ctx.project}
                  onSelect={setSelectedEvent}
                />
                <CaseMarkerLayer markers={layers?.case_markers} project={ctx.project} />
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
          Candidate event locations derive from camera geo profiles, simulated drone telemetry, and mission overlays. Operator review required for enforcement actions.
        </p>
      </section>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <MapFilterPanel value={filters} onChange={onFiltersChange} />
        <NearbyCamerasPanel latitude={refLat} longitude={refLon} />
        <div className="panel" style={{ padding: 12, fontSize: '0.72rem' }}>
          <p className="eyebrow">Stream status</p>
          <div className="button-row" style={{ marginBottom: 8 }}>
            <span className="state-chip">active routes: {(layers?.active_mission_paths || []).length}</span>
            <span className="state-chip">handoff arrows: {(layers?.fixed_camera_handoffs || []).length}</span>
          </div>
          <ul style={{ paddingLeft: 16 }}>
            {cameras.slice(0, 8).map(c => (
              <li key={c.camera_id}>
                {c.camera_id}: {layers?.stream_status_by_camera?.[c.camera_id]?.state || layers?.stream_status_by_camera?.[c.camera_id]?.status || 'unknown'}
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
