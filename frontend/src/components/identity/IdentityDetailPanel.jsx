/**
 * IdentityDetailPanel — full detail view for a selected identity including
 * face enrollments and match timeline.
 */
import React from 'react';
import FaceEnrollmentPanel from './FaceEnrollmentPanel.jsx';
import IdentityMatchTimeline from './IdentityMatchTimeline.jsx';

export default function IdentityDetailPanel({
  selectedIdentity,
  enrollments,
  matches,
  archive,
  uploadFace,
  watchlistHook,
}) {
  const id = selectedIdentity;
  if (!id) return null;

  const handleAddToWatchlist = async () => {
    const severity = window.prompt(
      'Watchlist severity (low/medium/high/critical):',
      'medium',
    );
    if (!severity) return;
    const reason = window.prompt('Reason (optional, press Enter to skip):') || undefined;
    await watchlistHook.addEntry({ identity_id: id.identity_id, severity, reason });
  };

  return (
    <div
      style={{
        background: '#161b22',
        borderRadius: '8px',
        border: '1px solid #21262d',
        padding: '16px',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
          marginBottom: '16px',
        }}
      >
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: '16px', color: '#e6edf3' }}>
            {id.display_name || 'Unnamed Identity'}
          </h3>
          <div style={{ fontSize: '11px', color: '#8b949e', fontFamily: 'monospace' }}>
            {id.identity_id}
          </div>
          {id.notes && (
            <div style={{ marginTop: '6px', fontSize: '13px', color: '#8b949e' }}>
              {id.notes}
            </div>
          )}
        </div>
        <button
          onClick={handleAddToWatchlist}
          style={{
            padding: '6px 12px',
            borderRadius: '5px',
            border: '1px solid #f85149',
            cursor: 'pointer',
            background: 'transparent',
            color: '#f85149',
            fontSize: '12px',
          }}
        >
          + Watchlist
        </button>
        <button
          onClick={() => archive(id.identity_id)}
          style={{
            padding: '6px 12px',
            borderRadius: '5px',
            border: '1px solid #30363d',
            cursor: 'pointer',
            background: 'transparent',
            color: '#8b949e',
            fontSize: '12px',
          }}
        >
          Archive
        </button>
      </div>

      <FaceEnrollmentPanel
        identityId={id.identity_id}
        enrollments={enrollments}
        uploadFace={uploadFace}
      />
      <IdentityMatchTimeline matches={matches} />
    </div>
  );
}
