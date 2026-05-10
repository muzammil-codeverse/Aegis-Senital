import EmptyState from '../common/EmptyState'
import LlmSafetyBadge from './LlmSafetyBadge'

function SourceList({ sources = [] }) {
  if (!sources.length) return null
  return (
    <div className="llm-sources">
      <strong>Evidence references</strong>
      <ul>
        {sources.map(source => (
          <li key={`${source.type}-${source.id}`}>[{source.type}] {source.id} - {source.label}</li>
        ))}
      </ul>
    </div>
  )
}

function OutputCard({ title, output }) {
  if (!output) return <EmptyState message={`No ${title.toLowerCase()} generated yet.`} />
  return (
    <article className="llm-output-card">
      <LlmSafetyBadge output={output} compact />
      <pre className="llm-content">{output.content}</pre>
      <SourceList sources={output.sources} />
    </article>
  )
}

export default function CaseSummaryPanel({
  summaryOutput,
  timelineSummary,
  busy,
  onGenerateCaseSummary,
  onGenerateIncidentSummary,
  onGenerateTimelineSummary,
  canGenerate,
}) {
  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Case Summary</h3>
        <span>AI-assisted draft</span>
      </div>
      <div className="button-row">
        <button type="button" className="text-button" disabled={busy || !canGenerate} onClick={() => onGenerateCaseSummary?.()}>
          Generate Case Summary
        </button>
        <button type="button" className="text-button" disabled={busy || !canGenerate} onClick={() => onGenerateIncidentSummary?.()}>
          Incident Summary
        </button>
        <button type="button" className="text-button" disabled={busy || !canGenerate} onClick={() => onGenerateTimelineSummary?.()}>
          Timeline Summary
        </button>
      </div>
      <div className="llm-output-grid">
        <div>
          <h4>Summary Draft</h4>
          <OutputCard title="Summary Draft" output={summaryOutput} />
        </div>
        <div>
          <h4>Timeline Summary</h4>
          <OutputCard title="Timeline Summary" output={timelineSummary} />
        </div>
      </div>
    </section>
  )
}
