export default function PathOverlayLayer({ hypothesis, project }) {
  if (!hypothesis || !project) return null;
  const steps = hypothesis.steps || [];
  const points = steps
    .filter((s) => s.latitude != null && s.longitude != null)
    .map((s) => project(s.latitude, s.longitude));

  if (points.length < 2) return null;

  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');

  return (
    <g>
      <path
        d={d}
        fill="none"
        stroke="rgba(59,130,246,0.8)"
        strokeWidth={3}
        strokeDasharray="6 3"
      />
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={6} fill="#3b82f6" stroke="white" strokeWidth={2}>
          <title>Step {i + 1}: {steps[i]?.camera_name || steps[i]?.camera_id}</title>
        </circle>
      ))}
      {hypothesis.confidence < 0.5 && (
        <text x={points[0].x} y={points[0].y - 10} fontSize={10} fill="#f59e0b" fontWeight="bold">
          Low confidence
        </text>
      )}
    </g>
  );
}
