import React from 'react';

function formatPercent(value) {
  if (!Number.isFinite(value)) return '0%';
  return `${Math.round(value * 100)}%`;
}

function formatDate(value) {
  if (!value) return 'n/a';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return 'n/a';
  return parsed.toLocaleString();
}

export default function GlobalIdentityDrawer({
  open,
  onClose,
  globalIdentities,
  identities,
  onSelectIdentity,
}) {
  if (!open) return null;

  const identityMap = new Map((identities || []).map((identity) => [identity.identity_id, identity]));

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(1, 4, 9, 0.72)',
        display: 'flex',
        justifyContent: 'flex-end',
        zIndex: 40,
      }}
      onClick={onClose}
    >
      <aside
        style={{
          width: 'min(440px, 100vw)',
          height: '100%',
          background: '#0d1117',
          borderLeft: '1px solid #21262d',
          padding: '20px 16px',
          overflowY: 'auto',
          display: 'grid',
          gap: '12px',
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: '16px', fontWeight: 600, color: '#e6edf3' }}>Global Identity View</div>
            <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>
              Cross-camera continuity with operator review wording.
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: '1px solid #30363d',
              background: 'transparent',
              color: '#e6edf3',
              cursor: 'pointer',
              fontSize: '12px',
            }}
          >
            Close
          </button>
        </div>

        {(globalIdentities || []).length === 0 ? (
          <div style={{ fontSize: '12px', color: '#8b949e' }}>No global identity records are active.</div>
        ) : (
          globalIdentities.map((record) => {
            const profile = identityMap.get(record.global_id);
            const label = profile?.display_name || 'Unknown person';
            const canOpen = Boolean(profile);
            return (
              <button
                key={record.global_id}
                onClick={() => {
                  if (canOpen) onSelectIdentity(profile);
                }}
                style={{
                  textAlign: 'left',
                  border: '1px solid #21262d',
                  background: '#161b22',
                  borderRadius: '8px',
                  padding: '12px',
                  display: 'grid',
                  gap: '8px',
                  cursor: canOpen ? 'pointer' : 'default',
                  color: 'inherit',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '13px', color: '#e6edf3', fontWeight: 600 }}>{label}</span>
                  <span style={{ fontSize: '12px', color: '#58a6ff' }}>
                    Confidence {formatPercent(record.confidence)}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '12px', color: '#8b949e' }}>
                  <span>{profile ? 'Possible identity match' : 'Unknown person'}</span>
                  <span>Cameras {record.cameras_seen?.length || 0}</span>
                  <span>Observations {record.observation_count || 0}</span>
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', fontSize: '11px', color: '#8b949e' }}>
                  <span>FACE {formatPercent(record.sources?.face)}</span>
                  <span>REID {formatPercent(record.sources?.reid)}</span>
                  <span>TRACK {formatPercent(record.sources?.track)}</span>
                </div>
                <div style={{ fontSize: '11px', color: '#8b949e' }}>
                  Last seen {formatDate(record.last_seen)}
                </div>
              </button>
            );
          })
        )}
      </aside>
    </div>
  );
}
