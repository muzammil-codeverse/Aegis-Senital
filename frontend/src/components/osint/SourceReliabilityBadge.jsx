export default function SourceReliabilityBadge({ value = 'unknown' }) {
  const normalized = String(value || 'unknown').toLowerCase()
  return <span className="state-chip">Source reliability: {normalized}</span>
}
