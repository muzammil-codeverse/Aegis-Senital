export default function HypothesisReviewControls({ hypothesis, onReview, loading = false }) {
  if (!hypothesis) return null;
  const status = hypothesis.review_status;

  return (
    <div className="flex gap-2 pt-2">
      <button
        disabled={loading || status === 'accepted'}
        onClick={() => onReview(hypothesis.hypothesis_id, 'accept')}
        className="rounded bg-green-600 px-3 py-1 text-xs text-white disabled:opacity-40"
      >
        Accept
      </button>
      <button
        disabled={loading || status === 'rejected'}
        onClick={() => onReview(hypothesis.hypothesis_id, 'reject')}
        className="rounded bg-red-600 px-3 py-1 text-xs text-white disabled:opacity-40"
      >
        Reject
      </button>
      <button
        disabled={loading || status === 'inconclusive'}
        onClick={() => onReview(hypothesis.hypothesis_id, 'inconclusive')}
        className="rounded bg-gray-500 px-3 py-1 text-xs text-white disabled:opacity-40"
      >
        Inconclusive
      </button>
      <span className="ml-auto self-center text-xs text-gray-400 capitalize">
        Status: <strong>{status}</strong>
      </span>
    </div>
  );
}
