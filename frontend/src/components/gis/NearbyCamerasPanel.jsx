import { useEffect, useState } from 'react'
import { getNearbyCameras } from '../../api/gisApi'

export default function NearbyCamerasPanel({ latitude, longitude, radiusMeters = 800 }) {
  const [items, setItems] = useState([])
  const [error, setError] = useState(null)
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await getNearbyCameras({ latitude, longitude, radius_meters: radiusMeters })
        if (!cancelled) setItems(res.items || [])
      } catch (e) {
        if (!cancelled) setError(String(e.message || e))
      }
    })()
    return () => { cancelled = true }
  }, [latitude, longitude, radiusMeters])
  return (
    <div className="panel" style={{ padding: 12 }}>
      <p className="eyebrow">Nearby cameras</p>
      {error && <p className="error-text">{error}</p>}
      <ul style={{ fontSize: '0.75rem', paddingLeft: 16 }}>
        {items.map(i => (
          <li key={i.camera_id}>{i.name} — {i.distance_meters?.toFixed?.(1) ?? i.distance_meters} m</li>
        ))}
      </ul>
    </div>
  )
}
