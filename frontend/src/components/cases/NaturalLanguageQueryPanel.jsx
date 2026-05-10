import { useState } from 'react'
import EmptyState from '../common/EmptyState'
import LlmSafetyBadge from './LlmSafetyBadge'

export default function NaturalLanguageQueryPanel({ output, busy, onAsk, canGenerate }) {
  const [question, setQuestion] = useState('')

  function submit(event) {
    event.preventDefault()
    if (!question.trim()) return
    onAsk?.({ question: question.trim() }).then(() => {
      setQuestion('')
    }).catch(() => {})
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Natural-Language Case Q&amp;A</h3>
        <span>Operator review safe</span>
      </div>
      <form className="llm-query-form" onSubmit={submit}>
        <input
          value={question}
          onChange={event => setQuestion(event.target.value)}
          placeholder="Ask a grounded question about this case"
        />
        <button type="submit" className="text-button" disabled={busy || !canGenerate}>
          Ask
        </button>
      </form>
      {!output ? (
        <EmptyState message="No case Q&A response generated yet." />
      ) : (
        <article className="llm-output-card">
          <LlmSafetyBadge output={output} compact />
          <pre className="llm-content">{output.content}</pre>
        </article>
      )}
    </section>
  )
}
