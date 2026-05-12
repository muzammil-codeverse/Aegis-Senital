/**
 * Safety disclaimer badge shown on all mission planner screens.
 * Enforces safe wording per Phase 45 policy.
 */
export default function MissionSafetyBadge() {
  return (
    <div className="safety-badge" style={{
      background: '#1a2a1a',
      border: '1px solid #3a6b3a',
      borderRadius: 4,
      padding: '6px 12px',
      fontSize: 11,
      color: '#7ec87e',
      display: 'flex',
      alignItems: 'center',
      gap: 8,
    }}>
      <span style={{ fontWeight: 700 }}>SIM ONLY</span>
      <span>Simulated aerial patrol — operator review required — not for operational use</span>
    </div>
  )
}
