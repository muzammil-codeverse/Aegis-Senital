export default function PathConfidenceBreakdown({ breakdown = {}, confidence = 0 }) {
  const pct = (v) => (v != null ? `${Math.round(v * 100)}%` : '—');
  const bar = (v) => (
    <div className="h-2 w-full rounded bg-gray-200">
      <div
        className="h-2 rounded bg-blue-500"
        style={{ width: `${Math.round((v ?? 0) * 100)}%` }}
      />
    </div>
  );

  const rows = [
    ['Time Consistency', breakdown.time_consistency],
    ['Geo Distance', breakdown.geo_distance],
    ['Travel Feasibility', breakdown.travel_feasibility],
    ['Identity Similarity', breakdown.identity_similarity],
    ['Camera FOV', breakdown.camera_fov],
    ['Event Severity', breakdown.event_severity],
  ].filter(([, v]) => v != null);

  return (
    <div className="space-y-1 text-xs">
      <div className="mb-2 font-semibold text-gray-700">
        Overall Confidence: <span className="text-blue-700">{pct(confidence)}</span>
      </div>
      {rows.map(([label, value]) => (
        <div key={label}>
          <div className="flex justify-between text-gray-500">
            <span>{label}</span>
            <span>{pct(value)}</span>
          </div>
          {bar(value)}
        </div>
      ))}
    </div>
  );
}
