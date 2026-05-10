import React, { useState } from 'react';
import { useAnomalyEvents } from '../../hooks/useAnomalyEvents';

const TYPE_ICONS = {
  violence: '⚠',
  loitering: '◉',
  abandoned_object: '◈',
  panic_running: '▶',
  restricted_zone: '◻',
  crowd_anomaly: '◎',
  generic: '◆',
};

const SEVERITY_BG = {
  critical: 'rgba(220,38,38,0.15)',
  high: 'rgba(234,88,12,0.12)',
  medium: 'rgba(217,119,6,0.10)',
  low: 'rgba(37,99,235,0.08)',
};

export function AnomalyAlertFeed({ cameraId, maxItems = 30 }) {
  const { events, loading, error, submitFeedback } = useAnomalyEvents(cameraId, 5000);
  const [expanded, setExpanded] = useState(null);

  const visible = events.slice(0, maxItems);

  if (loading) return <div style={{ padding: 12, fontSize: 12 }}>Loading...</div>;

  return (
    <div style={{ fontFamily: 'monospace', fontSize: 12 }}>
      {error && (
        <div style={{ color: '#dc2626', padding: '4px 8px' }}>{error}</div>
      )}
      {visible.length === 0 && (
        <div style={{ color: '#6b7280', padding: 16, textAlign: 'center' }}>No anomaly alerts</div>
      )}
      {visible.map((ev, idx) => {
        const key = ev.window_id || idx;
        const isOpen = expanded === key;
        return (
          <div
            key={key}
            onClick={() => setExpanded(isOpen ? null : key)}
            style={{
              padding: '8px 12px',
              marginBottom: 4,
              borderRadius: 4,
              cursor: 'pointer',
              background: SEVERITY_BG[ev.severity] || SEVERITY_BG.low,
              border: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>{TYPE_ICONS[ev.anomaly_type] || '◆'}</span>
              <span style={{ fontWeight: 700, flex: 1 }}>{ev.display_label || ev.anomaly_type}</span>
              <span style={{ color: '#9ca3af' }}>{ev.camera_id}</span>
              <span style={{ color: '#6b7280' }}>{(ev.score * 100).toFixed(0)}%</span>
            </div>

            {isOpen && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <div>Severity: <strong>{ev.severity}</strong></div>
                <div>Duration: {ev.duration_seconds?.toFixed(1)}s</div>
                <div>Confidence: {(ev.confidence * 100).toFixed(1)}%</div>
                {ev.track_ids?.length > 0 && (
                  <div>Tracks: {ev.track_ids.join(', ')}</div>
                )}
                {ev.requires_review && (
                  <div style={{ color: '#fbbf24', marginTop: 4 }}>Requires operator review</div>
                )}
                {ev.evidence && (
                  <div style={{ color: '#9ca3af', marginTop: 4 }}>
                    {JSON.stringify(ev.evidence).slice(0, 120)}
                  </div>
                )}
                <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
                  <button
                    onClick={(e) => { e.stopPropagation(); submitFeedback(ev.window_id, true); }}
                    style={{ fontSize: 11, padding: '2px 8px', background: 'rgba(220,38,38,0.3)', border: 'none', borderRadius: 3, color: '#fca5a5', cursor: 'pointer' }}
                  >
                    Mark False Alarm
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); submitFeedback(ev.window_id, false); }}
                    style={{ fontSize: 11, padding: '2px 8px', background: 'rgba(22,163,74,0.3)', border: 'none', borderRadius: 3, color: '#86efac', cursor: 'pointer' }}
                  >
                    Confirm
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default AnomalyAlertFeed;
