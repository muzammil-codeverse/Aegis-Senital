import { useState } from 'react'

export default function DroneControlPanel({
  canControl,
  status,
  actionError,
  onStart,
  onStop,
  onTakeoff,
  onLand,
  onHover,
  onMove,
}) {
  const [form, setForm] = useState({ x: 0, y: 0, z: -30, velocity: 5 })
  const active = Boolean(status?.session?.active)

  return (
    <section className="rounded border bg-white p-4 shadow-sm">
      <div className="mb-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Control</p>
        <h2 className="text-base font-semibold text-slate-900">Operator actions</h2>
      </div>
      {!canControl ? (
        <p className="text-xs text-slate-500">You do not have drone:control permission.</p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <button type="button" className="rounded bg-slate-900 px-3 py-2 text-xs text-white" onClick={onStart}>
              Start session
            </button>
            <button type="button" className="rounded border px-3 py-2 text-xs text-slate-700" onClick={onStop}>
              Stop session
            </button>
            <button type="button" className="rounded border px-3 py-2 text-xs text-slate-700" onClick={onTakeoff} disabled={!active}>
              Takeoff
            </button>
            <button type="button" className="rounded border px-3 py-2 text-xs text-slate-700" onClick={onLand} disabled={!active}>
              Land
            </button>
            <button type="button" className="rounded border px-3 py-2 text-xs text-slate-700" onClick={onHover} disabled={!active}>
              Hover
            </button>
          </div>
          <div className="grid gap-2 md:grid-cols-4">
            {['x', 'y', 'z', 'velocity'].map(field => (
              <label key={field} className="text-xs text-slate-600">
                {field}
                <input
                  type="number"
                  value={form[field]}
                  onChange={event => setForm(previous => ({ ...previous, [field]: Number(event.target.value) }))}
                  className="mt-1 w-full rounded border px-2 py-2 text-xs"
                />
              </label>
            ))}
          </div>
          <button
            type="button"
            className="mt-3 rounded bg-amber-500 px-3 py-2 text-xs font-medium text-slate-950"
            disabled={!active}
            onClick={() => onMove(form)}
          >
            Move to candidate aerial path point
          </button>
          {actionError ? <p className="mt-3 text-xs text-rose-700">{actionError}</p> : null}
        </>
      )}
    </section>
  )
}
