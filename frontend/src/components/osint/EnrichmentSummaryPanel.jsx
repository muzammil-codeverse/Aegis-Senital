import { useState } from 'react'
import EmptyState from '../common/EmptyState'
import { formatTimestamp } from '../../utils/time'

export default function EnrichmentSummaryPanel({ items = [], sourceCount = 0, busy, canSummarize, onSummarize }) {
  const [operatorInstructions, setOperatorInstructions] = useState('')

  function submit(event) {
    event.preventDefault()
    onSummarize?.({
      operator_instructions: operatorInstructions,
      source_ids: [],
    })
    setOperatorInstructions('')
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Enrichment Summaries</h3>
        <span>Source-grounded summary</span>
      </div>
      <form className="case-inline-form" onSubmit={submit}>
        <input aria-label="Summarization instructions" value={operatorInstructions} onChange={event => setOperatorInstructions(event.target.value)} placeholder="Optional summarization instructions" />
        <button type="submit" className="text-button" disabled={busy || !canSummarize || sourceCount === 0}>
          Summarize Enrichment
        </button>
      </form>
      {!items.length ? (
        <EmptyState message="No enrichment summaries generated yet." />
      ) : (
        <div className="stack-list">
          {items.map(item => (
            <article key={item.summary_id} className="llm-output-card">
              <div className="alert-card-header">
                <strong>Requires operator review</strong>
                <span>{formatTimestamp(item.created_at)}</span>
              </div>
              <p className="drawer-description">{item.operator_review_caveat}</p>
              <pre className="llm-content llm-preview">{item.summary}</pre>
              {item.key_points?.length ? (
                <div className="drawer-grid">
                  <span>Key Points</span><strong>{item.key_points.join(' | ')}</strong>
                  <span>Limitations</span><strong>{(item.limitations || []).join(' | ') || 'N/A'}</strong>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
