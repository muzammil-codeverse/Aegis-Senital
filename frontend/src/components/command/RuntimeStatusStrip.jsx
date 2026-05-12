import { RefreshCcw } from 'lucide-react'

export default function RuntimeStatusStrip({ runtimeStatus, compact = false }) {
  const status = runtimeStatus

  return (
    <section className={`runtime-status-strip ${compact ? 'compact' : ''}`} aria-label="Runtime status strip">
      <div className="runtime-status-strip__header">
        <div>
          <p className="eyebrow">Runtime Status</p>
          <h2>Operational dependencies</h2>
        </div>
        <button type="button" className="command-action-button subtle" onClick={status.refresh} aria-label="Refresh runtime status">
          <RefreshCcw size={14} />
          Refresh
        </button>
      </div>
      <div className="runtime-status-strip__items">
        {status.items.map(item => (
          <article key={item.key} className={`runtime-status-card tone-${item.status}`}>
            <div className="runtime-status-card__top">
              <span>{item.label}</span>
              <strong>{item.status}</strong>
            </div>
            <p>{item.summary}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
