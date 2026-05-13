import { useRef, useState } from 'react'

export default function UploadedVideoDropzone({ onUpload, busy = false }) {
  const inputRef = useRef(null)
  const [dragActive, setDragActive] = useState(false)
  const [localError, setLocalError] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)

  function validate(file) {
    if (!file) return 'Choose a video file to continue.'
    const allowed = ['.mp4', '.avi', '.mov', '.mkv']
    const extension = `.${(file.name.split('.').pop() || '').toLowerCase()}`
    if (!allowed.includes(extension)) {
      return `Unsupported file type ${extension}.`
    }
    return null
  }

  function handleFile(file) {
    const error = validate(file)
    setLocalError(error)
    if (error || !file) {
      setSelectedFile(null)
      return
    }
    setSelectedFile(file)
  }

  return (
    <section className={`panel upload-dropzone ${dragActive ? 'drag-active' : ''}`}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Phase 38</p>
          <h2>Uploaded Video Analysis</h2>
        </div>
        <span className="count-pill">Managed Storage</span>
      </div>
      <button
        type="button"
        className="upload-dropzone-body"
        onClick={() => inputRef.current?.click()}
        onDragEnter={event => { event.preventDefault(); setDragActive(true) }}
        onDragOver={event => { event.preventDefault(); setDragActive(true) }}
        onDragLeave={event => { event.preventDefault(); setDragActive(false) }}
        onDrop={event => {
          event.preventDefault()
          setDragActive(false)
          handleFile(event.dataTransfer.files?.[0] || null)
        }}
        disabled={busy}
      >
        <strong>Drop an evidence video here</strong>
        <span>MP4, AVI, MOV, MKV. The upload is validated, hashed, and stored under managed paths.</span>
      </button>
      <div className="button-row">
        <button type="button" className="primary-button" onClick={() => inputRef.current?.click()} disabled={busy}>
          {busy ? 'Uploading...' : 'Select video'}
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={busy || !selectedFile}
          onClick={() => selectedFile && onUpload(selectedFile)}
        >
          {busy ? 'Uploading...' : 'Upload selected file'}
        </button>
        <span className="muted">
          {selectedFile ? `${selectedFile.name} (${Math.round(selectedFile.size / 1024)} KB)` : 'No file selected'}
        </span>
      </div>
      {localError ? <p className="error-text">{localError}</p> : null}
      <input
        ref={inputRef}
        aria-label="Upload video file"
        type="file"
        accept=".mp4,.avi,.mov,.mkv,video/mp4,video/x-msvideo,video/quicktime,video/x-matroska"
        hidden
        onChange={event => handleFile(event.target.files?.[0] || null)}
      />
    </section>
  )
}
