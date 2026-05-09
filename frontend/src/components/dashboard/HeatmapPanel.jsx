import { useEffect, useState } from 'react'
import { getCameraHeatmap } from '../../api/camerasApi'
import { normalizeError } from '../../api/client'
import EmptyState from '../common/EmptyState'
import ErrorState from '../common/ErrorState'
import LoadingState from '../common/LoadingState'
import { formatDateTime } from '../../utils/time'

export default function HeatmapPanel({ defaultCameraId = 'cam_1' }) {
  const [cameraId, setCameraId] = useState(defaultCameraId)
  const [activeCameraId, setActiveCameraId] = useState(defaultCameraId)
  const [heatmap, setHeatmap] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (!activeCameraId) return
      setLoading(true)
      setError(null)
      try {
        const response = await getCameraHeatmap(activeCameraId)
        if (!cancelled) setHeatmap(response.item)
      } catch (err) {
        if (!cancelled) setError(normalizeError(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [activeCameraId])

  const gridSize = heatmap?.grid_size || [16, 9]
  const cells = Array.isArray(heatmap?.cells) ? heatmap.cells : []
  const maxDensity = Number(heatmap?.max_density || 0)

  return (
    <section className="panel heatmap-panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Spatial Density</p>
          <h2>Heatmap</h2>
        </div>
        <form className="inline-form" onSubmit={event => { event.preventDefault(); setActiveCameraId(cameraId) }}>
          <input value={cameraId} onChange={event => setCameraId(event.target.value)} aria-label="Camera ID" />
          <button type="submit">Load</button>
        </form>
      </div>
      {loading && <LoadingState label="Loading heatmap" />}
      {error && <ErrorState message={error} />}
      {!loading && !error && cells.length === 0 && <EmptyState message="No heatmap density recorded for this camera." />}
      {cells.length > 0 && (
        <>
          <div
            className="heatmap-grid"
            style={{ gridTemplateColumns: `repeat(${gridSize[0]}, minmax(8px, 1fr))` }}
          >
            {cells.map((cell, index) => {
              const density = Number(cell.density ?? cell.value ?? 0)
              const opacity = maxDensity > 0 ? Math.max(0.08, Math.min(1, density / maxDensity)) : 0.08
              return <span key={`${cell.x ?? index}-${cell.y ?? index}`} style={{ opacity }} title={`density ${density}`} />
            })}
          </div>
          <div className="panel-footnote">
            Generated {formatDateTime(heatmap.generated_at)} / max density {maxDensity.toFixed(2)}
          </div>
        </>
      )}
    </section>
  )
}
