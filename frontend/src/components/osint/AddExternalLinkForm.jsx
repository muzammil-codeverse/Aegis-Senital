import { useState } from 'react'

const INITIAL_FORM = {
  title: '',
  url: '',
  description: '',
  source_reliability: 'unknown',
}

export default function AddExternalLinkForm({ busy, disabled, onSubmit }) {
  const [form, setForm] = useState(INITIAL_FORM)

  function submit(event) {
    event.preventDefault()
    if (!form.url.trim()) return
    onSubmit?.({
      source_type: 'external_link',
      title: form.title,
      url: form.url,
      description: form.description,
      source_reliability: form.source_reliability,
      metadata: {},
    })
    setForm(INITIAL_FORM)
  }

  return (
    <form className="case-inline-form" onSubmit={submit}>
      <input value={form.title} onChange={event => setForm(current => ({ ...current, title: event.target.value }))} placeholder="Analyst-provided article title" />
      <input value={form.url} onChange={event => setForm(current => ({ ...current, url: event.target.value }))} placeholder="https://example.com/manual-source" />
      <input value={form.description} onChange={event => setForm(current => ({ ...current, description: event.target.value }))} placeholder="Manual source context" />
      <select value={form.source_reliability} onChange={event => setForm(current => ({ ...current, source_reliability: event.target.value }))}>
        <option value="unknown">Reliability unknown</option>
        <option value="low">Reliability low</option>
        <option value="medium">Reliability medium</option>
        <option value="high">Reliability high</option>
      </select>
      <button type="submit" className="text-button" disabled={busy || disabled}>Add Link</button>
    </form>
  )
}
