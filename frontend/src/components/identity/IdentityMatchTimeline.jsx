/**
 * IdentityMatchTimeline — reverse-chronological list of identity match records.
 */
import React from 'react';

export default function IdentityMatchTimeline({ matches }) {
  return (
    <div>
      <div style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3', marginBottom: '8px' }}>
        Match Timeline ({matches.length})
      </div>
      {matches.length === 0 ? (
        <div style={{ color: '#8b949e', fontSize: '12px' }}>No matches recorded</div>
      ) : (
        <div
          style={{
            maxHeight: '200px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '4px',
          }}
        >
          {[...matches].reverse().map((m) => (
            <div
              key={m.match_id}
              style={{
                padding: '6px 10px',
                background: '#0d1117',
                borderRadius: '4px',
                fontSize: '12px',
                color: '#8b949e',
                display: 'flex',
                gap: '10px',
              }}
            >
              <span style={{ color: '#e6edf3' }}>{(m.confidence * 100).toFixed(1)}%</span>
              <span>Camera: {m.camera_id || 'N/A'}</span>
              <span>Track: {m.track_id ?? 'N/A'}</span>
              <span style={{ marginLeft: 'auto' }}>
                {new Date(m.matched_at * 1000).toLocaleString()}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
