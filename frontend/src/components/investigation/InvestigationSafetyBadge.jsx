export default function InvestigationSafetyBadge({ className = '' }) {
  return (
    <div className={`rounded border border-yellow-500 bg-yellow-50 px-3 py-2 text-xs text-yellow-800 ${className}`}>
      <span className="font-semibold">Operator Review Required — </span>
      Path hypotheses are investigative aids, not confirmed facts. Do not attribute guilt, identity, or criminality.
    </div>
  );
}
