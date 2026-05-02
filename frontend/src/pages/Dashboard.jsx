import { useEffect, useState } from 'react'
import axios from 'axios'

const API = 'http://127.0.0.1:8000'

export default function Dashboard() {
  const [health, setHealth] = useState(null)
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
