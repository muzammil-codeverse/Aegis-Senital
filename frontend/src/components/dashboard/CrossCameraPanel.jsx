import React, { useMemo, useState } from 'react'

const STATE_COLOR = {
  predicted: '#a78bfa',
  candidate: '#60a5fa',
  confirmed: '#34d399',
  rejected: '#f87171',
  expired: '#6b7280',
}

const STATE_LABEL = {
  predicted: 'Predicted',
  candidate: 'Candidate',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
  expired: 'Expired',
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = value >= 0.8 ? '#34d399' : value >= 0.6 ? '#fbbf24' : '#f87171'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, height: 4, background: '#374151', borderRadius: 2 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.3s' }} />
      </div>
      <span style={{ fontSize: 11, color, minWidth: 32 }}>{pct}%</span>
    </div>
  )
}

function EvidenceRow({ label, value }) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
      <span>{label}</span>
      <span style={{ color: '#d1d5db' }}>{pct}%</span>
    </div>
  )
}

function HandoffCard({ handoff, expanded, onToggle }) {
  const stateColor = STATE_COLOR[handoff.state] ?? '#9ca3af'
  const evidence = handoff.evidence ?? {}

  return (
    <div
      style={{
        background: '#1f2937',
        border: `1px solid ${stateColor}44`,
        borderLeft: `3px solid ${stateColor}`,
        borderRadius: 6,
        marginBottom: 8,
        overflow: 'hidden',
      }}
    >
      <div
        onClick={onToggle}
        style={{
          padding: '8px 10px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'flex-start',
          gap: 8,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3, flexWrap: 'wrap' }}>
            <span
              style={{
                fontSize: 10,
                fontWeight: 600,
                background: stateColor + '22',
                color: stateColor,
                padding: '1px 6px',
                borderRadius: 10,
                letterSpacing: 0.5,
              }}
            >
              {STATE_LABEL[handoff.state] ?? handoff.state}
            </span>
            {handoff.identity_id && (
              <span style={{ fontSize: 10, color: '#9ca3af' }}>
                ID: {handoff.identity_id.slice(0, 8)}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: '#e5e7eb', display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ fontFamily: 'monospace' }}>{handoff.source_camera}</span>
            <span style={{ color: '#6b7280' }}>→</span>
            <span style={{ fontFamily: 'monospace' }}>{handoff.target_camera}</span>
          </div>
          <ConfidenceBar value={handoff.confidence} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2, minWidth: 56 }}>
          {handoff.eta_seconds != null && (
            <span style={{ fontSize: 11, color: '#fbbf24' }}>ETA {handoff.eta_seconds.toFixed(0)}s</span>
          )}
          <span style={{ fontSize: 10, color: '#6b7280' }}>{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ padding: '0 10px 10px', borderTop: '1px solid #374151' }}>
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Evidence Breakdown
            </div>
            <EvidenceRow label="Topology" value={evidence.topology_score} />
            <EvidenceRow label="Temporal" value={evidence.temporal_score} />
            <EvidenceRow label="Motion" value={evidence.motion_score} />
            <EvidenceRow label="Appearance" value={evidence.appearance_score} />
            <EvidenceRow label="Identity" value={evidence.identity_score} />
            <EvidenceRow label="Face" value={evidence.face_score} />
          </div>

          {handoff.route && handoff.route.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Route
              </div>
              <div style={{ fontSize: 11, color: '#d1d5db', fontFamily: 'monospace' }}>
                {handoff.route.join(' → ')}
              </div>
            </div>
          )}

          {handoff.source_track_id != null && (
            <div style={{ marginTop: 8, display: 'flex', gap: 16 }}>
              <div>
                <span style={{ fontSize: 10, color: '#6b7280' }}>Source Track </span>
                <span style={{ fontSize: 11, color: '#d1d5db', fontFamily: 'monospace' }}>#{handoff.source_track_id}</span>
              </div>
              {handoff.target_track_id != null && (
                <div>
                  <span style={{ fontSize: 10, color: '#6b7280' }}>Target Track </span>
                  <span style={{ fontSize: 11, color: '#d1d5db', fontFamily: 'monospace' }}>#{handoff.target_track_id}</span>
                </div>
              )}
            </div>
          )}

          {handoff.reason && (
            <div style={{ marginTop: 8, fontSize: 11, color: '#9ca3af', fontStyle: 'italic' }}>
              {handoff.reason}
            </div>
          )}

          <div style={{ marginTop: 8, fontSize: 10, color: '#6b7280' }}>
            ID: {handoff.handoff_id}
          </div>
        </div>
      )}
    </div>
  )
}

const FILTERS = ['all', 'predicted', 'candidate', 'confirmed', 'rejected', 'expired']

export default function CrossCameraPanel({ activeHandoffs = [], recentHandoffs = [], wsStatus = 'disconnected' }) {
  const [filter, setFilter] = useState('all')
  const [expandedId, setExpandedId] = useState(null)
  const [showRecent, setShowRecent] = useState(false)

  const displayed = useMemo(() => {
    const source = showRecent ? recentHandoffs : activeHandoffs
    if (filter === 'all') return source
    return source.filter((h) => h.state === filter)
  }, [activeHandoffs, recentHandoffs, showRecent, filter])

  const counts = useMemo(() => {
    const all = [...activeHandoffs, ...recentHandoffs]
    return FILTERS.reduce((acc, f) => {
      acc[f] = f === 'all' ? activeHandoffs.length : activeHandoffs.filter((h) => h.state === f).length
      return acc
    }, {})
  }, [activeHandoffs, recentHandoffs])

  const wsColor = wsStatus === 'connected' ? '#34d399' : wsStatus === 'connecting' ? '#fbbf24' : '#6b7280'

  return (
    <div
      style={{
        background: '#111827',
        border: '1px solid #374151',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ padding: '10px 12px', borderBottom: '1px solid #374151', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#e5e7eb', flex: 1 }}>Cross-Camera Handoffs</span>
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: wsColor,
            display: 'inline-block',
            flexShrink: 0,
          }}
          title={`WebSocket: ${wsStatus}`}
        />
        <span style={{ fontSize: 11, color: '#6b7280' }}>{wsStatus}</span>
      </div>

      {/* Mode toggle */}
      <div style={{ padding: '6px 12px', borderBottom: '1px solid #374151', display: 'flex', gap: 4 }}>
        {['Active', 'Recent'].map((label, i) => {
          const isRecent = i === 1
          return (
            <button
              key={label}
              onClick={() => setShowRecent(isRecent)}
              style={{
                fontSize: 11,
                padding: '3px 10px',
                borderRadius: 4,
                border: 'none',
                cursor: 'pointer',
                background: showRecent === isRecent ? '#374151' : 'transparent',
                color: showRecent === isRecent ? '#e5e7eb' : '#6b7280',
              }}
            >
              {label}
            </button>
          )
        })}
      </div>

      {/* Filter chips */}
      <div style={{ padding: '6px 12px', borderBottom: '1px solid #374151', display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              fontSize: 10,
              padding: '2px 8px',
              borderRadius: 10,
              border: `1px solid ${filter === f ? (STATE_COLOR[f] ?? '#60a5fa') : '#374151'}`,
              cursor: 'pointer',
              background: filter === f ? (STATE_COLOR[f] ?? '#60a5fa') + '22' : 'transparent',
              color: filter === f ? (STATE_COLOR[f] ?? '#60a5fa') : '#9ca3af',
            }}
          >
            {f === 'all' ? 'All' : STATE_LABEL[f]} {counts[f] != null ? `(${counts[f]})` : ''}
          </button>
        ))}
      </div>

      {/* List */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px' }}>
        {displayed.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#6b7280', fontSize: 12, marginTop: 32 }}>
            No {filter !== 'all' ? filter : ''} handoffs
          </div>
        ) : (
          displayed.map((h) => (
            <HandoffCard
              key={h.handoff_id}
              handoff={h}
              expanded={expandedId === h.handoff_id}
              onToggle={() => setExpandedId((prev) => (prev === h.handoff_id ? null : h.handoff_id))}
            />
          ))
        )}
      </div>
    </div>
  )
}
