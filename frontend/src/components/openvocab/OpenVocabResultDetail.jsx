import { formatTimestamp } from '../../utils/time'

const SEVERITY_COLORS = {
  low: '#34d399', medium: '#fbbf24', high: '#f97316', critical: '#ef4444',
}

function BBoxDisplay({ bbox }) {
  if (!Array.isArray(bbox) || bbox.length < 4) return <span style={{ color: '#6b7280' }}>—</span>
  return (
    <span style={{ fontFamily: 'monospace', fontSize: '0.68rem', color: '#9ca3af' }}>
      [{bbox.map(v => typeof v === 'number' ? v.toFixed(1) : v).join(', ')}]
    </span>
  )
}

/**
 * OpenVocabResultDetail — full detail for a single scan result including
 * detection table, risk score, status, and error handling.
 */
export default function OpenVocabResultDetail({ result, onClose }) {
  if (!result) return null

  const detections = result.detections || []
  const isError = result.status === 'error' || result.status === 'unavailable'
  const riskPct = result.risk_score != null ? (result.risk_score * 100).toFixed(1) : null
  const riskColor = result.risk_score >= 0.55 ? '#ef4444' : result.risk_score >= 0.35 ? '#f97316' : '#34d399'

  return (
    <div style={{
      background: '#0d1117', border: '1px solid #1c2535', borderRadius: 6,
      padding: 16, position: 'relative',
    }}>
      {onClose && (
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: 10, right: 10, background: 'none', border: 'none', color: '#4b5563', cursor: 'pointer', fontSize: '0.9rem' }}
          aria-label="Close"
        >
          ✕
        </button>
      )}

      <p style={{ margin: '0 0 10px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1.5 }}>
        Scan Detail
      </p>

      {/* Status banner */}
      {isError && (
        <div style={{
          background: '#431407', border: '1px solid #7c2d12', borderRadius: 4,
          padding: '6px 10px', marginBottom: 12, fontSize: '0.72rem', color: '#fdba74',
        }}>
          {result.status === 'unavailable' ? 'Model unavailable' : 'Scan error'}
          {result.error && <span style={{ color: '#9ca3af', marginLeft: 6 }}>{result.error}</span>}
        </div>
      )}

      {/* Summary row */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12, fontSize: '0.75rem' }}>
        <span style={{ color: '#6b7280' }}>
          Scan ID: <span style={{ color: '#9ca3af', fontFamily: 'monospace' }}>{result.scan_id || '—'}</span>
        </span>
        <span style={{ color: '#6b7280' }}>
          Status: <strong style={{
            color: result.status === 'completed' ? '#34d399' : result.status === 'unavailable' ? '#fbbf24' : '#f87171',
          }}>
            {result.status || '—'}
          </strong>
        </span>
        {riskPct != null && (
          <span style={{ color: '#6b7280' }}>
            Risk: <strong style={{ color: riskColor }}>{riskPct}%</strong>
          </span>
        )}
        {result.camera_id && (
          <span style={{ color: '#6b7280' }}>
            Camera: <span style={{ color: '#d1d5db' }}>{result.camera_id}</span>
          </span>
        )}
        {result.frame_id != null && (
          <span style={{ color: '#6b7280' }}>
            Frame: <span style={{ color: '#d1d5db' }}>#{result.frame_id}</span>
          </span>
        )}
        {result.source && (
          <span style={{ color: '#6b7280' }}>
            Source: <span style={{ color: '#d1d5db' }}>{result.source}</span>
          </span>
        )}
        {result.created_at && (
          <span style={{ color: '#6b7280' }}>
            At: <span style={{ color: '#9ca3af' }}>{formatTimestamp(result.created_at)}</span>
          </span>
        )}
      </div>

      {/* Prompts used */}
      {result.prompts?.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <p style={{ margin: '0 0 5px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1 }}>
            Prompts Used
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {result.prompts.map((p, i) => (
              <span key={i} style={{
                padding: '2px 8px', borderRadius: 10, background: '#1e3a5f',
                color: '#93c5fd', fontSize: '0.68rem', border: '1px solid #1d4ed8',
              }}>
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Detections table */}
      <div>
        <p style={{ margin: '0 0 6px', fontSize: '0.6rem', color: '#4b5563', textTransform: 'uppercase', letterSpacing: 1 }}>
          Detections ({detections.length})
        </p>
        {detections.length === 0 ? (
          <p style={{ color: '#6b7280', fontSize: '0.75rem' }}>
            {result.status === 'completed' ? 'No threats detected.' : 'No detections available.'}
          </p>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.73rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #1c2535', color: '#4b5563', textTransform: 'uppercase', fontSize: '0.58rem', letterSpacing: 1 }}>
                  <th style={{ padding: '5px 8px', textAlign: 'left' }}>Label</th>
                  <th style={{ padding: '5px 8px', textAlign: 'left' }}>Severity</th>
                  <th style={{ padding: '5px 8px', textAlign: 'center' }}>Confidence</th>
                  <th style={{ padding: '5px 8px', textAlign: 'left' }}>BBox</th>
                  <th style={{ padding: '5px 8px', textAlign: 'left' }}>Model</th>
                </tr>
              </thead>
              <tbody>
                {detections.map((det, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #111827' }}>
                    <td style={{ padding: '5px 8px', color: '#e5e7eb' }}>{det.label || '—'}</td>
                    <td style={{ padding: '5px 8px' }}>
                      {det.severity ? (
                        <span style={{ color: SEVERITY_COLORS[det.severity] || '#9ca3af', fontWeight: 600 }}>
                          {det.severity}
                        </span>
                      ) : <span style={{ color: '#6b7280' }}>—</span>}
                    </td>
                    <td style={{ padding: '5px 8px', textAlign: 'center', color: '#d1d5db' }}>
                      {det.confidence != null ? `${(det.confidence * 100).toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ padding: '5px 8px' }}>
                      <BBoxDisplay bbox={det.bbox} />
                    </td>
                    <td style={{ padding: '5px 8px', color: '#6b7280', fontFamily: 'monospace', fontSize: '0.68rem' }}>
                      {det.source_model || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
