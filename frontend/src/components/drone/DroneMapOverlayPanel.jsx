export default function DroneMapOverlayPanel({ telemetry, flightPath = [] }) {
  return (
    <section className="rounded border bg-white p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Map overlay</p>
        <h2 className="text-base font-semibold text-slate-900">GIS and investigation links</h2>
      </div>
      <div className="space-y-3 text-xs text-slate-600">
        <p>
          The GIS view displays the simulated drone marker, aerial trail, and field of view cone using authorized map layers.
        </p>
        <div className="rounded bg-slate-50 p-3">
          <div>Latest telemetry: {telemetry?.timestamp || 'n/a'}</div>
          <div>Recorded path points: {flightPath.length}</div>
          <div>Source ID: drone_sim_01</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border px-3 py-2 text-xs text-slate-700"
            onClick={() => {
              window.sessionStorage.setItem('aegis.map.camera_id', 'drone_sim_01')
              window.location.hash = 'map-operations'
            }}
          >
            Open map overlay
          </button>
          <button
            type="button"
            className="rounded border px-3 py-2 text-xs text-slate-700"
            onClick={() => {
              window.location.hash = 'investigation'
            }}
          >
            Open investigation workspace
          </button>
        </div>
      </div>
    </section>
  )
}
