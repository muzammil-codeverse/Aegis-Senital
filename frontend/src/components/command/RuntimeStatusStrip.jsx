import { RefreshCcw } from 'lucide-react'

export default function RuntimeStatusStrip({ runtimeStatus, compact = false }) {
  const status = runtimeStatus
  const isLoading = status.loading && (!Array.isArray(status.items) || status.items.length === 0)
  const hasItems = Array.isArray(status.items) && status.items.length > 0

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
        {isLoading ? <p className="muted">Signed in, waiting for runtime status</p> : null}
        {!isLoading && !hasItems ? <p className="muted">No recent data</p> : null}
        {!isLoading && hasItems
          ? status.items.map(item => (
            <article key={item.key} className={`runtime-status-card tone-${item.status}`}>
              <div className="runtime-status-card__top">
                <span>{item.label}</span>
                <strong>{item.status}</strong>
              </div>
              <p>{item.summary}</p>
            </article>
          ))
          : null}
      </div>
    </section>
  )
}
