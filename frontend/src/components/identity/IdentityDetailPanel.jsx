import React from 'react';
import EnrollmentPanel from './EnrollmentPanel.jsx';
import IdentityTimelinePanel from './IdentityTimelinePanel.jsx';

function formatPercent(value) {
  if (!Number.isFinite(value)) return '0%';
  return `${Math.round(value * 100)}%`;
}

export default function IdentityDetailPanel({
  selectedIdentity,
  enrollments,
  enrollmentProfiles,
  matches,
  archive,
  batchEnroll,
  deleteEnrollment,
  globalIdentities,
  watchlistHook,
}) {
  const identity = selectedIdentity;
  if (!identity) return null;

  const globalIdentity = (globalIdentities || []).find((item) => item.global_id === identity.identity_id) || null;

  const handleAddToWatchlist = async () => {
    const severity = window.prompt(
      'Watchlist severity (low/medium/high/critical):',
      'medium',
    );
    if (!severity) return;
    const reason = window.prompt('Reason (optional, press Enter to skip):') || undefined;
    await watchlistHook.addEntry({ identity_id: identity.identity_id, severity, reason });
  };

  return (
    <div
      style={{
        background: '#161b22',
        borderRadius: '8px',
        border: '1px solid #21262d',
        padding: '16px',
        display: 'grid',
        gap: '16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: '16px', color: '#e6edf3' }}>
            {identity.display_name || 'Unnamed Identity'}
          </h3>
          <div style={{ fontSize: '11px', color: '#8b949e', fontFamily: 'monospace' }}>
            {identity.identity_id}
          </div>
          {identity.notes && (
            <div style={{ marginTop: '6px', fontSize: '13px', color: '#8b949e' }}>
              {identity.notes}
            </div>
          )}
          {globalIdentity && (
            <div style={{ marginTop: '10px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              <span
                style={{
                  fontSize: '11px',
                  padding: '3px 8px',
                  borderRadius: '999px',
                  background: '#0d1117',
                  color: '#58a6ff',
                  border: '1px solid #21262d',
                }}
              >
                Possible identity match {formatPercent(globalIdentity.confidence)}
              </span>
              {globalIdentity.confidence < 0.8 && (
                <span
                  style={{
                    fontSize: '11px',
                    padding: '3px 8px',
                    borderRadius: '999px',
                    background: '#2d1f06',
                    color: '#d29922',
                    border: '1px solid #5f4b1c',
                  }}
                >
                  Operator review required
                </span>
              )}
              {['face', 'reid', 'track'].map((source) => (
                <span
                  key={source}
                  style={{
                    fontSize: '11px',
                    padding: '3px 8px',
                    borderRadius: '999px',
                    background: '#0d1117',
                    color: '#8b949e',
                    border: '1px solid #21262d',
                  }}
                >
                  {source.toUpperCase()} {formatPercent(globalIdentity.sources?.[source])}
                </span>
              ))}
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
          onClick={() => archive(identity.identity_id)}
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

      <EnrollmentPanel
        selectedIdentity={identity}
        enrollments={enrollments}
        enrollmentProfiles={enrollmentProfiles}
        batchEnroll={batchEnroll}
        deleteEnrollment={deleteEnrollment}
      />
      <IdentityTimelinePanel matches={matches} globalIdentity={globalIdentity} />
    </div>
  );
}
