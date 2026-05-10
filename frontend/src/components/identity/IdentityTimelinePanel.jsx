import React from 'react';

function formatPercent(value) {
  if (!Number.isFinite(value)) return '0%';
  return `${Math.round(value * 100)}%`;
}

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value) {
  if (!value) return 'n/a';
  const parsed = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'n/a';
  return parsed.toLocaleString();
}

function SourceBreakdown({ sources = {} }) {
  return (
    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
      {['face', 'reid', 'track'].map((source) => (
        <span
          key={source}
          style={{
            fontSize: '11px',
            padding: '3px 7px',
            borderRadius: '999px',
            background: '#21262d',
            color: '#8b949e',
          }}
        >
          {source.toUpperCase()} {formatPercent(sources[source])}
        </span>
      ))}
    </div>
  );
}

export default function IdentityTimelinePanel({ matches, globalIdentity }) {
  const auditEvents = [...(globalIdentity?.audit_events || [])].reverse().slice(0, 8);
  const orderedMatches = [...(matches || [])].reverse().slice(0, 12);

  return (
    <div
      style={{
        border: '1px solid #21262d',
        background: '#161b22',
        borderRadius: '8px',
        padding: '16px',
        display: 'grid',
        gap: '16px',
      }}
    >
      <div style={{ display: 'grid', gap: '8px' }}>
        <div style={{ fontSize: '14px', fontWeight: 600, color: '#e6edf3' }}>Identity Timeline</div>
        {globalIdentity ? (
          <div
            style={{
              border: '1px solid #21262d',
              background: '#0d1117',
              borderRadius: '8px',
              padding: '12px',
              display: 'grid',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '12px', color: '#58a6ff' }}>
                Possible identity match confidence {formatPercent(globalIdentity.confidence)}
              </span>
              <span style={{ fontSize: '12px', color: '#8b949e' }}>
                Cameras {globalIdentity.cameras_seen?.join(', ') || 'n/a'}
              </span>
            </div>
            <SourceBreakdown sources={globalIdentity.sources} />
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: '12px', color: '#8b949e' }}>
              <span>First seen {formatDate(globalIdentity.first_seen)}</span>
              <span>Last seen {formatDate(globalIdentity.last_seen)}</span>
              <span>Observations {globalIdentity.observation_count || 0}</span>
            </div>
          </div>
        ) : (
          <div style={{ fontSize: '12px', color: '#8b949e' }}>
            No cross-camera continuity record is available for this identity yet.
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gap: '8px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3' }}>
          Match History ({orderedMatches.length})
        </div>
        {orderedMatches.length === 0 ? (
          <div style={{ fontSize: '12px', color: '#8b949e' }}>No match events recorded.</div>
        ) : (
          orderedMatches.map((match) => (
            <div
              key={match.match_id}
              style={{
                border: '1px solid #21262d',
                background: '#0d1117',
                borderRadius: '8px',
                padding: '12px',
                display: 'grid',
                gap: '8px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: '#58a6ff' }}>
                  {formatLabel(match.match_type || 'possible_identity_match')}
                </span>
                <span style={{ fontSize: '12px', color: '#8b949e' }}>{formatDate(match.matched_at)}</span>
              </div>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', fontSize: '12px', color: '#e6edf3' }}>
                <span>Confidence {formatPercent(match.confidence)}</span>
                <span>Camera {match.camera_id || 'n/a'}</span>
                <span>Track {match.track_id ?? 'n/a'}</span>
                <span>Quality {formatPercent(match.quality_score)}</span>
              </div>
              <SourceBreakdown sources={match.source_breakdown} />
              {match.operator_review_required && (
                <div style={{ fontSize: '12px', color: '#d29922' }}>Operator review required.</div>
              )}
            </div>
          ))
        )}
      </div>

      <div style={{ display: 'grid', gap: '8px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3' }}>Registry Audit</div>
        {auditEvents.length === 0 ? (
          <div style={{ fontSize: '12px', color: '#8b949e' }}>No registry audit events recorded.</div>
        ) : (
          auditEvents.map((event, index) => (
            <div
              key={`${event.timestamp}-${event.type}-${index}`}
              style={{
                border: '1px solid #21262d',
                background: '#0d1117',
                borderRadius: '8px',
                padding: '10px 12px',
                display: 'grid',
                gap: '4px',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '12px', color: '#e6edf3' }}>{formatLabel(event.type)}</span>
                <span style={{ fontSize: '11px', color: '#8b949e' }}>{formatDate(event.timestamp)}</span>
              </div>
              {event.reason && (
                <div style={{ fontSize: '12px', color: '#8b949e' }}>{formatLabel(event.reason)}</div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
