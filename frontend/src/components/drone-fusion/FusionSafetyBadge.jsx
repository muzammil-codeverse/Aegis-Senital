export default function FusionSafetyBadge({ simulated, operatorReviewRequired }) {
  return (
    <span style={{ display: 'inline-flex', gap: 4 }}>
      {simulated && (
        <span style={{ background: '#7c3aed', color: '#fff', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
          Simulated
        </span>
      )}
      {operatorReviewRequired && (
        <span style={{ background: '#b45309', color: '#fff', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
          Operator Review Required
        </span>
      )}
    </span>
  )
}
