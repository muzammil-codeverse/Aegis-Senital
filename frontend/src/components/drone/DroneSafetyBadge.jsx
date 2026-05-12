export default function DroneSafetyBadge({ className = '' }) {
  return (
    <div className={`rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 ${className}`}>
      Simulated drone feed. Telemetry, pathing, and aerial observations remain simulated and require operator review.
    </div>
  )
}
