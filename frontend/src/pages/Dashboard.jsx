import { useEffect, useState } from 'react'
import axios from 'axios'

const API = 'http://127.0.0.1:8000'

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [videoFile, setVideoFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [analysisResult, setAnalysisResult] = useState(null)
  const [uploadError, setUploadError] = useState(null)
  const [alerts] = useState([
    { id: 1, time: '14:02:11', message: 'Unattended object detected — Zone A' },
    { id: 2, time: '14:01:47', message: 'Person loitering > 30s — Entrance' },
    { id: 3, time: '13:58:03', message: 'Motion detected in restricted zone' },
  ])
  const [logs] = useState([
    { id: 1, time: '14:02:30', message: 'Frame pipeline OK — 30 fps' },
    { id: 2, time: '14:02:00', message: 'Scenario loaded: security' },
    { id: 3, time: '14:01:00', message: 'DetectionEngine initialized' },
    { id: 4, time: '14:00:00', message: 'System startup complete' },
  ])

  useEffect(() => {
    axios.get(`${API}/health`)
      .then(r => setHealth(r.data))
      .catch(() => setHealth({ status: 'unreachable' }))
  }, [])

  async function handleAnalyze() {
    if (!videoFile) return
    setUploading(true)
    setAnalysisResult(null)
    setUploadError(null)

    const form = new FormData()
    form.append('file', videoFile)

    try {
      const r = await axios.post(`${API}/process-video`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setAnalysisResult(r.data)
    } catch (e) {
      setUploadError(e.response?.data?.detail || 'Analysis failed — check backend logs')
    } finally {
      setUploading(false)
    }
  }

  const labelCounts = analysisResult?.detections
    ? analysisResult.detections.reduce((acc, d) => {
        acc[d.label] = (acc[d.label] || 0) + 1
        return acc
      }, {})
    : {}

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 p-6">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Sentinel AI — Dashboard</h1>
        <span className={`text-sm px-3 py-1 rounded-full font-medium ${
          health?.status === 'ok' ? 'bg-green-800 text-green-200' : 'bg-red-800 text-red-200'
        }`}>
          Backend: {health ? health.status : 'connecting...'}
        </span>
      </header>

      {/* Video Analysis */}
      <section className="mb-6">
        <h2 className="text-lg font-semibold mb-3 text-slate-300">Video Analysis</h2>
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
          <div className="flex flex-wrap gap-3 items-center mb-4">
            <input
              type="file"
              accept=".mp4,.avi,.mov,.mkv"
              onChange={e => {
                setVideoFile(e.target.files[0] || null)
                setAnalysisResult(null)
                setUploadError(null)
              }}
              className="text-sm text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-slate-700 file:text-slate-200 file:cursor-pointer hover:file:bg-slate-600"
            />
            <button
              onClick={handleAnalyze}
              disabled={!videoFile || uploading}
              className="px-4 py-1.5 text-sm font-medium rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {uploading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>

          {uploading && (
            <p className="text-sm text-slate-400 animate-pulse">
              Running YOLO inference — this may take a moment...
            </p>
          )}

          {uploadError && (
            <p className="text-sm text-red-400">{uploadError}</p>
          )}

          {analysisResult && (
            <div className="space-y-3">
              <div className="flex gap-6 text-sm">
                <span className="text-slate-400">
                  Total frames: <span className="text-white font-medium">{analysisResult.frames}</span>
                </span>
                <span className="text-slate-400">
                  Frames sampled: <span className="text-white font-medium">{analysisResult.output_frames.length}</span>
                </span>
                <span className="text-slate-400">
                  Detections: <span className="text-white font-medium">{analysisResult.detections.length}</span>
                </span>
              </div>

              {analysisResult.detections.length > 0 ? (
                <div>
                  <p className="text-xs text-slate-500 mb-2 uppercase tracking-wide">Detected objects</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(labelCounts)
                      .sort((a, b) => b[1] - a[1])
                      .map(([label, count]) => (
                        <span
                          key={label}
                          className="text-xs px-2.5 py-1 bg-indigo-900 text-indigo-200 rounded-full font-medium"
                        >
                          {label} &times; {count}
                        </span>
                      ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-500">No objects detected in sampled frames.</p>
              )}

              {analysisResult.output_frames.length > 0 && (
                <p className="text-xs text-slate-600">
                  Annotated frames saved to <code className="text-slate-400">backend/output/</code>
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Live Feed */}
      <section className="mb-6">
        <h2 className="text-lg font-semibold mb-3 text-slate-300">Live Surveillance Feed</h2>
        <div className="bg-slate-800 border border-slate-700 rounded-xl h-64 flex items-center justify-center">
          <div className="text-center text-slate-500">
            <div className="text-5xl mb-2">📷</div>
            <p className="text-sm">Camera feed not connected</p>
            <p className="text-xs mt-1 text-slate-600">Awaiting video source</p>
          </div>
        </div>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Alerts */}
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300">Alerts</h2>
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            {alerts.length === 0 ? (
              <p className="p-4 text-slate-500 text-sm">No active alerts</p>
            ) : (
              <ul>
                {alerts.map((a, i) => (
                  <li key={a.id} className={`flex gap-3 px-4 py-3 text-sm ${i < alerts.length - 1 ? 'border-b border-slate-700' : ''}`}>
                    <span className="text-red-400 font-medium shrink-0">⚠</span>
                    <span className="text-slate-400 shrink-0">{a.time}</span>
                    <span className="text-slate-200">{a.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Logs */}
        <section>
          <h2 className="text-lg font-semibold mb-3 text-slate-300">System Logs</h2>
          <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
            {logs.length === 0 ? (
              <p className="p-4 text-slate-500 text-sm">No logs</p>
            ) : (
              <ul>
                {logs.map((l, i) => (
                  <li key={l.id} className={`flex gap-3 px-4 py-3 text-sm font-mono ${i < logs.length - 1 ? 'border-b border-slate-700' : ''}`}>
                    <span className="text-slate-500 shrink-0">{l.time}</span>
                    <span className="text-slate-300">{l.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
