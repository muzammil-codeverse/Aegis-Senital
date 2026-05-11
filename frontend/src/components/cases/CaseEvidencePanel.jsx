import { useState } from 'react'
import EmptyState from '../common/EmptyState'
import ReplayClipPanel from '../streaming/ReplayClipPanel'
import { formatTimestamp } from '../../utils/time'

function integrityLabel(status) {
  switch (String(status || '').toLowerCase()) {
    case 'verified':
      return 'Verified'
    case 'missing_file':
      return 'Missing file'
    case 'hash_mismatch':
      return 'Hash mismatch'
    case 'not_applicable':
      return 'Not file-backed'
    default:
      return 'Operator review required'
  }
}

function downloadBlob(payload) {
  if (!payload?.blob) return
  const href = URL.createObjectURL(payload.blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = payload.filename || 'evidence.bin'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(href)
}

export default function CaseEvidencePanel({
  items = [],
  onAddEvidence,
  onUploadEvidenceFile,
  onVerifyEvidence,
  onDownloadEvidence,
  onExportManifest,
  busy,
  caseId = null,
  defaultCameraId = null,
  legalHoldEnabled = false,
}) {
  const [form, setForm] = useState({
    evidence_type: 'event',
    title: '',
    description: '',
    source_event_id: '',
    storage_uri: '',
  })
  const [uploadForm, setUploadForm] = useState({
    file: null,
    title: '',
    description: '',
    evidence_type: 'upload',
    camera_id: defaultCameraId || '',
    track_ids: '',
  })

  function submit(event) {
    event.preventDefault()
    onAddEvidence?.(form)
    setForm({ evidence_type: 'event', title: '', description: '', source_event_id: '', storage_uri: '' })
  }

  async function submitUpload(event) {
    event.preventDefault()
    if (!uploadForm.file) return
    const data = new FormData()
    data.append('file', uploadForm.file)
    data.append('title', uploadForm.title)
    data.append('description', uploadForm.description)
    data.append('evidence_type', uploadForm.evidence_type)
    data.append('camera_id', uploadForm.camera_id)
    data.append('track_ids', uploadForm.track_ids)
    await onUploadEvidenceFile?.(data)
    setUploadForm(current => ({
      ...current,
      file: null,
      title: '',
      description: '',
      evidence_type: 'upload',
      track_ids: '',
    }))
    event.target.reset()
  }

  async function handleDownload(item) {
    const payload = await onDownloadEvidence?.(item.evidence_id)
    downloadBlob(payload)
  }

  async function handleManifestExport() {
    const manifest = await onExportManifest?.()
    if (!manifest) return
    const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' })
    downloadBlob({
      blob,
      filename: `case-evidence-manifest-${caseId || 'case'}.json`,
    })
  }

  async function copyHash(hash) {
    if (!hash) return
    try {
      await navigator.clipboard.writeText(hash)
    } catch (_error) {
      // Browser clipboard permission failures can be ignored here.
    }
  }

  return (
    <section className="drawer-section">
      <div className="panel-subheader">
        <h3>Evidence</h3>
        <span>{items.length} item(s)</span>
      </div>
      <div className="button-row" style={{ marginBottom: 12 }}>
        <button type="button" className="text-button" disabled={busy} onClick={handleManifestExport}>
          Export Manifest
        </button>
        {legalHoldEnabled ? <span className="state-chip">legal hold</span> : null}
      </div>
      {items.length === 0 ? (
        <EmptyState message="No evidence items attached." />
      ) : (
        <div className="stack-list">
          {items.map(item => (
            <article key={item.evidence_id} className="case-subcard">
              <div className="alert-card-header">
                <strong>{item.title || item.evidence_type}</strong>
                <span className="state-chip">{item.evidence_type}</span>
                <span className="state-chip">{integrityLabel(item.integrity_status)}</span>
                {item.chain_status === 'legal_hold' ? <span className="state-chip">legal hold</span> : null}
              </div>
              <p className="drawer-description">{item.description || 'Evidence item requires operator review.'}</p>
              <div className="drawer-grid">
                <span>Timestamp</span><strong>{formatTimestamp(item.timestamp || item.created_at)}</strong>
                <span>Camera</span><strong>{item.camera_id || 'N/A'}</strong>
                <span>Source Event</span><strong>{item.source_event_id || 'N/A'}</strong>
                <span>Hash</span><strong>{item.hash_sha256 || 'Metadata only'}</strong>
                <span>Filename</span><strong>{item.safe_filename || item.original_filename || 'N/A'}</strong>
              </div>
              <div className="button-row" style={{ marginTop: 10 }}>
                <button type="button" className="text-button" disabled={busy || !item.hash_sha256} onClick={() => copyHash(item.hash_sha256)}>
                  Copy Hash
                </button>
                <button type="button" className="text-button" disabled={busy} onClick={() => onVerifyEvidence?.(item.evidence_id)}>
                  Verify
                </button>
                <button type="button" className="text-button" disabled={busy || !item.storage_uri || item.integrity_status === 'not_applicable'} onClick={() => handleDownload(item)}>
                  Download
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      <form className="case-inline-form" onSubmit={submitUpload}>
        <input type="file" accept=".mp4,.avi,.mov,.mkv,.jpg,.jpeg,.png,.pdf,.txt,.md,.json,.csv" onChange={event => setUploadForm(current => ({ ...current, file: event.target.files?.[0] || null }))} />
        <input value={uploadForm.title} onChange={event => setUploadForm(current => ({ ...current, title: event.target.value }))} placeholder="Upload title" />
        <input value={uploadForm.description} onChange={event => setUploadForm(current => ({ ...current, description: event.target.value }))} placeholder="Upload description" />
        <select value={uploadForm.evidence_type} onChange={event => setUploadForm(current => ({ ...current, evidence_type: event.target.value }))}>
          <option value="upload">Upload</option>
          <option value="image">Image</option>
          <option value="document">Document</option>
          <option value="clip">Clip</option>
        </select>
        <button type="submit" className="text-button" disabled={busy || !uploadForm.file}>Upload Evidence</button>
      </form>
      <form className="case-inline-form" onSubmit={submit}>
        <select value={form.evidence_type} onChange={event => setForm(current => ({ ...current, evidence_type: event.target.value }))}>
          <option value="event">Event</option>
          <option value="osint">OSINT</option>
          <option value="system_report">System Report</option>
          <option value="external_link">External Link</option>
        </select>
        <input value={form.title} onChange={event => setForm(current => ({ ...current, title: event.target.value }))} placeholder="Evidence title" />
        <input value={form.source_event_id} onChange={event => setForm(current => ({ ...current, source_event_id: event.target.value }))} placeholder="Source event ID" />
        <input value={form.storage_uri} onChange={event => setForm(current => ({ ...current, storage_uri: event.target.value }))} placeholder="Reference URI" />
        <button type="submit" className="text-button" disabled={busy}>Attach</button>
      </form>
      {caseId && defaultCameraId && (
        <div style={{ marginTop: 12 }}>
          <ReplayClipPanel cameraId={defaultCameraId} caseId={caseId} />
        </div>
      )}
    </section>
  )
}
