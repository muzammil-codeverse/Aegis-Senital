import { useEffect, useState } from 'react'
import axios from 'axios'

const API = 'http://127.0.0.1:8000'

const SCENARIOS = [
  { value: 'security',  label: 'Security Mode',   desc: 'Weapons · Loitering · Intrusion' },
  { value: 'classroom', label: 'Classroom Mode',  desc: 'Overcrowding · Unauthorized devices' },
  { value: 'traffic',   label: 'Traffic Mode',    desc: 'Pedestrians · Vehicle density' },
]

const SEVERITY_STYLES = {
  high:   'bg-red-900 text-red-200 border border-red-700',
  medium: 'bg-yellow-900 text-yellow-200 border border-yellow-700',
  low:    'bg-slate-700 text-slate-300 border border-slate-600',
}

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [scenario, setScenario] = useState('security')
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
      const r = await axios.post(`${API}/process-video?scenario=${scenario}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setAnalysisResult(r.data)
    } catch (e) {
      setUploadError(e.response?.data?.detail || 'Analysis failed — check backend logs')
    } finally {
      setUploading(false)
    }
  }

  // Flatten all detected objects across all sampled frames
  const allObjects = analysisResult?.detections?.flatMap(f => f.objects) ?? []
  const labelCounts = allObjects.reduce((acc, obj) => {
    acc[obj.type] = (acc[obj.type] || 0) + 1
    return acc
  }, {})

  const confirmedEvents = analysisResult?.event_summary?.events ?? []

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
        <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 space-y-4">

          {/* Scenario Selector */}
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Scenario</p>
            <div className="flex flex-wrap gap-2">
              {SCENARIOS.map(s => (
                <button
                  key={s.value}
                  onClick={() => { setScenario(s.value); setAnalysisResult(null) }}
                  className={`px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                    scenario === s.value
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  <span className="font-medium block">{s.label}</span>
                  <span className="text-xs opacity-70">{s.desc}</span>
                </button>
              ))}
            </div>
          </div>

          {/* File Input + Analyze */}
          <div className="flex flex-wrap gap-3 items-center">
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
              Running YOLO · Tracker · {SCENARIOS.find(s => s.value === scenario)?.label} — this may take a moment...
            </p>
          )}

          {uploadError && <p className="text-sm text-red-400">{uploadError}</p>}

          {/* Results */}
          {analysisResult && (
            <div className="space-y-4 pt-1 border-t border-slate-700">

              {/* Stats row */}
              <div className="flex flex-wrap gap-6 text-sm">
                <span className="text-slate-400">
                  Scenario: <span className="text-indigo-300 font-medium">{analysisResult.scenario}</span>
                </span>
                <span className="text-slate-400">
                  Frames: <span className="text-white font-medium">{analysisResult.frames}</span>
                </span>
                <span className="text-slate-400">
                  Sampled: <span className="text-white font-medium">{analysisResult.frames_sampled}</span>
                </span>
                <span className="text-slate-400">
                  Detections: <span className="text-white font-medium">{allObjects.length}</span>
                </span>
              </div>

              {/* Detected object labels */}
              {allObjects.length > 0 ? (
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-2">Detected objects</p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(labelCounts)
                      .sort((a, b) => b[1] - a[1])
                      .map(([label, count]) => (
                        <span key={label} className="text-xs px-2.5 py-1 bg-indigo-900 text-indigo-200 rounded-full font-medium">
                          {label} &times; {count}
                        </span>
                      ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-slate-500">No objects detected in sampled frames.</p>
              )}

              {/* Confirmed events */}
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <p className="text-xs text-slate-500 uppercase tracking-wide">Confirmed Events</p>
                  <div className="flex gap-2 text-xs">
                    {analysisResult.event_summary.high > 0 &&
                      <span className="px-2 py-0.5 rounded bg-red-900 text-red-200">
                        {analysisResult.event_summary.high} HIGH
                      </span>}
                    {analysisResult.event_summary.medium > 0 &&
                      <span className="px-2 py-0.5 rounded bg-yellow-900 text-yellow-200">
                        {analysisResult.event_summary.medium} MED
                      </span>}
                    {analysisResult.event_summary.low > 0 &&
                      <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300">
                        {analysisResult.event_summary.low} LOW
                      </span>}
                  </div>
                </div>

                {confirmedEvents.length > 0 ? (
                  <ul className="space-y-1.5">
                    {confirmedEvents.map((e, i) => (
                      <li key={i} className={`flex items-start gap-3 px-3 py-2 rounded-lg text-sm ${SEVERITY_STYLES[e.severity] ?? SEVERITY_STYLES.low}`}>
                        <span className="font-mono font-bold shrink-0">
                          {e.severity === 'high' ? '🔴' : e.severity === 'medium' ? '🟡' : '⚪'}
                        </span>
                        <span className="font-medium shrink-0">{e.event_type}</span>
                        <span className="opacity-80 text-xs self-center">{e.detail}</span>
                        <span className="ml-auto text-xs opacity-50 shrink-0">f#{e.frame_id}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-500">
                    No sustained events confirmed ({analysisResult.event_summary.total} raw triggers).
                  </p>
                )}
              </div>

              {analysisResult.output_frames.length > 0 && (
                <p className="text-xs text-slate-600">
                  {analysisResult.output_frames.length} annotated frames saved to{' '}
                  <code className="text-slate-400">backend/output/</code>
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
