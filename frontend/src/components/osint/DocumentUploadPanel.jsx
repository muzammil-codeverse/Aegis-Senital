import { useState } from 'react'

const INITIAL_FORM = {
  title: '',
  description: '',
  source_reliability: 'unknown',
}

export default function DocumentUploadPanel({ busy, disabled, onUpload }) {
  const [file, setFile] = useState(null)
  const [form, setForm] = useState(INITIAL_FORM)

  function submit(event) {
    event.preventDefault()
    if (!file) return
    onUpload?.(file, {
      title: form.title || file.name,
      description: form.description,
      source_reliability: form.source_reliability,
      metadata: {},
    })
    setFile(null)
    setForm(INITIAL_FORM)
    event.target.reset()
  }

  return (
    <form className="case-inline-form" onSubmit={submit}>
      <input aria-label="Upload document file" type="file" accept=".pdf,.txt,.md,.json,.csv,.png,.jpg,.jpeg" onChange={event => setFile(event.target.files?.[0] || null)} />
      <input aria-label="Document title" value={form.title} onChange={event => setForm(current => ({ ...current, title: event.target.value }))} placeholder="Upload title" />
      <input aria-label="Analyst note" value={form.description} onChange={event => setForm(current => ({ ...current, description: event.target.value }))} placeholder="Analyst note for upload" />
      <select value={form.source_reliability} onChange={event => setForm(current => ({ ...current, source_reliability: event.target.value }))}>
        <option value="unknown">Reliability unknown</option>
        <option value="low">Reliability low</option>
        <option value="medium">Reliability medium</option>
        <option value="high">Reliability high</option>
      </select>
      <button type="submit" className="text-button" disabled={busy || disabled}>Upload</button>
    </form>
  )
}
