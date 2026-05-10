import EmptyState from '../common/EmptyState'
import LlmSafetyBadge from './LlmSafetyBadge'

export default function EvidenceExplanationPanel({ output, busy, onGenerate, canGenerate }) {
  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Evidence Explanation</h3>
        <span>Source-grounded summary</span>
      </div>
      <button type="button" className="text-button" disabled={busy || !canGenerate} onClick={() => onGenerate?.()}>
        Generate Evidence Summary
      </button>
      {!output ? (
        <EmptyState message="No evidence explanation generated yet." />
      ) : (
        <article className="llm-output-card">
          <LlmSafetyBadge output={output} compact />
          <pre className="llm-content">{output.content}</pre>
          <div className="llm-sources">
            <strong>Evidence references</strong>
            <ul>
              {output.sources?.map(source => (
                <li key={`${source.type}-${source.id}`}>[{source.type}] {source.id} - {source.label}</li>
              ))}
            </ul>
          </div>
        </article>
      )}
    </section>
  )
}
