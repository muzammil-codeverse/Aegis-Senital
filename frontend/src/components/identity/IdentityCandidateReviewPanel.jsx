import React, { useCallback, useEffect, useState } from 'react';
import {
  acceptIdentityCandidate,
  escalateIdentityCandidate,
  getIdentityCandidates,
  rejectIdentityCandidate,
} from '../../api/identityApi.js';
import IdentityConfidenceBreakdown from './IdentityConfidenceBreakdown.jsx';

export default function IdentityCandidateReviewPanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    const res = await getIdentityCandidates();
    if (res.status === 'error') {
      setError(res.detail || 'Failed to load candidates');
      setItems([]);
    } else {
      setError(null);
      setItems(res.items || []);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (candidateId, fn) => {
    setBusyId(candidateId);
    await fn(candidateId, { review_notes: 'operator review via UI' });
    setBusyId(null);
    await load();
  };

  return (
    <div
      style={{
        border: '1px solid #21262d',
        borderRadius: '8px',
        padding: '16px',
        background: '#161b22',
        display: 'grid',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px' }}>
        <div>
          <div style={{ fontSize: '15px', fontWeight: 600, color: '#e6edf3' }}>Identity candidate review</div>
          <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>
            Possible matches require operator review. Review actions are audited; acceptance does not confirm identity.
          </div>
        </div>
        <button
          type="button"
          onClick={load}
          style={{
            padding: '6px 12px',
            borderRadius: '6px',
            border: '1px solid #30363d',
            background: '#0d1117',
            color: '#e6edf3',
            cursor: 'pointer',
            fontSize: '12px',
          }}
        >
          Refresh
        </button>
      </div>

      {loading && <div style={{ fontSize: '12px', color: '#8b949e' }}>Loading…</div>}
      {error && <div style={{ fontSize: '12px', color: '#f85149' }}>{error}</div>}

      {!loading && items.length === 0 && (
        <div style={{ fontSize: '12px', color: '#8b949e' }}>No identity candidates are pending in this workspace.</div>
      )}

      {items.map((row) => (
        <div
          key={row.identity_candidate_id}
          style={{
            border: '1px solid #30363d',
            borderRadius: '8px',
            padding: '12px',
            display: 'grid',
            gap: '10px',
            background: '#0d1117',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '12px', color: '#8b949e' }}>Candidate {row.identity_candidate_id}</span>
            <span style={{ fontSize: '12px', color: '#d29922' }}>Status: {row.review_status || 'pending'}</span>
          </div>
          <IdentityConfidenceBreakdown explainability={row.explainability} />
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              type="button"
              disabled={busyId === row.identity_candidate_id}
              onClick={() => act(row.identity_candidate_id, acceptIdentityCandidate)}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #238636',
                background: '#1a3d24',
                color: '#e6edf3',
                cursor: 'pointer',
                fontSize: '12px',
              }}
            >
              Accept (tracking only)
            </button>
            <button
              type="button"
              disabled={busyId === row.identity_candidate_id}
              onClick={() => act(row.identity_candidate_id, rejectIdentityCandidate)}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #8b2b2b',
                background: '#301a1a',
                color: '#e6edf3',
                cursor: 'pointer',
                fontSize: '12px',
              }}
            >
              Reject candidate
            </button>
            <button
              type="button"
              disabled={busyId === row.identity_candidate_id}
              onClick={() => act(row.identity_candidate_id, escalateIdentityCandidate)}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: '1px solid #30363d',
                background: '#161b22',
                color: '#e6edf3',
                cursor: 'pointer',
                fontSize: '12px',
              }}
            >
              Escalate
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
