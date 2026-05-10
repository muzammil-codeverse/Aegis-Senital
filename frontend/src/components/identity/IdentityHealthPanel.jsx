import React from 'react';

const STATUS_COLORS = {
  healthy: '#3fb950',
  degraded: '#d29922',
  disabled: '#8b949e',
  failed: '#f85149',
  error: '#f85149',
};

function formatCount(value) {
  return Number.isFinite(value) ? value.toLocaleString() : '0';
}

export default function IdentityHealthPanel({
  health,
  metrics,
  globalIdentities,
  identities,
  onOpenRegistry,
}) {
  const status = health?.status || 'disabled';
  const statusColor = STATUS_COLORS[status] || '#8b949e';
  const cards = [
    {
      label: 'Possible Matches',
      value: formatCount(metrics?.identity_matches_total),
      accent: '#58a6ff',
    },
    {
      label: 'Unknown Person Observations',
      value: formatCount(metrics?.identity_unknowns_total),
      accent: '#d29922',
    },
    {
      label: 'Quality Rejections',
      value: formatCount(metrics?.identity_face_quality_rejected_total),
      accent: '#f85149',
    },
    {
      label: 'Active Global Identities',
      value: formatCount(metrics?.identity_registry_active_count ?? globalIdentities?.length),
      accent: '#3fb950',
    },
  ];

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
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: '16px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'grid', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#e6edf3' }}>Identity Runtime</h3>
            <span
              style={{
                fontSize: '11px',
                padding: '3px 8px',
                borderRadius: '999px',
                background: `${statusColor}22`,
                border: `1px solid ${statusColor}55`,
                color: statusColor,
                textTransform: 'uppercase',
              }}
            >
              {status}
            </span>
          </div>
          <div style={{ fontSize: '12px', color: '#8b949e', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <span>Face: {health?.face_provider || 'n/a'} {health?.face_loaded ? 'loaded' : 'unavailable'}</span>
            <span>ReID: {health?.reid_provider || 'n/a'} {health?.reid_loaded ? 'loaded' : 'unavailable'}</span>
            <span>Liveness: {health?.liveness_enabled ? 'configured' : 'disabled'}</span>
            <span>Profiles: {formatCount(identities?.length)}</span>
          </div>
          {health?.last_error && (
            <div style={{ fontSize: '12px', color: '#d29922' }}>
              Operator review required: {health.last_error}
            </div>
          )}
        </div>

        <button
          onClick={onOpenRegistry}
          style={{
            padding: '7px 12px',
            borderRadius: '6px',
            border: '1px solid #30363d',
            background: '#0d1117',
            color: '#e6edf3',
            cursor: 'pointer',
            fontSize: '12px',
          }}
        >
          Global Identity View
        </button>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px',
        }}
      >
        {cards.map((card) => (
          <div
            key={card.label}
            style={{
              border: '1px solid #21262d',
              background: '#0d1117',
              borderRadius: '8px',
              padding: '12px',
              minHeight: '78px',
              display: 'grid',
              gap: '6px',
            }}
          >
            <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase' }}>
              {card.label}
            </div>
            <div style={{ fontSize: '24px', lineHeight: 1, color: card.accent, fontWeight: 700 }}>
              {card.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
