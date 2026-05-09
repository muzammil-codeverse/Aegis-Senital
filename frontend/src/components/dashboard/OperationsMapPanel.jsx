import { useCallback, useMemo, useRef, useState } from 'react'
import MapLegend from './MapLegend'
import MapLayerControls from './MapLayerControls'
import LoadingState from '../common/LoadingState'
import ErrorState from '../common/ErrorState'

// ── Color helpers ──────────────────────────────────────────────────────────────

const CAMERA_STATUS_COLOR = {
  online: '#52c41a',
  degraded: '#fa8c16',
  error: '#ff4d4f',
  offline: '#8c8c8c',
  disabled: '#595959',
}

const PRIORITY_BORDER = {
  critical: '#ff4d4f',
  high: '#fa8c16',
  normal: '#1890ff',
  low: '#8c8c8c',
}

const SEVERITY_COLOR = {
  critical: '#ff4d4f',
  high: '#fa8c16',
  medium: '#fadb14',
  low: '#52c41a',
  info: '#1890ff',
}

const ZONE_TYPE_COLOR = {
  restricted: { fill: 'rgba(255,77,79,0.15)', stroke: '#ff4d4f' },
  entrance:   { fill: 'rgba(24,144,255,0.10)', stroke: '#1890ff' },
  lobby:      { fill: 'rgba(24,144,255,0.08)', stroke: '#1890ff80' },
  corridor:   { fill: 'rgba(82,196,26,0.08)', stroke: '#52c41a60' },
  parking:    { fill: 'rgba(108,117,125,0.10)', stroke: '#6b728080' },
  general:    { fill: 'rgba(24,144,255,0.07)', stroke: '#1890ff50' },
}

function zoneStyle(zoneType, restricted) {
  if (restricted) return ZONE_TYPE_COLOR.restricted
  return ZONE_TYPE_COLOR[zoneType] || ZONE_TYPE_COLOR.general
}

// ── FOV cone ──────────────────────────────────────────────────────────────────

function fovPath(x, y, radiusPx, dirDeg, fovDeg) {
  const halfFov = (fovDeg / 2) * (Math.PI / 180)
  const dir = ((dirDeg - 90) * Math.PI) / 180
  const x1 = x + radiusPx * Math.cos(dir - halfFov)
  const y1 = y + radiusPx * Math.sin(dir - halfFov)
  const x2 = x + radiusPx * Math.cos(dir + halfFov)
  const y2 = y + radiusPx * Math.sin(dir + halfFov)
  const largeArc = fovDeg > 180 ? 1 : 0
  return `M ${x} ${y} L ${x1.toFixed(1)} ${y1.toFixed(1)} A ${radiusPx} ${radiusPx} 0 ${largeArc} 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z`
}

// ── Incident pulse ─────────────────────────────────────────────────────────────

function IncidentMarker({ cx, cy, severity, onClick }) {
  const color = SEVERITY_COLOR[severity] || SEVERITY_COLOR.medium
  return (
    <g onClick={onClick} style={{ cursor: 'pointer' }}>
      <circle cx={cx} cy={cy} r={10} fill={`${color}40`} stroke={color} strokeWidth={1.5} />
      <circle cx={cx} cy={cy} r={5} fill={color} />
      <text x={cx} y={cy + 1} textAnchor="middle" dominantBaseline="middle"
        fontSize={7} fill="#000" fontWeight="bold">!</text>
    </g>
  )
}

// ── Alert marker ───────────────────────────────────────────────────────────────

function AlertMarkerDot({ cx, cy, severity }) {
  const color = SEVERITY_COLOR[severity] || SEVERITY_COLOR.medium
  return (
    <g>
      <rect x={cx - 5} y={cy - 5} width={10} height={10}
        fill={`${color}60`} stroke={color} strokeWidth={1} rx={2} />
    </g>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

const DEFAULT_LAYERS = {
  cameras: true,
  zones: true,
  geofences: true,
  connections: true,
  incidents: true,
  alerts: true,
  heatmap: false,
  fov: true,
}

export default function OperationsMapPanel({
  mapState,
  loading,
  error,
  onRefresh,
  selectedCameraId,
  onCameraSelect,
  onIncidentSelect,
}) {
  const containerRef = useRef(null)
  const [layers, setLayers] = useState(DEFAULT_LAYERS)
  const [hoveredCamera, setHoveredCamera] = useState(null)
  const [hoveredZone, setHoveredZone] = useState(null)

  const toggleLayer = useCallback(id => {
    setLayers(prev => ({ ...prev, [id]: !prev[id] }))
  }, [])

  // Derive canvas dimensions from site bounds
  const site = mapState?.site
  const bounds = site?.bounds || { x_min: 0, y_min: 0, x_max: 1600, y_max: 900 }
  const canvasW = (bounds.x_max || 1600) - (bounds.x_min || 0)
  const canvasH = (bounds.y_max || 900) - (bounds.y_min || 0)

  const zones = mapState?.zones || []
  const geofences = mapState?.geofences || []
  const cameras = mapState?.cameras || []
  const connections = mapState?.connections || []
  const incidents = mapState?.incidents || []
  const alerts = mapState?.alerts || []

  // Build camera position lookup
  const cameraPos = useMemo(() => {
    const m = {}
    for (const cam of cameras) {
      const loc = cam.location || {}
      if (loc.x != null && loc.y != null) m[cam.camera_id] = { x: loc.x, y: loc.y }
    }
    return m
  }, [cameras])

  const viewBox = `${bounds.x_min} ${bounds.y_min} ${canvasW} ${canvasH}`

  return (
    <section className="panel operations-map-panel" style={{ display: 'flex', flexDirection: 'column', minHeight: 360 }}>
      {/* Header */}
      <div className="panel-header" style={{ flexShrink: 0 }}>
        <div>
          <p className="eyebrow">Spatial Intelligence</p>
          <h2>Operations Map {site ? `— ${site.name}` : ''}</h2>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="count-pill">{cameras.length} cams</span>
          {onRefresh && (
            <button className="ctrl-btn" onClick={onRefresh} style={{ fontSize: '0.7rem' }} title="Refresh">↺</button>
          )}
        </div>
      </div>

      {/* Layer controls */}
      <MapLayerControls layers={layers} onToggle={toggleLayer} />

      {/* Map canvas */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          position: 'relative',
          background: '#080d16',
          overflow: 'hidden',
          minHeight: 280,
        }}
      >
        {loading && !mapState && <LoadingState label="Loading map…" />}
        {error && !mapState && <ErrorState message={error} onRetry={onRefresh} />}

        {(mapState || (!loading && !error)) && (
          <svg
            width="100%"
            height="100%"
            viewBox={viewBox}
            preserveAspectRatio="xMidYMid meet"
            style={{ display: 'block' }}
          >
            {/* Background grid */}
            <defs>
              <pattern id="mapGrid" x="0" y="0" width="100" height="100" patternUnits="userSpaceOnUse">
                <path d="M 100 0 L 0 0 0 100" fill="none" stroke="#0d1a2e" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect x={bounds.x_min} y={bounds.y_min} width={canvasW} height={canvasH}
              fill="url(#mapGrid)" />

            {/* Zones */}
            {layers.zones && zones.map(zone => {
              if (!zone.polygon?.length) return null
              const { fill, stroke } = zoneStyle(zone.zone_type, zone.restricted)
              const pts = zone.polygon.map(p => p.join(',')).join(' ')
              const isHovered = hoveredZone === zone.zone_id
              return (
                <g key={zone.zone_id}
                  onMouseEnter={() => setHoveredZone(zone.zone_id)}
                  onMouseLeave={() => setHoveredZone(null)}
                  style={{ cursor: 'default' }}
                >
                  <polygon
                    points={pts}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth={isHovered ? 2 : 1}
                    strokeDasharray={zone.restricted ? '6,3' : '0'}
                  />
                  {isHovered && (
                    <text
                      x={(zone.polygon[0][0] + zone.polygon[2][0]) / 2}
                      y={(zone.polygon[0][1] + zone.polygon[2][1]) / 2}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={11} fill={stroke} opacity={0.9}
                    >
                      {zone.name}
                    </text>
                  )}
                  {/* Always show zone label */}
                  {!isHovered && (
                    <text
                      x={(zone.polygon[0][0] + zone.polygon[2][0]) / 2}
                      y={(zone.polygon[0][1] + zone.polygon[2][1]) / 2}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={9} fill={stroke} opacity={0.55}
                    >
                      {zone.name}
                    </text>
                  )}
                </g>
              )
            })}

            {/* Geofences (restricted only, separate layer toggle) */}
            {layers.geofences && geofences.filter(f => f.restricted).map(fence => {
              if (!fence.polygon?.length) return null
              const pts = fence.polygon.map(p => p.join(',')).join(' ')
              return (
                <polygon
                  key={`gf-${fence.geofence_id}`}
                  points={pts}
                  fill="none"
                  stroke="#ff4d4f"
                  strokeWidth={2}
                  strokeDasharray="8,4"
                  opacity={0.8}
                />
              )
            })}

            {/* Camera connections */}
            {layers.connections && connections.map((conn, idx) => {
              const from = cameraPos[conn.from_camera]
              const to = cameraPos[conn.to_camera]
              if (!from || !to) return null
              const opacity = Math.max(0.15, conn.transition_probability || 0.5)
              return (
                <line
                  key={`conn-${idx}`}
                  x1={from.x} y1={from.y}
                  x2={to.x} y2={to.y}
                  stroke="#1890ff"
                  strokeWidth={1.5}
                  strokeDasharray="6,4"
                  opacity={opacity}
                />
              )
            })}

            {/* FOV cones */}
            {layers.fov && cameras.map(cam => {
              const loc = cam.location || {}
              if (loc.x == null || loc.y == null) return null
              const color = CAMERA_STATUS_COLOR[cam.status] || '#8c8c8c'
              const radiusPx = Math.min(cam.coverage_radius || 150, canvasW / 4)
              return (
                <path
                  key={`fov-${cam.camera_id}`}
                  d={fovPath(loc.x, loc.y, radiusPx, cam.view_direction_degrees || 0, cam.fov_degrees || 90)}
                  fill={`${color}12`}
                  stroke={`${color}30`}
                  strokeWidth={0.5}
                />
              )
            })}

            {/* Incident markers */}
            {layers.incidents && incidents.map(inc => {
              const loc = inc.location || {}
              if (loc.x == null || loc.y == null) return null
              return (
                <IncidentMarker
                  key={`inc-${inc.incident_id}`}
                  cx={loc.x}
                  cy={loc.y - 20}
                  severity={inc.severity}
                  onClick={() => onIncidentSelect && onIncidentSelect(inc)}
                />
              )
            })}

            {/* Alert markers */}
            {layers.alerts && alerts.map((alert, idx) => {
              const loc = alert.location || {}
              if (loc.x == null || loc.y == null) return null
              return (
                <AlertMarkerDot
                  key={`alert-${alert.alert_id || idx}`}
                  cx={loc.x + 12}
                  cy={loc.y - 12}
                  severity={alert.severity}
                />
              )
            })}

            {/* Camera nodes (rendered last / on top) */}
            {layers.cameras && cameras.map(cam => {
              const loc = cam.location || {}
              if (loc.x == null || loc.y == null) return null
              const color = CAMERA_STATUS_COLOR[cam.status] || '#8c8c8c'
              const borderColor = PRIORITY_BORDER[cam.priority] || '#6b7280'
              const isSelected = cam.camera_id === selectedCameraId
              const isHovered = hoveredCamera === cam.camera_id
              const r = isSelected ? 12 : 9
              const alertColor = cam.latest_alert_severity
                ? (SEVERITY_COLOR[cam.latest_alert_severity] || SEVERITY_COLOR.info)
                : null

              return (
                <g
                  key={`cam-${cam.camera_id}`}
                  onClick={() => onCameraSelect && onCameraSelect(cam)}
                  onMouseEnter={() => setHoveredCamera(cam.camera_id)}
                  onMouseLeave={() => setHoveredCamera(null)}
                  style={{ cursor: 'pointer' }}
                >
                  {/* Selection ring */}
                  {isSelected && (
                    <circle cx={loc.x} cy={loc.y} r={r + 5} fill="none"
                      stroke="#1890ff" strokeWidth={1.5} opacity={0.6} />
                  )}
                  {/* Alert ring */}
                  {alertColor && (
                    <circle cx={loc.x} cy={loc.y} r={r + 3} fill="none"
                      stroke={alertColor} strokeWidth={1} opacity={0.7} />
                  )}
                  {/* Camera body */}
                  <circle cx={loc.x} cy={loc.y} r={r}
                    fill="#0d1117" stroke={borderColor} strokeWidth={1.5} />
                  {/* Status dot */}
                  <circle cx={loc.x} cy={loc.y} r={r - 4} fill={color} />
                  {/* Camera icon */}
                  <text x={loc.x} y={loc.y + 1} textAnchor="middle" dominantBaseline="middle"
                    fontSize={r - 2} fill="#000">▶</text>
                  {/* Label */}
                  {(isHovered || isSelected) && (
                    <g>
                      <rect x={loc.x - 38} y={loc.y + r + 2} width={76} height={14}
                        rx={2} fill="rgba(0,0,0,0.75)" />
                      <text x={loc.x} y={loc.y + r + 10} textAnchor="middle"
                        fontSize={8} fill="#e6e6e6">
                        {cam.name}
                      </text>
                    </g>
                  )}
                  {/* Persistent short label */}
                  {!isHovered && !isSelected && (
                    <text x={loc.x} y={loc.y + r + 10} textAnchor="middle"
                      fontSize={7} fill="#6b7280" opacity={0.8}>
                      {cam.camera_id.replace('cam_', '').replace('_01', '')}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        )}

        {/* Hovered zone info tooltip */}
        {hoveredZone && (() => {
          const zone = zones.find(z => z.zone_id === hoveredZone)
          if (!zone) return null
          return (
            <div style={{
              position: 'absolute', top: 8, right: 8,
              background: '#0d1117', border: '1px solid #1c2535',
              borderRadius: 4, padding: '5px 10px', fontSize: '0.68rem',
              color: '#9ca3af', pointerEvents: 'none', zIndex: 10,
            }}>
              <strong style={{ color: '#e6e6e6' }}>{zone.name}</strong>
              <div style={{ color: '#6b7280' }}>{zone.zone_type} · {zone.priority}</div>
              {zone.restricted && <div style={{ color: '#ff4d4f' }}>RESTRICTED</div>}
            </div>
          )
        })()}
      </div>

      {/* Legend */}
      <MapLegend />
    </section>
  )
}
