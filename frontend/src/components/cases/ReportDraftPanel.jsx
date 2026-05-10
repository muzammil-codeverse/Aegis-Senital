import EmptyState from '../common/EmptyState'
import LlmSafetyBadge from './LlmSafetyBadge'

export default function ReportDraftPanel({
  output,
  busy,
  onGenerateDraft,
  onGenerateHandoff,
  onOpenReport,
  canGenerate,
  canReport,
  enrichmentCount = 0,
}) {
  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Report Drafts</h3>
        <span>Requires operator review</span>
      </div>
      <div className="button-row">
        <button type="button" className="text-button" disabled={busy || !canReport} onClick={() => onGenerateDraft?.()}>
          Draft Case Report
        </button>
        <button type="button" className="text-button" disabled={busy || !canReport} onClick={() => onGenerateHandoff?.()}>
          Operator Handoff
        </button>
        <button type="button" className="text-button" disabled={!output || !canGenerate} onClick={() => onOpenReport?.()}>
          Open Generated Report
        </button>
      </div>
      {enrichmentCount > 0 ? <p className="drawer-description">Analyst-provided enrichment will be included as source-grounded context when available.</p> : null}
      {!output ? (
        <EmptyState message="No generated report is ready yet." />
      ) : (
        <article className="llm-output-card">
          <LlmSafetyBadge output={output} compact />
          <pre className="llm-content llm-preview">{output.content}</pre>
        </article>
      )}
    </section>
  )
}
