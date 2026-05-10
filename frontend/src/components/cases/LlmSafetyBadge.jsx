export default function LlmSafetyBadge({ output, status, compact = false }) {
  const sourceCount = output?.sources?.length || 0
  const providerLabel = output?.provider || status?.active_provider || status?.provider || 'llm'

  return (
    <div className={`llm-badge-row${compact ? ' compact' : ''}`}>
      <span className="llm-badge">AI-assisted draft</span>
      <span className="llm-badge">Requires operator review</span>
      <span className="llm-badge">Source-grounded summary</span>
      <span className={`llm-badge${output?.safety_check_passed === false ? ' danger' : ' success'}`}>
        {output?.safety_check_passed === false ? 'Safety review required' : 'Safety check passed'}
      </span>
      {sourceCount > 0 && <span className="llm-badge muted">Evidence references: {sourceCount}</span>}
      <span className="llm-badge muted">Provider: {providerLabel}</span>
    </div>
  )
}
