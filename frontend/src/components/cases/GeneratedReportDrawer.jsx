import LlmSafetyBadge from './LlmSafetyBadge'

export default function GeneratedReportDrawer({ open, output, onClose }) {
  if (!open || !output) return null
  return (
    <div className="report-drawer-backdrop" onClick={onClose}>
      <aside className="report-drawer" onClick={event => event.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <p className="eyebrow">Generated Report</p>
            <h2>{output.metadata?.report_type || output.task_type || 'AI-assisted draft'}</h2>
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close generated report">
            x
          </button>
        </div>
        <LlmSafetyBadge output={output} />
        <div className="report-meta">
          <span>Model</span><strong>{output.model}</strong>
          <span>Provider</span><strong>{output.provider}</strong>
          <span>Report ID</span><strong>{output.report_id || 'Not persisted'}</strong>
        </div>
        <pre className="llm-content report-body">{output.content}</pre>
        <div className="llm-sources">
          <strong>Evidence references</strong>
          <ul>
            {output.sources?.map(source => (
              <li key={`${source.type}-${source.id}`}>[{source.type}] {source.id} - {source.label}</li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  )
}
