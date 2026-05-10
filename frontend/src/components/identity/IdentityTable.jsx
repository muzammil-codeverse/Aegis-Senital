import React, { useMemo, useState } from 'react';

const STATUS_COLORS = {
  active: '#3fb950',
  inactive: '#8b949e',
  watchlisted: '#f85149',
  archived: '#6e7681',
  unknown: '#8b949e',
};

export default function IdentityTable({
  identities,
  selectedIdentity,
  selectIdentity,
  create,
  globalIdentities,
  loading,
  error,
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ display_name: '', tags: '', notes: '' });
  const [creating, setCreating] = useState(false);
  const registryById = useMemo(
    () => new Map((globalIdentities || []).map((record) => [record.global_id, record])),
    [globalIdentities],
  );

  const handleCreate = async () => {
    setCreating(true);
    await create({
      display_name: form.display_name || null,
      tags: form.tags
        ? form.tags.split(',').map((tag) => tag.trim()).filter(Boolean)
        : [],
      notes: form.notes || null,
    });
    setCreating(false);
    setShowCreate(false);
    setForm({ display_name: '', tags: '', notes: '' });
  };

  return (
    <div style={{ background: '#161b22', borderRadius: '8px', border: '1px solid #21262d', overflow: 'hidden' }}>
      <div style={{ padding: '12px 14px', borderBottom: '1px solid #21262d', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: '#e6edf3' }}>
          Identities ({identities.length})
        </span>
        <button
          onClick={() => setShowCreate(!showCreate)}
          style={{ padding: '4px 10px', borderRadius: '5px', border: 'none', cursor: 'pointer', background: '#1f6feb', color: '#e6edf3', fontSize: '12px' }}
        >
          + New
        </button>
      </div>

      {showCreate && (
        <div style={{ padding: '12px', borderBottom: '1px solid #21262d', background: '#0d1117' }}>
          <input
            placeholder="Display name"
            value={form.display_name}
            onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
            style={{ width: '100%', padding: '6px 8px', marginBottom: '6px', background: '#21262d', border: '1px solid #30363d', borderRadius: '4px', color: '#e6edf3', fontSize: '12px', boxSizing: 'border-box' }}
          />
          <input
            placeholder="Tags (comma-separated)"
            value={form.tags}
            onChange={(event) => setForm((current) => ({ ...current, tags: event.target.value }))}
            style={{ width: '100%', padding: '6px 8px', marginBottom: '6px', background: '#21262d', border: '1px solid #30363d', borderRadius: '4px', color: '#e6edf3', fontSize: '12px', boxSizing: 'border-box' }}
          />
          <input
            placeholder="Notes"
            value={form.notes}
            onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
            style={{ width: '100%', padding: '6px 8px', marginBottom: '8px', background: '#21262d', border: '1px solid #30363d', borderRadius: '4px', color: '#e6edf3', fontSize: '12px', boxSizing: 'border-box' }}
          />
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              onClick={handleCreate}
              disabled={creating}
              style={{ flex: 1, padding: '6px', borderRadius: '4px', border: 'none', cursor: 'pointer', background: '#1f6feb', color: '#e6edf3', fontSize: '12px' }}
            >
              {creating ? 'Creating...' : 'Create'}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              style={{ flex: 1, padding: '6px', borderRadius: '4px', border: 'none', cursor: 'pointer', background: '#21262d', color: '#8b949e', fontSize: '12px' }}
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

      <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
        {identities.length === 0 && !loading ? (
          <div style={{ padding: '24px', color: '#8b949e', fontSize: '13px', textAlign: 'center' }}>
            No identities registered
          </div>
        ) : (
          identities.map((identity) => {
            const registryRecord = registryById.get(identity.identity_id);
            return (
              <div
                key={identity.identity_id}
                onClick={() => selectIdentity(identity)}
                style={{
                  padding: '10px 14px',
                  cursor: 'pointer',
                  borderBottom: '1px solid #21262d',
                  background:
                    selectedIdentity?.identity_id === identity.identity_id
                      ? '#1c2128'
                      : 'transparent',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: STATUS_COLORS[identity.status] || '#8b949e',
                      flexShrink: 0,
                    }}
                  />
                  <span style={{ fontSize: '13px', color: '#e6edf3', fontWeight: 500, flex: 1 }}>
                    {identity.display_name || `ID: ${identity.identity_id.slice(0, 8)}...`}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      color: STATUS_COLORS[identity.status] || '#8b949e',
                      textTransform: 'uppercase',
                    }}
                  >
                    {identity.status}
                  </span>
                </div>
                {registryRecord && (
                  <div style={{ marginTop: '6px', display: 'flex', gap: '10px', flexWrap: 'wrap', fontSize: '11px', color: '#8b949e' }}>
                    <span>Confidence {(registryRecord.confidence * 100).toFixed(0)}%</span>
                    <span>Cameras {registryRecord.cameras_seen?.length || 0}</span>
                    {registryRecord.confidence < 0.8 && <span style={{ color: '#d29922' }}>Review</span>}
                  </div>
                )}
                {identity.tags?.length > 0 && (
                  <div style={{ marginTop: '4px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                    {identity.tags.map((tag) => (
                      <span
                        key={tag}
                        style={{
                          fontSize: '10px',
                          padding: '1px 6px',
                          borderRadius: '10px',
                          background: '#21262d',
                          color: '#8b949e',
                        }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
