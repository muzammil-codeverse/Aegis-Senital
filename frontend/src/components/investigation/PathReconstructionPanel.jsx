import { useState } from 'react';
import InvestigationSafetyBadge from './InvestigationSafetyBadge';
import PathConfidenceBreakdown from './PathConfidenceBreakdown';
import PathHypothesisTimeline from './PathHypothesisTimeline';
import HypothesisReviewControls from './HypothesisReviewControls';

export default function PathReconstructionPanel({
  onReconstruct,
  hypotheses = [],
  onReview,
  reconstructing = false,
  error = null,
}) {
  const [caseId, setCaseId] = useState('');
  const [eventId, setEventId] = useState('');
  const [backMin, setBackMin] = useState(20);
  const [fwdMin, setFwdMin] = useState(30);
  const [selected, setSelected] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!caseId && !eventId) return;
    onReconstruct({ case_id: caseId || undefined, event_id: eventId || undefined, backward_minutes: backMin, forward_minutes: fwdMin });
  };

  const selectedHyp = hypotheses.find((h) => h.hypothesis_id === selected);

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3 text-sm">
      <InvestigationSafetyBadge />

      <form onSubmit={handleSubmit} className="space-y-2 rounded border p-3">
        <div className="font-semibold text-gray-700">Path Reconstruction</div>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded border px-2 py-1 text-xs"
            placeholder="Case ID (optional)"
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
          />
          <input
            className="flex-1 rounded border px-2 py-1 text-xs"
            placeholder="Event ID (optional)"
            value={eventId}
            onChange={(e) => setEventId(e.target.value)}
          />
        </div>
        <div className="flex gap-2 text-xs">
          <label className="flex items-center gap-1 text-gray-600">
            Back min:
            <input type="number" min={1} max={120} value={backMin} onChange={(e) => setBackMin(+e.target.value)}
              className="w-14 rounded border px-1" />
          </label>
          <label className="flex items-center gap-1 text-gray-600">
            Fwd min:
            <input type="number" min={1} max={120} value={fwdMin} onChange={(e) => setFwdMin(+e.target.value)}
              className="w-14 rounded border px-1" />
          </label>
        </div>
        <button
          type="submit"
          disabled={reconstructing || (!caseId && !eventId)}
          className="rounded bg-blue-600 px-3 py-1 text-xs text-white disabled:opacity-40"
        >
          {reconstructing ? 'Reconstructing…' : 'Reconstruct Path'}
        </button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </form>

      {hypotheses.length > 0 && (
        <div className="space-y-2">
          <div className="font-semibold text-gray-700">Candidate Hypotheses ({hypotheses.length})</div>
          {hypotheses.map((h) => (
            <div
              key={h.hypothesis_id}
              className={`cursor-pointer rounded border p-2 ${selected === h.hypothesis_id ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'}`}
              onClick={() => setSelected(h.hypothesis_id === selected ? null : h.hypothesis_id)}
            >
              <div className="flex justify-between text-xs">
                <span className="font-medium truncate">{h.hypothesis_id}</span>
                <span className="text-gray-500 capitalize">{h.review_status}</span>
              </div>
              <p className="mt-1 text-xs text-gray-600">{h.safe_summary}</p>
              {selected === h.hypothesis_id && selectedHyp && (
                <div className="mt-2 space-y-2 border-t pt-2">
                  <PathConfidenceBreakdown breakdown={h.confidence_breakdown} confidence={h.confidence} />
                  <PathHypothesisTimeline steps={h.steps} />
                  {h.evidence_refs?.length > 0 && (
                    <div className="text-xs text-gray-500">
                      Evidence refs: {h.evidence_refs.join(', ')}
                    </div>
                  )}
                  <HypothesisReviewControls hypothesis={selectedHyp} onReview={onReview} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
