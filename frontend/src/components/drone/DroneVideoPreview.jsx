function frameSrc(frame) {
  if (!frame?.image_base64) return null
  return `data:${frame.content_type || 'image/jpeg'};base64,${frame.image_base64}`
}

export default function DroneVideoPreview({ frame, stats, onRefresh }) {
  const src = frameSrc(frame)

  return (
    <section className="rounded border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Aerial preview</p>
          <h2 className="text-base font-semibold text-slate-900">Latest simulated drone frame</h2>
        </div>
        <button type="button" className="text-xs text-sky-700" onClick={onRefresh}>
          Refresh frame
        </button>
      </div>
      <div className="overflow-hidden rounded border bg-slate-950">
        {src ? (
          <img src={src} alt="Simulated drone preview" className="h-72 w-full object-cover" />
        ) : (
          <div className="flex h-72 items-center justify-center px-6 text-center text-xs text-slate-300">
            No simulated frame is currently available. Start the simulator session to enable aerial observation.
          </div>
        )}
      </div>
      <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-4">
        <div>Frame index: {frame?.frame_index ?? 'n/a'}</div>
        <div>Events: {stats.events}</div>
        <div>Anomalies: {stats.anomalies}</div>
        <div>Incidents: {stats.incidents}</div>
      </div>
    </section>
  )
}
