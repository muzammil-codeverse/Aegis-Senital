import React from 'react';
import { useAnomalyEvents } from '../../hooks/useAnomalyEvents';

const SEVERITY_COLORS = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#d97706',
  low: '#2563eb',
};

function StatusDot({ status }) {
  const color =
    status === 'healthy' ? '#16a34a' :
    status === 'degraded' ? '#d97706' :
    status === 'disabled' ? '#6b7280' : '#dc2626';
  return (
    <span style={{
      display: 'inline-block', width: 10, height: 10,
      borderRadius: '50%', backgroundColor: color, marginRight: 6,
    }} />
  );
}

export function AnomalyStatusPanel() {
  const { events, health, loading, error } = useAnomalyEvents(null, 8000);

  if (loading) {
    return <div className="panel anomaly-status-panel" style={{ padding: 16 }}>Loading anomaly status...</div>;
  }

  return (
    <div className="panel anomaly-status-panel" style={{ padding: 16 }}>
      <h3 style={{ marginBottom: 12, fontSize: 14, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>
        Anomaly Detection
      </h3>

      {health && (
        <div style={{ marginBottom: 12, fontSize: 13 }}>
          <StatusDot status={health.status} />
          <strong>{health.status?.toUpperCase() || 'UNKNOWN'}</strong>
          {' — '}
          {health.provider || 'rule_only'}
          {!health.model_loaded && (
            <span style={{ color: '#d97706', marginLeft: 8 }}>(model unavailable)</span>
          )}
        </div>
      )}

      {error && (
        <div style={{ color: '#dc2626', fontSize: 12, marginBottom: 8 }}>{error}</div>
      )}

      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 8 }}>
        Recent events: {events.length}
      </div>

      <div style={{ maxHeight: 280, overflowY: 'auto' }}>
        {events.length === 0 && (
          <div style={{ fontSize: 12, color: '#9ca3af', textAlign: 'center', padding: 16 }}>
            No anomaly events
          </div>
        )}
        {events.map((ev, idx) => (
          <AnomalyEventCard key={ev.window_id || idx} event={ev} />
        ))}
      </div>
    </div>
  );
}

function AnomalyEventCard({ event }) {
  const color = SEVERITY_COLORS[event.severity] || '#6b7280';
  return (
    <div style={{
      borderLeft: `3px solid ${color}`,
      padding: '8px 10px',
      marginBottom: 8,
      background: 'rgba(0,0,0,0.15)',
      borderRadius: 4,
      fontSize: 12,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
        <strong style={{ color }}>{event.display_label || event.anomaly_type}</strong>
        <span style={{ color: '#9ca3af', fontSize: 11 }}>{event.camera_id}</span>
      </div>
      <div style={{ color: '#d1d5db' }}>
        Score: {(event.score * 100).toFixed(1)}% &nbsp;|&nbsp;
        {event.duration_seconds?.toFixed(1)}s
      </div>
      {event.requires_review && (
        <div style={{ color: '#fbbf24', fontSize: 11, marginTop: 2 }}>Requires operator review</div>
      )}
    </div>
  );
}

export default AnomalyStatusPanel;
