function formatNumber(value, digits = 4) {
  if (value == null || Number.isNaN(Number(value))) return 'n/a'
  return Number(value).toFixed(digits)
}

export default function DroneTelemetryPanel({ telemetry }) {
  const orientation = telemetry?.orientation || {}
  const position = telemetry?.position || {}
  const velocity = telemetry?.velocity || {}

  return (
    <section className="rounded border bg-white p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Telemetry</p>
        <h2 className="text-base font-semibold text-slate-900">Simulated telemetry readout</h2>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded bg-slate-50 p-3 text-xs">
          <div className="font-medium text-slate-700">Geo</div>
          <div className="mt-2 text-slate-600">Latitude: {formatNumber(telemetry?.latitude)}</div>
          <div className="text-slate-600">Longitude: {formatNumber(telemetry?.longitude)}</div>
          <div className="text-slate-600">Altitude: {formatNumber(telemetry?.altitude_meters, 2)} m</div>
          <div className="text-slate-600">Timestamp: {telemetry?.timestamp || 'n/a'}</div>
        </div>
        <div className="rounded bg-slate-50 p-3 text-xs">
          <div className="font-medium text-slate-700">Pose</div>
          <div className="mt-2 text-slate-600">Position: x {formatNumber(position.x, 2)} / y {formatNumber(position.y, 2)} / z {formatNumber(position.z, 2)}</div>
          <div className="text-slate-600">Velocity: x {formatNumber(velocity.x, 2)} / y {formatNumber(velocity.y, 2)} / z {formatNumber(velocity.z, 2)}</div>
          <div className="text-slate-600">Orientation: pitch {formatNumber(orientation.pitch, 2)} / roll {formatNumber(orientation.roll, 2)} / yaw {formatNumber(orientation.yaw, 2)}</div>
          <div className="text-slate-600">Camera: {telemetry?.camera_name || 'front_center'}</div>
        </div>
      </div>
    </section>
  )
}
