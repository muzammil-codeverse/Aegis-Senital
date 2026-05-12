export default function GeofenceLayer({ geofences, project }) {
  return (
    <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} viewBox="0 0 100 100" preserveAspectRatio="none">
      {(geofences || []).filter(z => z.active).map(zone => {
        const pts = (zone.polygon || [])
          .map(p => {
            const pos = project(p.latitude, p.longitude)
            const x = parseFloat(String(pos.left).replace('%', ''))
            const y = parseFloat(String(pos.top).replace('%', ''))
            return `${x},${y}`
          })
          .join(' ')
        return <polygon key={zone.zone_id} points={pts} fill="rgba(250,204,21,0.06)" stroke="rgba(250,204,21,0.45)" strokeWidth="0.25" />
      })}
    </svg>
  )
}
