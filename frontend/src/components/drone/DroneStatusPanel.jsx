function MetricRow({ label, value }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1 text-xs last:border-b-0">
      <span className="text-slate-500">{label}</span>
      <strong className="text-slate-900">{value}</strong>
    </div>
  )
}

export default function DroneStatusPanel({ status, stats, wsStatus, uiState }) {
  const session = status?.session || {}
  const connection = status?.connection || {}
  const health = status?.health || {}

  return (
    <section className="rounded border bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Drone status</p>
          <h2 className="text-base font-semibold text-slate-900">Simulated aerial source</h2>
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700">
          WS {wsStatus || 'unknown'}
        </span>
      </div>
      <div className="space-y-1">
        <MetricRow label="Connection" value={connection.status || 'unknown'} />
        <MetricRow label="Health" value={health.status || 'unknown'} />
        <MetricRow label="Runtime state" value={uiState || 'unknown'} />
        <MetricRow label="Session" value={session.status || 'idle'} />
        <MetricRow label="Active session" value={session.active ? 'yes' : 'no'} />
        <MetricRow label="Frames processed" value={stats.framesProcessed} />
        <MetricRow label="Telemetry updates" value={stats.telemetryUpdates} />
        <MetricRow label="Detected events" value={stats.events} />
      </div>
      {health.last_error ? (
        <p className="mt-3 rounded bg-rose-50 px-2 py-2 text-xs text-rose-700">{health.last_error}</p>
      ) : null}
    </section>
  )
}
