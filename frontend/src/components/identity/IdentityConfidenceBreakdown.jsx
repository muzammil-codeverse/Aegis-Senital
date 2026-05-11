import React from 'react';

function formatScore(value) {
  if (!Number.isFinite(value)) return 'n/a';
  return `${(value * 100).toFixed(1)}%`;
}

export default function IdentityConfidenceBreakdown({ explainability }) {
  if (!explainability) {
    return (
      <div style={{ fontSize: '12px', color: '#8b949e' }}>
        Possible match context is unavailable for this record.
      </div>
    );
  }

  const rows = [
    { label: 'Face score', value: explainability.face_score },
    { label: 'ReID score', value: explainability.reid_score },
    { label: 'Fusion score', value: explainability.fusion_score },
    { label: 'Track continuity', value: explainability.track_continuity_score },
    { label: 'Quality score', value: explainability.quality_score },
    { label: 'Liveness', value: explainability.liveness_status, text: true },
  ];

  return (
    <div
      style={{
        border: '1px solid #21262d',
        borderRadius: '8px',
        padding: '12px',
        background: '#0d1117',
        display: 'grid',
        gap: '10px',
      }}
    >
      <div style={{ fontSize: '12px', color: '#58a6ff', fontWeight: 600 }}>
        {explainability.wording?.match_label || 'Possible identity match'}
      </div>
      <div style={{ fontSize: '11px', color: '#d29922' }}>
        {explainability.wording?.review_label || 'Requires operator review'}
      </div>
      <div style={{ fontSize: '11px', color: '#8b949e' }}>
        {explainability.wording?.liveness_note || 'Liveness disabled'}
      </div>
      <div style={{ display: 'grid', gap: '6px' }}>
        {rows.map((row) => (
          <div
            key={row.label}
            style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', fontSize: '12px' }}
          >
            <span style={{ color: '#8b949e' }}>{row.label}</span>
            <span style={{ color: '#e6edf3' }}>{row.text ? String(row.value ?? 'n/a') : formatScore(row.value)}</span>
          </div>
        ))}
      </div>
      {Array.isArray(explainability.evidence_refs) && explainability.evidence_refs.length > 0 && (
        <div style={{ fontSize: '11px', color: '#8b949e' }}>
          Evidence refs: {explainability.evidence_refs.length} linked artifact(s) (opaque references only).
        </div>
      )}
    </div>
  );
}
