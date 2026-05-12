/**
 * WatchlistPanel — active watchlist management: add, remove, view entries.
 */
import React, { useState } from 'react';

const SEVERITY_COLORS = {
  low: '#8b949e',
  medium: '#e3b341',
  high: '#f0883e',
  critical: '#f85149',
};

export default function WatchlistPanel({ watchlistHook, identityHook }) {
  const { entries, loading, error, addEntry, removeEntry } = watchlistHook;
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({
    identity_id: '',
    severity: 'medium',
    reason: '',
    expires_days: '',
  });

  const handleAdd = async () => {
    const payload = {
      identity_id: form.identity_id,
      severity: form.severity,
      reason: form.reason || undefined,
      expires_days: form.expires_days ? Number(form.expires_days) : undefined,
    };
    await addEntry(payload);
    setShowAdd(false);
    setForm({ identity_id: '', severity: 'medium', reason: '', expires_days: '' });
  };

  return (
    <div
      style={{
        background: '#161b22',
        borderRadius: '8px',
        border: '1px solid #21262d',
        overflow: 'hidden',
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          padding: '12px 14px',
          borderBottom: '1px solid #21262d',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3' }}>
          Active Watchlist ({entries.length})
        </span>
        <button
          onClick={() => setShowAdd(!showAdd)}
          style={{
            padding: '4px 10px',
            borderRadius: '5px',
            border: 'none',
            cursor: 'pointer',
            background: '#f85149',
            color: '#e6edf3',
            fontSize: '12px',
          }}
        >
          + Add Entry
        </button>
      </div>

      {/* Add form */}
      {showAdd && (
        <div
          style={{
            padding: '12px',
            borderBottom: '1px solid #21262d',
            background: '#0d1117',
          }}
        >
          <select
            value={form.identity_id}
            onChange={(e) => setForm((f) => ({ ...f, identity_id: e.target.value }))}
            style={{
              width: '100%',
              padding: '6px',
              marginBottom: '6px',
              background: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '4px',
              color: '#e6edf3',
              fontSize: '12px',
            }}
          >
            <option value="">Select identity...</option>
            {identityHook.identities.map((i) => (
              <option key={i.identity_id} value={i.identity_id}>
                {i.display_name || i.identity_id.slice(0, 12)}
              </option>
            ))}
          </select>
          <select
            value={form.severity}
            onChange={(e) => setForm((f) => ({ ...f, severity: e.target.value }))}
            style={{
              width: '100%',
              padding: '6px',
              marginBottom: '6px',
              background: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '4px',
              color: '#e6edf3',
              fontSize: '12px',
            }}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
          <input
            aria-label="Watchlist reason"
            placeholder="Reason (optional)"
            value={form.reason}
            onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
            style={{
              width: '100%',
              padding: '6px',
              marginBottom: '6px',
              background: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '4px',
              color: '#e6edf3',
              fontSize: '12px',
              boxSizing: 'border-box',
            }}
          />
          <input
            aria-label="Expiry days"
            placeholder="Expires in days (optional)"
            type="number"
            value={form.expires_days}
            onChange={(e) => setForm((f) => ({ ...f, expires_days: e.target.value }))}
            style={{
              width: '100%',
              padding: '6px',
              marginBottom: '8px',
              background: '#21262d',
              border: '1px solid #30363d',
              borderRadius: '4px',
              color: '#e6edf3',
              fontSize: '12px',
              boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={handleAdd}
              disabled={!form.identity_id}
              style={{
                flex: 1,
                padding: '6px',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: '#f85149',
                color: '#e6edf3',
                fontSize: '12px',
              }}
            >
              Add to Watchlist
            </button>
            <button
              onClick={() => setShowAdd(false)}
              style={{
                flex: 1,
                padding: '6px',
                borderRadius: '4px',
                border: 'none',
                cursor: 'pointer',
                background: '#21262d',
                color: '#8b949e',
                fontSize: '12px',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {loading && (
        <div style={{ padding: '16px', color: '#8b949e', fontSize: '13px', textAlign: 'center' }}>
          Loading...
        </div>
      )}
      {error && (
        <div style={{ padding: '12px', color: '#f85149', fontSize: '12px' }}>{error}</div>
      )}

      {/* Entry list */}
      <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
        {entries.length === 0 && !loading ? (
          <div
            style={{
              padding: '24px',
              color: '#8b949e',
              fontSize: '13px',
              textAlign: 'center',
            }}
          >
            Watchlist is empty
          </div>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.watchlist_id}
              style={{
                padding: '10px 14px',
                borderBottom: '1px solid #21262d',
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
              }}
            >
              <div
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: '50%',
                  background: SEVERITY_COLORS[entry.severity] || '#8b949e',
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: '12px',
                    color: SEVERITY_COLORS[entry.severity],
                    fontWeight: 600,
                    textTransform: 'uppercase',
                  }}
                >
                  {entry.severity}
                </div>
                <div style={{ fontSize: '11px', color: '#8b949e', fontFamily: 'monospace' }}>
                  {entry.identity_id.slice(0, 16)}...
                </div>
                {entry.reason && (
                  <div style={{ fontSize: '11px', color: '#8b949e' }}>{entry.reason}</div>
                )}
              </div>
              <button
                onClick={() => removeEntry(entry.watchlist_id)}
                style={{
                  padding: '3px 8px',
                  borderRadius: '4px',
                  border: '1px solid #30363d',
                  cursor: 'pointer',
                  background: 'transparent',
                  color: '#8b949e',
                  fontSize: '11px',
                }}
              >
                Remove
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
