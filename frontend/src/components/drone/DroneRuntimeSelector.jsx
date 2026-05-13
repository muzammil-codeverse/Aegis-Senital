export default function DroneRuntimeSelector({
  runtimeStatus,
  onLaunchRuntime,
  onRefreshStatus,
  launching = false,
}) {
  const selected = runtimeStatus?.selected_runtime || 'unknown'
  const available = runtimeStatus?.available_runtimes || []
  const fallbackUsed = Boolean(runtimeStatus?.fallback_used)

  return (
    <section className="panel" style={{ padding: 12 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Runtime</p>
          <h2>City Runtime Selector</h2>
        </div>
      </div>
      <div className="drawer-grid case-health-grid">
        <span>Selected runtime</span><strong>{selected}</strong>
        <span>Available</span><strong>{available.join(', ') || 'none'}</strong>
        <span>Fallback used</span><strong>{fallbackUsed ? 'true' : 'false'}</strong>
        <span>RPC connected</span><strong>{runtimeStatus?.connected ? 'true' : 'false'}</strong>
      </div>
      <div className="button-row" style={{ marginTop: 10 }}>
        <button type="button" className="text-button" onClick={() => onLaunchRuntime?.('CityEnviron')} disabled={launching}>
          Launch CityEnviron
        </button>
        <button type="button" className="text-button" onClick={() => onLaunchRuntime?.('AirSimNH')} disabled={launching}>
          Launch AirSimNH
        </button>
        <button type="button" className="text-button" onClick={() => onLaunchRuntime?.('Blocks')} disabled={launching}>
          Launch Blocks
        </button>
        <button type="button" className="text-button" onClick={onRefreshStatus}>
          Refresh
        </button>
      </div>
      <p className="muted" style={{ marginTop: 8 }}>
        Simulated source only. Operator review required.
      </p>
    </section>
  )
}
