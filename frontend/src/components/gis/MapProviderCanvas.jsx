import { useEffect, useRef } from 'react'
import { computeBboxFromCameras, projectLatLon } from './mapUtils'

export default function MapProviderCanvas({ provider, mapConfig, cameras, children }) {
  const hostRef = useRef(null)
  const mapRef = useRef(null)
  const token = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_MAPBOX_TOKEN : ''
  const useMapbox = provider === 'mapbox' && token

  useEffect(() => {
    if (!useMapbox || !hostRef.current) return undefined
    let cancelled = false
    ;(async () => {
      const mapboxgl = (await import('mapbox-gl')).default
      await import('mapbox-gl/dist/mapbox-gl.css')
      if (cancelled || !hostRef.current) return
      mapboxgl.accessToken = token
      const center = mapConfig?.map?.default_center || {}
      const map = new mapboxgl.Map({
        container: hostRef.current,
        style: 'mapbox://styles/mapbox/dark-v11',
        center: [center.longitude || 71.5249, center.latitude || 30.1575],
        zoom: mapConfig?.map?.default_zoom || 13,
      })
      mapRef.current = map
    })()
    return () => {
      cancelled = true
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [useMapbox, token, mapConfig])

  if (useMapbox) {
    return <div ref={hostRef} style={{ width: '100%', height: '100%', minHeight: 420 }} />
  }

  const bbox = computeBboxFromCameras(cameras || [])
  return (
    <div
      className="gis-local-mock-map"
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 420,
        background: 'radial-gradient(circle at 30% 20%, #152238 0%, #0b111a 55%)',
        border: '1px solid #1f2a3d',
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, opacity: 0.35 }}>
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#2a3f5f" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
      </svg>
      <div style={{ position: 'absolute', left: 12, top: 10, fontSize: 11, color: '#8da3bf' }}>
        Map provider: local_mock (no external tile key)
      </div>
      {children?.({ bbox, project: (lat, lon) => projectLatLon(lat, lon, bbox) })}
    </div>
  )
}
