import { useState } from 'react'
import OpenVocabResultDetail from './OpenVocabResultDetail'
import { formatTimestamp } from '../../utils/time'

const STATUS_COLORS = {
  completed: '#34d399',
  unavailable: '#fbbf24',
  error: '#f87171',
  cooldown: '#9ca3af',
}

/**
 * OpenVocabResultsPanel — table of recent open-vocab scan results.
 * Click a row to see full detail in the same panel.
 */
export default function OpenVocabResultsPanel({ results, loading, onRefresh }) {
  const [selected, setSelected] = useState(null)

  if (selected) {
    return (
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header">
          <div>
            <p className="eyebrow">Results</p>
            <h2>Scan Detail</h2>
          </div>
          <button className="ctrl-btn" onClick={() => setSelected(null)}>Back to List</button>
        </div>
        <div style={{ padding: '10px 12px' }}>
          <OpenVocabResultDetail result={selected} onClose={() => setSelected(null)} />
        </div>
      </div>
    )
  }

  return (
    <div className="panel" style={{ marginBottom: 16 }}>
      <div className="panel-header">
        <div>
          <p className="eyebrow">Recent</p>
          <h2>Scan Results</h2>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className="count-pill">{results.length}</span>
          <button className="ctrl-btn" onClick={onRefresh} title="Refresh">↺</button>
        </div>
      </div>

      {loading && results.length === 0 && (
        <p style={{ color: '#6b7280', fontSize: '0.78rem', padding: '10px 12px' }}>Loading results…</p>
      )}
      {!loading && results.length === 0 && (
        <p style={{ color: '#6b7280', fontSize: '0.78rem', padding: '10px 12px' }}>No scan results yet.</p>
      )}

      {results.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.73rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #1c2535', color: '#4b5563', textTransform: 'uppercase', fontSize: '0.58rem', letterSpacing: 1 }}>
                <th style={{ padding: '6px 12px', textAlign: 'left' }}>Scan ID</th>
                <th style={{ padding: '6px 8px', textAlign: 'left' }}>Camera</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Status</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Risk</th>
                <th style={{ padding: '6px 8px', textAlign: 'center' }}>Detections</th>
                <th style={{ padding: '6px 8px', textAlign: 'left' }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {results.map(result => (
                <tr
                  key={result.scan_id}
                  onClick={() => setSelected(result)}
                  style={{
                    borderBottom: '1px solid #111827', cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = '#0a0f1a'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '6px 12px', fontFamily: 'monospace', fontSize: '0.68rem', color: '#9ca3af' }}>
                    {result.scan_id?.slice(0, 16) || '—'}…
                  </td>
                  <td style={{ padding: '6px 8px', color: '#d1d5db' }}>
                    {result.camera_id || <span style={{ color: '#4b5563' }}>—</span>}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    <span style={{
                      padding: '1px 7px', borderRadius: 10, fontSize: '0.6rem', fontWeight: 700,
                      color: STATUS_COLORS[result.status] || '#9ca3af',
                      background: `${STATUS_COLORS[result.status] || '#9ca3af'}18`,
                    }}>
                      {result.status || '—'}
                    </span>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                    {result.risk_score != null ? (
                      <span style={{
                        color: result.risk_score >= 0.55 ? '#ef4444' : result.risk_score >= 0.35 ? '#f97316' : '#34d399',
                        fontWeight: 600,
                      }}>
                        {(result.risk_score * 100).toFixed(1)}%
                      </span>
                    ) : <span style={{ color: '#4b5563' }}>—</span>}
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center', color: '#d1d5db' }}>
                    {Array.isArray(result.detections) ? result.detections.length : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', color: '#6b7280', fontSize: '0.7rem' }}>
                    {result.created_at ? formatTimestamp(result.created_at) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
