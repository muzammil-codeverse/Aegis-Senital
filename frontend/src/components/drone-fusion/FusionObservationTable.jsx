import FusionSafetyBadge from './FusionSafetyBadge'

export default function FusionObservationTable({ observations = [] }) {
  if (!observations.length) return <div style={{ color: '#6b7280', padding: 8 }}>No observations.</div>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #374151', textAlign: 'left' }}>
            <th style={{ padding: '4px 8px' }}>Source</th>
            <th style={{ padding: '4px 8px' }}>Event Type</th>
            <th style={{ padding: '4px 8px' }}>Timestamp</th>
            <th style={{ padding: '4px 8px' }}>Geo</th>
            <th style={{ padding: '4px 8px' }}>Labels</th>
          </tr>
        </thead>
        <tbody>
          {observations.map(obs => (
            <tr key={obs.observation_id} style={{ borderBottom: '1px solid #1f2937' }}>
              <td style={{ padding: '4px 8px' }}>
                <span style={{ color: '#60a5fa' }}>{obs.source_type}</span>
                <br /><span style={{ fontSize: 11, color: '#6b7280' }}>{obs.source_id}</span>
              </td>
              <td style={{ padding: '4px 8px' }}>{obs.event_type || '—'}</td>
              <td style={{ padding: '4px 8px', fontSize: 11 }}>{obs.timestamp?.slice(0, 19)}</td>
              <td style={{ padding: '4px 8px', fontSize: 11 }}>
                {obs.geo_missing
                  ? <span style={{ color: '#ef4444' }}>No geo</span>
                  : `${obs.latitude?.toFixed(4)}, ${obs.longitude?.toFixed(4)}`}
              </td>
              <td style={{ padding: '4px 8px' }}>
                <FusionSafetyBadge simulated={obs.simulated} operatorReviewRequired={false} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
