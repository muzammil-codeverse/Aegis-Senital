/** Simple equirectangular projection to CSS percentages inside a viewport box. */
export function computeBboxFromCameras(cameras = []) {
  if (!cameras.length) {
    return { minLat: 30.15, maxLat: 30.17, minLon: 71.52, maxLon: 71.53 }
  }
  const lats = cameras.map(c => c.latitude)
  const lons = cameras.map(c => c.longitude)
  const pad = 0.002
  return {
    minLat: Math.min(...lats) - pad,
    maxLat: Math.max(...lats) + pad,
    minLon: Math.min(...lons) - pad,
    maxLon: Math.max(...lons) + pad,
  }
}

export function projectLatLon(lat, lon, bbox) {
  const { minLat, maxLat, minLon, maxLon } = bbox
  const x = ((lon - minLon) / (maxLon - minLon || 1e-9)) * 100
  const y = (1 - (lat - minLat) / (maxLat - minLat || 1e-9)) * 100
  return { left: `${Math.min(100, Math.max(0, x))}%`, top: `${Math.min(100, Math.max(0, y))}%` }
}
