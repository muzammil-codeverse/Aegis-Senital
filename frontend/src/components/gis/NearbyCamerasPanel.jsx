import { useEffect, useState } from 'react'
import { getNearbyCameras } from '../../api/gisApi'

export default function NearbyCamerasPanel({ latitude, longitude, radiusMeters = 800, fallbackItems = [] }) {
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await getNearbyCameras({ latitude, longitude, radius_meters: radiusMeters })
        if (!cancelled) {
          setItems(res.items || [])
          setError(null)
        }
      } catch (e) {
        if (!cancelled) setError(String(e.message || e))
      }
    })()
    return () => { cancelled = true }
  }, [latitude, longitude, radiusMeters])

  const visibleItems = items.length > 0 ? items : fallbackItems.slice(0, 8)

  return (
    <div className="panel" style={{ padding: 12 }}>
      <p className="eyebrow">Nearby cameras</p>
      {error && items.length > 0 ? <p className="error-text">{error}</p> : null}
      {error && visibleItems.length > 0 && items.length === 0 ? <p className="muted">Using simulation camera registry.</p> : null}
      <ul style={{ fontSize: '0.75rem', paddingLeft: 16 }}>
        {visibleItems.map(i => (
          <li key={i.camera_id}>{i.name} - {i.distance_meters?.toFixed?.(1) ?? i.distance_meters ?? 'local'} m</li>
        ))}
      </ul>
      {visibleItems.length === 0 && <p className="muted">No nearby cameras in the current map view.</p>}
    </div>
  )
}
