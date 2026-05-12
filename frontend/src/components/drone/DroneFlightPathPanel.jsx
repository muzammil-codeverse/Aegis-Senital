export default function DroneFlightPathPanel({ flightPath = [] }) {
  const recent = [...flightPath].slice(-8).reverse()

  return (
    <section className="rounded border bg-white p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Flight path</p>
        <h2 className="text-base font-semibold text-slate-900">Candidate aerial path</h2>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Flight path points are simulated telemetry samples and should be treated as a possible movement path.
      </p>
      {recent.length === 0 ? (
        <p className="text-xs text-slate-500">No simulated telemetry path points recorded yet.</p>
      ) : (
        <ol className="space-y-2 text-xs">
          {recent.map(point => (
            <li key={`${point.timestamp}-${point.latitude}-${point.longitude}`} className="rounded bg-slate-50 p-2 text-slate-700">
              <div className="font-medium">{point.timestamp}</div>
              <div>
                {Number(point.latitude).toFixed(5)}, {Number(point.longitude).toFixed(5)}
                {point.altitude_meters != null ? ` at ${Number(point.altitude_meters).toFixed(1)} m` : ''}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
