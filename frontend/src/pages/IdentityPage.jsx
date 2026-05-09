/**
 * IdentityPage — two-tab view for identity management and watchlist operations.
 */
import React, { useState } from 'react';
import { useIdentities } from '../hooks/useIdentities.js';
import { useWatchlist } from '../hooks/useWatchlist.js';
import IdentityTable from '../components/identity/IdentityTable.jsx';
import IdentityDetailPanel from '../components/identity/IdentityDetailPanel.jsx';
import WatchlistPanel from '../components/identity/WatchlistPanel.jsx';

export default function IdentityPage() {
  const identityHook = useIdentities();
  const watchlistHook = useWatchlist();
  const [activeTab, setActiveTab] = useState('identities');

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: '#0d1117',
        color: '#e6edf3',
        padding: '16px',
        gap: '16px',
        overflowY: 'auto',
      }}
    >
      {/* Tab bar */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '1px solid #21262d',
          paddingBottom: '8px',
        }}
      >
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600, flex: 1 }}>
          Identity Intelligence
        </h2>
        <button
          onClick={() => setActiveTab('identities')}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: 'none',
            cursor: 'pointer',
            background: activeTab === 'identities' ? '#1f6feb' : '#21262d',
            color: '#e6edf3',
            fontSize: '13px',
          }}
        >
          Identities
        </button>
        <button
          onClick={() => setActiveTab('watchlist')}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            border: 'none',
            cursor: 'pointer',
            background: activeTab === 'watchlist' ? '#1f6feb' : '#21262d',
            color: '#e6edf3',
            fontSize: '13px',
          }}
        >
          Watchlist
        </button>
      </div>

      {/* Identities tab */}
      {activeTab === 'identities' && (
        <div style={{ display: 'flex', gap: '16px', flex: 1, minHeight: 0 }}>
          <div style={{ flex: '0 0 380px', overflowY: 'auto' }}>
            <IdentityTable {...identityHook} watchlistHook={watchlistHook} />
          </div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {identityHook.selectedIdentity ? (
              <IdentityDetailPanel
                {...identityHook}
                watchlistHook={watchlistHook}
              />
            ) : (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '200px',
                  color: '#8b949e',
                  fontSize: '14px',
                }}
              >
                Select an identity to view details
              </div>
            )}
          </div>
        </div>
      )}

      {/* Watchlist tab */}
      {activeTab === 'watchlist' && (
        <WatchlistPanel
          watchlistHook={watchlistHook}
          identityHook={identityHook}
        />
      )}
    </div>
  );
}
